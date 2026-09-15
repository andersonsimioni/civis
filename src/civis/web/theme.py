"""
Shared theme, palette and page config for the CIVIS Streamlit app.

Centralising visual tokens here (colour, spacing, copy for the page config)
keeps the pages consistent and lets us change the palette in one place.
"""

from __future__ import annotations

# Product identity — used by st.set_page_config and by the sidebar header.
APP_TITLE = "CIVIS"
APP_TAGLINE = "Cidadão virtual para treinamento de atendimento"
APP_ICON = "💬"
# Deep academic blue; pairs with the purple accents in the pitch PDFs.
PRIMARY_COLOR = "#1f4b8f"
PRIMARY_COLOR_SOFT = "#e6ecf7"  # background tint for chat bubbles / cards
NEUTRAL_BG = "#fafaf7"          # off-white page background
NEUTRAL_TEXT = "#1c2530"        # near-black text
BORDER_COLOR = "#dfe3ea"
HIGHLIGHT_COLOR = "#fff3b0"     # used briefly when a citation is clicked

# CSS injected once per page via st.markdown(unsafe_allow_html=True). Small
# on purpose: Streamlit's defaults already give us usable typography and
# spacing. Custom CSS only fixes what feels like a template.
BASE_CSS = f"""
<style>
    /* Page-level tweaks */
    section.main > div.block-container {{
        padding-top: 2.2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }}
    /* Sidebar polish */
    section[data-testid="stSidebar"] {{
        background: {NEUTRAL_BG};
        border-right: 1px solid {BORDER_COLOR};
    }}
    /* Chat bubble container */
    .civis-turn {{
        border-radius: 10px;
        padding: 0.65rem 0.85rem;
        margin-bottom: 0.5rem;
        border: 1px solid {BORDER_COLOR};
        background: white;
        transition: background-color 1.2s ease-out;
    }}
    .civis-turn-agent {{
        background: {PRIMARY_COLOR_SOFT};
        border-color: {PRIMARY_COLOR}33;
    }}
    .civis-turn-persona {{
        background: white;
    }}
    .civis-turn-meta {{
        font-size: 0.78rem;
        color: #667085;
        margin-bottom: 0.2rem;
    }}
    /* Applied briefly after a citation click. See chat_view.render_transcript */
    .civis-turn-highlight {{
        background: {HIGHLIGHT_COLOR} !important;
        border-color: #d4a800 !important;
    }}
    /* Verdict card */
    .civis-card {{
        border: 1px solid {BORDER_COLOR};
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 0.6rem;
        background: white;
    }}
    .civis-score-badge {{
        display: inline-block;
        min-width: 2.2rem;
        text-align: center;
        padding: 0.15rem 0.5rem;
        border-radius: 999px;
        font-weight: 600;
        color: white;
        margin-right: 0.4rem;
    }}
    .civis-quote {{
        border-left: 3px solid {PRIMARY_COLOR};
        padding-left: 0.6rem;
        margin: 0.35rem 0 0.15rem 0;
        color: #333;
        font-style: italic;
    }}
    /* Empty state block */
    .civis-empty {{
        border: 1px dashed {BORDER_COLOR};
        border-radius: 10px;
        padding: 1.5rem;
        text-align: center;
        color: #556070;
        background: {NEUTRAL_BG};
    }}
</style>
"""

# Score-to-colour ramp used by the verdict badges. 0-2 red-ish, 3 amber,
# 4-5 green. Investor eye scans the colour first, then the number.
SCORE_COLORS: dict[int, str] = {
    0: "#b3261e",
    1: "#c25a1a",
    2: "#d68f1f",
    3: "#b58900",
    4: "#3f8f4a",
    5: "#1f7a34",
}


def score_color(score: int) -> str:
    """Return the badge colour for a rubric score in [0, 5]."""
    return SCORE_COLORS.get(int(score), "#666")


def apply_page_config(page_title: str | None = None) -> None:
    """
    Apply st.set_page_config with product identity. Safe to call from any
    page: `page_title` overrides the browser-tab title while the sidebar
    label continues to come from st.navigation.
    """
    import streamlit as st

    st.set_page_config(
        page_title=page_title or APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": (
                f"{APP_TITLE} — {APP_TAGLINE}. Simulador de cidadão virtual para "
                "treinamento de atendentes de balcão registral."
            ),
        },
    )


def inject_base_css() -> None:
    """Inject the shared CSS block once per page render."""
    import streamlit as st

    st.markdown(BASE_CSS, unsafe_allow_html=True)
