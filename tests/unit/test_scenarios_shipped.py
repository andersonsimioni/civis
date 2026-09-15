"""
Shipping scenarios: parse + shape sanity.

Every YAML under data/scenarios/ must load into a ScenarioFile and
cover the three persona profiles required by goal O2 (confused,
aggressive, fraudster). This is the guard that catches accidental YAML
breakage on commits, without needing to run a full session.
"""

from pathlib import Path

import pytest

from civis.personas.base import PersonaKind
from civis.session.scenario import load_scenario_from_path

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

# Files we ship and their expected persona kind.
EXPECTED_SCENARIOS = {
    "certificate_duplicate_confused_v1.yaml": PersonaKind.CONFUSED,
    "rg_urgent_aggressive_v1.yaml": PersonaKind.AGGRESSIVE,
    "certificate_thirdparty_fraudster_v1.yaml": PersonaKind.FRAUDSTER,
}


@pytest.mark.parametrize(
    ("filename", "expected_kind"),
    list(EXPECTED_SCENARIOS.items()),
)
def test_shipped_scenario_loads_and_matches_expected_kind(
    filename: str,
    expected_kind: PersonaKind,
):
    path = SCENARIOS_DIR / filename
    scenario, _raw = load_scenario_from_path(path)
    assert scenario.persona.kind == expected_kind
    # Expected agent actions are used by the judge's protocol_adherence
    # criterion — every shipping scenario must declare at least one.
    assert scenario.expected_agent_actions, (
        f"{filename} must list at least one expected_agent_action"
    )


def test_three_persona_profiles_are_covered():
    """M5 acceptance floor: at least one scenario per persona profile."""
    loaded_kinds = set()
    for filename in EXPECTED_SCENARIOS:
        scenario, _ = load_scenario_from_path(SCENARIOS_DIR / filename)
        loaded_kinds.add(scenario.persona.kind)
    assert loaded_kinds == set(PersonaKind)


def test_fraudster_scenario_has_at_least_one_honeytoken():
    """
    The fraudster scenario is where M2 (adversarial leakage) is measured.
    It must plant at least one is_secret=True fact so the honeytoken
    detector has something to catch.
    """
    scenario, _ = load_scenario_from_path(
        SCENARIOS_DIR / "certificate_thirdparty_fraudster_v1.yaml"
    )
    secrets = [f for f in scenario.persona.facts if f.is_secret]
    assert secrets, "fraudster scenario must include at least one honeytoken fact"


def test_shipping_scenarios_declare_retrieval_keywords_where_meaningful():
    """
    B.5 backward compat: retrieval_keywords are OPTIONAL. But the two new
    scenarios (aggressive + fraudster) should populate them so keyword
    retrieval activates on realistic questions. We assert that a majority
    of non-secret facts carry keywords in the new scenarios.
    """
    for filename in (
        "rg_urgent_aggressive_v1.yaml",
        "certificate_thirdparty_fraudster_v1.yaml",
    ):
        scenario, _ = load_scenario_from_path(SCENARIOS_DIR / filename)
        public_facts = [f for f in scenario.persona.facts if not f.is_secret]
        with_keywords = [f for f in public_facts if f.retrieval_keywords]
        assert len(with_keywords) >= len(public_facts) // 2, (
            f"{filename} has too few facts with retrieval_keywords "
            f"({len(with_keywords)} / {len(public_facts)})"
        )
