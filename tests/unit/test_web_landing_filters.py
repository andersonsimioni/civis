"""
AppTest cases for the Onda 4 S4.3 landing filters.

The landing exposes two dropdowns (category, persona kind) and a
counter reporting how many cards are visible. Both dropdowns bind to
``session_state`` under stable keys so a rerun keeps the selection.
The random-launch button respects the current filter — an empty pool
disables it.

Every test drives the app through Streamlit's :class:`AppTest`. The
underlying scenarios directory is not mocked — the real 15 shipping
YAMLs are read, since the counter numbers change if a scenario is
added, and pinning that to a specific value would make the tests
brittle. Assertions target invariants: totals, contains, ordering.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from civis.personas.base import PersonaKind
from civis.scenarios.discovery import ScenarioCard, discover_scenarios

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"
_SCENARIOS_DIR = _REPO_ROOT / "data" / "scenarios"


@pytest.fixture()
def landing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point sessions at a tmp folder so the landing does not touch real data."""
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


def _boot_landing(landing_env: Path) -> AppTest:
    """Boot the landing page fresh, with the real scenarios directory."""
    del landing_env
    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    at.run()
    return at


def _count_scenario_start_buttons(at: AppTest) -> int:
    """How many 'start_<scenario_id>' buttons are on the rendered landing."""
    return sum(
        1 for b in at.button if b.key and b.key.startswith("start_")
        and b.key != "start_random"
    )


# ---------------------------------------------------------------------------
# Default view — no filter, every discoverable scenario is on screen
# ---------------------------------------------------------------------------


def test_landing_default_view_lists_every_discoverable_scenario(
    landing_env: Path,
) -> None:
    """Fresh landing: both dropdowns default to 'Todos*' and every card
    on disk shows up. Counter reports the discovered total."""
    at = _boot_landing(landing_env)

    real_cards = discover_scenarios(_SCENARIOS_DIR)
    total_expected = len(real_cards)
    rendered = _count_scenario_start_buttons(at)
    assert rendered == total_expected, (
        f"expected {total_expected} start buttons, saw {rendered}"
    )

    # Counter caption carries the number literally.
    caption_text = " ".join(c.value for c in at.caption)
    assert f"**{total_expected}** cenário" in caption_text


# ---------------------------------------------------------------------------
# Category filter — narrows the pool
# ---------------------------------------------------------------------------


def test_category_filter_narrows_visible_cards(landing_env: Path) -> None:
    """Choosing a specific category reduces the grid to cards in that bucket."""
    at = _boot_landing(landing_env)

    # Categoria is the first selectbox on the landing.
    category_select = at.selectbox[0]
    # Pick a label that includes "Casamento" (has one scenario in the
    # ship set: casamento_habilitacao_confused_v1).
    casamento_label = next(
        label for label in category_select.options if "Casamento" in label
    )
    category_select.select(casamento_label).run()

    rendered = _count_scenario_start_buttons(at)
    # Casamento bucket has exactly one shipping scenario.
    assert rendered == 1
    # The right one is on screen.
    keys = {b.key for b in at.button if b.key}
    assert "start_casamento_habilitacao_confused_v1" in keys


# ---------------------------------------------------------------------------
# Persona-kind filter — narrows the pool
# ---------------------------------------------------------------------------


def test_persona_kind_filter_narrows_visible_cards(landing_env: Path) -> None:
    """Choosing 'Fraudador social' shows only fraudster scenarios."""
    at = _boot_landing(landing_env)

    # Perfil da persona is the second selectbox.
    kind_select = at.selectbox[1]
    kind_select.select("Fraudador social").run()

    real_cards = discover_scenarios(_SCENARIOS_DIR)
    expected_ids = {
        c.scenario_id for c in real_cards if c.persona_kind == PersonaKind.FRAUDSTER
    }
    keys = {b.key for b in at.button if b.key and b.key.startswith("start_")}
    keys.discard("start_random")
    rendered_ids = {k.removeprefix("start_") for k in keys}
    assert rendered_ids == expected_ids


# ---------------------------------------------------------------------------
# Random launch respects the filter
# ---------------------------------------------------------------------------


def test_random_launch_respects_active_filters(landing_env: Path) -> None:
    """When a filter is active, the random-launch button picks from the
    filtered pool only. We drive that by selecting 'Fraudador social'
    and asserting the started scenario is a fraudster one."""
    at = _boot_landing(landing_env)

    at.selectbox[1].select("Fraudador social").run()

    random_btn = next(b for b in at.button if b.key == "start_random")
    assert not random_btn.disabled
    random_btn.click().run()

    started_id: str = at.session_state["civis.chat.scenario_id"]
    # Every fraudster scenario id is discoverable, and its persona kind
    # must be FRAUDSTER when re-loaded from disk.
    real_cards = discover_scenarios(_SCENARIOS_DIR)
    lookup = {c.scenario_id: c for c in real_cards}
    assert started_id in lookup
    assert lookup[started_id].persona_kind == PersonaKind.FRAUDSTER


# ---------------------------------------------------------------------------
# Empty state when combined filters match nothing
# ---------------------------------------------------------------------------


def test_landing_empty_state_when_filters_leave_no_card(
    landing_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prime the landing cache with a single confused / casamento card and
    then filter by 'Divórcio' — the intersection is empty. The grid
    should render the empty-state info banner and the random-launch
    button should be disabled."""
    del monkeypatch
    stub_card = ScenarioCard(
        scenario_id="stub_confused_casamento_v1",
        title="Stub casamento confused",
        category="casamento",
        persona_kind=PersonaKind.CONFUSED,
        persona_label="Cidadã confusa",
        difficulty="Fácil",
        icon="🤝",
        pitch="Stub pitch.",
        what_happens="Stub como corre.",
        watch_for="Stub observação.",
    )

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    # Prime the cache so no real scenarios are pulled from disk.
    at.session_state["civis.landing.cards"] = [stub_card]
    at.run()

    # Both selectboxes start at "all" — the single stub is visible.
    assert _count_scenario_start_buttons(at) == 1

    # Narrow the category filter to 'Divórcio', which the stub does not have.
    category_select = at.selectbox[0]
    divorcio_label = next(
        (label for label in category_select.options if "Divórcio" in label),
        None,
    )
    # If Divórcio is not in the options (because the stub's category
    # bucket does not include it), the filter cannot select it — the
    # test is only meaningful when both categories are present, so we
    # inject a second card with divorcio to enable the option, then
    # verify that picking Divórcio hides the stub_confused_casamento card.
    if divorcio_label is None:
        divorcio_stub = ScenarioCard(
            scenario_id="stub_aggressive_divorcio_v1",
            title="Stub divorcio aggressive",
            category="divorcio",
            persona_kind=PersonaKind.AGGRESSIVE,
            persona_label="Cidadão apressado",
            difficulty="Média",
            icon="✂️",
            pitch="Stub pitch.",
            what_happens="Stub como corre.",
            watch_for="Stub observação.",
        )
        at.session_state["civis.landing.cards"] = [stub_card, divorcio_stub]
        at.run()
        category_select = at.selectbox[0]
        divorcio_label = next(
            label for label in category_select.options if "Divórcio" in label
        )

    category_select.select(divorcio_label).run()
    # Now combine with 'Cidadã confusa' — no confused divorcio card exists.
    kind_select = at.selectbox[1]
    kind_select.select("Cidadã confusa").run()

    assert _count_scenario_start_buttons(at) == 0
    random_btn = next(b for b in at.button if b.key == "start_random")
    assert random_btn.disabled

    # Empty-state info banner is shown.
    info_text = " ".join(i.value for i in at.info)
    assert "Nenhum cenário encontrado" in info_text
