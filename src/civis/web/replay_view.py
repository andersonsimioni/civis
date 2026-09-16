"""
Replay timeline renderer (ONDA 3, R1.2).

Draws the horizontal navigation bar that sits above the transcript:
one coloured dot per :class:`ReplayEvent`, each anchored at its
turn's horizontal position. Hover shows a native tooltip (``title``
attribute); clicking the small Streamlit button next to each dot
stores the event's ``turn_index`` in
``st.session_state["civis.highlight_turn_index"]`` so
:mod:`civis.web.chat_view` flashes the corresponding turn on the
next rerun.

Design notes:
    - Pure SVG for the bar, so the layout stays deterministic and
      renders in every Streamlit version we support (no HTML canvas,
      no JS callback).
    - The clickable surface is a real ``st.button`` below the bar,
      not the SVG dot itself. Streamlit does not currently forward
      clicks on inline SVG shapes to callbacks, so we keep the SVG
      purely visual and put a compact button list underneath. The
      button and the dot share a colour class so the pairing is
      visible.
    - Two states we handle explicitly:
        * empty timeline (no events) — the bar still renders so the
          layout does not jump when a session with no verdict is
          opened; a small caption explains why the bar is empty;
        * single-turn session — placing a dot at 100 % of the bar
          would push it off-screen, so we clamp the horizontal
          position to the [4 %, 96 %] band.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from civis.web.replay import ReplayEvent
from civis.web.state import HIGHLIGHT_TURN_KEY

# Colour ramp per severity. Kept in one place so the legend and the
# SVG use the same swatches.
_SEVERITY_COLOR: dict[str, str] = {
    "positive": "#2f9e44",
    "warning": "#f59f00",
    "critical": "#e03131",
    "neutral": "#868e96",
}

# Human-friendly labels for the legend, keyed by severity.
_SEVERITY_LEGEND: dict[str, str] = {
    "positive": "Acerto",
    "warning": "Atenção",
    "critical": "Erro",
    "neutral": "Ação / Fila",
}

# Human-friendly labels per event type — used in the button caption
# so the click surface tells the viewer what the dot means before
# they hover.
_EVENT_TYPE_LABEL: dict[str, str] = {
    "citation": "Citação",
    "contradiction": "Contradição",
    "honeytoken_leak": "Vazamento",
    "action": "Ação",
    "queue": "Fila",
}

_BAR_WIDTH_PX = 800
_BAR_HEIGHT_PX = 40
_DOT_RADIUS_PX = 6
# Horizontal padding as a fraction of the bar width. Keeps the first
# and last dots from being clipped by the container.
_LEFT_PAD_FRAC = 0.04
_RIGHT_PAD_FRAC = 0.04


def render_replay_timeline(
    events: list[ReplayEvent],
    total_turns: int,
    *,
    key_prefix: str = "replay",
) -> None:
    """
    Render the timeline SVG plus a compact list of clickable event
    buttons underneath.

    Args:
        events: The extracted timeline, as returned by
            :func:`civis.web.replay.build_replay_timeline`.
        total_turns: Number of turns in the transcript. Used to
            position each dot; a value of 0 renders an empty bar.
        key_prefix: Streamlit widget-key prefix. Callers displaying
            more than one timeline on the same page (unusual, but the
            supervisor dashboard might) pass a unique prefix to avoid
            duplicate-key errors.
    """
    st.subheader("Linha do tempo do atendimento")
    st.markdown(_svg_html(events, total_turns), unsafe_allow_html=True)
    _render_legend()
    _render_event_buttons(events, key_prefix=key_prefix)


def _svg_html(events: list[ReplayEvent], total_turns: int) -> str:
    """
    Build the timeline as a single inline SVG string.

    Each dot carries a ``<title>`` child so the browser shows a
    native tooltip on hover. The SVG has an explicit viewBox so it
    scales to whatever width the Streamlit column gives it.
    """
    width = _BAR_WIDTH_PX
    height = _BAR_HEIGHT_PX
    baseline_y = height // 2

    # Background rail — a thin grey line spanning the padded band.
    left_edge = width * _LEFT_PAD_FRAC
    right_edge = width * (1 - _RIGHT_PAD_FRAC)
    rail = (
        f'<line x1="{left_edge:.1f}" y1="{baseline_y}" '
        f'x2="{right_edge:.1f}" y2="{baseline_y}" '
        f'stroke="#dee2e6" stroke-width="2" />'
    )

    dots: list[str] = []
    for ev in events:
        x = _event_x_position(ev.turn_index, total_turns)
        color = _SEVERITY_COLOR.get(ev.severity, "#868e96")
        # <title> renders as a native browser tooltip when hovering
        # the parent element. Escape carefully — the label might
        # contain quotes.
        tooltip = escape(f"Turno {ev.turn_index} · {ev.label}")
        dots.append(
            f'<circle cx="{x:.1f}" cy="{baseline_y}" r="{_DOT_RADIUS_PX}" '
            f'fill="{color}" stroke="#fff" stroke-width="1.5">'
            f'<title>{tooltip}</title>'
            f'</circle>'
        )

    body = rail + "".join(dots)
    return (
        f'<div class="civis-replay-timeline" '
        f'style="width:100%; overflow-x:auto;">'
        f'<svg viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="width:100%; height:{height}px;" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="Linha do tempo do atendimento">'
        f'{body}'
        f'</svg>'
        f'</div>'
    )


def _event_x_position(turn_index: int, total_turns: int) -> float:
    """
    Map a turn index to a horizontal pixel position on the bar.

    When ``total_turns`` is 0 or 1 we anchor the dot at the middle
    of the bar — dividing by 0 would explode and dividing by 1 puts
    the dot flat on the right edge, which reads as 'end of session'
    for a session with a single turn. The middle is friendlier.
    """
    width = _BAR_WIDTH_PX
    left_edge = width * _LEFT_PAD_FRAC
    right_edge = width * (1 - _RIGHT_PAD_FRAC)
    usable = right_edge - left_edge
    if total_turns <= 1:
        return left_edge + usable / 2
    # Clamp the index into [0, total_turns - 1] defensively — a
    # malformed sidecar could point at a turn beyond the transcript.
    idx = max(0, min(turn_index, total_turns - 1))
    fraction = idx / (total_turns - 1)
    return left_edge + fraction * usable


def _render_legend() -> None:
    """Colour → severity legend below the bar, as inline HTML."""
    chips: list[str] = []
    for severity, label in _SEVERITY_LEGEND.items():
        color = _SEVERITY_COLOR[severity]
        chips.append(
            f'<span style="display:inline-flex; align-items:center; '
            f'gap:0.35rem; margin-right:1rem; font-size:0.85rem;">'
            f'<span style="display:inline-block; width:10px; height:10px; '
            f'border-radius:50%; background:{color};"></span>'
            f'{escape(label)}'
            f'</span>'
        )
    st.markdown(
        f'<div class="civis-replay-legend" style="margin-top:0.4rem;">'
        f'{"".join(chips)}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_event_buttons(
    events: list[ReplayEvent],
    *,
    key_prefix: str,
) -> None:
    """
    Emit one compact ``st.button`` per event. Clicking sets the
    highlight state key so :mod:`civis.web.chat_view` flashes the
    corresponding turn on rerun.
    """
    if not events:
        st.caption(
            "Sem eventos para exibir. Rode a sessão com juiz habilitado "
            "para preencher a linha do tempo."
        )
        return

    st.caption("Clique em um evento para destacar o turno correspondente:")
    # Use up to 6 columns per row so the buttons wrap gracefully on
    # narrower viewports. Streamlit gives every column equal width.
    columns_per_row = 6
    for row_start in range(0, len(events), columns_per_row):
        row = events[row_start : row_start + columns_per_row]
        cols = st.columns(columns_per_row)
        for offset, ev in enumerate(row):
            with cols[offset]:
                _render_single_event_button(
                    ev,
                    key=f"{key_prefix}_event_{row_start + offset}",
                )


def _render_single_event_button(ev: ReplayEvent, *, key: str) -> None:
    """
    Render one event's clickable button. Kept as its own function so
    the callback and the label formatting live side by side — easier
    to keep them in sync.
    """
    type_label = _EVENT_TYPE_LABEL.get(ev.event_type, ev.event_type)
    # Compact button label: type + turn index. The full ``ev.label``
    # already lives in the SVG tooltip and in the help text below,
    # so we keep the button itself terse.
    button_label = f"{type_label} · T{ev.turn_index}"
    if st.button(
        button_label,
        key=key,
        help=ev.label,
        use_container_width=True,
    ):
        st.session_state[HIGHLIGHT_TURN_KEY] = ev.turn_index
        st.rerun()


__all__ = ["render_replay_timeline"]
