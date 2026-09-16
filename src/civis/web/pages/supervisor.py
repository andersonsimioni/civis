"""
"Gestão" (Supervisor Dashboard) page — ONDA 3, D2.2.

Aggregates every session on disk into KPIs, per-criterion breakdowns
and short ranking tables so a supervisor can spot which attendants
need retraining and which sessions to review.

Layout:

    Row 1 — four ``st.metric`` cards (KPIs).
    Row 2 — bar chart of mean score by rubric criterion.
    Row 3 — line chart of sessions per day.
    Row 4 — two-column layout: worst sessions | best sessions.
             Each table row carries an 'Abrir' button that stores the
             session id in ``SELECTED_SESSION_KEY`` and switches to
             the "Sessões passadas" drill-down.

Design notes:
    - Every widget is native Streamlit — no Altair / Plotly / matplotlib
      and no pandas either (charts consume plain ``dict[str, list]``,
      matching what :mod:`civis.web.pages.metrics` already does).
    - Empty state (no sessions) shows a friendly copy instead of a
      barrage of zero cards.
    - Clicking a session in the ranking tables reuses the same state
      key ``past_sessions.py`` reads, so the two pages stay in sync
      without any extra wiring.
"""

from __future__ import annotations

import streamlit as st

from civis.web.formatting import (
    criterion_label,
    format_score_average,
    format_session_datetime,
    scenario_label,
)
from civis.web.state import SELECTED_SESSION_KEY, get_sessions_dir
from civis.web.supervisor import (
    SessionRanking,
    SupervisorMetrics,
    compute_supervisor_metrics,
)


def render() -> None:
    """Render the supervisor dashboard."""
    st.title("Painel do supervisor")
    st.caption(
        "Agrega todas as sessões salvas em disco. Cada bloco cruza "
        "atendentes, cenários e critérios — clique num item das tabelas "
        "para abrir a sessão em detalhe."
    )

    metrics = compute_supervisor_metrics(get_sessions_dir())

    if metrics.total_sessions == 0:
        _render_empty_state()
        return

    _render_kpis(metrics)
    st.markdown("---")

    _render_criterion_chart(metrics)
    st.markdown("---")

    _render_sessions_over_time(metrics)
    st.markdown("---")

    _render_ranking_tables(metrics)


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


def _render_empty_state() -> None:
    """Copy shown when no session has been recorded yet."""
    st.markdown(
        '<div class="civis-empty">'
        "Nenhuma sessão registrada ainda. Rode uma sessão em "
        "<b>Nova sessão</b> ou pelo CLI (<code>civis session</code>) "
        "para começar a alimentar o painel."
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------


def _render_kpis(metrics: SupervisorMetrics) -> None:
    """Four top-level st.metric cards: sessions, agents, mean score, kappa placeholder."""
    cols = st.columns(4)
    cols[0].metric("Total de sessões", metrics.total_sessions)
    cols[1].metric("Atendentes únicos", metrics.unique_agents)
    cols[2].metric(
        "Nota média",
        _format_mean_score(metrics.mean_score),
        help="Média das notas médias por sessão, considerando apenas sessões com juiz.",
    )
    # Kappa placeholder — the hybrid M1 study is scheduled for the
    # window 20/10-01/12 (roadmap). Until then, show a dash rather
    # than a fake number.
    cols[3].metric(
        "Kappa (M1)",
        "—",
        help=(
            "Índice de concordância inter-modelo. Preenchido após a "
            "janela de estudo M1 (20/10-01/12)."
        ),
    )


def _format_mean_score(value: float | None) -> str:
    """Human-friendly rendering for the mean-score KPI card."""
    if value is None:
        return "—"
    return f"{value:.2f}"


# ---------------------------------------------------------------------------
# Row 2: bar chart of scores by criterion
# ---------------------------------------------------------------------------


def _render_criterion_chart(metrics: SupervisorMetrics) -> None:
    """
    Native Streamlit bar chart of the mean score per rubric criterion.

    ``st.bar_chart`` accepts a plain dict-of-lists where the values are
    the bar heights and the keys become the legend labels. Order comes
    from ``score_distribution``, which is already stable.
    """
    st.subheader("Nota média por critério")
    chart_data: dict[str, list[float]] = {
        criterion_label(key): [round(value, 2)]
        for key, value in metrics.score_distribution.items()
    }
    st.bar_chart(chart_data, height=260, use_container_width=True)


# ---------------------------------------------------------------------------
# Row 3: sessions per day
# ---------------------------------------------------------------------------


def _render_sessions_over_time(metrics: SupervisorMetrics) -> None:
    """
    Line chart of sessions created per day. If every session lives on
    the same day the chart still renders — a single point at the top
    of the range reads as 'all activity happened today'.

    We pass a dict-of-lists to keep the page free of pandas: the key
    'Sessões' becomes the series label and Streamlit uses the list
    index as the x axis. That's a slight cosmetic hit vs. real dates,
    but it stays consistent with the rest of the app.
    """
    st.subheader("Sessões ao longo do tempo")
    if not metrics.sessions_over_time:
        st.caption("Sem dados temporais registrados.")
        return
    labels = [day.isoformat() for day, _ in metrics.sessions_over_time]
    counts = [count for _, count in metrics.sessions_over_time]
    chart_data = {"Sessões": counts}
    st.line_chart(chart_data, height=260, use_container_width=True)
    # Caption shows the first / last date so the x-axis-as-index does
    # not leave the viewer guessing.
    if labels:
        st.caption(f"Período: {labels[0]} → {labels[-1]}")


# ---------------------------------------------------------------------------
# Row 4: ranking tables
# ---------------------------------------------------------------------------


def _render_ranking_tables(metrics: SupervisorMetrics) -> None:
    """Two side-by-side tables — worst and best sessions."""
    st.subheader("Rankings")
    left, right = st.columns(2)
    with left:
        st.markdown("**Piores sessões**")
        _render_ranking_rows(
            metrics.worst_sessions,
            key_prefix="worst",
            empty_message="Sem sessões avaliadas ainda.",
        )
    with right:
        st.markdown("**Melhores sessões**")
        _render_ranking_rows(
            metrics.best_sessions,
            key_prefix="best",
            empty_message="Sem sessões avaliadas ainda.",
        )


def _render_ranking_rows(
    rows: list[SessionRanking],
    *,
    key_prefix: str,
    empty_message: str,
) -> None:
    """
    Render one ranking table. Each row is a compact
    ``session_id · cenário · atendente · nota · data · Abrir``
    layout using ``st.columns`` so the 'Abrir' button lives on the
    right side.
    """
    if not rows:
        st.caption(empty_message)
        return
    for row in rows:
        cols = st.columns([2.2, 1.5, 1.2, 0.9, 1.4, 1.0])
        cols[0].markdown(f"`{row.session_id}`")
        cols[1].write(scenario_label(row.scenario_id))
        cols[2].write(row.agent_name)
        cols[3].write(format_score_average([round(row.average_score * 2)]))
        cols[4].write(format_session_datetime(row.created_at))
        if cols[5].button(
            "Abrir",
            key=f"supervisor_{key_prefix}_open_{row.session_id}",
            use_container_width=True,
        ):
            # Reuse the same key that the past-sessions page reads so
            # the drill-down opens on the referenced session.
            st.session_state[SELECTED_SESSION_KEY] = row.session_id
            st.switch_page("pages/past_sessions.py")


render()
