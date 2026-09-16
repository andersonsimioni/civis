"""
AppTest cases for the replay-timeline integration in the
"Sessões passadas" drill-down (ONDA 3, R1.3).

We reuse the demo-session generator so the fixture is exactly what
the investor sees in the demo. Two assertions matter:

    1. The 'Ver replay' button is present on the detail header.
    2. Clicking it toggles the state key AND makes the timeline SVG
       appear above the transcript on the next rerun.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"


@pytest.fixture()
def open_first_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AppTest:
    """
    Boot the app against a tmp sessions folder pre-populated with the
    demo fixture and open the first session on the list.
    """
    from scripts.generate_demo_sessions import emit_all

    folder = tmp_path / "sessions"
    emit_all(folder)
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "past_sessions.py"))
    at.run()

    open_buttons = [b for b in at.button if b.key and b.key.startswith("open_")]
    assert open_buttons, "expected at least one 'Abrir' button"
    open_buttons[0].click()
    at.run()
    return at


def test_ver_replay_button_is_present_on_detail_panel(
    open_first_session: AppTest,
) -> None:
    """
    The drill-down header exposes a 'Ver replay' toggle. Before any
    click the label reads 'Ver replay'; after clicking, it flips to
    'Fechar replay'.
    """
    at = open_first_session
    toggle = [b for b in at.button if b.key == "toggle_replay"]
    assert len(toggle) == 1, "expected exactly one 'toggle_replay' button"
    assert "Ver replay" in (toggle[0].label or "")


def test_clicking_ver_replay_reveals_the_timeline(
    open_first_session: AppTest,
) -> None:
    """
    Clicking 'Ver replay' toggles the state key AND the SVG bar
    appears in the markdown stream on the following rerun.
    """
    at = open_first_session
    toggle = [b for b in at.button if b.key == "toggle_replay"][0]
    toggle.click()
    at.run()

    # State toggle stuck.
    assert at.session_state["civis.show_replay_timeline"] is True

    # The SVG bar landed in one of the markdown blocks.
    dump = "\n".join(m.value for m in at.markdown)
    assert "<svg" in dump, "expected the replay SVG to render after toggle"
    assert "civis-replay-timeline" in dump

    # The button label flipped to 'Fechar replay'.
    toggle_after = [b for b in at.button if b.key == "toggle_replay"][0]
    assert "Fechar replay" in (toggle_after.label or "")
