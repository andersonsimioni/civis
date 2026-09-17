"""
Scenario loader tests.

The loader parses the YAML from data/scenarios/, validates it against
ScenarioFile (which wraps PersonaProfile) and offers a small helper to
resolve a bare scenario id into a path on disk.
"""

from pathlib import Path

import pytest

from civis.personas.base import PersonaKind
from civis.scenarios.categories import CANONICAL_CATEGORIES, FALLBACK_CATEGORY
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
    target = repo_root / "data" / "scenarios" / "certificate_duplicate_confused_v1.yaml"
    assert target.exists(), f"Example scenario missing at {target}"
    scenario, _ = load_scenario_from_path(target)
    assert scenario.scenario_id == "certificate_duplicate_confused_v1"
    assert scenario.persona.kind == PersonaKind.CONFUSED


# ---------------------------------------------------------------------------
# Onda 4 S4.1 — optional `category` field
# ---------------------------------------------------------------------------
#
# Rules under test:
#   1. A YAML without `category` still loads and falls back to "outros".
#   2. Every canonical value is accepted verbatim.
#   3. A non-canonical value raises ValueError at load time.
#   4. All shipping scenarios now declare a canonical category.


def test_scenario_defaults_category_to_outros_when_missing():
    """Retrocompat: a scenario YAML that never mentions `category` still
    loads and lands on the fallback bucket."""
    scenario = load_scenario_from_text(_MINIMAL_YAML)
    assert scenario.category == FALLBACK_CATEGORY  # "outros"


def test_scenario_accepts_explicit_category():
    """A YAML that declares `category: "casamento"` round-trips as-is."""
    yaml_with_category = (
        _MINIMAL_YAML.replace(
            'title: "Título de teste"',
            'title: "Título de teste"\ncategory: "casamento"',
        )
    )
    scenario = load_scenario_from_text(yaml_with_category)
    assert scenario.category == "casamento"


@pytest.mark.parametrize("value", CANONICAL_CATEGORIES)
def test_scenario_accepts_every_canonical_category(value: str):
    """The full closed set must load without raising."""
    yaml_text = _MINIMAL_YAML.replace(
        'title: "Título de teste"',
        f'title: "Título de teste"\ncategory: "{value}"',
    )
    scenario = load_scenario_from_text(yaml_text)
    assert scenario.category == value


def test_scenario_rejects_unknown_category():
    """A typo raises at load time — no silent mis-bucketing."""
    yaml_text = _MINIMAL_YAML.replace(
        'title: "Título de teste"',
        'title: "Título de teste"\ncategory: "typo_nao_existe"',
    )
    with pytest.raises(ValueError, match="Unknown scenario category"):
        load_scenario_from_text(yaml_text)


def test_all_shipping_scenarios_declare_category():
    """Every YAML currently under data/scenarios/ now carries a canonical
    category. Guards against regressions when a new file is added without
    the field or with a typo."""
    repo_root = Path(__file__).resolve().parents[2]
    scenarios_dir = repo_root / "data" / "scenarios"
    yaml_files = sorted(scenarios_dir.glob("*.yaml"))
    assert yaml_files, "no shipping scenarios found on disk"
    for path in yaml_files:
        scenario, _raw = load_scenario_from_path(path)
        assert scenario.category in CANONICAL_CATEGORIES, (
            f"{path.name} carries unknown category '{scenario.category}'"
        )
