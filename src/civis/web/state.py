"""
Cross-page state helpers for the CIVIS Streamlit app.

Streamlit reloads the whole page module on every interaction, so we
centralise anything that must survive a rerun (or come from outside the
app entirely, like tests) here.

Two knobs matter for the demo:

    - `CIVIS_SESSIONS_DIR` env var: points the UI at a custom sessions
      folder. AppTest fixtures set this before calling `AppTest.from_file`
      so tests never touch `data/sessions/` on the real filesystem.
    - `CIVIS_REPORTS_DIR` env var: same idea, for the adversarial reports
      produced by Phase C.

`st.session_state` holds ephemeral UI state (which session is selected in
the drill-down, which turn to highlight after a citation click, and so
on). The helpers below give callers a stable name for each key.
"""

from __future__ import annotations

import os
from pathlib import Path

from civis.web.data_access import DEFAULT_REPORTS_DIR, DEFAULT_SESSIONS_DIR

# Env var names — one place to grep.
SESSIONS_DIR_ENV = "CIVIS_SESSIONS_DIR"
REPORTS_DIR_ENV = "CIVIS_REPORTS_DIR"

# Streamlit session-state keys. Namespaced with 'civis.' so a future
# extension can't accidentally collide with them.
SELECTED_SESSION_KEY = "civis.selected_session_id"
HIGHLIGHT_TURN_KEY = "civis.highlight_turn_index"


def get_sessions_dir() -> Path:
    """
    Return the sessions directory the current process should read from.

    Resolution order:
        1. `$CIVIS_SESSIONS_DIR` — set by AppTest fixtures or by a dev
           who wants to point the UI at a temporary folder.
        2. `DEFAULT_SESSIONS_DIR` from data_access.
    """
    override = os.environ.get(SESSIONS_DIR_ENV)
    if override:
        return Path(override)
    return DEFAULT_SESSIONS_DIR


def get_reports_dir() -> Path:
    """Return the reports directory the current process should read from."""
    override = os.environ.get(REPORTS_DIR_ENV)
    if override:
        return Path(override)
    return DEFAULT_REPORTS_DIR
