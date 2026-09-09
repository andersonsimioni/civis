"""
FSM engine.

Pure function of state: given a PersonaState and no LLM call, produces the
next PersonaState by applying phase and emotional transitions from
fsm.transitions.

Language rendering (turning "phase=INFO_GATHERING, emotion=ANXIOUS" into an
actual utterance in pt-BR) is not this module's job. That happens in the LLM
provider layer (week 2), consuming the state produced here.

The state is treated as immutable — every advance returns a new instance.
This makes sessions replayable turn by turn (goal O6, reproducibility).
"""

from civis.fsm.transitions import BASELINE_PHASE_RULES, EMOTION_RULE_BY_KIND
from civis.personas.base import PersonaState


def advance_turn(state: PersonaState) -> PersonaState:
    """
    Advance the persona by one turn.

    Order of operations matters:
        1. Increment the turn counter — rules read the UPDATED count.
        2. Apply the first matching phase-transition rule.
        3. Apply the profile-specific emotional-transition rule.

    Returns a new PersonaState; the input is not mutated.
    """
    next_state = state.model_copy(update={"turn_count": state.turn_count + 1})

    # Phase progression: first matching rule wins. Rules are ordered so that
    # earlier phases in the interaction come first in the list.
    for rule in BASELINE_PHASE_RULES:
        if next_state.phase == rule.from_phase and rule.predicate(next_state):
            next_state = next_state.model_copy(update={"phase": rule.to_phase})
            break

    # Emotional escalation is dispatched by persona kind. Keeps profile-specific
    # behavior out of the engine so new profiles need no engine changes.
    emotion_rule = EMOTION_RULE_BY_KIND[next_state.profile.kind]
    updated_emotion = emotion_rule(next_state)
    if updated_emotion != next_state.emotion:
        next_state = next_state.model_copy(update={"emotion": updated_emotion})

    return next_state
