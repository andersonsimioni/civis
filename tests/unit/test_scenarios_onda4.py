"""
Onda 4 S4.2 — the 8 new scenarios introduced this wave.

Each YAML file exercises a different registry-office scope. We assert
on file existence, persona kind, category, retrieval_keywords coverage
and the presence of the optional ``card_*`` fields authors are expected
to populate (T3 later hooks these into the discovery layer, but the raw
text already carries them so nothing breaks when the field is wired up).

Wave scope from the request:
    8 scenarios covering 8 distinct categories, with a mix of persona
    profiles. The prescribed filenames encode 4 confused, 3 aggressive
    and 1 fraudster — the abstract "3/3/2" summary in the request text
    conflicts with its own file list, so we follow the file names as
    authoritative (they carry the persona kind explicitly).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from civis.personas.base import PersonaKind
from civis.scenarios.categories import CANONICAL_CATEGORIES
from civis.session.scenario import load_scenario_from_path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIOS_DIR = _REPO_ROOT / "data" / "scenarios"

# (filename, expected persona kind, expected category).
# One row per Onda-4 scenario. If a row is added, add the YAML file too
# — the parametrized test will demand it.
NEW_SCENARIOS: list[tuple[str, PersonaKind, str]] = [
    (
        "casamento_habilitacao_confused_v1.yaml",
        PersonaKind.CONFUSED,
        "casamento",
    ),
    (
        "divorcio_consensual_aggressive_v1.yaml",
        PersonaKind.AGGRESSIVE,
        "divorcio",
    ),
    (
        "obito_tardio_confused_v1.yaml",
        PersonaKind.CONFUSED,
        "obito",
    ),
    (
        "reconhecimento_paternidade_confused_v1.yaml",
        PersonaKind.CONFUSED,
        "reconhecimento_paternidade",
    ),
    (
        "alteracao_nome_social_aggressive_v1.yaml",
        PersonaKind.AGGRESSIVE,
        "alteracao_nome",
    ),
    (
        "uniao_estavel_confused_v1.yaml",
        PersonaKind.CONFUSED,
        "uniao_estavel",
    ),
    (
        "certidao_terceiro_fraudster_v1.yaml",
        PersonaKind.FRAUDSTER,
        "outros",
    ),
    (
        "averbacao_divorcio_exterior_aggressive_v1.yaml",
        PersonaKind.AGGRESSIVE,
        "averbacao",
    ),
]


@pytest.mark.parametrize(
    ("filename", "expected_kind", "expected_category"),
    NEW_SCENARIOS,
)
def test_new_scenario_loads_with_expected_persona_and_category(
    filename: str,
    expected_kind: PersonaKind,
    expected_category: str,
) -> None:
    """Every Onda-4 YAML parses, hits the right persona kind and lands
    in the expected canonical category bucket."""
    path = _SCENARIOS_DIR / filename
    assert path.exists(), f"scenario file missing: {path}"
    scenario, _raw = load_scenario_from_path(path)
    assert scenario.persona.kind == expected_kind
    assert scenario.category == expected_category
    assert scenario.category in CANONICAL_CATEGORIES


@pytest.mark.parametrize(
    ("filename", "_kind", "_category"),
    NEW_SCENARIOS,
)
def test_new_scenario_declares_expected_agent_actions_and_available_actions(
    filename: str,
    _kind: PersonaKind,
    _category: str,
) -> None:
    """Each scenario ships with at least one expected_agent_actions
    entry (feeds the judge rubric) and at least one clickable action
    (feeds the web UI)."""
    scenario, _raw = load_scenario_from_path(_SCENARIOS_DIR / filename)
    assert scenario.expected_agent_actions, (
        f"{filename} must declare at least one expected_agent_action"
    )
    assert scenario.available_actions.actions, (
        f"{filename} must declare at least one clickable action"
    )


@pytest.mark.parametrize(
    ("filename", "_kind", "_category"),
    NEW_SCENARIOS,
)
def test_new_scenario_has_retrieval_keywords_on_public_facts(
    filename: str,
    _kind: PersonaKind,
    _category: str,
) -> None:
    """B.5 discipline: every non-secret fact in the new scenarios carries
    at least one retrieval keyword so the persona surfaces information
    only when the agent asks a related question."""
    scenario, _raw = load_scenario_from_path(_SCENARIOS_DIR / filename)
    public_facts = [f for f in scenario.persona.facts if not f.is_secret]
    for fact in public_facts:
        assert fact.retrieval_keywords, (
            f"{filename}: fact '{fact.key}' lacks retrieval_keywords"
        )


@pytest.mark.parametrize(
    ("filename", "_kind", "_category"),
    NEW_SCENARIOS,
)
def test_new_scenario_yaml_carries_card_metadata(
    filename: str,
    _kind: PersonaKind,
    _category: str,
) -> None:
    """S4.2 authorship rule: every new scenario must populate the four
    ``card_*`` fields so the landing (S4.4) never has to fall back.

    We read the raw YAML because ``ScenarioFile`` will only wire the
    fields into the model in T3 — asserting on the raw text keeps the
    test truthful even if the model side is not yet done.
    """
    path = _SCENARIOS_DIR / filename
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("card_pitch", "card_what_happens", "card_watch_for", "card_icon"):
        value = raw.get(key)
        assert isinstance(value, str) and value.strip(), (
            f"{filename}: field '{key}' must be a non-empty string"
        )


def test_onda4_wave_covers_every_persona_kind() -> None:
    """Wave discipline: at least one scenario per PersonaKind so the M5
    persona-coverage floor still holds across the Onda-4 additions
    alone. (Absolute counts follow the filenames the request prescribed:
    4 confused, 3 aggressive, 1 fraudster — the "3/3/2" summary in the
    prose conflicts with its own file list, and the filenames win.)"""
    kinds_seen = {kind for _filename, kind, _category in NEW_SCENARIOS}
    assert kinds_seen == set(PersonaKind), (
        f"wave must cover every persona kind. Missing: "
        f"{set(PersonaKind) - kinds_seen}"
    )


def test_onda4_fraudster_scenario_carries_honeytokens() -> None:
    """The new fraudster scenario must plant at least one honeytoken so
    the M2 detector has a trap to catch — same discipline the shipped
    fraudster carries."""
    scenario, _raw = load_scenario_from_path(
        _SCENARIOS_DIR / "certidao_terceiro_fraudster_v1.yaml"
    )
    secrets = [f for f in scenario.persona.facts if f.is_secret]
    assert secrets, "new fraudster scenario must include at least one honeytoken"


def test_onda4_wave_covers_at_least_seven_distinct_categories() -> None:
    """Category-diversity floor for the wave: the 8 new scenarios must
    exercise at least 7 distinct canonical categories — one duplicate
    is OK, but the whole point of Onda-4 is escaping the mono-scope."""
    categories = {c for _f, _k, c in NEW_SCENARIOS}
    assert len(categories) >= 7, (
        f"expected >=7 distinct categories in the wave, got {sorted(categories)}"
    )
