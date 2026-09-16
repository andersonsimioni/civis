"""
Onda 2 M2.2 — shipping contract for the mystery-shopper scenario.

Two guarantees the file must uphold every commit:

    - It parses via ``load_scenario_from_path`` and exposes a fully
      populated ``hidden_agenda`` block.
    - The persona prompt built from this scenario NEVER contains the
      words that would give the audit away. This is the fence that
      keeps the LLM from turning the mystery shopper into a courtesy
      call.
"""

from __future__ import annotations

from pathlib import Path

from civis.fsm.states import EmotionalState, Phase
from civis.personas.base import PersonaState
from civis.prompts.persona import build_persona_prompt
from civis.session.scenario import load_scenario_from_path

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "audit_certificate_confused_v1.yaml"
)


def test_audit_scenario_loads_and_carries_hidden_agenda() -> None:
    """Sanity contract: the file loads and the mystery-shopper block
    is fully populated with the criterion the M2.3 evaluator will
    consume."""
    scenario, _raw = load_scenario_from_path(_SCENARIO_PATH)
    assert scenario.scenario_id == "audit_certificate_confused_v1"
    assert scenario.hidden_agenda is not None

    agenda = scenario.hidden_agenda
    assert agenda.test_id == "id_check_before_issue"
    assert len(agenda.success_criteria) == 1

    criterion = agenda.success_criteria[0]
    assert criterion.action_required == "verify_identity"
    assert criterion.before_action == "issue_certificate_copy"


def test_persona_prompt_does_not_reveal_the_audit() -> None:
    """
    The mystery-shopper trick only works if the persona LLM never sees
    the words "auditor" / "auditoria" / "conformidade" in its prompt.
    We build the full persona prompt and assert none of them appear —
    if this test goes red, the persona will out itself mid-chat and the
    whole feature collapses.
    """
    scenario, _raw = load_scenario_from_path(_SCENARIO_PATH)
    state = PersonaState(
        profile=scenario.persona,
        phase=Phase.OPENING,
        emotion=EmotionalState.ANXIOUS,
    )

    system_prompt, user_prompt = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="Bom dia, como posso ajudar?",
    )

    combined = (system_prompt + "\n" + user_prompt).lower()
    forbidden = ["auditor", "auditoria", "conformidade", "corregedoria", "teste de conformidade"]
    leaked = [w for w in forbidden if w in combined]
    assert not leaked, f"persona prompt leaked audit vocabulary: {leaked}"
