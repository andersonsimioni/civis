"""
Contradiction detector (metric M3).

The persona LLM sometimes contradicts itself across turns (says "12 de
março de 1954" at turn 3 and "15 de março de 1954" at turn 6 for the
same birth_date fact). This module compares the fact values observed in
each turn against previous observations and flags divergences.

Metric shape:
    - Total contradictions in the session.
    - Contradictions per 100 turns, so sessions of different lengths are
      comparable. Turns here means ALL turns (agent + persona), matching
      the "turnos" unit used elsewhere in CIVIS docs.

Design notes:
    - The detector consumes TurnEvent records produced by the session
      orchestrator on every turn. It doesn't re-run substring detection
      — that's the orchestrator's job; here we just diff observed
      values across turns.
    - We track by fact_key, not by value. A fact revealed once is
      "locked in" to whatever value first appeared; any later turn that
      surfaces a DIFFERENT value for that key is a contradiction.
"""

from pydantic import BaseModel, Field

from civis.session.turn_events import TurnEvent


class ContradictionEvent(BaseModel):
    """
    One contradiction observation.

    turn_index      Zero-based index of the turn where the divergent value
                    appeared (persona turn).
    fact_key        The scenario fact whose value diverged.
    prior_value     Value first observed for this fact_key.
    new_value       Value observed at turn_index.
    """

    turn_index: int = Field(ge=0)
    fact_key: str
    prior_value: str
    new_value: str


class ContradictionReport(BaseModel):
    """Aggregate report for one session."""

    contradictions: list[ContradictionEvent] = Field(default_factory=list)
    total_turns: int = Field(ge=0)

    @property
    def total(self) -> int:
        """Number of contradictions observed."""
        return len(self.contradictions)

    @property
    def contradictions_per_100_turns(self) -> float:
        """
        Rate normalised to 100 turns. Returns 0.0 when total_turns is 0
        (empty session) — a rate is undefined but 0 is the sensible
        default for aggregation.
        """
        if self.total_turns <= 0:
            return 0.0
        return 100.0 * self.total / self.total_turns


def detect_contradictions(turn_events: list[TurnEvent]) -> ContradictionReport:
    """
    Walk the turn events and return a ContradictionReport.

    Algorithm:
        1. Maintain a dict {fact_key: (first_turn_index, first_value)}.
        2. For each persona turn, look at observed_fact_values (a
           mapping produced by the orchestrator).
        3. If a fact_key is already in the dict AND the new value differs
           from the prior value, record a ContradictionEvent.
        4. Otherwise, keep the first value as the canonical one (we do
           NOT overwrite — the persona 'committed' to its first answer).

    total_turns counts ALL turn events (agent + persona), matching how
    the study protocol talks about "turnos".
    """
    seen: dict[str, tuple[int, str]] = {}
    contradictions: list[ContradictionEvent] = []

    for event in turn_events:
        if not event.observed_fact_values:
            continue
        for fact_key, new_value in event.observed_fact_values.items():
            if fact_key in seen:
                _, prior_value = seen[fact_key]
                if _normalise(new_value) != _normalise(prior_value):
                    contradictions.append(
                        ContradictionEvent(
                            turn_index=event.turn_index,
                            fact_key=fact_key,
                            prior_value=prior_value,
                            new_value=new_value,
                        )
                    )
            else:
                seen[fact_key] = (event.turn_index, new_value)

    return ContradictionReport(
        contradictions=contradictions,
        total_turns=len(turn_events),
    )


def _normalise(value: str) -> str:
    """
    Case-insensitive, whitespace-tolerant comparison so "12 de março"
    and " 12 de Março " count as the SAME value, not a contradiction.
    Difference at token level ("12 de março" vs "15 de março") still
    fires because the tokens themselves differ.
    """
    return " ".join(value.strip().lower().split())
