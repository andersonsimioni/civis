"""
Chat-style transcript renderer with citation-driven highlight.

Two mechanisms wired together let the user click a citation on the right
panel and see the corresponding turn light up on the left panel:

    1. Each turn is rendered as an HTML `<div>` with a stable anchor id
       (`turn-<i>`). The div carries a CSS class chosen by speaker so
       agent / persona bubbles look different at a glance.

    2. When `st.session_state["civis.highlight_turn_index"]` is set (a
       verdict citation was clicked on the last rerun), we append a
       one-shot `<script>` block that:
           - scrolls the anchored div into view,
           - adds the .civis-turn-highlight class for a brief background
             flash,
           - clears the state key so the highlight only fires once per
             click.

The transcript itself is the SessionTranscript object loaded by
data_access — we don't touch disk here.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from civis.session.storage import SessionTranscript
from civis.web.formatting import format_session_datetime
from civis.web.state import HIGHLIGHT_TURN_KEY


def render_transcript(transcript: SessionTranscript) -> None:
    """
    Render the full transcript as a stack of chat bubbles.

    The caller controls whether the transcript sits in a `st.container`
    with fixed height — this function only writes the bubbles.
    """
    if not transcript.turns:
        st.markdown(
            '<div class="civis-empty">Transcript vazio.</div>',
            unsafe_allow_html=True,
        )
        return

    html_blocks: list[str] = []
    for t in transcript.turns:
        if t.speaker == "action":
            # Phase D+++: action turns carry a JSON payload that describes
            # a clickable-button emission (verify identity, issue document).
            # Render a compact bubble that shows the human-readable label
            # and, when present, the ASCII document body inline.
            html_blocks.append(
                _render_action_html(t.turn_index, t.content, t.timestamp)
            )
        else:
            html_blocks.append(
                _render_turn_html(t.turn_index, t.speaker, t.content, t.timestamp)
            )
    st.markdown("\n".join(html_blocks), unsafe_allow_html=True)

    _emit_highlight_script_if_pending()


def _render_turn_html(
    turn_index: int,
    speaker: str,
    content: str,
    timestamp: str,
) -> str:
    """
    Build the HTML block for one turn. Content is HTML-escaped because
    the persona is an LLM — we never trust its output as literal markup.
    """
    speaker_label = "Atendente" if speaker == "agent" else "Cidadão"
    speaker_icon = "👤" if speaker == "agent" else "🧑‍💼"
    bubble_class = "civis-turn-agent" if speaker == "agent" else "civis-turn-persona"
    safe_content = escape(content).replace("\n", "<br>")
    friendly_ts = escape(format_session_datetime(timestamp))

    return (
        f'<div id="turn-{turn_index}" class="civis-turn {bubble_class}">'
        f'  <div class="civis-turn-meta">'
        f'    {speaker_icon} <b>{speaker_label}</b> · turno {turn_index} · {friendly_ts}'
        f'  </div>'
        f'  <div class="civis-turn-body">{safe_content}</div>'
        f'</div>'
    )


def _render_action_html(
    turn_index: int,
    content: str,
    timestamp: str,
) -> str:
    """
    Render one Phase D+++ action turn as a bordered card.

    The stored content is a JSON payload — see
    civis.web.pages.new_session._action_turn_content. When the
    payload includes a document block, its body is rendered
    inline inside a monospace <pre> so the historic view of a past
    session shows the exact same document the trainee saw at emission
    time.
    """
    import json as _json

    friendly_ts = escape(format_session_datetime(timestamp))
    try:
        payload = _json.loads(content)
    except (ValueError, TypeError):
        # Corrupt payload — degrade gracefully.
        payload = {"label": content}

    label = escape(str(payload.get("label", payload.get("action_id", "ação"))))
    document = payload.get("document") or None

    meta = (
        f'<div class="civis-turn-meta">'
        f'  🏛️ <b>Ação do atendente</b> · turno {turn_index} · {friendly_ts}'
        f'</div>'
    )
    body_bits: list[str] = [f'<div class="civis-action-label">{label}</div>']
    if isinstance(document, dict):
        doc_title = escape(str(document.get("title", "Documento emitido")))
        doc_body = escape(str(document.get("body", "")))
        body_bits.append(
            f'<div class="civis-document">'
            f'  <div class="civis-document-title">{doc_title}</div>'
            f'  <pre class="civis-document-body">{doc_body}</pre>'
            f'</div>'
        )
    body = "".join(body_bits)

    return (
        f'<div id="turn-{turn_index}" class="civis-turn civis-turn-action">'
        f'  {meta}'
        f'  <div class="civis-turn-body">{body}</div>'
        f'</div>'
    )


def _emit_highlight_script_if_pending() -> None:
    """
    If a citation click set HIGHLIGHT_TURN_KEY on the previous rerun,
    inject a small JS snippet that flashes the target turn and then
    clears the state key so the effect only fires once.

    Note: Streamlit disables inline <script> execution when its
    `unsafe_allow_html` is true. We still write the block so that when
    the app is served through a component wrapper (or the security
    posture changes upstream), the effect works. Meanwhile, the CSS
    class alone gives the persistent highlight — the JS scroll is
    best-effort.
    """
    turn_index = st.session_state.get(HIGHLIGHT_TURN_KEY)
    if turn_index is None:
        return

    st.markdown(
        f"""
        <style>
            #turn-{turn_index} {{
                background: #fff3b0 !important;
                border-color: #d4a800 !important;
            }}
        </style>
        <script>
            (function() {{
                const el = document.getElementById("turn-{turn_index}");
                if (el) {{
                    el.scrollIntoView({{behavior: "smooth", block: "center"}});
                    el.classList.add("civis-turn-highlight");
                    setTimeout(function() {{
                        el.classList.remove("civis-turn-highlight");
                    }}, 2500);
                }}
            }})();
        </script>
        """,
        unsafe_allow_html=True,
    )
    # Clear the flag so a rerun triggered by an unrelated widget does
    # not re-flash the same turn.
    st.session_state[HIGHLIGHT_TURN_KEY] = None
