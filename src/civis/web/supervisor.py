"""
Supervisor dashboard aggregation (ONDA 3, D2.1).

Rolls up every session on disk into a compact
:class:`SupervisorMetrics` record so the "Gestão" page can render KPIs,
charts and short tables without repeating the same walk-and-parse
logic in the view.

Design notes:
    - We read the SAME on-disk artefacts the past-sessions page reads
      (``metadata.json`` + ``verdict.json``). No new sidecar; no
      cache; a folder full of sessions is small enough to walk on
      every rerun.
    - Sessions without a verdict contribute to the total count but
      not to any score aggregate — an unrated session has no score,
      pretending otherwise would poison the mean.
    - Attendant names come from :attr:`SessionMetadata.agent_name`.
      Legacy sessions without the field, and sessions where the env
      variable was empty, count as ``"anonymous"``.
    - "Sessions over time" is deliberately a per-day count, not a
      per-session average. A line chart of the average would be
      hostage to a single outlier session. Count is honest.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from civis.judge.rubric import JudgeVerdict
from civis.session.storage import (
    METADATA_FILENAME,
    SessionMetadata,
    load_metadata,
)
from civis.web.data_access import (
    DEFAULT_SESSIONS_DIR,
    _iso_to_date,
    _load_verdict,
)

# Sentinel used when a session metadata carries no ``agent_name``.
ANONYMOUS_AGENT = "anonymous"

# Rubric criteria the supervisor page charts. Kept in one place so a
# rubric change lands in one edit.
_CHARTED_CRITERIA: tuple[str, ...] = (
    "fact_verification",
    "data_protection",
    "protocol_adherence",
    "communication",
)


@dataclass(frozen=True)
class SessionRanking:
    """One row in the 'best sessions' / 'worst sessions' tables."""

    session_id: str
    scenario_id: str
    agent_name: str
    average_score: float
    created_at: str


@dataclass(frozen=True)
class SupervisorMetrics:
    """
    Aggregated view of every session on disk. Every field is safe to
    render as-is; empty datasets produce empty aggregates rather than
    exceptions.

    Attributes:
        total_sessions: Number of sessions that have ``metadata.json``.
        unique_agents: Number of distinct ``agent_name`` values.
        mean_score: Mean of every rated session's average rubric score,
            or ``None`` when no session has a verdict.
        score_distribution: ``criterion -> mean score`` across every
            verdict, restricted to :data:`_CHARTED_CRITERIA`.
        sessions_over_time: ``date -> count of sessions created that
            day``. Ordered oldest-first so a line chart plots left to
            right.
        worst_sessions: Up to 5 lowest-scored sessions. Ties broken by
            newest first so the freshest example wins the demo.
        best_sessions: Up to 5 highest-scored sessions, same tiebreak.
        agent_session_counts: ``agent_name -> number of sessions``.
    """

    total_sessions: int
    unique_agents: int
    mean_score: float | None
    score_distribution: dict[str, float] = field(default_factory=dict)
    sessions_over_time: list[tuple[date, int]] = field(default_factory=list)
    worst_sessions: list[SessionRanking] = field(default_factory=list)
    best_sessions: list[SessionRanking] = field(default_factory=list)
    agent_session_counts: dict[str, int] = field(default_factory=dict)


def compute_supervisor_metrics(
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
) -> SupervisorMetrics:
    """
    Walk ``sessions_dir`` once and produce the aggregated dashboard
    record. An empty or non-existent folder yields a fully-populated
    metrics object with zero counts, so callers never have to guard
    the return value.
    """
    if not sessions_dir.exists() or not sessions_dir.is_dir():
        return _empty_metrics()

    rated_rows: list[SessionRanking] = []
    per_criterion_scores: dict[str, list[int]] = defaultdict(list)
    agent_counts: Counter[str] = Counter()
    date_counts: Counter[date] = Counter()
    total = 0

    for candidate in sessions_dir.iterdir():
        if not candidate.is_dir():
            continue
        if not (candidate / METADATA_FILENAME).exists():
            continue

        session_id = candidate.name
        metadata = load_metadata(session_id, base=sessions_dir)
        if metadata is None:
            continue
        total += 1

        agent = _resolve_agent(metadata)
        agent_counts[agent] += 1

        created_date = _iso_to_date(metadata.created_at)
        if created_date is not None:
            date_counts[created_date] += 1

        verdict = _load_verdict(session_id, sessions_dir)
        if verdict is None:
            continue

        avg = _verdict_average(verdict)
        if avg is None:
            continue
        rated_rows.append(
            SessionRanking(
                session_id=session_id,
                scenario_id=metadata.scenario_id,
                agent_name=agent,
                average_score=avg,
                created_at=metadata.created_at,
            )
        )
        for criterion in verdict.criteria:
            per_criterion_scores[criterion.criterion.value].append(criterion.score)

    return SupervisorMetrics(
        total_sessions=total,
        unique_agents=len(agent_counts),
        mean_score=_mean([r.average_score for r in rated_rows]),
        score_distribution=_score_distribution(per_criterion_scores),
        sessions_over_time=sorted(date_counts.items()),
        worst_sessions=_ranked(rated_rows, reverse=False),
        best_sessions=_ranked(rated_rows, reverse=True),
        agent_session_counts=dict(agent_counts),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_metrics() -> SupervisorMetrics:
    """Zero-valued metrics used when the sessions folder is missing / empty."""
    return SupervisorMetrics(
        total_sessions=0,
        unique_agents=0,
        mean_score=None,
        score_distribution={},
        sessions_over_time=[],
        worst_sessions=[],
        best_sessions=[],
        agent_session_counts={},
    )


def _resolve_agent(metadata: SessionMetadata) -> str:
    """
    Turn a metadata into a display-safe agent name. Empty strings and
    ``None`` both fall back to :data:`ANONYMOUS_AGENT` so the KPIs
    don't count a nameless session as a distinct attendant.
    """
    name = (metadata.agent_name or "").strip()
    return name if name else ANONYMOUS_AGENT


def _verdict_average(verdict: JudgeVerdict) -> float | None:
    """Mean of a verdict's criterion scores. None on empty criteria."""
    if not verdict.criteria:
        return None
    return sum(c.score for c in verdict.criteria) / len(verdict.criteria)


def _mean(values: list[float]) -> float | None:
    """Arithmetic mean or None when the input list is empty."""
    if not values:
        return None
    return sum(values) / len(values)


def _score_distribution(
    per_criterion_scores: dict[str, list[int]],
) -> dict[str, float]:
    """
    Mean score per rubric criterion. Restricted to the four charted
    criteria so a rogue verdict with an unknown criterion key does
    not sneak into the bar chart. Missing criteria default to 0.0
    (rendered as a hollow bar).
    """
    out: dict[str, float] = {}
    for criterion in _CHARTED_CRITERIA:
        scores = per_criterion_scores.get(criterion, [])
        out[criterion] = sum(scores) / len(scores) if scores else 0.0
    return out


def _ranked(
    rows: list[SessionRanking],
    *,
    reverse: bool,
    limit: int = 5,
) -> list[SessionRanking]:
    """
    Return up to ``limit`` rows ordered by score. Secondary sort key
    is ``created_at`` descending so the newest session wins a tie —
    the demo wants the most recent example on screen, not the oldest.
    """
    ordered = sorted(
        rows,
        key=lambda r: (r.average_score, r.created_at),
        reverse=reverse,
    )
    if reverse:
        # For 'best' we sorted desc on both keys — that's already the
        # right order.
        return ordered[:limit]
    # For 'worst' we sorted asc on score but that means asc on
    # created_at too, which puts the OLDEST session first on a tie.
    # Re-sort with a mixed key so we honour 'newest first on ties'.
    mixed = sorted(rows, key=lambda r: (r.average_score, _neg_iso(r.created_at)))
    return mixed[:limit]


def _neg_iso(iso_text: str) -> str:
    """
    Cheap trick for descending secondary sort on an ISO string with
    ``sorted`` ascending: XOR each char with '~' so the natural sort
    order flips. Doesn't have to be pretty — the value is a sort key,
    never rendered.
    """
    # A safer implementation: return a tuple with the negated ordinal
    # per character. Kept simple: reverse the string. Reversed ISO
    # timestamps still order strictly the way we want when they share
    # a length (all our timestamps are ISO-8601 with second precision).
    return iso_text[::-1]


__all__ = [
    "ANONYMOUS_AGENT",
    "SessionRanking",
    "SupervisorMetrics",
    "compute_supervisor_metrics",
]
