"""
Unit tests for :mod:`civis.web.replay` — the replay-timeline event
extractor (ONDA 3, R1.1).

Each test builds a minimal, hand-crafted fixture rather than reaching
for the demo-session generator, so a failure points at the extractor,
not at the demo data.
"""

from __future__ import annotations

import json

from civis.judge.rubric import (
    CitedTurn,
    CriterionKind,
    CriterionVerdict,
    JudgeVerdict,
)
from civis.session.storage import SessionTranscript, Turn
from civis.web.replay import ReplayEvent, build_replay_timeline


def _make_transcript(*speakers_and_contents: tuple[str, str]) -> SessionTranscript:
    """Build a transcript from ``(speaker, content)`` pairs."""
    turns = [
        Turn(
            turn_index=i,
            speaker=speaker,
            content=content,
            timestamp="2026-09-16T12:00:00+00:00",
        )
        for i, (speaker, content) in enumerate(speakers_and_contents)
    ]
    return SessionTranscript(session_id="sid", turns=turns)


def _make_verdict(
    *criterion_specs: tuple[CriterionKind, int, list[tuple[int, str]]],
) -> JudgeVerdict:
    """
    Build a verdict from ``(criterion, score, cited_turns)`` tuples,
    where ``cited_turns`` is a list of ``(turn_index, excerpt)`` pairs.
    """
    criteria = [
        CriterionVerdict(
            criterion=criterion,
            score=score,
            rationale="test",
            cited_turns=[
                CitedTurn(turn_index=idx, excerpt=excerpt)
                for idx, excerpt in cites
            ],
        )
        for criterion, score, cites in criterion_specs
    ]
    return JudgeVerdict(
        session_id="sid",
        criteria=criteria,
        overall_summary="test",
    )


# ---------------------------------------------------------------------------
# 1. Citation events pick up the criterion score and turn_index
# ---------------------------------------------------------------------------


def test_citation_events_map_high_scores_to_positive() -> None:
    """A criterion scored 5/5 emits ``positive`` citation events."""
    transcript = _make_transcript(
        ("agent", "boa tarde"),
        ("persona", "boa tarde, moço"),
    )
    verdict = _make_verdict(
        (CriterionKind.COMMUNICATION, 5, [(1, "boa tarde, moço")]),
    )
    events = build_replay_timeline(transcript, verdict, None, None)

    citations = [e for e in events if e.event_type == "citation"]
    assert len(citations) == 1
    ev = citations[0]
    assert ev.turn_index == 1
    assert ev.severity == "positive"
    assert ev.criterion == "communication"
    assert "Comunicação" in ev.label
    assert "5/5" in ev.label


# ---------------------------------------------------------------------------
# 2. Citation events with low scores map to critical, mid to warning
# ---------------------------------------------------------------------------


def test_citation_events_map_low_and_mid_scores_correctly() -> None:
    """Score 1 -> critical; score 3 -> warning."""
    transcript = _make_transcript(
        ("agent", "a"),
        ("persona", "b"),
        ("agent", "c"),
    )
    verdict = _make_verdict(
        (CriterionKind.FACT_VERIFICATION, 1, [(0, "sem verificar")]),
        (CriterionKind.PROTOCOL_ADHERENCE, 3, [(2, "meio-termo")]),
    )
    events = build_replay_timeline(transcript, verdict, None, None)
    critical = [
        e for e in events if e.event_type == "citation" and e.severity == "critical"
    ]
    warning = [
        e for e in events if e.event_type == "citation" and e.severity == "warning"
    ]
    assert len(critical) == 1 and critical[0].criterion == "fact_verification"
    assert len(warning) == 1 and warning[0].criterion == "protocol_adherence"


# ---------------------------------------------------------------------------
# 3. Contradictions are always critical
# ---------------------------------------------------------------------------


def test_contradiction_events_are_always_critical() -> None:
    """One row in the ContradictionReport payload yields one critical dot."""
    transcript = _make_transcript(
        ("agent", "qual sua data de nascimento?"),
        ("persona", "12/03/1954"),
        ("agent", "confirma?"),
        ("persona", "15/03/1954"),
    )
    contradictions = {
        "contradictions": [
            {
                "turn_index": 3,
                "fact_key": "birth_date",
                "prior_value": "12/03/1954",
                "new_value": "15/03/1954",
            }
        ],
        "total_turns": 4,
    }
    events = build_replay_timeline(transcript, None, contradictions, None)
    matches = [e for e in events if e.event_type == "contradiction"]
    assert len(matches) == 1
    assert matches[0].severity == "critical"
    assert matches[0].turn_index == 3
    assert "birth_date" in matches[0].label


# ---------------------------------------------------------------------------
# 4. Honeytoken leaks emit critical dots on the leaking turn
# ---------------------------------------------------------------------------


def test_honeytoken_leak_events_are_critical_on_the_leaking_turn() -> None:
    """One planted leak yields one critical honeytoken_leak dot."""
    transcript = _make_transcript(
        ("agent", "qual o cpf da pessoa?"),
        ("persona", "999.999.999-99"),
    )
    honeytokens = {
        "session_id": "sid",
        "scenario_id": "cen",
        "leaks": [
            {
                "turn_index": 1,
                "fact_key": "mother_maiden_name",
                "honeytoken_value": "SILVA",
                "context": "...",
            }
        ],
    }
    events = build_replay_timeline(transcript, None, None, honeytokens)
    leaks = [e for e in events if e.event_type == "honeytoken_leak"]
    assert len(leaks) == 1
    assert leaks[0].severity == "critical"
    assert leaks[0].turn_index == 1
    assert "mother_maiden_name" in leaks[0].label


# ---------------------------------------------------------------------------
# 5. Action and queue transcript turns emit neutral markers
# ---------------------------------------------------------------------------


def test_action_and_queue_turns_emit_neutral_markers() -> None:
    """Structural non-speech turns become neutral action / queue dots."""
    transcript = _make_transcript(
        ("agent", "oi"),
        ("action", json.dumps({"id": "verify_identity", "label": "Verificar identidade"})),
        ("persona", "obrigado"),
        ("queue", json.dumps({"severity": "warning", "label": "3 min esperando"})),
    )
    events = build_replay_timeline(transcript, None, None, None)
    actions = [e for e in events if e.event_type == "action"]
    queues = [e for e in events if e.event_type == "queue"]
    assert len(actions) == 1
    assert actions[0].severity == "neutral"
    assert actions[0].turn_index == 1
    assert actions[0].label == "Verificar identidade"
    assert len(queues) == 1
    assert queues[0].severity == "neutral"
    assert queues[0].turn_index == 3
    assert queues[0].label == "3 min esperando"


# ---------------------------------------------------------------------------
# 6. Missing / malformed sidecars degrade gracefully
# ---------------------------------------------------------------------------


def test_missing_and_malformed_inputs_return_empty_or_stable_timeline() -> None:
    """
    None inputs are ignored. Malformed sidecar shapes never crash the
    extractor — they contribute zero events.
    """
    transcript = _make_transcript(("agent", "hi"))

    # Everything None → empty timeline.
    assert build_replay_timeline(transcript, None, None, None) == []

    # Malformed shapes: strings instead of dicts, missing keys, wrong types.
    bad_contradictions = {"contradictions": "not a list"}
    bad_honeytokens = {"leaks": [{"no_turn_index": True}]}
    events = build_replay_timeline(
        transcript,
        None,
        bad_contradictions,  # type: ignore[arg-type]
        bad_honeytokens,
    )
    assert events == []


# ---------------------------------------------------------------------------
# 7. Bonus: full mix keeps deterministic order
# ---------------------------------------------------------------------------


def test_events_are_sorted_by_turn_index_then_type() -> None:
    """
    Same turn hosting a citation, a contradiction and a queue event
    must emit them in the fixed type order: citation < contradiction
    < queue. This is what lets the UI place dots consistently.
    """
    transcript = _make_transcript(
        ("agent", "a"),
        ("persona", "b"),
        ("queue", json.dumps({"label": "pressao"})),
    )
    verdict = _make_verdict(
        (CriterionKind.PROTOCOL_ADHERENCE, 4, [(2, "cite on queue turn")]),
    )
    contradictions = {
        "contradictions": [
            {
                "turn_index": 2,
                "fact_key": "birth_date",
                "prior_value": "x",
                "new_value": "y",
            }
        ],
        "total_turns": 3,
    }
    events = build_replay_timeline(transcript, verdict, contradictions, None)
    types_at_turn_2 = [e.event_type for e in events if e.turn_index == 2]
    assert types_at_turn_2 == ["citation", "contradiction", "queue"]


def test_replay_event_dataclass_is_hashable_and_frozen() -> None:
    """ReplayEvent is a frozen dataclass — mutating fields must raise."""
    ev = ReplayEvent(
        turn_index=0,
        event_type="action",
        severity="neutral",
        label="test",
    )
    try:
        ev.turn_index = 42  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ReplayEvent must be immutable")
