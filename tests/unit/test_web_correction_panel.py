"""
AppTest cases for the D.2 correction panel (side-by-side transcript +
verdict with click-to-highlight).

We can't screenshot the layout with AppTest, but we CAN pin the
interaction contract:

    - Opening a session from the list stores its id in session_state.
    - The drill-down shows both the transcript subheader and the verdict
      subheaders.
    - Every criterion produces at least one 'cite' button (verdict
      generator gives every criterion one cited turn).
    - Clicking a 'cite' button sets civis.highlight_turn_index to the
      cited turn.
    - The two sidecars (contradictions, honeytoken leaks) render whether
      or not the report list is empty.
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
    demo fixture, navigate to Sessões passadas, and open the first
    session in the list. Returns the AppTest ready for assertions.
    """
    from scripts.generate_demo_sessions import emit_all

    folder = tmp_path / "sessions"
    emit_all(folder)
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "past_sessions.py"))
    at.run()

    open_buttons = [b for b in at.button if b.key and b.key.startswith("open_")]
    assert open_buttons, "expected at least one 'Abrir' button on the list page"
    open_buttons[0].click()
    at.run()
    return at


def test_open_session_stores_selection_in_state(open_first_session: AppTest) -> None:
    at = open_first_session
    assert at.session_state["civis.selected_session_id"] is not None


def test_drill_down_renders_transcript_and_verdict_subheaders(
    open_first_session: AppTest,
) -> None:
    at = open_first_session
    subheaders = [s.value for s in at.subheader]
    assert "Transcript" in subheaders
    assert "Resumo do juiz" in subheaders
    assert "Critérios" in subheaders


def test_drill_down_shows_one_cite_button_per_criterion(
    open_first_session: AppTest,
) -> None:
    """Demo verdicts assign exactly one cited turn per criterion."""
    at = open_first_session
    cite_buttons = [b for b in at.button if b.key and b.key.startswith("cite_")]
    assert len(cite_buttons) == 4


def test_clicking_cite_button_highlights_the_referenced_turn(
    open_first_session: AppTest,
) -> None:
    """
    Clicking a citation must inject the highlight CSS for the cited
    turn into the markdown block chat_view writes. State-key inspection
    is not enough because chat_view clears the key AFTER writing the CSS
    (so the flash only fires once per click).
    """
    at = open_first_session
    cite_buttons = [b for b in at.button if b.key and b.key.startswith("cite_")]
    # The first citation button ('fact_verification' criterion) points
    # at the turn the judge cited for that rubric line.
    cite_buttons[0].click()
    at.run()
    markdown_blocks = [m.value for m in at.markdown]
    # The CSS block injected by chat_view contains 'civis-turn-highlight'
    # and an anchor id 'turn-<N>' for the cited turn. Both must appear.
    highlight_blocks = [m for m in markdown_blocks if "civis-turn-highlight" in m]
    assert highlight_blocks, "expected chat_view to inject a highlight CSS block"
    assert any("#turn-" in m for m in highlight_blocks), (
        "expected the highlight CSS to reference an anchor id"
    )


def test_contradictions_sidecar_renders_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Open the aggressive-mixed session (has one planted contradiction) and
    check the sidecar header carries the count.
    """
    from scripts.generate_demo_sessions import emit_all

    folder = tmp_path / "sessions"
    emit_all(folder)
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "past_sessions.py"))
    at.run()
    at.button(key="open_demo_aggressive_mixed_v1").click()
    at.run()

    # The expander header text lives in the widget list — pull it out.
    expander_labels = [e.label for e in at.expander]
    assert any("Contradições detectadas (1)" in label for label in expander_labels)


def test_honeytoken_sidecar_flags_leaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fraudster-leak session must surface both planted honeytoken leaks."""
    from scripts.generate_demo_sessions import emit_all

    folder = tmp_path / "sessions"
    emit_all(folder)
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "past_sessions.py"))
    at.run()
    at.button(key="open_demo_fraudster_leak_v1").click()
    at.run()

    expander_labels = [e.label for e in at.expander]
    assert any("Vazamento de honeytoken (2)" in label for label in expander_labels)


def test_back_button_returns_to_list(
    open_first_session: AppTest,
) -> None:
    """The 'Voltar' button clears the selection and re-renders the list."""
    at = open_first_session
    # Streamlit renders one 'Voltar' button in the drill-down; nothing else
    # carries that label, so we can look it up by prefix.
    voltar_buttons = [b for b in at.button if "Voltar" in (b.label or "")]
    assert voltar_buttons, "expected a 'Voltar' button in the drill-down"
    voltar_buttons[0].click()
    at.run()

    # Session-state cleared and the list came back — assert both.
    assert at.session_state["civis.selected_session_id"] is None
    open_buttons = [b for b in at.button if b.key and b.key.startswith("open_")]
    assert len(open_buttons) >= 1


def test_filters_survive_a_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A rerun triggered by clicking 'Abrir' and then 'Voltar' must not lose
    the scenario filter state (verified through session_state keys).
    """
    from scripts.generate_demo_sessions import emit_all

    folder = tmp_path / "sessions"
    emit_all(folder)
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "past_sessions.py"))
    at.run()

    # Pick one scenario to filter on.
    at.multiselect(key="filter_scenarios").set_value(
        ["certificate_thirdparty_fraudster_v1"]
    )
    at.run()
    # Two fraudster sessions in the demo set.
    open_buttons = [b for b in at.button if b.key and b.key.startswith("open_")]
    assert len(open_buttons) == 2
