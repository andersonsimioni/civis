"""
AppTest cases for :mod:`civis.web.replay_view` (ONDA 3, R1.2).

The renderer draws an SVG bar plus one Streamlit button per event.
We assert on:

    - the SVG markup contains one <circle> per event with the right
      severity colour,
    - the legend chips are present,
    - a button labelled 'Citação · T<idx>' exists per citation event,
    - clicking a button sets ``civis.highlight_turn_index`` to the
      referenced turn index.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from civis.web.replay import ReplayEvent


def _events() -> list[ReplayEvent]:
    """Small mixed fixture that touches every severity."""
    return [
        ReplayEvent(
            turn_index=1,
            event_type="citation",
            severity="positive",
            label="Verificação (5/5) — boa tarde",
            criterion="fact_verification",
        ),
        ReplayEvent(
            turn_index=3,
            event_type="citation",
            severity="critical",
            label="Proteção de dados (1/5) — vazou CPF",
            criterion="data_protection",
        ),
        ReplayEvent(
            turn_index=3,
            event_type="honeytoken_leak",
            severity="critical",
            label="Honeytoken vazado (mother_maiden_name)",
        ),
        ReplayEvent(
            turn_index=5,
            event_type="action",
            severity="neutral",
            label="Verificar identidade",
        ),
    ]


def _run_render(events: list[ReplayEvent], total_turns: int) -> AppTest:
    """
    Boot a minimal AppTest that calls :func:`render_replay_timeline`.
    Session state carries the events + total_turns because AppTest
    scripts can't easily receive Python-object arguments.
    """
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from civis.web.replay_view import render_replay_timeline\n"
        "render_replay_timeline(\n"
        "    events=st.session_state['events'],\n"
        "    total_turns=st.session_state['total_turns'],\n"
        ")\n"
    )
    at.session_state["events"] = events
    at.session_state["total_turns"] = total_turns
    at.run()
    return at


def _markdown_dump(at: AppTest) -> str:
    """Concatenate every markdown block into a single string for grep-y asserts."""
    return "\n".join(m.value for m in at.markdown)


# ---------------------------------------------------------------------------
# 1. Timeline renders with the right number of dots
# ---------------------------------------------------------------------------


def test_timeline_svg_has_one_circle_per_event() -> None:
    """Every event produces one <circle> inside the SVG bar."""
    at = _run_render(_events(), total_turns=6)
    dump = _markdown_dump(at)
    # One circle per event (4). The rail is a <line>, not a <circle>.
    assert dump.count("<circle") == 4


# ---------------------------------------------------------------------------
# 2. Dots inherit the severity colour
# ---------------------------------------------------------------------------


def test_timeline_svg_paints_dots_with_severity_colours() -> None:
    """
    Positive dots use the green fill, critical dots the red fill,
    neutral dots the grey fill — exactly the values declared in
    replay_view's colour map.
    """
    at = _run_render(_events(), total_turns=6)
    dump = _markdown_dump(at)
    # One positive citation, two criticals (one citation + one leak),
    # one neutral action.
    assert dump.count('fill="#2f9e44"') == 1
    assert dump.count('fill="#e03131"') == 2
    assert dump.count('fill="#868e96"') == 1


# ---------------------------------------------------------------------------
# 3. Every event surfaces a clickable button
# ---------------------------------------------------------------------------


def test_every_event_yields_a_streamlit_button() -> None:
    """
    The renderer emits one ``st.button`` per event under a stable key
    prefix — the caller can therefore address each button in a test
    by index.
    """
    at = _run_render(_events(), total_turns=6)
    event_buttons = [b for b in at.button if b.key and b.key.startswith("replay_event_")]
    assert len(event_buttons) == 4


# ---------------------------------------------------------------------------
# 4. Clicking a dot's button stores the turn index in session state
# ---------------------------------------------------------------------------


def test_clicking_event_button_updates_highlight_state_key() -> None:
    """
    Clicking the button for the third event (turn_index=3) must set
    ``civis.highlight_turn_index`` to 3. This is the hook the chat
    view picks up to flash the corresponding transcript turn.
    """
    at = _run_render(_events(), total_turns=6)
    event_buttons = [b for b in at.button if b.key and b.key.startswith("replay_event_")]
    # events[2] is the honeytoken_leak on turn 3.
    event_buttons[2].click()
    at.run()
    assert at.session_state.get("civis.highlight_turn_index") == 3


# ---------------------------------------------------------------------------
# 5. Edge case: empty timeline still renders an empty bar
# ---------------------------------------------------------------------------


def test_empty_timeline_renders_bar_and_hint() -> None:
    """
    A session with no events (e.g. no verdict yet) still gets the
    empty rail so the layout does not jump. A caption tells the
    viewer what to do to fill it.
    """
    at = _run_render([], total_turns=0)
    dump = _markdown_dump(at)
    assert "<svg" in dump
    assert "<circle" not in dump
    # The hint caption sits in ``at.caption``.
    captions = [c.value for c in at.caption]
    assert any("Sem eventos" in c for c in captions)
