"""
Tests for the Onda 2 M2.1 HiddenAgenda scenario extension.

Covers three concerns (matching the task's acceptance list):

    - Parsing shape: ``HiddenAgenda`` accepts the flat YAML layout
      described in the task text.
    - Optionality: a scenario without the block still loads and
      exposes ``hidden_agenda = None`` (so the reveal card is skipped
      on the verdict screen).
    - Cross-validation: a criterion referencing an action id absent
      from ``available_actions`` is rejected at load time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from civis.scenarios.hidden_agenda import HiddenAgenda, SuccessCriterion
from civis.session.scenario import load_scenario_from_text

# Persona + one action so the criterion has something valid to point at.
_BASE_SCENARIO_YAML = """
scenario_id: "hidden_agenda_test_v1"
title: "Cenário de teste — mystery shopper"

persona:
  kind: "confused"
  name: "Fulana"
  background: |
    Cidadã fictícia.
  goal: |
    Obter um documento.
  initial_emotion: "anxious"
  facts:
    - key: "birth_date"
      value: "12 de março de 1954"
      is_secret: false

expected_agent_actions:
  - "Verificar identidade."

available_actions:
  - id: "verify_identity"
    label: "Verificar identidade"
    description: "Pede documento com foto."
    requires: []
  - id: "issue_certificate_copy"
    label: "Emitir segunda via"
    description: "Emite a segunda via da certidão."
    requires: []
"""


# ---------------------------------------------------------------------------
# Parsing + optionality
# ---------------------------------------------------------------------------


def test_scenario_without_hidden_agenda_keeps_field_as_none() -> None:
    """No block → ``hidden_agenda`` stays None; the reveal card will
    silently not render on the verdict screen."""
    scenario = load_scenario_from_text(_BASE_SCENARIO_YAML)
    assert scenario.hidden_agenda is None


def test_scenario_with_hidden_agenda_parses_all_fields() -> None:
    """The full YAML block from the task text loads into a populated
    HiddenAgenda with a single ordering criterion."""
    yaml_text = _BASE_SCENARIO_YAML + """
hidden_agenda:
  test_id: "id_check_before_issue"
  description: |
    Auditor testa se atendente pede documento com foto antes de emitir
    2ª via.
  success_criteria:
    - action_required: "verify_identity"
      before_action: "issue_certificate_copy"
  reveal_message: |
    Meu nome é Fulana, sou auditor(a) do Corregedoria Regional de
    Cartórios. Este atendimento foi um teste de conformidade. Você
    [passou/falhou] no critério: pedir documento com foto antes de
    emitir a segunda via.
"""
    scenario = load_scenario_from_text(yaml_text)

    assert scenario.hidden_agenda is not None
    agenda = scenario.hidden_agenda
    assert agenda.test_id == "id_check_before_issue"
    assert "auditor testa" in agenda.description.lower()
    assert len(agenda.success_criteria) == 1

    criterion = agenda.success_criteria[0]
    assert isinstance(criterion, SuccessCriterion)
    assert criterion.action_required == "verify_identity"
    assert criterion.before_action == "issue_certificate_copy"

    # Reveal message keeps placeholders verbatim so the UI can render
    # them literally on the card (Anderson can wire real names later).
    assert "[passou/falhou]" in agenda.reveal_message


# ---------------------------------------------------------------------------
# Cross-validation with available_actions
# ---------------------------------------------------------------------------


def test_hidden_agenda_rejects_unknown_action_id() -> None:
    """A criterion pointing at an action id not declared in the scenario's
    ``available_actions`` must fail at load time."""
    yaml_text = _BASE_SCENARIO_YAML + """
hidden_agenda:
  test_id: "typo_test"
  description: "descrição"
  success_criteria:
    - action_required: "verify_identity"
      before_action: "issue_certificate_typo"
  reveal_message: "reveal"
"""
    with pytest.raises(ValueError, match="unknown action ids"):
        load_scenario_from_text(yaml_text)


def test_hidden_agenda_direct_model_accepts_minimal_shape() -> None:
    """The Pydantic model itself validates independently of the
    ScenarioFile — needed for tests that build fixture agendas without a
    full YAML scenario around them."""
    agenda = HiddenAgenda(
        test_id="t1",
        description="descrição",
        success_criteria=[
            SuccessCriterion(
                action_required="a", before_action="b"
            )
        ],
        reveal_message="reveal",
    )
    assert agenda.test_id == "t1"
    assert agenda.success_criteria[0].action_required == "a"


def test_hidden_agenda_rejects_empty_test_id() -> None:
    """Empty strings on the required fields must fail — an empty test_id
    breaks downstream aggregation across batches."""
    with pytest.raises(ValidationError):
        HiddenAgenda(
            test_id="",
            description="descrição",
            success_criteria=[],
            reveal_message="reveal",
        )
