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
    PRIMARY_COLOR_DEEP,
    apply_page_config,
    inject_base_css,
)

# Resolved absolute paths — Streamlit's st.Page accepts absolute paths;
# using __file__ makes the app runnable from any working directory
# (`streamlit run src/civis/web/app.py` from repo root or from anywhere).
_PAGES_DIR = Path(__file__).resolve().parent / "pages"


def _sidebar_header() -> None:
    """
    Render the sidebar identity block above the navigation tree. A small
    HTML card gives the product name real presence — the default h3
    render looks too casual for an investor demo.
    """
    st.sidebar.markdown(
        f"""
        <div style="padding: 0.4rem 0 0.9rem 0;">
            <div style="font-size:1.65rem; line-height:1;">
                {APP_ICON}
                <span style="font-weight:700; color:{PRIMARY_COLOR_DEEP};
                             letter-spacing:0.02em; margin-left:0.3rem;">
                    {APP_TITLE}
                </span>
            </div>
            <div style="font-size:0.85rem; color:#5b6473; margin-top:0.2rem;">
                {APP_TAGLINE}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")


def _sidebar_footer() -> None:
    """Attribution and version footer at the bottom of the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Projeto acadêmico · UFSC INE5448  \n"
        "Anderson Simioni Assunção · 2026"
    )


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
    _sidebar_footer()


main()
