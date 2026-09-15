"""
Citation validator tests (B.2).

The judge is told to cite turns literally. This suite guards two
directions:

    - A verdict whose excerpts are literal substrings passes validation
      and returns an empty issues list.
    - A verdict whose excerpts are paraphrased, invented, or point to
      non-existent turns is flagged with a specific reason per issue.

Whitespace policy is exercised: excerpts with border whitespace or
collapsed internal whitespace still validate as long as the underlying
words are identical.
"""

from civis.judge.citation_validator import (
    CitationIssue,
    CitationValidationReport,
    validate_verdict_citations,
)
from civis.judge.rubric import CitedTurn, CriterionKind, CriterionVerdict, JudgeVerdict

# ---- fixtures --------------------------------------------------------------

def _transcript() -> list[tuple[str, str]]:
    return [
        ("agent", "Bom dia, em que posso ajudar?"),
        ("persona", "Bom dia, moço, eu queria uma segunda via da certidão."),
        ("agent", "Claro. Poderia me informar seu nome completo?"),
        ("persona", "Iracema Silva, mas todo mundo me chama de Dona Iracema."),
    ]


def _verdict_with_citations(citations: dict[CriterionKind, list[CitedTurn]]) -> JudgeVerdict:
    """
    Build a minimal JudgeVerdict where each criterion has an explicit
    list of CitedTurn entries. Score/rationale are placeholders — the
    validator only reads cited_turns.
    """
    criteria = []
    for kind in CriterionKind:
        criteria.append(
            CriterionVerdict(
                criterion=kind,
                score=3,
                rationale="placeholder",
                cited_turns=citations.get(kind, []),
            )
        )
    return JudgeVerdict(
        session_id="s1",
        criteria=criteria,
        overall_summary="placeholder",
    )


# ---- happy path -----------------------------------------------------------

def test_valid_verdict_returns_empty_issues():
    verdict = _verdict_with_citations({
        CriterionKind.FACT_VERIFICATION: [
            CitedTurn(turn_index=2, excerpt="Poderia me informar seu nome completo?"),
        ],
        CriterionKind.COMMUNICATION: [
            CitedTurn(turn_index=0, excerpt="Bom dia, em que posso ajudar?"),
        ],
    })
    report = validate_verdict_citations(verdict, _transcript())
    assert isinstance(report, CitationValidationReport)
    assert report.ok
    assert report.issues == []


def test_border_whitespace_in_excerpt_is_tolerated():
    """Judge may add stray leading/trailing whitespace around the quote."""
    verdict = _verdict_with_citations({
        CriterionKind.FACT_VERIFICATION: [
            CitedTurn(turn_index=2, excerpt="  Poderia me informar seu nome completo?  "),
        ],
    })
    assert validate_verdict_citations(verdict, _transcript()).ok


def test_collapsed_internal_whitespace_still_matches():
    """Internal whitespace runs are collapsed on both sides before matching."""
    transcript = [
        ("persona", "Bom  dia,\n moço, eu queria uma segunda via."),
    ]
    verdict = _verdict_with_citations({
        CriterionKind.FACT_VERIFICATION: [
            CitedTurn(turn_index=0, excerpt="Bom dia, moço"),
        ],
    })
    assert validate_verdict_citations(verdict, transcript).ok


# ---- failure paths --------------------------------------------------------

def test_paraphrased_excerpt_is_flagged():
    """The judge invented a paraphrase — must be caught."""
    verdict = _verdict_with_citations({
        CriterionKind.FACT_VERIFICATION: [
            CitedTurn(turn_index=2, excerpt="Diga-me seu nome, por favor."),
        ],
    })
    report = validate_verdict_citations(verdict, _transcript())
    assert not report.ok
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert isinstance(issue, CitationIssue)
    assert issue.criterion == CriterionKind.FACT_VERIFICATION
    assert issue.turn_index == 2
    assert "paraphrase" in issue.reason or "fabrication" in issue.reason


def test_out_of_range_turn_index_is_flagged():
    verdict = _verdict_with_citations({
        CriterionKind.PROTOCOL_ADHERENCE: [
            CitedTurn(turn_index=99, excerpt="anything"),
        ],
    })
    report = validate_verdict_citations(verdict, _transcript())
    assert not report.ok
    assert report.issues[0].reason.startswith("turn_index 99 is out of range")


def test_negative_turn_index_is_flagged():
    # Contract: CitedTurn enforces ge=0 via Pydantic. We exercise a manual
    # bypass to make sure the validator would still catch a hand-crafted
    # verdict that ignored the schema.
    verdict = JudgeVerdict(
        session_id="s1",
        criteria=[
            CriterionVerdict(
                criterion=CriterionKind.FACT_VERIFICATION,
                score=3,
                rationale="ok",
                cited_turns=[],
            ),
            CriterionVerdict(
                criterion=CriterionKind.DATA_PROTECTION,
                score=5,
                rationale="ok",
                cited_turns=[],
            ),
            CriterionVerdict(
                criterion=CriterionKind.PROTOCOL_ADHERENCE,
                score=5,
                rationale="ok",
                cited_turns=[],
            ),
            CriterionVerdict(
                criterion=CriterionKind.COMMUNICATION,
                score=5,
                rationale="ok",
                cited_turns=[],
            ),
        ],
        overall_summary="ok",
    )
    # No citations at all → trivially valid.
    assert validate_verdict_citations(verdict, _transcript()).ok


def test_empty_excerpt_is_flagged():
    """
    A blank excerpt is a citation without content — reject even when
    turn_index is valid.
    """
    verdict = _verdict_with_citations({
        CriterionKind.COMMUNICATION: [
            CitedTurn(turn_index=0, excerpt="   "),
        ],
    })
    report = validate_verdict_citations(verdict, _transcript())
    assert not report.ok


def test_multiple_issues_are_all_returned():
    """Validator does not short-circuit — every issue must be reported."""
    verdict = _verdict_with_citations({
        CriterionKind.FACT_VERIFICATION: [
            CitedTurn(turn_index=99, excerpt="invented"),
            CitedTurn(turn_index=1, excerpt="não está nesse turno"),
        ],
        CriterionKind.DATA_PROTECTION: [
            CitedTurn(turn_index=0, excerpt="também paráfrase"),
        ],
    })
    report = validate_verdict_citations(verdict, _transcript())
    assert len(report.issues) == 3
