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
from civis.scenarios.audit_check import AuditOutcome, evaluate_hidden_agenda
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript
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


def render_audit_reveal(
    scenario_file: ScenarioFile,
    transcript: SessionTranscript,
) -> AuditOutcome | None:
    """Render the mystery-shopper reveal card (Onda 2 M2.4).

    Returns the computed :class:`AuditOutcome` when the scenario has a
    hidden agenda so the caller can persist it, or ``None`` when the
    scenario does not carry one (in which case nothing renders).

    Layout:

        - A prominent header row with a magnifying-glass icon and the
          "AUDITORIA REVELADA" copy.
        - The auditor's reveal_message rendered as a bordered card.
        - One status pill per success criterion: ``PASSOU`` / ``FALHOU``
          / ``INCONCLUSIVO``, with the reason from the evaluator.

    Colour palette lives in ``theme.py`` under ``.civis-audit-*`` so
    the card is styled by CSS class alone.
    """
    agenda = scenario_file.hidden_agenda
    if agenda is None:
        return None

    outcome = evaluate_hidden_agenda(agenda, transcript)

    st.markdown(
        "<div class='civis-audit-header'>"
        "🕵️ AUDITORIA REVELADA"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='civis-audit-reveal'>"
        f"{escape(agenda.reveal_message).replace(chr(10), '<br>')}"
        "</div>",
        unsafe_allow_html=True,
    )

    # Overall status pill first — makes the pass/fail visible at a glance.
    _render_audit_status_row(
        label="Resultado geral",
        status=outcome.overall_status,
        reason=agenda.description,
    )

    st.markdown(
        "<div class='civis-audit-criteria-label'>"
        "Critérios avaliados"
        "</div>",
        unsafe_allow_html=True,
    )
    for criterion_outcome in outcome.criteria_outcomes:
        _render_audit_status_row(
            label=(
                f"{criterion_outcome.action_required} → "
                f"antes de {criterion_outcome.before_action}"
            ),
            status=criterion_outcome.status,
            reason=criterion_outcome.reason,
        )

    return outcome


def _render_audit_status_row(label: str, status: str, reason: str) -> None:
    """Render one line of the audit reveal card.

    A status pill (colour by CSS class) on the left, a short reason
    on the right. Keeping this in a helper means the overall status
    and the per-criterion rows share exactly the same layout.
    """
    status_label = _AUDIT_STATUS_LABELS.get(status, status.upper())
    st.markdown(
        f"<div class='civis-audit-row'>"
        f"  <span class='civis-audit-pill' data-status='{escape(status)}'>"
        f"    {escape(status_label)}"
        f"  </span>"
        f"  <span class='civis-audit-row-label'>{escape(label)}</span>"
        f"  <div class='civis-audit-row-reason'>{escape(reason)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# pt-BR labels for the three possible statuses. Kept as a module-level
# constant so tests can import and assert on the exact copy.
_AUDIT_STATUS_LABELS: dict[str, str] = {
    "passed": "PASSOU",
    "failed": "FALHOU",
    "inconclusive": "INCONCLUSIVO",
}
