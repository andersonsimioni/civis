"""
On-disk persistence of CIVIS sessions.

Fase A layout (SQLite / Postgres come later):
    data/sessions/{session_id}/
        transcript.json         Ordered list of turns.
        metadata.json           Scenario id, timestamps, provider names, seeds.
        verdict.json            Present only after the judge has scored the
                                session; absent while the session is in progress.
        contradictions.json     Contradiction detector output (B.4). Present
                                after any session run, judge or no judge.
        honeytoken_leaks.json   Honeytoken leak detector output (C.2). Present
                                after any session run — total=0 means the
                                persona did not pronounce any planted honeytoken.
        issued_documents/       Phase D+++: one .md file per document the
                                attendant "issued" during the session
                                (fake certidão, RG). Absent when no
                                emission happened.

Two design choices worth calling out:

    - session_id is caller-controlled, not derived. This lets the CLI
      resume a session with the same id, and keeps the on-disk name
      stable across renames of the scenario.

    - Metadata carries scenario_id + the SHA-256 of the loaded scenario
      YAML. Reopening a session against a mutated scenario file is
      rejected with a clear error, per the acceptance criterion of A.6
      ("relançar CLI com mesmo session_id reabre e continua ou erra
      claramente se cenário mudou").

Phase D+++: `Turn.speaker` now also accepts the value ``"action"`` for
turns that record a clickable-button emission (verify identity, issue
certificate, ...). Downstream consumers ignore action turns when
building the persona prompt, so the LLM never sees them as user speech
— they exist purely as visible artefacts in the transcript.

Onda 2 T1.3: `Turn.speaker` also accepts ``"queue"`` — a pressure
event injected by the web chat when the session timer crosses the
warning / critical thresholds declared in the scenario's
``service_sla``. Queue turns are also filtered out of the persona and
judge prompts (same logic as action turns), so they never contaminate
the LLM context.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

# Filenames within data/sessions/{session_id}/
TRANSCRIPT_FILENAME = "transcript.json"
METADATA_FILENAME = "metadata.json"
VERDICT_FILENAME = "verdict.json"
CONTRADICTIONS_FILENAME = "contradictions.json"
HONEYTOKEN_LEAKS_FILENAME = "honeytoken_leaks.json"
# Phase D sidecar — per-turn LLM telemetry (input tokens, output tokens,
# latency, provider name). Absent for sessions written before Phase D.
TURN_TELEMETRY_FILENAME = "turn_telemetry.json"
# Phase D+++ — subfolder that collects one Markdown file per document
# the attendant "issued" during the session. Created lazily on the
# first emission.
ISSUED_DOCUMENTS_DIRNAME = "issued_documents"


class Turn(BaseModel):
    """One utterance in a session. Ordered by turn_index (0-based).

    Speaker values:
        - "agent"   — the trainee's message.
        - "persona" — the LLM-driven persona reply.
        - "action"  — Phase D+++ button click. The `content` is a JSON
                      payload (see `civis.web.pages.new_session._action_turn_content`)
                      so a single string field carries the id, label and
                      optional emitted-document details.
        - "queue"   — Onda 2 T1.3 pressure event. Injected by the chat
                      view when the elapsed session time crosses the
                      warning / critical SLA thresholds. The `content`
                      is a JSON payload with the severity, minutes
                      waited and the pt-BR complaint line. Filtered out
                      of both the persona prompt and the judge prompt,
                      so it never leaks into the LLM context.
    """

    turn_index: int = Field(ge=0)
    speaker: str = Field(pattern="^(agent|persona|action|queue)$")
    content: str
    # ISO-8601 UTC timestamp string. Kept as text for round-trip friendliness
    # with jq / spreadsheets. Parse only when a datetime is needed.
    timestamp: str


class SessionTranscript(BaseModel):
    """The ordered list of turns, plus the session id it belongs to."""

    session_id: str
    turns: list[Turn] = Field(default_factory=list)

    def append(self, speaker: str, content: str) -> Turn:
        """
        Append a new turn and return it. Turn index is derived from the
        current length so callers never need to compute it themselves.
        """
        turn = Turn(
            turn_index=len(self.turns),
            speaker=speaker,
            content=content,
            timestamp=_now_utc_iso(),
        )
        self.turns.append(turn)
        return turn


class SessionMetadata(BaseModel):
    """
    Sidecar carrying everything about the session other than the turns.
    Written once at session creation and updated on every save so the
    'last_updated_at' timestamp reflects the most recent activity.
    """

    session_id: str
    scenario_id: str
    # SHA-256 of the scenario YAML text, hex-encoded. Reopening a session
    # against a mutated scenario file is refused (see load_session).
    scenario_hash: str
    persona_provider_name: str
    judge_provider_name: str | None = None
    created_at: str
    last_updated_at: str
    # Optional numeric seed for anything downstream that needs
    # deterministic sampling (e.g. adversarial provider selection).
    seed: int | None = None


# ---- read / write helpers -------------------------------------------------

def session_dir(base: Path, session_id: str) -> Path:
    """Return the directory that holds all files for the given session."""
    return base / session_id


def new_session_id(now: datetime | None = None) -> str:
    """
    Build a fresh session id from the current UTC time. Format is
    'YYYY-MM-DD_HHMMSS' so ids sort lexicographically by creation time
    and are safe on every filesystem.
    """
    dt = now or datetime.now(UTC)
    return dt.strftime("%Y-%m-%d_%H%M%S")


def scenario_hash(scenario_text: str) -> str:
    """SHA-256 of the scenario YAML source, hex-encoded."""
    return hashlib.sha256(scenario_text.encode("utf-8")).hexdigest()


def save_transcript(transcript: SessionTranscript, base: Path) -> Path:
    """Write the transcript to disk. Overwrites any prior version."""
    target = session_dir(base, transcript.session_id) / TRANSCRIPT_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    _dump_json(target, transcript.model_dump(mode="json"))
    return target


def save_metadata(metadata: SessionMetadata, base: Path) -> Path:
    """Write metadata to disk. Overwrites any prior version."""
    target = session_dir(base, metadata.session_id) / METADATA_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    _dump_json(target, metadata.model_dump(mode="json"))
    return target


def save_verdict_json(verdict_payload: dict, session_id: str, base: Path) -> Path:
    """
    Persist the judge verdict as a raw dict. Accepting the dict directly
    (instead of a JudgeVerdict) keeps this module free of a dependency
    on the judge contracts — the orchestrator does the conversion.
    """
    target = session_dir(base, session_id) / VERDICT_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    _dump_json(target, verdict_payload)
    return target


def save_contradictions_json(
    report_payload: dict,
    session_id: str,
    base: Path,
) -> Path:
    """
    Persist the ContradictionReport as a raw dict. Same rationale as
    save_verdict_json — this module stays free of a dependency on the
    session.contradiction_detector contracts.
    """
    target = session_dir(base, session_id) / CONTRADICTIONS_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    _dump_json(target, report_payload)
    return target


def save_honeytoken_leaks_json(
    report_payload: dict,
    session_id: str,
    base: Path,
) -> Path:
    """
    Persist the HoneytokenLeakReport as a raw dict. Same rationale as
    save_contradictions_json — this module stays free of a dependency on
    the honeytoken detector contracts.
    """
    target = session_dir(base, session_id) / HONEYTOKEN_LEAKS_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    _dump_json(target, report_payload)
    return target


def save_turn_telemetry_json(
    payload: dict,
    session_id: str,
    base: Path,
) -> Path:
    """
    Persist per-turn LLM telemetry (input/output tokens, latency,
    provider name) for the M4 metrics panel. Payload shape:

        {"session_id": ..., "turns": [{"turn_index", "input_tokens",
         "output_tokens", "latency_ms", "provider_name"}, ...]}

    The CLI accumulates one entry per persona turn (agent turns cost no
    tokens) and rewrites this file on every turn so a crash mid-session
    does not lose the telemetry recorded so far.
    """
    target = session_dir(base, session_id) / TURN_TELEMETRY_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    _dump_json(target, payload)
    return target


def issued_document_path(
    session_id: str,
    document_id: str,
    base: Path,
) -> Path:
    """
    Return the on-disk path where an issued document markdown file lives.
    Callers create it via :func:`save_issued_document`.
    """
    return (
        session_dir(base, session_id)
        / ISSUED_DOCUMENTS_DIRNAME
        / f"{document_id}.md"
    )


def save_issued_document(
    session_id: str,
    document_id: str,
    body: str,
    base: Path,
) -> Path:
    """
    Persist a rendered document (Markdown/ASCII body) under
    ``data/sessions/<sid>/issued_documents/<document_id>.md``. Creates
    the subdirectory on first call.
    """
    target = issued_document_path(session_id, document_id, base)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8")
    return target


def load_transcript(session_id: str, base: Path) -> SessionTranscript | None:
    """Return the transcript, or None if the session does not exist."""
    target = session_dir(base, session_id) / TRANSCRIPT_FILENAME
    if not target.exists():
        return None
    return SessionTranscript.model_validate_json(target.read_text(encoding="utf-8"))


def load_metadata(session_id: str, base: Path) -> SessionMetadata | None:
    """Return the metadata, or None if the session does not exist."""
    target = session_dir(base, session_id) / METADATA_FILENAME
    if not target.exists():
        return None
    return SessionMetadata.model_validate_json(target.read_text(encoding="utf-8"))


def touch_metadata(metadata: SessionMetadata) -> SessionMetadata:
    """Return a copy of the metadata with last_updated_at set to now."""
    return metadata.model_copy(update={"last_updated_at": _now_utc_iso()})


def session_exists(session_id: str, base: Path) -> bool:
    """True if metadata.json already exists under the session directory."""
    return (session_dir(base, session_id) / METADATA_FILENAME).exists()


class ScenarioDriftError(RuntimeError):
    """
    Raised when reopening a session against a scenario file whose SHA-256
    differs from the one captured when the session was created. The caller
    must decide whether to start a fresh session or to ignore the drift
    (which risks a stale transcript against an updated rubric).
    """


def ensure_scenario_matches(
    metadata: SessionMetadata,
    current_scenario_text: str,
) -> None:
    """Raise ScenarioDriftError if the scenario file has changed on disk."""
    current_hash = scenario_hash(current_scenario_text)
    if current_hash != metadata.scenario_hash:
        raise ScenarioDriftError(
            f"Scenario '{metadata.scenario_id}' has changed since session "
            f"'{metadata.session_id}' was created (hash mismatch). "
            f"Start a fresh session or revert the scenario file."
        )


# ---- internal helpers ------------------------------------------------------

def _now_utc_iso() -> str:
    """Current UTC time as ISO-8601 with second precision (no microseconds)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _dump_json(path: Path, payload: dict) -> None:
    """
    Pretty-print JSON with UTF-8 preserved (ensure_ascii=False) and a
    trailing newline so the files diff cleanly in git.
    """
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
