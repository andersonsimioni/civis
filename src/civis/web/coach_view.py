"""
Streamlit helpers for the real-time coach (ONDA 3, C3.2 / C3.3).

The new-session page delegates every coach-related widget to this
module so the (already large) page file stays focused on the chat
flow. Three responsibilities live here:

    1. :func:`render_sidebar_toggle` — the on/off switch.
    2. :func:`render_suggestion_block` — the coloured hint bubble
       above the chat input.
    3. :func:`compute_suggestion` — invokes
       :meth:`Coach.suggest_next_move` with a 10-second timeout so a
       slow LLM never blocks the next turn.

Design notes:
    - The toggle default is off. An investor watching the demo turns
      it on explicitly; nothing about the base flow depends on it.
    - The suggestion block is rendered from
      ``COACH_LAST_SUGGESTION_KEY``. That decouples the render pass
      from the LLM call — the LLM runs at end-of-turn, stores its
      output in session state, and the next rerun paints it.
    - We use a raw daemon :class:`threading.Thread` for the timeout,
      not :class:`concurrent.futures.ThreadPoolExecutor`. The pool
      would block on ``__exit__`` waiting for the running worker,
      which is exactly what we do NOT want here — the whole point of
      the timeout is to abandon a slow call and return to the UI.
    - On timeout / provider error we swallow the failure silently.
      The prompt asked for a suggestion; if the model does not
      deliver in time, 'no hint this turn' is the correct answer.
"""

from __future__ import annotations

import threading
from html import escape
from queue import Empty, Queue

import streamlit as st

from civis.coach.coach import Coach, CoachSuggestion
from civis.session.storage import SessionTranscript
from civis.web.state import COACH_ENABLED_KEY, COACH_LAST_SUGGESTION_KEY

# Coach LLM call timeout, in seconds. A slow model returning nothing
# is treated as 'no hint' — the trainee never waits on the coach.
_COACH_TIMEOUT_SECONDS = 10.0

# Colour per suggestion type. Mirrors the review-orchestrator
# severity conventions we use elsewhere in the app.
_TYPE_TO_COLOR: dict[str, str] = {
    "hint": "#0d6efd",       # bootstrap blue
    "warning": "#f59f00",    # amber
    "info": "#6c757d",       # slate grey
}


def render_sidebar_toggle() -> bool:
    """
    Render the sidebar coach toggle and return the current state.

    The widget writes to :data:`COACH_ENABLED_KEY` directly (Streamlit
    binds ``key=`` to session state), so callers can read the same
    key without going through the return value.
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🎓 Coach ao vivo**")
    enabled = st.sidebar.toggle(
        "Coach ativo",
        value=bool(st.session_state.get(COACH_ENABLED_KEY, False)),
        key=COACH_ENABLED_KEY,
        help=(
            "Um supervisor virtual analisa a conversa após cada resposta "
            "da persona e sugere o próximo movimento. Desligue para não "
            "gastar chamadas de LLM durante uma demo."
        ),
    )
    if enabled:
        st.sidebar.caption(
            "Uma sugestão aparece acima do campo de mensagem depois de "
            "cada resposta do cidadão."
        )
    return bool(enabled)


def render_suggestion_block() -> None:
    """
    Render the last coach suggestion above the chat input, if any.

    Reads :data:`COACH_LAST_SUGGESTION_KEY` from session state; a
    ``None`` value renders nothing. Called every time the chat view
    repaints so the hint sticks between reruns until a fresh turn
    replaces it.
    """
    suggestion: CoachSuggestion | None = st.session_state.get(COACH_LAST_SUGGESTION_KEY)
    if suggestion is None:
        return

    color = _TYPE_TO_COLOR.get(suggestion.type, _TYPE_TO_COLOR["hint"])
    # Prepend an emoji even when the model did not pick one, so the
    # bubble always reads as coach-labelled.
    emoji = suggestion.emoji or "💡"
    st.markdown(
        f'<div class="civis-coach-bubble" '
        f'style="border-left: 4px solid {color}; '
        f'background: {color}10; '
        f'padding: 0.55rem 0.8rem; margin: 0.4rem 0; '
        f'border-radius: 4px; font-size: 0.92rem;">'
        f'<b>{emoji} Coach:</b> {escape(suggestion.message)}'
        f'</div>',
        unsafe_allow_html=True,
    )


def compute_suggestion(
    coach: Coach,
    transcript: SessionTranscript,
    *,
    timeout_seconds: float = _COACH_TIMEOUT_SECONDS,
) -> CoachSuggestion | None:
    """
    Ask the coach for a suggestion, capped by ``timeout_seconds``.

    A daemon thread runs the LLM call. If the thread does not deliver
    a result within the timeout we abandon it — Python daemon threads
    exit with the process, and the coach method is idempotent, so
    abandoning is safe (worst case we discard a suggestion we could
    have shown a few seconds later).

    Returns:
        The suggestion, or ``None`` on 'nothing to say' / timeout /
        provider error.
    """
    result_queue: Queue[tuple[str, CoachSuggestion | None]] = Queue(maxsize=1)

    def _worker() -> None:
        try:
            suggestion = coach.suggest_next_move(transcript)
            result_queue.put(("ok", suggestion))
        except Exception:  # noqa: BLE001 - swallow provider failures
            result_queue.put(("error", None))

    worker = threading.Thread(target=_worker, name="civis-coach", daemon=True)
    worker.start()

    try:
        status, suggestion = result_queue.get(timeout=timeout_seconds)
    except Empty:
        # Timeout: abandon the thread. It runs to completion in the
        # background but its result never reaches the UI.
        return None

    if status != "ok":
        return None
    return suggestion


def store_suggestion(suggestion: CoachSuggestion | None) -> None:
    """
    Write the suggestion to session state so the next rerun can
    render it. Called by the chat handler after each persona turn.
    """
    st.session_state[COACH_LAST_SUGGESTION_KEY] = suggestion


def clear_suggestion() -> None:
    """Drop the current suggestion — used when the trainee sends a new turn."""
    st.session_state[COACH_LAST_SUGGESTION_KEY] = None


__all__ = [
    "clear_suggestion",
    "compute_suggestion",
    "render_sidebar_toggle",
    "render_suggestion_block",
    "store_suggestion",
]
