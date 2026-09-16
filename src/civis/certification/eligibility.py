"""
Certification eligibility calculator.

Walks a directory of CIVIS sessions, reads every `verdict.json` it finds,
and aggregates the judge scores into a single `CertificationEligibility`
report — level (BRONZE/SILVER/GOLD or None), session count, mean score,
and per-criterion means.

Scoring conventions:

    - The judge scores each criterion on the 0..5 integer scale defined by
      `civis.judge.rubric` (MIN_SCORE=0, MAX_SCORE=5).
    - This module normalises to the [0, 1] float scale that the
      certification thresholds use (0.6 / 0.7 / 0.8). Normalisation is
      `score / MAX_SCORE`, applied per criterion, then averaged.

Thresholds are declared as class constants on `CertificationLevel` so the
CLI can also print them in the "not eligible" error message.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from civis.judge.rubric import MAX_SCORE, JudgeVerdict


class CertificationLevel(StrEnum):
    """
    Three-tier certification. Level thresholds (n_sessions, min_mean_score)
    are exposed on the enum so the CLI can quote them verbatim in error
    messages, and future callers can order the levels without repeating
    numbers.
    """

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


# Per-level requirements. Ordering matters — we scan from highest to lowest
# so `compute_eligibility` awards the top level the attendant qualifies for.
# Each tuple is (level, min_n_sessions, min_mean_score in [0, 1]).
_LEVEL_REQUIREMENTS: list[tuple[CertificationLevel, int, float]] = [
    (CertificationLevel.GOLD, 30, 0.8),
    (CertificationLevel.SILVER, 15, 0.7),
    (CertificationLevel.BRONZE, 5, 0.6),
]


class CertificationEligibility(BaseModel):
    """
    Result of aggregating verdict.json files into a certification decision.

    `level` is None when the attendant does not meet even the BRONZE
    threshold — the CLI turns that into a friendly error message.
    """

    level: CertificationLevel | None = Field(
        default=None,
        description=(
            "Highest tier the attendant qualifies for, or None when even "
            "the BRONZE threshold is not met."
        ),
    )
    n_sessions: int = Field(
        ge=0,
        description="Number of verdict.json files successfully aggregated.",
    )
    mean_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Session-level mean of per-criterion means, normalised to [0, 1]. "
            "0.0 when no verdicts were found."
        ),
    )
    per_criterion_mean: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Mean score per criterion (criterion name -> mean in [0, 1]). "
            "Empty when no verdicts were found."
        ),
    )


def compute_eligibility(sessions: list[Path]) -> CertificationEligibility:
    """
    Aggregate every reachable verdict.json under the given session paths.

    Arguments:
        sessions: list of session directories to consider. Each directory
                  is expected to contain a `verdict.json`; entries that
                  don't (still-running sessions, judgeless runs, malformed
                  JSON) are silently skipped so a single bad session does
                  not sink the whole aggregation.

    Returns:
        A CertificationEligibility with the highest level the aggregate
        meets, or level=None when even BRONZE (5 sessions, mean >= 0.6) is
        out of reach.
    """
    verdicts = _load_verdicts(sessions)

    if not verdicts:
        return CertificationEligibility(
            level=None,
            n_sessions=0,
            mean_score=0.0,
            per_criterion_mean={},
        )

    # Session-level mean: for each verdict compute the mean of its criteria
    # (normalised to [0, 1]), then average across sessions. Averaging in two
    # steps keeps sessions with more criteria from double-counting.
    per_session_means: list[float] = []
    per_criterion_sums: dict[str, float] = {}
    per_criterion_counts: dict[str, int] = {}

    for verdict in verdicts:
        if not verdict.criteria:
            # Defensive: a verdict without criteria contributes nothing.
            continue

        criterion_values: list[float] = []
        for c in verdict.criteria:
            normalised = c.score / MAX_SCORE
            criterion_values.append(normalised)
            key = c.criterion.value
            per_criterion_sums[key] = per_criterion_sums.get(key, 0.0) + normalised
            per_criterion_counts[key] = per_criterion_counts.get(key, 0) + 1

        per_session_means.append(sum(criterion_values) / len(criterion_values))

    n_sessions = len(per_session_means)
    if n_sessions == 0:
        return CertificationEligibility(
            level=None,
            n_sessions=0,
            mean_score=0.0,
            per_criterion_mean={},
        )

    mean_score = sum(per_session_means) / n_sessions
    per_criterion_mean = {
        key: per_criterion_sums[key] / per_criterion_counts[key]
        for key in per_criterion_sums
    }

    level = _award_level(n_sessions=n_sessions, mean_score=mean_score)

    return CertificationEligibility(
        level=level,
        n_sessions=n_sessions,
        mean_score=mean_score,
        per_criterion_mean=per_criterion_mean,
    )


def discover_session_dirs(sessions_root: Path) -> list[Path]:
    """
    Convenience helper for the CLI: list every immediate subdirectory of
    `sessions_root` (each is one CIVIS session). Returns an empty list if
    the root does not exist so the CLI can produce a "no sessions found"
    message rather than crashing.
    """
    if not sessions_root.exists() or not sessions_root.is_dir():
        return []
    return sorted(p for p in sessions_root.iterdir() if p.is_dir())


def _load_verdicts(session_dirs: list[Path]) -> list[JudgeVerdict]:
    """
    Read `verdict.json` from each session directory. Skips silently on:
      - missing file (session ran with --no-judge or hasn't finished);
      - unreadable file (permission errors);
      - malformed JSON or a JudgeVerdict shape mismatch (older schema).

    Returning a "best-effort" list matches the semantics the CLI wants:
    one broken sidecar should not block certification of the other 29.
    """
    verdicts: list[JudgeVerdict] = []
    for session_dir in session_dirs:
        verdict_path = session_dir / "verdict.json"
        if not verdict_path.is_file():
            continue
        try:
            raw = verdict_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            verdicts.append(JudgeVerdict.model_validate(payload))
        except (OSError, json.JSONDecodeError, ValueError):
            # ValueError covers Pydantic's ValidationError.
            continue
    return verdicts


def _award_level(
    n_sessions: int,
    mean_score: float,
) -> CertificationLevel | None:
    """
    Return the highest CertificationLevel whose (min_sessions, min_score)
    is met, or None when even BRONZE is out of reach.
    """
    for level, min_sessions, min_score in _LEVEL_REQUIREMENTS:
        if n_sessions >= min_sessions and mean_score >= min_score:
            return level
    return None


def level_requirements() -> list[tuple[CertificationLevel, int, float]]:
    """Expose the threshold table so the CLI can format error messages."""
    return list(_LEVEL_REQUIREMENTS)
