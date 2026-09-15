"""
Session persistence tests.

The storage layer is dumb on purpose: read/write JSON files under
data/sessions/{session_id}/. What matters is that:

    - Turns appended to a transcript get sequential zero-based indices.
    - save + load round-trips a transcript byte-for-byte in content.
    - session_exists / load_metadata correctly signal absence with None
      or False (so the CLI can decide 'new session' vs 'resume').
    - Scenario drift is detected via a SHA-256 hash captured at
      creation and re-checked on reopen — reopening against a mutated
      scenario file must raise ScenarioDriftError.
"""

from datetime import UTC
from pathlib import Path

import pytest

from civis.session.storage import (
    ScenarioDriftError,
    SessionMetadata,
    SessionTranscript,
    Turn,
    ensure_scenario_matches,
    load_metadata,
    load_transcript,
    new_session_id,
    save_metadata,
    save_transcript,
    save_verdict_json,
    scenario_hash,
    session_exists,
    touch_metadata,
)

# ---- fixtures --------------------------------------------------------------

def _metadata(session_id: str, scenario_text: str = "sc: v1") -> SessionMetadata:
    return SessionMetadata(
        session_id=session_id,
        scenario_id="certificate_duplicate_confused_v1",
        scenario_hash=scenario_hash(scenario_text),
        persona_provider_name="ollama:qwen2.5:7b",
        judge_provider_name="anthropic:claude-sonnet-4-6",
        created_at="2026-09-15T14:30:12+00:00",
        last_updated_at="2026-09-15T14:30:12+00:00",
    )


# ---- append + round-trip ---------------------------------------------------

def test_append_assigns_sequential_zero_based_indices():
    transcript = SessionTranscript(session_id="s1")
    t0 = transcript.append("agent", "Bom dia")
    t1 = transcript.append("persona", "Oi")
    t2 = transcript.append("agent", "Como posso ajudar?")
    assert (t0.turn_index, t1.turn_index, t2.turn_index) == (0, 1, 2)
    assert transcript.turns == [t0, t1, t2]


def test_turn_rejects_invalid_speaker():
    with pytest.raises(ValueError):
        Turn(turn_index=0, speaker="clerk", content="hi", timestamp="2026-01-01T00:00:00+00:00")


def test_save_and_load_transcript_roundtrip(tmp_path: Path):
    transcript = SessionTranscript(session_id="2026-09-15_143012")
    transcript.append("agent", "Bom dia, em que posso ajudar?")
    transcript.append("persona", "Queria uma segunda via.")

    written = save_transcript(transcript, base=tmp_path)
    assert written.exists()
    assert written.name == "transcript.json"

    reloaded = load_transcript(transcript.session_id, base=tmp_path)
    assert reloaded is not None
    assert reloaded.session_id == transcript.session_id
    assert [(t.speaker, t.content) for t in reloaded.turns] == [
        ("agent", "Bom dia, em que posso ajudar?"),
        ("persona", "Queria uma segunda via."),
    ]


def test_load_transcript_returns_none_when_missing(tmp_path: Path):
    assert load_transcript("nonexistent", base=tmp_path) is None


# ---- metadata --------------------------------------------------------------

def test_save_and_load_metadata_roundtrip(tmp_path: Path):
    metadata = _metadata("s1")
    written = save_metadata(metadata, base=tmp_path)
    assert written.exists()
    reloaded = load_metadata("s1", base=tmp_path)
    assert reloaded == metadata


def test_session_exists_returns_true_after_save(tmp_path: Path):
    assert not session_exists("s1", base=tmp_path)
    save_metadata(_metadata("s1"), base=tmp_path)
    assert session_exists("s1", base=tmp_path)


def test_touch_metadata_updates_last_updated_at():
    metadata = _metadata("s1")
    updated = touch_metadata(metadata)
    assert updated.last_updated_at != metadata.last_updated_at
    # The rest of the fields are untouched.
    assert updated.session_id == metadata.session_id
    assert updated.scenario_hash == metadata.scenario_hash


# ---- verdict ---------------------------------------------------------------

def test_save_verdict_writes_file(tmp_path: Path):
    payload = {"session_id": "s1", "criteria": [], "overall_summary": "ok"}
    written = save_verdict_json(payload, session_id="s1", base=tmp_path)
    assert written.name == "verdict.json"
    assert written.exists()
    # Trailing newline for git-friendly diffs.
    text = written.read_text(encoding="utf-8")
    assert text.endswith("\n")


# ---- scenario drift --------------------------------------------------------

def test_ensure_scenario_matches_accepts_same_hash():
    metadata = _metadata("s1", scenario_text="scenario: v1")
    # No exception should be raised.
    ensure_scenario_matches(metadata, current_scenario_text="scenario: v1")


def test_ensure_scenario_matches_rejects_drift():
    metadata = _metadata("s1", scenario_text="scenario: v1")
    with pytest.raises(ScenarioDriftError, match="has changed"):
        ensure_scenario_matches(metadata, current_scenario_text="scenario: v2")


# ---- ids -------------------------------------------------------------------

def test_new_session_id_is_lexicographically_sortable():
    from datetime import datetime
    earlier = new_session_id(datetime(2026, 9, 15, 14, 30, 0, tzinfo=UTC))
    later = new_session_id(datetime(2026, 9, 15, 14, 31, 0, tzinfo=UTC))
    assert earlier < later
    # Format check: no spaces, no colons.
    assert " " not in earlier and ":" not in earlier
