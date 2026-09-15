"""
Observable turn events emitted by the session orchestrator.

Each event is a compact, serialisable snapshot of one turn:
    - speaker (agent | persona) and content;
    - which fact_keys were newly revealed on this turn;
    - which concrete VALUES were observed per fact_key (used by the
      contradiction detector to catch persona-value drift across turns).

The orchestrator appends one TurnEvent per turn to
SessionOrchestrator.turn_events. Consumers (contradiction detector,
future adversarial replayer) read the list at the end of a session and
never mutate the orchestrator state.
"""

from pydantic import BaseModel, Field


class TurnEvent(BaseModel):
    """One turn's worth of observable data downstream analysers care about."""

    turn_index: int = Field(ge=0, description="Zero-based index in the transcript.")
    speaker: str = Field(pattern="^(agent|persona)$")
    content: str
    # Fact keys that transitioned from 'not revealed' to 'revealed' on this
    # turn. Empty for agent turns and for persona turns that added nothing new.
    newly_revealed_fact_keys: list[str] = Field(default_factory=list)
    # Per-fact concrete VALUE observed in this turn's content. Populated when
    # a fact_key was detected in the persona reply — the value stored here is
    # the fact's canonical value at that time. Used to spot future
    # contradictions where the same key surfaces with a different value.
    observed_fact_values: dict[str, str] = Field(default_factory=dict)
