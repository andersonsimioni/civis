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
PRIMARY_COLOR_DEEP = "#163669"  # hover state / darker accents
ACCENT_COLOR = "#7159c1"        # matches the purple in the deck cover
NEUTRAL_BG = "#fafaf7"          # off-white page background
NEUTRAL_TEXT = "#1c2530"        # near-black text
NEUTRAL_SUBTLE = "#5b6473"      # secondary text
BORDER_COLOR = "#dfe3ea"
HIGHLIGHT_COLOR = "#fff3b0"     # used briefly when a citation is clicked

# CSS injected once per page via st.markdown(unsafe_allow_html=True). Small
# on purpose: Streamlit's defaults already give us usable typography and
# spacing. Custom CSS only fixes what feels like a template.
BASE_CSS = f"""
<style>
    /* Root typography — a step up from Streamlit's default. */
    html, body, [class*="css"] {{
        color: {NEUTRAL_TEXT};
    }}
    /* Page-level tweaks */
    section.main > div.block-container {{
        padding-top: 2.2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }}
    /* Slightly bolder page title so it earns the space at the top. */
    section.main h1 {{
        color: {PRIMARY_COLOR_DEEP};
        letter-spacing: -0.01em;
        margin-bottom: 0.35rem;
    }}
    section.main h2 {{
        color: {NEUTRAL_TEXT};
        border-bottom: 1px solid {BORDER_COLOR};
        padding-bottom: 0.3rem;
        margin-top: 1.8rem;
    }}
    section.main h3 {{
        color: {NEUTRAL_TEXT};
        margin-top: 1.2rem;
    }}
    /* Sidebar polish */
    section[data-testid="stSidebar"] {{
        background: {NEUTRAL_BG};
        border-right: 1px solid {BORDER_COLOR};
    }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{
        color: {PRIMARY_COLOR_DEEP};
    }}
    /* Primary buttons take the brand blue */
    button[kind="primary"] {{
        background-color: {PRIMARY_COLOR} !important;
        border-color: {PRIMARY_COLOR} !important;
    }}
    button[kind="primary"]:hover {{
        background-color: {PRIMARY_COLOR_DEEP} !important;
        border-color: {PRIMARY_COLOR_DEEP} !important;
    }}
    /* Chat bubble container — explicit text color prevents dark-mode
       inheritance from painting invisible white text on the white bg. */
    .civis-turn {{
        border-radius: 10px;
        padding: 0.65rem 0.85rem;
        margin-bottom: 0.5rem;
        border: 1px solid {BORDER_COLOR};
        background: white;
        color: {NEUTRAL_TEXT};
        transition: background-color 1.2s ease-out;
    }}
    .civis-turn-agent {{
        background: {PRIMARY_COLOR_SOFT};
        border-color: {PRIMARY_COLOR}33;
        color: {NEUTRAL_TEXT};
    }}
    .civis-turn-persona {{
        background: white;
        color: {NEUTRAL_TEXT};
    }}
    .civis-turn-body {{
        color: {NEUTRAL_TEXT};
    }}
    .civis-turn-meta {{
        font-size: 0.78rem;
        color: {NEUTRAL_SUBTLE};
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
        color: {NEUTRAL_TEXT};
    }}
    .civis-card p, .civis-card div, .civis-card span {{
        color: inherit;
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
        color: {NEUTRAL_SUBTLE};
        background: {NEUTRAL_BG};
    }}
    /* Scenario cards on the Nova sessão landing */
    .civis-scenario-card {{
        border: 1px solid {BORDER_COLOR};
        border-top: 4px solid {PRIMARY_COLOR};
        border-radius: 12px;
        padding: 1.1rem 1rem 0.9rem 1rem;
        background: white;
        color: {NEUTRAL_TEXT};
        margin-bottom: 0.6rem;
        min-height: 320px;
        box-shadow: 0 1px 2px rgba(28, 37, 48, 0.04);
    }}
    .civis-scenario-icon {{
        font-size: 2rem;
        line-height: 1;
    }}
    .civis-scenario-title {{
        font-size: 1.05rem;
        font-weight: 700;
        color: {PRIMARY_COLOR_DEEP};
        margin: 0.35rem 0 0.4rem 0;
    }}
    .civis-scenario-meta {{
        margin-bottom: 0.65rem;
    }}
    .civis-scenario-pitch {{
        font-weight: 500;
        color: {NEUTRAL_TEXT};
        margin: 0 0 0.55rem 0;
        line-height: 1.4;
    }}
    .civis-scenario-body {{
        color: {NEUTRAL_SUBTLE};
        font-size: 0.92rem;
        margin: 0 0 0.5rem 0;
        line-height: 1.45;
    }}
    .civis-chip {{
        display: inline-block;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 0.15rem 0.55rem;
        border-radius: 999px;
        background: {PRIMARY_COLOR_SOFT};
        color: {PRIMARY_COLOR_DEEP};
        margin-right: 0.35rem;
    }}
    /* Highlighted callout used for the demo-tip block */
    .civis-callout {{
        border-left: 4px solid {ACCENT_COLOR};
        background: {PRIMARY_COLOR_SOFT};
        padding: 0.85rem 1rem;
        border-radius: 4px;
        color: {NEUTRAL_TEXT};
        margin-top: 0.6rem;
    }}
    .civis-callout code {{
        background: white;
        padding: 0.05rem 0.35rem;
        border-radius: 4px;
        border: 1px solid {BORDER_COLOR};
    }}
    /* Phase D+++: attendant action turn — dashed border to set it apart
       from human/persona speech; document block uses a beige paper
       background and monospace so a screenshot passes for real. */
    .civis-turn-action {{
        background: #fdfaf3;
        border: 1px dashed {ACCENT_COLOR};
        color: {NEUTRAL_TEXT};
    }}
    .civis-action-label {{
        font-weight: 600;
        color: {PRIMARY_COLOR_DEEP};
        margin-bottom: 0.4rem;
    }}
    .civis-document {{
        background: #fbf5e2;
        border: 3px double #a58a3a;
        border-radius: 6px;
        padding: 0.7rem 0.9rem;
        margin-top: 0.5rem;
        color: {NEUTRAL_TEXT};
    }}
    .civis-document-title {{
        font-weight: 700;
        color: #6b5410;
        letter-spacing: 0.02em;
        margin-bottom: 0.35rem;
    }}
    .civis-document-body {{
        font-family: "SFMono-Regular", "Menlo", "Consolas",
                     "Liberation Mono", monospace;
        font-size: 0.86rem;
        line-height: 1.25;
        white-space: pre;
        color: #2b2200;
        margin: 0;
        background: transparent;
        border: none;
    }}
    /* Grid of clickable action buttons under the chat input. */
    .civis-action-grid-label {{
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: {NEUTRAL_SUBTLE};
        margin: 0.6rem 0 0.3rem 0;
    }}
    /* Onda 2 T1.2 — chat header timer badge. Colour comes from the
       phase attribute set inline on the container. Monospace so the
       digits do not jump between reruns. */
    .civis-timer {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        font-family: "SFMono-Regular", "Menlo", "Consolas",
                     "Liberation Mono", monospace;
        font-size: 1.5rem;
        font-weight: 700;
        padding: 0.35rem 0.75rem;
        border-radius: 8px;
        letter-spacing: 0.05em;
        border: 2px solid transparent;
    }}
    .civis-timer[data-phase="green"] {{
        background: #eaf7ec;
        color: #1f7a34;
        border-color: #3f8f4a;
    }}
    .civis-timer[data-phase="amber"] {{
        background: #fff8d6;
        color: #8a6d1a;
        border-color: #c9a521;
    }}
    .civis-timer[data-phase="warning"] {{
        background: #fdecd6;
        color: #a04a10;
        border-color: #d68f1f;
    }}
    .civis-timer[data-phase="red"] {{
        background: #fbe0dd;
        color: #8a1a12;
        border-color: #b3261e;
    }}
    .civis-timer-label {{
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        opacity: 0.75;
    }}
    /* Onda 2 M2.4 — mystery-shopper reveal card on the verdict page.
       Deliberately noisier than a rubric card (purple/orange border)
       so an investor sees this is a different event from the judge
       verdict. */
    .civis-audit-header {{
        font-size: 1.15rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        color: #6a2b8c;
        margin: 0.6rem 0 0.5rem 0;
    }}
    .civis-audit-reveal {{
        border: 2px solid #6a2b8c;
        background: #f6ebfa;
        color: {NEUTRAL_TEXT};
        border-radius: 8px;
        padding: 0.9rem 1rem;
        line-height: 1.45;
        margin-bottom: 0.9rem;
    }}
    .civis-audit-criteria-label {{
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: {NEUTRAL_SUBTLE};
        margin: 0.6rem 0 0.35rem 0;
    }}
    .civis-audit-row {{
        border: 1px solid #dfe3ea;
        border-left: 4px solid #d68f1f;
        border-radius: 6px;
        padding: 0.55rem 0.8rem;
        margin-bottom: 0.4rem;
        background: white;
        color: {NEUTRAL_TEXT};
    }}
    .civis-audit-pill {{
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        padding: 0.12rem 0.55rem;
        border-radius: 999px;
        color: white;
        margin-right: 0.55rem;
        background: {NEUTRAL_SUBTLE};
    }}
    .civis-audit-pill[data-status="passed"] {{
        background: #1f7a34;
    }}
    .civis-audit-pill[data-status="failed"] {{
        background: #b3261e;
    }}
    .civis-audit-pill[data-status="inconclusive"] {{
        background: #b58900;
    }}
    .civis-audit-row-label {{
        font-weight: 600;
        color: {NEUTRAL_TEXT};
    }}
    .civis-audit-row-reason {{
        color: {NEUTRAL_SUBTLE};
        font-size: 0.88rem;
        margin-top: 0.2rem;
    }}
    /* Onda 2 T1.3 — a "queue" turn (customer waiting complaining).
       Shown as an assistant bubble but with a coloured border so the
       trainee sees it is not the persona speaking. Orange for warning
       phase, red for critical. */
    .civis-turn-queue {{
        border-left: 4px solid #d68f1f;
        background: #fdf3e2;
        padding: 0.6rem 0.85rem;
        border-radius: 4px;
        color: {NEUTRAL_TEXT};
        margin: 0.3rem 0;
    }}
    .civis-turn-queue[data-severity="critical"] {{
        border-left-color: #b3261e;
        background: #fbe2df;
    }}
    .civis-queue-label {{
        font-weight: 700;
        color: #8a4a10;
        margin-bottom: 0.25rem;
    }}
    .civis-turn-queue[data-severity="critical"] .civis-queue-label {{
        color: #7a1a12;
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
