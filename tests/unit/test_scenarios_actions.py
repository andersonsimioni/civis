"""
Tests for the Phase D+++ scenario-action catalog.

Covers three concerns:

    - Parsing shape: AgentAction / AgentActionCatalog accept the flat
      YAML layout defined in `data/scenarios/*.yaml` (D+++.1).
    - Validation: duplicate ids and `requires` that reference unknown
      persona fact keys are rejected at load time.
    - Shipped-scenarios contract: the three demo scenarios expose the
      button ids the web UI expects, so a rename here breaks the tests.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from civis.scenarios.actions import AgentAction, AgentActionCatalog
from civis.session.scenario import (
    load_scenario_from_path,
    load_scenario_from_text,
)

# ---------------------------------------------------------------------------
# Small YAML fragments — one persona with two facts, then a variable
# `available_actions` block. Keeps each test focused on one thing.
# ---------------------------------------------------------------------------

_BASE_PERSONA_YAML = """
scenario_id: "test_scn_v1"
title: "Cenário de teste"

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
    - key: "mother_name"
      value: "Maria das Graças Silva"
      is_secret: false

expected_agent_actions:
  - "Verificar identidade."
"""


def _yaml_with_actions(actions_block: str) -> str:
    """Concatenate the base persona YAML with a custom actions block."""
    return _BASE_PERSONA_YAML + "\n" + actions_block


# ---------------------------------------------------------------------------
# D+++.1.1 — AgentAction parses the minimal YAML shape
# ---------------------------------------------------------------------------


def test_agent_action_parses_minimal_yaml_fields() -> None:
    """id, label, description are all required and parse verbatim."""
    action = AgentAction.model_validate(
        {
            "id": "verify_identity",
            "label": "🔍 Verificar identidade",
            "description": "Solicita documento com foto.",
        }
    )
    assert action.id == "verify_identity"
    assert action.label.startswith("🔍")
    assert action.description == "Solicita documento com foto."


# ---------------------------------------------------------------------------
# D+++.1.2 — defaults: no requires, no document
# ---------------------------------------------------------------------------


def test_agent_action_defaults_empty_requires_and_no_document() -> None:
    """Omitted optional fields become empty list / None."""
    action = AgentAction.model_validate(
        {"id": "end", "label": "✅ Encerrar", "description": "Fecha."}
    )
    assert action.requires == []
    assert action.emits_document is None


# ---------------------------------------------------------------------------
# D+++.1.3 — AgentActionCatalog parses a YAML list
# ---------------------------------------------------------------------------


def test_agent_action_catalog_from_yaml_list() -> None:
    """The catalog wraps a list[AgentAction] and iterates in order."""
    catalog = AgentActionCatalog.model_validate(
        {
            "actions": [
                {"id": "a", "label": "A", "description": "d1"},
                {
                    "id": "b",
                    "label": "B",
                    "description": "d2",
                    "requires": ["birth_date"],
                    "emits_document": "birth_certificate",
                },
            ]
        }
    )
    assert len(catalog) == 2
    ids = [a.id for a in catalog]
    assert ids == ["a", "b"]
    assert catalog.by_id("b") is not None
    assert catalog.by_id("b").emits_document == "birth_certificate"
    assert catalog.by_id("missing") is None


# ---------------------------------------------------------------------------
# D+++.1.4 — retrocompat: a scenario without available_actions loads
# ---------------------------------------------------------------------------


def test_scenario_without_available_actions_still_loads() -> None:
    """
    Older YAMLs without an available_actions block must keep loading —
    the field defaults to an empty catalog.
    """
    scenario = load_scenario_from_text(_BASE_PERSONA_YAML)
    assert len(scenario.available_actions) == 0
    assert list(scenario.available_actions) == []


# ---------------------------------------------------------------------------
# D+++.1.5 — a scenario WITH available_actions surfaces them
# ---------------------------------------------------------------------------


def test_scenario_with_available_actions_loads_them() -> None:
    """Happy path: two actions parsed, one with document emission."""
    yaml_text = _yaml_with_actions(
        """
available_actions:
  - id: "verify_identity"
    label: "🔍 Verificar identidade"
    description: "Solicita documento com foto."
    requires: []
  - id: "issue_certificate_copy"
    label: "📄 Emitir 2ª via"
    description: "Emite segunda via."
    requires:
      - "birth_date"
      - "mother_name"
    emits_document: "birth_certificate"
"""
    )
    scenario = load_scenario_from_text(yaml_text)
    assert len(scenario.available_actions) == 2
    issue = scenario.available_actions.by_id("issue_certificate_copy")
    assert issue is not None
    assert issue.requires == ["birth_date", "mother_name"]
    assert issue.emits_document == "birth_certificate"


# ---------------------------------------------------------------------------
# D+++.1.6 — requires must reference real fact keys
# ---------------------------------------------------------------------------


def test_agent_action_requires_referring_to_missing_fact_key_raises() -> None:
    """
    A typo in `requires` would leave the button permanently disabled
    and the investor never sees the wow moment. Fail loud at load.
    """
    yaml_text = _yaml_with_actions(
        """
available_actions:
  - id: "issue_certificate_copy"
    label: "📄 Emitir"
    description: "Emite."
    requires:
      - "birth_date"
      - "cpf"  # typo — not in the persona facts above
    emits_document: "birth_certificate"
"""
    )
    with pytest.raises(ValidationError, match="unknown persona fact"):
        load_scenario_from_text(yaml_text)


# ---------------------------------------------------------------------------
# D+++.1.7 — duplicate ids inside the catalog are rejected
# ---------------------------------------------------------------------------


def test_agent_action_ids_must_be_unique_within_scenario() -> None:
    """
    Two actions with the same id would collide on the Streamlit button
    key. Catch it at load time, not on the demo floor.
    """
    yaml_text = _yaml_with_actions(
        """
available_actions:
  - id: "verify_identity"
    label: "A"
    description: "d"
  - id: "verify_identity"
    label: "B"
    description: "d"
"""
    )
    with pytest.raises(ValidationError, match="Duplicate action ids"):
        load_scenario_from_text(yaml_text)


# ---------------------------------------------------------------------------
# D+++.1.8 — the three shipped scenarios expose the expected action ids
# ---------------------------------------------------------------------------


_EXPECTED_ACTION_IDS: dict[str, tuple[str, ...]] = {
    "certificate_duplicate_confused_v1": (
        "verify_identity",
        "explain_procedure",
        "issue_certificate_copy",
        "end_service",
    ),
    "rg_urgent_aggressive_v1": (
        "verify_identity",
        "de_escalate",
        "issue_rg_second_copy",
        "end_service",
    ),
    "certificate_thirdparty_fraudster_v1": (
        "verify_identity",
        "consult_supervisor",
        "refuse_procedure",
        "issue_certificate_thirdparty",
        "end_service",
    ),
}


@pytest.mark.parametrize("scenario_id,expected_ids", list(_EXPECTED_ACTION_IDS.items()))
def test_shipped_scenarios_expose_expected_action_ids(
    scenario_id: str, expected_ids: tuple[str, ...]
) -> None:
    """
    Contract test: the web UI reads action ids by hand-typed name (button
    keys, execution handlers). A rename in the YAML that isn't mirrored
    in the code path breaks the demo silently — this test breaks first.
    """
    repo_root = Path(__file__).resolve().parents[2]
    scenario_path = repo_root / "data" / "scenarios" / f"{scenario_id}.yaml"
    assert scenario_path.exists(), f"shipped scenario missing: {scenario_path}"

    scenario, _ = load_scenario_from_path(scenario_path)
    got_ids = tuple(a.id for a in scenario.available_actions)
    assert got_ids == expected_ids
