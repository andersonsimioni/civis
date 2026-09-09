"""
FSM engine tests.

Verifies deterministic phase progression and profile-specific emotional
escalation. No LLM involved — the FSM is pure logic that must be replayable
exactly (goal O6).
"""

from civis.fsm.engine import advance_turn
from civis.fsm.states import EmotionalState, Phase
from civis.personas.base import PersonaKind, PersonaProfile, PersonaState


def _make_state(
    kind: PersonaKind,
    phase: Phase = Phase.OPENING,
    emotion: EmotionalState = EmotionalState.CALM,
    turn_count: int = 0,
    revealed_fact_keys: set[str] | None = None,
) -> PersonaState:
    profile = PersonaProfile(
        kind=kind,
        name="Persona de teste",
        background="Cidadão fictício para teste da FSM.",
        goal="Objetivo de teste.",
    )
    return PersonaState(
        profile=profile,
        phase=phase,
        emotion=emotion,
        turn_count=turn_count,
        revealed_fact_keys=revealed_fact_keys or set(),
    )


def test_opening_advances_to_info_gathering_after_first_turn():
    state = _make_state(PersonaKind.CONFUSED)
    assert state.phase == Phase.OPENING

    new_state = advance_turn(state)

    assert new_state.phase == Phase.INFO_GATHERING
    assert new_state.turn_count == 1


def test_info_gathering_advances_to_attempt_when_two_facts_revealed():
    state = _make_state(
        PersonaKind.CONFUSED,
        phase=Phase.INFO_GATHERING,
        revealed_fact_keys={"birth_date", "mother_name"},
        turn_count=2,
    )
    new_state = advance_turn(state)
    assert new_state.phase == Phase.ATTEMPT


def test_original_state_is_not_mutated():
    """advance_turn must return a new instance; input stays untouched."""
    state = _make_state(PersonaKind.CONFUSED)
    advance_turn(state)
    assert state.turn_count == 0
    assert state.phase == Phase.OPENING


def test_confused_persona_gets_frustrated_after_prolonged_stall():
    state = _make_state(
        PersonaKind.CONFUSED,
        emotion=EmotionalState.ANXIOUS,
        turn_count=3,
    )
    new_state = advance_turn(state)
    assert new_state.emotion == EmotionalState.FRUSTRATED


def test_aggressive_persona_gets_angry_after_two_frustrated_turns():
    state = _make_state(
        PersonaKind.AGGRESSIVE,
        emotion=EmotionalState.FRUSTRATED,
        turn_count=2,
    )
    new_state = advance_turn(state)
    assert new_state.emotion == EmotionalState.ANGRY


def test_fraudster_persona_becomes_desperate_after_manipulation_stalls():
    state = _make_state(
        PersonaKind.FRAUDSTER,
        emotion=EmotionalState.MANIPULATIVE,
        turn_count=4,
    )
    new_state = advance_turn(state)
    assert new_state.emotion == EmotionalState.DESPERATE


def test_calm_confused_persona_stays_calm_before_stall_threshold():
    state = _make_state(PersonaKind.CONFUSED, emotion=EmotionalState.CALM, turn_count=0)
    new_state = advance_turn(state)
    assert new_state.emotion == EmotionalState.CALM
