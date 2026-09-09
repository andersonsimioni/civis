"""
FSM transition rules.

Two axes of transition, kept separate on purpose:

    - Phase progression is BASELINE — the same skeleton for all personas.
      Confused, aggressive and fraudster personas all go through opening ->
      info gathering -> attempt -> resolution. What differs is HOW they
      behave inside each phase (that's the LLM's job).

    - Emotional escalation is PROFILE-SPECIFIC. A confused citizen drifts
      toward frustration; an aggressive one toward outright anger; a
      fraudster ramps up manipulative pressure and then desperation.

Rules are deterministic functions of PersonaState. No randomness, no LLM
input — this is the auditable part of the persona (goal O1).

Week 1 keeps these rules intentionally simple. Week 4 refines them with
proactive behavior (pressure, escalation timing).
"""

from collections.abc import Callable
from dataclasses import dataclass

from civis.fsm.states import EmotionalState, Phase
from civis.personas.base import PersonaKind, PersonaState

# Phase-progression thresholds. Named for readability at call sites.
MIN_TURNS_BEFORE_INFO_GATHERING = 1
MIN_FACTS_REVEALED_BEFORE_ATTEMPT = 2
MIN_TURNS_BEFORE_RESOLUTION = 8

# Emotional-escalation thresholds by profile.
CONFUSED_TURNS_UNTIL_FRUSTRATED = 4
AGGRESSIVE_TURNS_UNTIL_ANGRY = 3
FRAUDSTER_TURNS_UNTIL_DESPERATE = 5


@dataclass(frozen=True)
class PhaseTransitionRule:
    """A single deterministic phase transition: (from + predicate) -> to."""

    from_phase: Phase
    to_phase: Phase
    predicate: Callable[[PersonaState], bool]


# Baseline phase progression, applied to every persona kind.
# First matching rule wins (see engine.advance_turn).
BASELINE_PHASE_RULES: list[PhaseTransitionRule] = [
    PhaseTransitionRule(
        from_phase=Phase.OPENING,
        to_phase=Phase.INFO_GATHERING,
        predicate=lambda s: s.turn_count >= MIN_TURNS_BEFORE_INFO_GATHERING,
    ),
    PhaseTransitionRule(
        from_phase=Phase.INFO_GATHERING,
        to_phase=Phase.ATTEMPT,
        predicate=lambda s: len(s.revealed_fact_keys) >= MIN_FACTS_REVEALED_BEFORE_ATTEMPT,
    ),
    PhaseTransitionRule(
        from_phase=Phase.ATTEMPT,
        to_phase=Phase.RESOLUTION,
        predicate=lambda s: s.turn_count >= MIN_TURNS_BEFORE_RESOLUTION,
    ),
]


def _next_emotion_confused(state: PersonaState) -> EmotionalState:
    """Confused personas drift from anxious to frustrated as the stall lengthens."""
    if (
        state.emotion == EmotionalState.ANXIOUS
        and state.turn_count >= CONFUSED_TURNS_UNTIL_FRUSTRATED
    ):
        return EmotionalState.FRUSTRATED
    return state.emotion


def _next_emotion_aggressive(state: PersonaState) -> EmotionalState:
    """Aggressive personas escalate from frustrated to angry quickly."""
    if (
        state.emotion == EmotionalState.FRUSTRATED
        and state.turn_count >= AGGRESSIVE_TURNS_UNTIL_ANGRY
    ):
        return EmotionalState.ANGRY
    return state.emotion


def _next_emotion_fraudster(state: PersonaState) -> EmotionalState:
    """Fraudsters ramp up pressure: manipulative posture becomes desperation."""
    if (
        state.emotion == EmotionalState.MANIPULATIVE
        and state.turn_count >= FRAUDSTER_TURNS_UNTIL_DESPERATE
    ):
        return EmotionalState.DESPERATE
    return state.emotion


# Dispatch table by persona kind. New profiles slot in here without touching engine.
EMOTION_RULE_BY_KIND: dict[PersonaKind, Callable[[PersonaState], EmotionalState]] = {
    PersonaKind.CONFUSED: _next_emotion_confused,
    PersonaKind.AGGRESSIVE: _next_emotion_aggressive,
    PersonaKind.FRAUDSTER: _next_emotion_fraudster,
}
