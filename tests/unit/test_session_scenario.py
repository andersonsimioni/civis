"""
Scenario loader tests.

The loader parses the YAML from data/scenarios/, validates it against
ScenarioFile (which wraps PersonaProfile) and offers a small helper to
resolve a bare scenario id into a path on disk.
"""

from pathlib import Path

import pytest

from civis.personas.base import PersonaKind
from civis.session.scenario import (
    load_scenario_from_path,
    load_scenario_from_text,
    resolve_scenario_path,
)

_MINIMAL_YAML = """
scenario_id: "test_confused_v1"
title: "Título de teste"

persona:
  kind: "confused"
  name: "Dona Fulana"
  background: |
    Cidadã fictícia para teste.
  goal: |
    Obter um documento.
  initial_emotion: "anxious"
  facts:
    - key: "birth_date"
      value: "12 de março de 1954"
      is_secret: false

expected_agent_actions:
  - "Verificar identidade da cidadã."
"""


def test_load_scenario_from_text_parses_all_fields():
    scenario = load_scenario_from_text(_MINIMAL_YAML)
    assert scenario.scenario_id == "test_confused_v1"
    assert scenario.title == "Título de teste"
    assert scenario.persona.kind == PersonaKind.CONFUSED
    assert scenario.persona.name == "Dona Fulana"
    assert len(scenario.persona.facts) == 1
    assert scenario.expected_agent_actions == ["Verificar identidade da cidadã."]


def test_load_scenario_from_text_rejects_non_mapping():
    with pytest.raises(ValueError, match="mapping at the top level"):
        load_scenario_from_text("- just\n- a\n- list\n")


def test_load_scenario_from_path_returns_raw_text_for_hashing(tmp_path: Path):
    target = tmp_path / "s.yaml"
    target.write_text(_MINIMAL_YAML, encoding="utf-8")

    scenario, raw = load_scenario_from_path(target)
    assert scenario.scenario_id == "test_confused_v1"
    # Raw text round-trips exactly (needed so drift detection is stable).
    assert raw == _MINIMAL_YAML


def test_resolve_scenario_path_accepts_direct_path(tmp_path: Path):
    target = tmp_path / "custom.yaml"
    target.write_text(_MINIMAL_YAML, encoding="utf-8")
    assert resolve_scenario_path(str(target), scenarios_dir=tmp_path) == target


def test_resolve_scenario_path_accepts_bare_id(tmp_path: Path):
    target = tmp_path / "test_confused_v1.yaml"
    target.write_text(_MINIMAL_YAML, encoding="utf-8")
    assert (
        resolve_scenario_path("test_confused_v1", scenarios_dir=tmp_path)
        == target
    )


def test_resolve_scenario_path_raises_for_unknown_ref(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="resolve"):
        resolve_scenario_path("nonexistent", scenarios_dir=tmp_path)


def test_load_shipped_example_scenario():
    """The example scenario shipped with the repo must load cleanly —
    if it stops loading, every downstream test breaks."""
    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "data" / "scenarios" / "example_v1.yaml"
    assert target.exists(), f"Example scenario missing at {target}"
    scenario, _ = load_scenario_from_path(target)
    assert scenario.scenario_id == "certificate_duplicate_confused_v1"
    assert scenario.persona.kind == PersonaKind.CONFUSED
