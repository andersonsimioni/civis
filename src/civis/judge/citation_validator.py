"""
Judge citation validator.

The judge is told to quote turns literally. This module verifies that
each CitedTurn.excerpt IS in fact a substring of the referenced turn's
content, and flags fabricated citations (out-of-range indices,
paraphrased quotes, invented lines).

Whitespace policy: leading/trailing whitespace on the excerpt is ignored
(models often add a stray space or newline around the quote), and internal
whitespace runs are collapsed to a single space on BOTH sides before the
substring check. Casing is preserved (case-sensitive), because in pt-BR a
change of case ("PIN" vs "pin") can flip the meaning of a citation.

Usage:
    report = validate_verdict_citations(verdict, transcript)
    if not report.ok:
        # retry with max_turn_index=len(transcript)-1 and stricter wording
        ...
"""

import re

from pydantic import BaseModel

from civis.judge.rubric import CriterionKind, JudgeVerdict


class CitationIssue(BaseModel):
    """
    One faulty citation. Kept as a Pydantic model so it can be serialised
    into a session-level report without a bespoke encoder.
    """

    criterion: CriterionKind
    turn_index: int
    excerpt: str
    reason: str


class CitationValidationReport(BaseModel):
    """Result of validating all citations in a JudgeVerdict."""

    issues: list[CitationIssue]

    @property
    def ok(self) -> bool:
        """True if no citation issue was found."""
        return not self.issues


# Whitespace collapser: turns \n, \t, and runs of spaces into a single space.
# Used symmetrically on excerpt and turn content so "quoted\n phrase" matches
# "quoted phrase" in the transcript.
_WS_RE = re.compile(r"\s+")


def validate_verdict_citations(
    verdict: JudgeVerdict,
    transcript: list[tuple[str, str]],
) -> CitationValidationReport:
    """
    Walk every CitedTurn in the verdict and check that its excerpt appears
    in the referenced transcript turn's content (after border-whitespace
    trimming + internal whitespace collapsing).

    Arguments:
        verdict     Parsed JudgeVerdict from the judge LLM.
        transcript  Same (speaker, content) list handed to build_judge_prompt.

    Returns:
        CitationValidationReport with one CitationIssue per faulty citation.
        Empty issues list means every citation checked out.
    """
    issues: list[CitationIssue] = []
    n_turns = len(transcript)

    for criterion_verdict in verdict.criteria:
        for cited in criterion_verdict.cited_turns:
            if cited.turn_index < 0 or cited.turn_index >= n_turns:
                issues.append(
                    CitationIssue(
                        criterion=criterion_verdict.criterion,
                        turn_index=cited.turn_index,
                        excerpt=cited.excerpt,
                        reason=(
                            f"turn_index {cited.turn_index} is out of range "
                            f"[0, {n_turns - 1}]."
                        ),
                    )
                )
                continue

            _speaker, content = transcript[cited.turn_index]
            if not _is_literal_substring(cited.excerpt, content):
                issues.append(
                    CitationIssue(
                        criterion=criterion_verdict.criterion,
                        turn_index=cited.turn_index,
                        excerpt=cited.excerpt,
                        reason=(
                            "excerpt is not a literal substring of the "
                            "cited turn (possible paraphrase or fabrication)."
                        ),
                    )
                )

    return CitationValidationReport(issues=issues)


# ---- helpers ---------------------------------------------------------------

def _is_literal_substring(excerpt: str, content: str) -> bool:
    """
    Return True if the excerpt appears verbatim inside the content, after
    normalising whitespace on both sides.

    Empty excerpts are considered invalid — a valid citation must quote
    something.
    """
    if not excerpt.strip():
        return False
    normalised_excerpt = _normalise_whitespace(excerpt)
    normalised_content = _normalise_whitespace(content)
    return normalised_excerpt in normalised_content


def _normalise_whitespace(text: str) -> str:
    """
    Trim border whitespace and collapse internal whitespace runs to single
    spaces. Applied symmetrically to excerpt and content so a citation like
    'Bom dia, moço.' still matches when the transcript stores 'Bom  dia,\n moço.'.
    """
    return _WS_RE.sub(" ", text).strip()
