"""
Onda-1 F1.3 scenario variants: three accent-flavoured copies of the
shipping scenarios must load, carry the expected accent, and render a
persona prompt with the matching `# Sotaque` block.

We keep the assertions minimal on purpose — the neutral scenarios are
covered by test_scenarios_shipped.py; the accent block itself by
test_prompts_accents.py. Here we only prove the wiring between YAML
and the prompt path is intact for the new files.
"""

from pathlib import Path

import pytest

from civis.personas.accents import RegionalAccent
from civis.personas.base import PersonaKind, PersonaState
from civis.prompts.accents import ACCENT_DESCRIPTIONS
from civis.prompts.persona import build_persona_prompt
from civis.session.scenario import load_scenario_from_path

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

# (filename, expected persona kind, expected accent).
ACCENT_VARIANTS = [
    (
        "certificate_duplicate_nordeste_v1.yaml",
        PersonaKind.CONFUSED,
        RegionalAccent.NORDESTE,
    ),
    (
        "rg_urgent_sul_v1.yaml",
        PersonaKind.AGGRESSIVE,
        RegionalAccent.SUL,
    ),
    (
        "certificate_thirdparty_rj_v1.yaml",
        PersonaKind.FRAUDSTER,
        RegionalAccent.SUDESTE_RJ,
    ),
]


@pytest.mark.parametrize(
    ("filename", "expected_kind", "expected_accent"),
    ACCENT_VARIANTS,
)
def test_accent_variant_scenario_loads(filename, expected_kind, expected_accent):
    """Each variant YAML parses and carries the right persona kind + accent."""
    scenario, _raw = load_scenario_from_path(SCENARIOS_DIR / filename)
    assert scenario.persona.kind == expected_kind
    assert scenario.persona.regional_accent == expected_accent
    # We reuse the shipping actions catalog, so at least one action must exist.
    assert scenario.available_actions.actions


@pytest.mark.parametrize(
    ("filename", "_kind", "expected_accent"),
    ACCENT_VARIANTS,
)
def test_accent_variant_prompt_carries_sotaque_block(
    filename,
    _kind,
    expected_accent,
):
    """The generated persona prompt for each variant carries `# Sotaque` + the right text."""
    scenario, _raw = load_scenario_from_path(SCENARIOS_DIR / filename)
    state = PersonaState(
        profile=scenario.persona,
        emotion=scenario.persona.initial_emotion,
    )

    system, _ = build_persona_prompt(
        state=state,
        history=[],
        last_agent_message="bom dia, em que posso ajudar?",
    )

    assert "# Sotaque" in system
    assert ACCENT_DESCRIPTIONS[expected_accent] in system
