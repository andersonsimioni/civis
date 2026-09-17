"""
Persona data contracts.

A PersonaProfile is the static definition of a character type (loaded from YAML).
A PersonaState is the runtime state during a session: which facts the persona knows,
which phase it's in, how it feels right now.

Structured state + selective fact retrieval is the mechanism against factual
contradictions across dozens of turns (goal O2).
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from civis.fsm.states import EmotionalState, Phase
from civis.personas.accents import RegionalAccent


class PersonaKind(StrEnum):
    """
    The three profiles required by O2.

    CONFUSED    - legitimate citizen who does not understand the process
    AGGRESSIVE  - legitimate citizen who is impatient / rude
    FRAUDSTER   - malicious actor attempting social engineering
    """

    CONFUSED = "confused"
    AGGRESSIVE = "aggressive"
    FRAUDSTER = "fraudster"


class PersonaFact(BaseModel):
    """
    A single scripted fact the persona 'knows' about the scenario.

    Facts are retrieved selectively during LLM prompt construction, not dumped
    whole into context. That selectivity is what keeps the persona consistent
    across many turns.

    retrieval_keywords is the B.5 trigger: when the last agent message
    contains any of these keywords (case-insensitive), the fact is
    inserted into the persona prompt. When empty, the fact only appears
    in the prompt after it has been revealed (or via the default
    background/goal + recent-history fallback).
    """

    key: str = Field(description="Stable identifier for retrieval (e.g. 'birth_date').")
    value: str = Field(description="The fact value in natural language (pt-BR).")
    is_secret: bool = Field(
        default=False,
        description=(
            "If True, the persona must not volunteer this fact. "
            "Honeytokens (see security model) are stored as secret facts."
        ),
    )
    retrieval_keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Keywords/phrases whose presence in the agent's last message "
            "activates this fact for retrieval (case-insensitive). Empty "
            "means the fact is not keyword-triggered — it only surfaces "
            "once already revealed, or via the fallback."
        ),
    )
    revealed_patterns: list[str] = Field(
        default_factory=list,
        description=(
            "Optional escape hatch for the 'did the persona confirm this "
            "fact?' matcher. When set, ANY of these strings (compared "
            "against the normalized persona reply — case- and accent-"
            "insensitive) marks the fact as revealed. Use this when the "
            "built-in matchers (normalized substring, date variants, "
            "multi-word overlap) miss a phrasing your persona actually "
            "produces. Leave empty for the default heuristics."
        ),
    )


class PersonaProfile(BaseModel):
    """
    Static definition of a persona type, loaded from a scenario YAML file.
    Immutable during a session.
    """

    kind: PersonaKind
    name: str = Field(description="Display name (pt-BR).")
    background: str = Field(description="One-paragraph biography in pt-BR.")
    goal: str = Field(description="What the persona wants from this interaction (pt-BR).")
    initial_emotion: EmotionalState = EmotionalState.CALM
    facts: list[PersonaFact] = Field(default_factory=list)
    # Onda-1 F1.1: optional Brazilian regional accent. When set, the persona
    # prompt appends a `# Sotaque` block steering the LLM toward the region's
    # slang. When None (default), the prompt is byte-identical to the
    # pre-onda-1 output — full backwards compat for shipping scenarios.
    regional_accent: RegionalAccent | None = Field(
        default=None,
        description=(
            "Optional Brazilian regional accent (nordeste, sul, sudeste_sp, "
            "sudeste_rj, sudeste_mg, norte, centro_oeste). Absent means "
            "neutral pt-BR — the default."
        ),
    )


class PersonaState(BaseModel):
    """
    Runtime state of a persona during an ongoing session.
    Mutated by the FSM engine on every turn.
    """

    profile: PersonaProfile
    phase: Phase = Phase.OPENING
    emotion: EmotionalState = EmotionalState.CALM
    turn_count: int = 0
    revealed_fact_keys: set[str] = Field(
        default_factory=set,
        description="Facts already disclosed to the agent (avoid re-disclosure churn).",
    )
