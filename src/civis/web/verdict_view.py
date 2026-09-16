"""
Judge verdict renderer for the correction panel.

For each rubric criterion we build a card with:

    - a coloured score badge (0-5 → colour ramp defined in theme.py),
    - the pt-BR criterion label,
    - the rationale in prose,
    - one button per cited turn — clicking a button stores the turn
      index in st.session_state and triggers a rerun so chat_view can
      inject the highlight CSS/JS on the left panel.

Contradictions and honeytoken leaks show up as two separate collapsible
sections BELOW the criteria — they are session-level signals, not
per-criterion scores.
"""

from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from civis.judge.rubric import JudgeVerdict
from civis.web.formatting import (
    criterion_label,
    format_score_badge_html,
)
from civis.web.state import HIGHLIGHT_TURN_KEY
from civis.web.theme import score_color


def render_verdict(verdict: JudgeVerdict) -> None:
    """
    Render the four rubric cards plus the overall summary block.

    Callers place this inside the right column of the drill-down layout.
    """
    st.subheader("Resumo do juiz")
    st.markdown(
        f'<div class="civis-card">{escape(verdict.overall_summary)}</div>',
        unsafe_allow_html=True,
    )

    st.subheader("Critérios")
    for idx, criterion in enumerate(verdict.criteria):
        _render_criterion_card(criterion, card_index=idx)


def _render_criterion_card(criterion: Any, card_index: int) -> None:
    """
    Render one CriterionVerdict as an expandable card. The header carries
    the score badge; the body shows rationale + cited-turn buttons.
    """
    badge_html = format_score_badge_html(
        criterion.score,
        score_color(criterion.score),
    )
    label = criterion_label(criterion.criterion.value)
    header_html = f"{badge_html} <b>{escape(label)}</b>"

    # Every card opens by default so the investor doesn't have to click
    # around during the demo.
    with st.expander(label=label, expanded=True):
        st.markdown(header_html, unsafe_allow_html=True)
        st.write(criterion.rationale)

        if not criterion.cited_turns:
            st.caption("Sem citações — critério atendido sem evento relevante.")
            return

        st.caption("Citações no transcript:")
        for cite_idx, cite in enumerate(criterion.cited_turns):
            _render_citation(
                criterion_key=criterion.criterion.value,
                card_index=card_index,
                cite_idx=cite_idx,
                turn_index=cite.turn_index,
                excerpt=cite.excerpt,
            )


def _render_citation(
    criterion_key: str,
    card_index: int,
    cite_idx: int,
    turn_index: int,
    excerpt: str,
) -> None:
    """
    Show the excerpt as a quoted block and a button that scrolls the
    transcript. The button key must be unique across cards.
    """
    st.markdown(
        f'<div class="civis-quote">"{escape(excerpt)}"</div>',
        unsafe_allow_html=True,
    )
    button_key = f"cite_{criterion_key}_{card_index}_{cite_idx}"
    if st.button(f"↗ Ver turno {turn_index}", key=button_key):
        # chat_view sits ABOVE the right column in the drill-down layout,
        # so we need the whole page to re-execute for the highlight
        # CSS/JS block to reach the transcript. Setting the state key
        # then calling st.rerun() achieves that.
        st.session_state[HIGHLIGHT_TURN_KEY] = turn_index
        st.rerun()


def render_contradictions(payload: dict[str, Any] | None) -> None:
    """
    Render the contradictions sidecar as a collapsible section. When
    total=0 we still show the block (with a green-friendly copy) so the
    investor sees the check exists.
    """
    if payload is None:
        return
    contradictions = payload.get("contradictions", [])
    total = len(contradictions)
    header = f"⚠️ Contradições detectadas ({total})"

    with st.expander(header, expanded=total > 0):
        if total == 0:
            st.success(
                "Nenhuma contradição factual detectada nesta sessão. "
                "A persona manteve os fatos consistentes ao longo dos turnos."
            )
            return
        for row in contradictions:
            st.markdown(
                f"- Turno **{row['turn_index']}** · fato "
                f"`{row['fact_key']}`: antes "
                f"\"{escape(str(row['prior_value']))}\", agora "
                f"\"{escape(str(row['new_value']))}\"."
            )


def render_honeytoken_leaks(payload: dict[str, Any] | None) -> None:
    """Render the honeytoken-leak sidecar. Zero leaks stays visible."""
    if payload is None:
        return
    leaks = payload.get("leaks", [])
    total = len(leaks)
    header = f"🕵️ Vazamento de honeytoken ({total})"

    with st.expander(header, expanded=total > 0):
        if total == 0:
            st.success(
                "Nenhum honeytoken plantado no cenário vazou nesta sessão. "
                "A blindagem do prompt segurou os dados sensíveis."
            )
            return
        for row in leaks:
            fact_key = row["fact_key"]
            turn_index = row["turn_index"]
            context = row.get("context", "")
            st.markdown(
                f"- Turno **{turn_index}** · honeytoken "
                f"`{fact_key}`: "
                f"\"{escape(str(context))}\""
            )
