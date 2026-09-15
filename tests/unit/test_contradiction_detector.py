"""
Contradiction detector tests (B.4).

Two acceptance shapes to prove:

    - Synthetic session with 1 planted contradiction ("12 de março" at
      turn 3, "15 de março" at turn 6 for the same fact_key) → detector
      reports exactly 1 contradiction with the correct prior/new values.

    - Rate normalisation: contradictions_per_100_turns is computed from
      total turns (agent + persona) so long and short sessions are
      comparable in the M3 report.
"""

from civis.session.contradiction_detector import (
    ContradictionEvent,
    ContradictionReport,
    detect_contradictions,
)
from civis.session.turn_events import TurnEvent

# ---- helpers --------------------------------------------------------------

def _agent(turn_index: int, content: str) -> TurnEvent:
    return TurnEvent(turn_index=turn_index, speaker="agent", content=content)


def _persona(
    turn_index: int,
    content: str,
    observed: dict[str, str] | None = None,
    newly_revealed: list[str] | None = None,
) -> TurnEvent:
    return TurnEvent(
        turn_index=turn_index,
        speaker="persona",
        content=content,
        newly_revealed_fact_keys=newly_revealed or [],
        observed_fact_values=observed or {},
    )


# ---- happy path -----------------------------------------------------------

def test_no_events_returns_empty_report():
    report = detect_contradictions([])
    assert isinstance(report, ContradictionReport)
    assert report.total == 0
    assert report.contradictions_per_100_turns == 0.0


def test_single_persona_turn_with_one_observation_no_contradiction():
    events = [
        _agent(0, "Qual sua data de nascimento?"),
        _persona(1, "12 de março de 1954.", observed={"birth_date": "12 de março de 1954."}),
    ]
    report = detect_contradictions(events)
    assert report.total == 0
    assert report.total_turns == 2


def test_two_turns_same_value_is_not_contradiction():
    """Repeating the same value across turns is CONSISTENT, not a divergence."""
    events = [
        _agent(0, "Qual sua data de nascimento?"),
        _persona(1, "12 de março de 1954.", observed={"birth_date": "12 de março de 1954."}),
        _agent(2, "Confirma novamente a data?"),
        _persona(3, "12 de março de 1954.", observed={"birth_date": "12 de março de 1954."}),
    ]
    report = detect_contradictions(events)
    assert report.total == 0


# ---- the planted contradiction (acceptance criterion) --------------------

def test_detects_one_planted_contradiction_across_turns():
    """
    Persona says '12 de março' on turn 3 and '15 de março' on turn 6 for
    the same fact_key. Detector must return exactly 1 event with prior
    and new values set correctly.
    """
    events = [
        _agent(0, "Bom dia."),
        _persona(1, "Bom dia."),
        _agent(2, "Qual sua data de nascimento?"),
        _persona(
            3,
            "Nasci em 12 de março de 1954.",
            observed={"birth_date": "Nasci em 12 de março de 1954."},
        ),
        _agent(4, "Confirma a data por favor."),
        _persona(5, "Já disse, moço."),
        _agent(6, "Repete a data pra mim."),
        _persona(
            7,
            "Nasci em 15 de março de 1954.",
            observed={"birth_date": "Nasci em 15 de março de 1954."},
        ),
    ]
    report = detect_contradictions(events)
    assert report.total == 1
    event = report.contradictions[0]
    assert isinstance(event, ContradictionEvent)
    assert event.fact_key == "birth_date"
    assert event.turn_index == 7  # the DIVERGENT turn's index
    assert "12 de março" in event.prior_value
    assert "15 de março" in event.new_value


# ---- multiple contradictions ---------------------------------------------

def test_multiple_contradictions_all_reported():
    events = [
        _agent(0, "a"),
        _persona(1, "Iracema.", observed={"name": "Iracema."}),
        _agent(2, "b"),
        _persona(1, "Adalgisa.", observed={"name": "Adalgisa."}),
        _agent(3, "c"),
        _persona(4, "12/03.", observed={"birth_date": "12/03."}),
        _agent(5, "d"),
        _persona(6, "15/03.", observed={"birth_date": "15/03."}),
    ]
    report = detect_contradictions(events)
    assert report.total == 2
    keys = {e.fact_key for e in report.contradictions}
    assert keys == {"name", "birth_date"}


# ---- rate normalisation ---------------------------------------------------

def test_rate_per_100_turns_is_computed_from_total_events():
    events = []
    # 10 total events, 1 contradiction planted at the end.
    events.append(_agent(0, "a"))
    events.append(_persona(1, "12/03", observed={"birth_date": "12/03"}))
    for i in range(2, 9):
        events.append(_agent(i, "..."))
    events.append(_persona(9, "15/03", observed={"birth_date": "15/03"}))
    report = detect_contradictions(events)
    assert report.total == 1
    assert report.total_turns == 10
    # 1 / 10 * 100 = 10.0
    assert report.contradictions_per_100_turns == 10.0


def test_rate_is_zero_when_no_events():
    report = detect_contradictions([])
    assert report.contradictions_per_100_turns == 0.0


# ---- normalisation of observed values ------------------------------------

def test_whitespace_and_case_differences_are_not_contradictions():
    """
    The detector normalises whitespace + case before comparing so trivial
    formatting drift ('  12 de Março  ' vs '12 de março') is NOT counted
    as a contradiction. Real token-level differences still fire.
    """
    events = [
        _persona(0, "a", observed={"birth_date": "  12 de Março de 1954  "}),
        _persona(1, "b", observed={"birth_date": "12 de março de 1954"}),
    ]
    report = detect_contradictions(events)
    assert report.total == 0


def test_first_value_wins_and_prior_value_reflects_it():
    """When contradiction is spotted, prior_value is the FIRST value seen,
    not the value from the immediately preceding turn — the persona
    'committed' to its first answer."""
    events = [
        _persona(0, "a", observed={"birth_date": "1954"}),
        _persona(1, "b", observed={"birth_date": "1954"}),
        _persona(2, "c", observed={"birth_date": "1960"}),
    ]
    report = detect_contradictions(events)
    assert report.total == 1
    assert report.contradictions[0].prior_value == "1954"
    assert report.contradictions[0].new_value == "1960"
