"""
Read-only access to on-disk sessions and security reports.

This module never mutates disk state and never imports Streamlit — every
function is a pure query against `data/sessions/` and `reports/`. Keeping
it framework-agnostic lets us unit test the filters and aggregations
with pytest, and lets AppTest fixtures inject a `tmp_path` sessions dir
via `list_sessions(sessions_dir=...)`.

Public shape:

    SessionSummary       Row rendered in the "Sessões passadas" list.
    SessionDetail        Full payload rendered in the drill-down.
    TelemetryEntry       One turn's LLM telemetry (input/output tokens etc).
    list_sessions        Enumerate every session on disk (newest first).
    filter_sessions      Apply the UI filters to a list of summaries.
    load_session_detail  Load transcript + verdict + sidecars for one id.
    load_adversarial_v1  Parse reports/adversarial_v1.json.
    load_judge_deceiver  Parse reports/judge_deceiver_pointwise_v1.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from civis.judge.rubric import JudgeVerdict
from civis.session.storage import (
    CONTRADICTIONS_FILENAME,
    HONEYTOKEN_LEAKS_FILENAME,
    METADATA_FILENAME,
    VERDICT_FILENAME,
    SessionMetadata,
    SessionTranscript,
    load_metadata,
    load_transcript,
    session_dir,
)

# Default filesystem layout — the CLI writes here, the UI reads from here.
DEFAULT_SESSIONS_DIR = Path("data/sessions")
DEFAULT_REPORTS_DIR = Path("reports")
# Sidecar for per-turn LLM telemetry (input_tokens/output_tokens/latency_ms).
# Written by the CLI in Phase D; absent for legacy sessions.
TURN_TELEMETRY_FILENAME = "turn_telemetry.json"


# ---------------------------------------------------------------------------
# Records rendered by the UI. Kept as dataclasses (not Pydantic) — they are
# derived views, not persisted contracts.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelemetryEntry:
    """One persona-turn's LLM telemetry, as persisted by the CLI."""

    turn_index: int
    input_tokens: int
    output_tokens: int
    latency_ms: int
    provider_name: str


@dataclass(frozen=True)
class SessionSummary:
    """One row in the 'Sessões passadas' list."""

    session_id: str
    scenario_id: str
    created_at: str            # ISO-8601 UTC
    total_turns: int
    average_score: float | None  # None when no verdict yet
    has_contradictions: bool
    has_honeytoken_leaks: bool
    has_verdict: bool


@dataclass(frozen=True)
class SessionDetail:
    """Everything the drill-down panel needs for one session."""

    metadata: SessionMetadata
    transcript: SessionTranscript
    verdict: JudgeVerdict | None
    contradictions: dict[str, Any] | None
    honeytoken_leaks: dict[str, Any] | None
    telemetry: list[TelemetryEntry]


# ---------------------------------------------------------------------------
# Listing + filtering
# ---------------------------------------------------------------------------


def list_sessions(
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
) -> list[SessionSummary]:
    """
    Return every session under `sessions_dir`, newest first.

    A directory is considered a session iff it contains a metadata.json;
    stray files or half-written folders are skipped silently. The average
    score is None when verdict.json is missing (e.g. the session was run
    with --no-judge).
    """
    if not sessions_dir.exists() or not sessions_dir.is_dir():
        return []

    summaries: list[SessionSummary] = []
    for candidate in sorted(sessions_dir.iterdir(), reverse=True):
        if not candidate.is_dir():
            continue
        if not (candidate / METADATA_FILENAME).exists():
            continue

        session_id = candidate.name
        metadata = load_metadata(session_id, base=sessions_dir)
        transcript = load_transcript(session_id, base=sessions_dir)
        if metadata is None or transcript is None:
            continue

        verdict = _load_verdict(session_id, sessions_dir)
        contradictions = _load_json(candidate / CONTRADICTIONS_FILENAME)
        honeytokens = _load_json(candidate / HONEYTOKEN_LEAKS_FILENAME)

        summaries.append(
            SessionSummary(
                session_id=session_id,
                scenario_id=metadata.scenario_id,
                created_at=metadata.created_at,
                total_turns=len(transcript.turns),
                average_score=_average_verdict_score(verdict),
                has_contradictions=_report_has_items(contradictions, "contradictions"),
                has_honeytoken_leaks=_report_has_items(honeytokens, "leaks"),
                has_verdict=verdict is not None,
            )
        )
    return summaries


def filter_sessions(
    sessions: list[SessionSummary],
    scenario_ids: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_avg_score: float | None = None,
    max_avg_score: float | None = None,
    require_contradictions: bool | None = None,
    require_honeytoken_leaks: bool | None = None,
) -> list[SessionSummary]:
    """
    Filter a session list by any combination of criteria. Every argument
    is optional — passing None (or an empty list) means 'don't filter on
    this dimension'.

    Score bounds are inclusive; sessions without a verdict are only kept
    when NO score bound is set. That's the honest thing: an unrated
    session shouldn't sneak past 'score >= 4' just because it's None.
    """
    kept: list[SessionSummary] = []
    for row in sessions:
        if not _passes_scenario(row, scenario_ids):
            continue
        if not _passes_dates(row, date_from, date_to):
            continue
        if not _passes_score(row, min_avg_score, max_avg_score):
            continue
        if (
            require_contradictions is not None
            and row.has_contradictions != require_contradictions
        ):
            continue
        if (
            require_honeytoken_leaks is not None
            and row.has_honeytoken_leaks != require_honeytoken_leaks
        ):
            continue
        kept.append(row)
    return kept


def _passes_scenario(
    row: SessionSummary,
    scenario_ids: list[str] | None,
) -> bool:
    """Scenario filter: empty/None accepts every row."""
    if not scenario_ids:
        return True
    return row.scenario_id in scenario_ids


def _passes_dates(
    row: SessionSummary,
    date_from: date | None,
    date_to: date | None,
) -> bool:
    """Date-range filter: None on either side means unbounded."""
    if date_from is None and date_to is None:
        return True
    row_date = _iso_to_date(row.created_at)
    if row_date is None:
        return False
    if date_from is not None and row_date < date_from:
        return False
    if date_to is not None and row_date > date_to:  # noqa: SIM103 - guard style stays readable
        return False
    return True


def _passes_score(
    row: SessionSummary,
    min_avg_score: float | None,
    max_avg_score: float | None,
) -> bool:
    """
    Score-range filter. Sessions without a verdict are excluded whenever
    any score bound is set — unrated sessions must not sneak past 'score
    >= 4' just because their average is None.
    """
    if min_avg_score is None and max_avg_score is None:
        return True
    if row.average_score is None:
        return False
    if min_avg_score is not None and row.average_score < min_avg_score:
        return False
    if max_avg_score is not None and row.average_score > max_avg_score:  # noqa: SIM103 - guard style stays readable
        return False
    return True


# ---------------------------------------------------------------------------
# Full detail for a single session
# ---------------------------------------------------------------------------


def load_session_detail(
    session_id: str,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
) -> SessionDetail | None:
    """
    Load metadata + transcript + verdict + sidecars for one session. Returns
    None when the metadata file is missing (session does not exist).
    """
    metadata = load_metadata(session_id, base=sessions_dir)
    transcript = load_transcript(session_id, base=sessions_dir)
    if metadata is None or transcript is None:
        return None

    verdict = _load_verdict(session_id, sessions_dir)
    session_folder = session_dir(sessions_dir, session_id)
    contradictions = _load_json(session_folder / CONTRADICTIONS_FILENAME)
    honeytokens = _load_json(session_folder / HONEYTOKEN_LEAKS_FILENAME)
    telemetry = load_turn_telemetry(session_id, sessions_dir=sessions_dir)

    return SessionDetail(
        metadata=metadata,
        transcript=transcript,
        verdict=verdict,
        contradictions=contradictions,
        honeytoken_leaks=honeytokens,
        telemetry=telemetry,
    )


def load_turn_telemetry(
    session_id: str,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
) -> list[TelemetryEntry]:
    """
    Load per-turn telemetry. Sessions written before Phase D don't have
    this sidecar; returning an empty list is a valid answer.
    """
    payload = _load_json(session_dir(sessions_dir, session_id) / TURN_TELEMETRY_FILENAME)
    if payload is None:
        return []
    raw_entries = payload.get("turns", []) if isinstance(payload, dict) else []
    entries: list[TelemetryEntry] = []
    for row in raw_entries:
        try:
            entries.append(
                TelemetryEntry(
                    turn_index=int(row["turn_index"]),
                    input_tokens=int(row["input_tokens"]),
                    output_tokens=int(row["output_tokens"]),
                    latency_ms=int(row["latency_ms"]),
                    provider_name=str(row["provider_name"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            # Skip malformed rows rather than break the whole page.
            continue
    return entries


def aggregate_telemetry(
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
    limit: int | None = None,
) -> list[TelemetryEntry]:
    """
    Return telemetry entries from the newest `limit` sessions concatenated.

    Metrics page consumes this to compute per-provider latency p95 and total
    estimated cost. When `limit` is None, every session is included.
    """
    summaries = list_sessions(sessions_dir=sessions_dir)
    if limit is not None:
        summaries = summaries[:limit]
    combined: list[TelemetryEntry] = []
    for row in summaries:
        combined.extend(load_turn_telemetry(row.session_id, sessions_dir=sessions_dir))
    return combined


# ---------------------------------------------------------------------------
# Security reports produced by Phase C
# ---------------------------------------------------------------------------


def load_adversarial_v1(
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> dict[str, Any] | None:
    """
    Parse `reports/adversarial_v1.json`. Returns None when the file is
    missing so the metrics page can show a 'run the battery first' hint
    instead of crashing.
    """
    return _load_json(reports_dir / "adversarial_v1.json")


def load_judge_deceiver_v1(
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> dict[str, Any] | None:
    """Parse `reports/judge_deceiver_pointwise_v1.json`."""
    return _load_json(reports_dir / "judge_deceiver_pointwise_v1.json")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any] | None:
    """Return a parsed JSON dict, or None on any error (missing / malformed)."""
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_verdict(session_id: str, sessions_dir: Path) -> JudgeVerdict | None:
    """
    Load and validate a session's verdict.json. Malformed verdicts are
    treated as 'no verdict' rather than crashing the list page.
    """
    target = session_dir(sessions_dir, session_id) / VERDICT_FILENAME
    if not target.exists():
        return None
    try:
        return JudgeVerdict.model_validate_json(target.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _average_verdict_score(verdict: JudgeVerdict | None) -> float | None:
    """Mean of criterion scores, or None when there's no verdict."""
    if verdict is None or not verdict.criteria:
        return None
    return sum(c.score for c in verdict.criteria) / len(verdict.criteria)


def _report_has_items(payload: dict[str, Any] | None, list_key: str) -> bool:
    """True iff the JSON payload contains a non-empty list at `list_key`."""
    if not isinstance(payload, dict):
        return False
    items = payload.get(list_key)
    return isinstance(items, list) and len(items) > 0


def _iso_to_date(iso_text: str) -> date | None:
    """Extract the calendar date from an ISO timestamp, or None if invalid."""
    try:
        # Accept 'Z' suffix and space separators.
        return date.fromisoformat(iso_text[:10])
    except ValueError:
        return None


# Expose the sidecar filename constant so the CLI can write to the same path.
__all__ = [
    "DEFAULT_REPORTS_DIR",
    "DEFAULT_SESSIONS_DIR",
    "SessionDetail",
    "SessionSummary",
    "TURN_TELEMETRY_FILENAME",
    "TelemetryEntry",
    "aggregate_telemetry",
    "filter_sessions",
    "list_sessions",
    "load_adversarial_v1",
    "load_judge_deceiver_v1",
    "load_session_detail",
    "load_turn_telemetry",
]
