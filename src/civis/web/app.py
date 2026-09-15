"""
CIVIS Streamlit app — entry point.

Run:

    streamlit run src/civis/web/app.py

Layout: `st.navigation` groups the four top-level pages under a single
sidebar. `st.set_page_config` runs once here so every page inherits the
same tab title, favicon, wide layout and menu items.

Pages live as standalone Python files under civis/web/pages/. Each file
defines a `render()` function AND calls it at module level, so that:

    - `AppTest.switch_page("civis/web/pages/about.py")` works.
    - Importing the module in a unit test also renders — this only
      matters when running against a Streamlit context, so it costs
      nothing outside AppTest.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from civis.web.theme import (
    APP_ICON,
    APP_TAGLINE,
    APP_TITLE,
    apply_page_config,
    inject_base_css,
)

# Resolved absolute paths — Streamlit's st.Page accepts absolute paths;
# using __file__ makes the app runnable from any working directory
# (`streamlit run src/civis/web/app.py` from repo root or from anywhere).
_PAGES_DIR = Path(__file__).resolve().parent / "pages"


def _sidebar_header() -> None:
    """Render the sidebar identity block above the navigation tree."""
    st.sidebar.markdown(
        f"### {APP_ICON} {APP_TITLE}\n"
        f"*{APP_TAGLINE}*"
    )
    st.sidebar.markdown("---")


def _build_navigation() -> st.navigation:
    """
    Wire the four top-level pages. Order matters: 'Nova sessão' comes
    first because it's what the trainee opens by default; 'Sobre' closes
    so an investor can drift into it after the demo.
    """
    return st.navigation(
        [
            st.Page(
                _PAGES_DIR / "new_session.py",
                title="Nova sessão",
                icon="🎬",
                url_path="new_session",
                default=True,
            ),
            st.Page(
                _PAGES_DIR / "past_sessions.py",
                title="Sessões passadas",
                icon="🗂️",
                url_path="past_sessions",
            ),
            st.Page(
                _PAGES_DIR / "metrics.py",
                title="Métricas",
                icon="📊",
                url_path="metrics",
            ),
            st.Page(
                _PAGES_DIR / "about.py",
                title="Sobre",
                icon="ℹ️",
                url_path="about",
            ),
        ]
    )


def main() -> None:
    """Application bootstrap. Idempotent — safe to call from AppTest."""
    apply_page_config()
    inject_base_css()
    _sidebar_header()
    _build_navigation().run()


main()
