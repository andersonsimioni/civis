"""
Onda 4 S4.4 — automatic discovery of scenario YAMLs.

The landing needs a list of scenarios without hardcoding filenames.
Discovery walks ``data/scenarios/``, loads every valid YAML into a
``ScenarioCard`` and skips broken files with a warning. Missing
``card_*`` fields fall back to persona-kind-specific defaults so an
unadorned YAML still shows on the landing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from civis.personas.base import PersonaKind
from civis.scenarios.categories import (
    CATEGORY_ICONS,
    FALLBACK_CATEGORY,
)
from civis.scenarios.discovery import (
    ScenarioCard,
    build_card_metadata,
    discover_scenarios,
)
from civis.session.scenario import load_scenario_from_text

# Minimal valid YAML — reused across tests. The persona kind flag flips
# per test via .replace(...).
_MINIMAL_YAML_CONFUSED = """
scenario_id: "disc_confused_v1"
title: "Cenário de discovery — confused"
category: "casamento"

persona:
  kind: "confused"
  name: "Dona Teste"
  background: |
    Cidadã fictícia.
  goal: |
    Objetivo do teste.
  initial_emotion: "anxious"
  facts:
    - key: "test_key"
      value: "valor"
      is_secret: false
      retrieval_keywords: ["teste"]

expected_agent_actions:
  - "Verificar identidade."
"""


# ---------------------------------------------------------------------------
# discover_scenarios
# ---------------------------------------------------------------------------


def test_discover_scenarios_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    """A caller pointing at a bare checkout does not get an exception —
    just an empty list. Streamlit will render the empty state."""
    missing = tmp_path / "does_not_exist"
    assert not missing.exists()
    cards = discover_scenarios(missing)
    assert cards == []


def test_discover_scenarios_returns_empty_for_empty_directory(tmp_path: Path) -> None:
    """Directory exists but has no YAMLs — returns []."""
    (tmp_path / "sub").mkdir()
    cards = discover_scenarios(tmp_path / "sub")
    assert cards == []


def test_discover_scenarios_returns_one_card_per_valid_yaml(tmp_path: Path) -> None:
    """Three valid YAMLs → three cards, sorted by scenario_id."""
    for scenario_id in ("aaa_v1", "ccc_v1", "bbb_v1"):
        text = _MINIMAL_YAML_CONFUSED.replace("disc_confused_v1", scenario_id)
        (tmp_path / f"{scenario_id}.yaml").write_text(text, encoding="utf-8")

    cards = discover_scenarios(tmp_path)
    assert [c.scenario_id for c in cards] == ["aaa_v1", "bbb_v1", "ccc_v1"]
    assert all(isinstance(c, ScenarioCard) for c in cards)


def test_discover_scenarios_skips_broken_yaml_but_keeps_valid_ones(
    tmp_path: Path,
    caplog,
) -> None:
    """Corrupt file must not stop the landing — just a warning + skip."""
    (tmp_path / "good.yaml").write_text(_MINIMAL_YAML_CONFUSED, encoding="utf-8")
    (tmp_path / "broken.yaml").write_text(
        "this: is: not: valid: yaml: [\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING, logger="civis.scenarios.discovery"):
        cards = discover_scenarios(tmp_path)

    # Only the good scenario survived.
    scenario_ids = [c.scenario_id for c in cards]
    assert scenario_ids == ["disc_confused_v1"]
    # And the broken one was logged.
    assert any("broken.yaml" in record.message for record in caplog.records)


def test_discover_scenarios_reads_shipped_directory() -> None:
    """The real ``data/scenarios/`` directory yields a positive count
    after the Onda-4 additions (7 shipping + 8 new + 3 accent variants
    + 1 audit → at least 12 cards)."""
    repo_root = Path(__file__).resolve().parents[2]
    scenarios_dir = repo_root / "data" / "scenarios"

    cards = discover_scenarios(scenarios_dir)
    assert len(cards) >= 12, (
        f"expected >=12 scenarios after Onda 4, discovered {len(cards)}"
    )
    # Every card must at minimum have a non-empty pitch and icon.
    for card in cards:
        assert card.pitch, f"{card.scenario_id} rendered without pitch"
        assert card.icon, f"{card.scenario_id} rendered without icon"


# ---------------------------------------------------------------------------
# build_card_metadata — fallbacks
# ---------------------------------------------------------------------------


def test_card_metadata_uses_explicit_fields_when_present() -> None:
    """When every ``card_*`` is set, all of them are copied verbatim."""
    yaml_text = _MINIMAL_YAML_CONFUSED + """
card_pitch: "Pitch explícito"
card_what_happens: "Como corre explícito"
card_watch_for: "Observação explícita"
card_icon: "🎯"
"""
    scenario = load_scenario_from_text(yaml_text)
    card = build_card_metadata(scenario)

    assert card.pitch == "Pitch explícito"
    assert card.what_happens == "Como corre explícito"
    assert card.watch_for == "Observação explícita"
    assert card.icon == "🎯"


def test_card_metadata_falls_back_when_fields_missing() -> None:
    """Base YAML omits every ``card_*`` — every field must resolve via
    a persona-kind- or category-driven default and stay non-empty."""
    scenario = load_scenario_from_text(_MINIMAL_YAML_CONFUSED)
    card = build_card_metadata(scenario)

    # Pitch falls back to the title.
    assert card.pitch == "Cenário de discovery — confused"
    # what_happens / watch_for come from persona-kind fallbacks.
    assert card.what_happens
    assert card.watch_for
    # Icon comes from the category (casamento -> 🤝).
    assert card.icon == CATEGORY_ICONS["casamento"]
    # Difficulty and persona label filled from the kind.
    assert card.difficulty == "Fácil"
    assert card.persona_label == "Cidadã confusa"


def test_card_metadata_icon_falls_back_to_persona_kind_when_category_is_outros() -> None:
    """When category is ``outros`` AND ``card_icon`` is absent, the icon
    escapes the generic folder emoji by falling back to a persona icon."""
    yaml_text = _MINIMAL_YAML_CONFUSED.replace(
        'category: "casamento"', 'category: "outros"'
    )
    scenario = load_scenario_from_text(yaml_text)
    # Ensure the fallback category is what we expect before continuing.
    assert scenario.category == FALLBACK_CATEGORY
    card = build_card_metadata(scenario)
    # The persona-kind fallback for confused is 🧓 — not the generic 📂.
    assert card.icon == "🧓"


def test_card_metadata_handles_every_persona_kind() -> None:
    """Building a card for each PersonaKind must always yield non-empty
    fallback copy, so no shipping scenario can produce a blank card."""
    for kind in PersonaKind:
        yaml_text = _MINIMAL_YAML_CONFUSED.replace(
            'kind: "confused"', f'kind: "{kind.value}"'
        )
        scenario = load_scenario_from_text(yaml_text)
        card = build_card_metadata(scenario)
        assert card.persona_kind == kind
        assert card.what_happens, f"empty what_happens for {kind}"
        assert card.watch_for, f"empty watch_for for {kind}"
        assert card.icon, f"empty icon for {kind}"
