"""
"Sessões passadas" page — filters, list, and side-by-side correction panel.

Flow:

    1. Sidebar filters (scenario, date range, score bounds, contradiction
       and leak toggles) narrow down the list.
    2. Left of the main column, the list renders as a clickable table
       with one 'Abrir' button per row. Clicking stores the session id
       in st.session_state; a rerun then paints the drill-down.
    3. When a session is selected, the layout switches to a 60/40 split:
       chat transcript on the left, verdict cards + contradictions +
       honeytoken leaks on the right.
    4. ONDA 3 (R1.3): a 'Ver replay' button on the detail header opens
       the replay timeline above the transcript. Clicking an event dot
       on that bar highlights the corresponding turn — same mechanism
       the verdict citations use.

The click-to-highlight interaction (verdict citation → transcript scroll
and flash) is implemented in verdict_view + chat_view: the citation
button stores a target turn index in st.session_state, and chat_view
injects the highlight CSS/JS on the next rerun.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from civis.web.chat_view import render_transcript
from civis.web.data_access import (
    SessionSummary,
    filter_sessions,
    list_sessions,
    load_session_detail,
)
from civis.web.formatting import (
    format_score_average,
    format_session_datetime,
    scenario_label,
)
from civis.web.replay import build_replay_timeline
from civis.web.replay_view import render_replay_timeline
from civis.web.state import (
    SELECTED_SESSION_KEY,
    SHOW_REPLAY_KEY,
    get_sessions_dir,
)
from civis.web.verdict_view import (
    render_contradictions,
    render_honeytoken_leaks,
    render_verdict,
)


def render() -> None:
    """Render the Sessões passadas page (list + drill-down)."""
    st.title("Sessões passadas")

    all_sessions = list_sessions(get_sessions_dir())
    if not all_sessions:
        _render_empty_state()
        return

    filtered = _render_sidebar_filters(all_sessions)

    # If the user has already clicked into a session, show the drill-down
    # instead of the list. A "voltar" button restores the list view.
    selected_id = st.session_state.get(SELECTED_SESSION_KEY)
    if selected_id and any(s.session_id == selected_id for s in all_sessions):
        _render_detail_panel(selected_id)
        return

    _render_session_list(filtered, total=len(all_sessions))


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------


def _render_empty_state() -> None:
    """Copy shown when there are no sessions to list at all."""
    st.markdown(
        '<div class="civis-empty">'
        "Nenhuma sessão ainda. Clique em <b>Nova sessão</b> para começar, "
        "ou execute <code>civis session</code> no terminal para gerar uma."
        "</div>",
        unsafe_allow_html=True,
    )


def _render_sidebar_filters(
    sessions: list[SessionSummary],
) -> list[SessionSummary]:
    """
    Render the filter widgets in the sidebar and return the filtered list.
    Every widget writes to session_state under a namespaced key so state
    survives a rerun triggered by a click somewhere else.
    """
    st.sidebar.header("Filtros")

    scenarios_seen = sorted({s.scenario_id for s in sessions})
    scenario_choice = st.sidebar.multiselect(
        "Cenário",
        options=scenarios_seen,
        format_func=scenario_label,
        default=[],
        help="Deixe vazio para incluir todos os cenários.",
        key="filter_scenarios",
    )

    # Date range with a sensible default that includes every session on disk.
    dates_seen = [_iso_to_date(s.created_at) for s in sessions if s.created_at]
    dates_seen = [d for d in dates_seen if d is not None]
    date_from_default = min(dates_seen) if dates_seen else date.today()
    date_to_default = max(dates_seen) if dates_seen else date.today()

    date_range = st.sidebar.date_input(
        "Período",
        value=(date_from_default, date_to_default),
        format="DD/MM/YYYY",
        key="filter_date_range",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        date_from, date_to = date_range
    else:
        date_from = date_from_default
        date_to = date_to_default

    score_range = st.sidebar.slider(
        "Nota média",
        min_value=0.0,
        max_value=5.0,
        value=(0.0, 5.0),
        step=0.5,
        key="filter_score_range",
    )

    require_contradictions = _tri_state_toggle(
        "Contradições",
        help_text="Filtrar sessões com pelo menos uma contradição factual detectada.",
        key="filter_contradictions",
    )
    require_leaks = _tri_state_toggle(
        "Vazamento de honeytoken",
        help_text="Filtrar sessões com pelo menos um honeytoken vazado.",
        key="filter_leaks",
    )

    return filter_sessions(
        sessions,
        scenario_ids=scenario_choice or None,
        date_from=date_from,
        date_to=date_to,
        min_avg_score=score_range[0] if score_range[0] > 0 else None,
        max_avg_score=score_range[1] if score_range[1] < 5 else None,
        require_contradictions=require_contradictions,
        require_honeytoken_leaks=require_leaks,
    )


def _tri_state_toggle(label: str, help_text: str, key: str) -> bool | None:
    """
    'Todas / Só com / Só sem' radio — three-state boolean-ish filter.
    Returns True, False or None so the data_access layer can distinguish
    'filter for X' from 'ignore this dimension'.
    """
    choice = st.sidebar.radio(
        label,
        options=["Todas", "Somente com", "Somente sem"],
        index=0,
        horizontal=True,
        help=help_text,
        key=key,
    )
    if choice == "Somente com":
        return True
    if choice == "Somente sem":
        return False
    return None


def _render_session_list(
    filtered: list[SessionSummary],
    total: int,
) -> None:
    """Render the filtered list as a compact table with 'Abrir' buttons."""
    st.caption(
        f"Exibindo {len(filtered)} de {total} sessão(ões)."
        if len(filtered) < total
        else f"{total} sessão(ões) no total."
    )

    if not filtered:
        st.markdown(
            '<div class="civis-empty">'
            "Nenhuma sessão bate com os filtros atuais. Ajuste no menu à esquerda."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # 6-column layout: id, scenario, date, turns, avg, alerts, button.
    header_cols = st.columns([2.8, 2.4, 1.6, 0.9, 1.0, 1.6, 1.2])
    _write_header(header_cols)
    st.markdown("<hr style='margin:0.3rem 0 0.8rem 0;' />", unsafe_allow_html=True)

    for row in filtered:
        cols = st.columns([2.8, 2.4, 1.6, 0.9, 1.0, 1.6, 1.2])
        cols[0].markdown(f"**{row.session_id}**")
        cols[1].write(scenario_label(row.scenario_id))
        cols[2].write(format_session_datetime(row.created_at))
        cols[3].write(str(row.total_turns))
        cols[4].write(
            format_score_average(_int_scores(row))
            if row.average_score is not None
            else "—"
        )
        cols[5].write(_alerts_badge(row))
        if cols[6].button("Abrir", key=f"open_{row.session_id}"):
            st.session_state[SELECTED_SESSION_KEY] = row.session_id
            st.rerun()


def _write_header(cols: list) -> None:
    labels = ["Sessão", "Cenário", "Data", "Turnos", "Média", "Sinais", ""]
    for col, label in zip(cols, labels, strict=False):
        col.markdown(f"<b>{label}</b>", unsafe_allow_html=True)


def _int_scores(row: SessionSummary) -> list[int]:
    """
    We only have the average, not the raw scores, in a SessionSummary.
    Round-trip the average as a two-element list so format_score_average
    reproduces it consistently. This is a display shim, not truth.
    """
    if row.average_score is None:
        return []
    return [round(row.average_score * 2)]  # multiplied so we keep .5 fidelity


def _alerts_badge(row: SessionSummary) -> str:
    """Compact pt-BR string flagging contradictions and honeytoken leaks."""
    flags: list[str] = []
    if row.has_contradictions:
        flags.append("⚠️ contradição")
    if row.has_honeytoken_leaks:
        flags.append("🕵️ vazamento")
    if not flags:
        return "—"
    return " · ".join(flags)


# ---------------------------------------------------------------------------
# Drill-down view (D.2)
# ---------------------------------------------------------------------------


def _render_detail_panel(session_id: str) -> None:
    """Render the 60/40 side-by-side correction panel for one session."""
    detail = load_session_detail(session_id, get_sessions_dir())
    if detail is None:
        st.error(f"Sessão `{session_id}` não encontrada — talvez tenha sido removida.")
        if st.button("← Voltar à lista"):
            st.session_state[SELECTED_SESSION_KEY] = None
            st.rerun()
        return

    header_col_left, header_col_mid, header_col_right = st.columns([3, 1.2, 1])
    with header_col_left:
        st.markdown(
            f"### {session_id} · {scenario_label(detail.metadata.scenario_id)}"
        )
        st.caption(
            f"Criada em {format_session_datetime(detail.metadata.created_at)} · "
            f"persona: `{detail.metadata.persona_provider_name}` · "
            f"juiz: `{detail.metadata.judge_provider_name or '—'}`"
        )
    with header_col_mid:
        _render_replay_toggle_button()
    with header_col_right:
        if st.button("← Voltar", use_container_width=True):
            st.session_state[SELECTED_SESSION_KEY] = None
            st.session_state[SHOW_REPLAY_KEY] = False
            st.rerun()

    # ONDA 3 (R1.3): timeline sits ABOVE the two columns so it spans
    # the whole width — a dashboard-y feel that fits the 'replay
    # tipo YouTube' framing better than a cramped bar inside the
    # transcript column.
    if st.session_state.get(SHOW_REPLAY_KEY, False):
        events = build_replay_timeline(
            transcript=detail.transcript,
            verdict=detail.verdict,
            contradictions=detail.contradictions,
            honeytokens=detail.honeytoken_leaks,
        )
        render_replay_timeline(
            events=events,
            total_turns=len(detail.transcript.turns),
            key_prefix=f"replay_{session_id}",
        )
        st.markdown("<hr style='margin:0.6rem 0;' />", unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Transcript")
        with st.container(border=False):
            render_transcript(detail.transcript)

    with right:
        if detail.verdict is not None:
            render_verdict(detail.verdict)
        else:
            st.info(
                "Esta sessão foi rodada sem o passo de avaliação do juiz "
                "(--no-judge). Rode novamente com juiz habilitado para "
                "ver a rubrica preenchida."
            )
        render_contradictions(detail.contradictions)
        render_honeytoken_leaks(detail.honeytoken_leaks)


def _render_replay_toggle_button() -> None:
    """
    Header button that toggles the replay timeline visibility.

    We keep it as an ordinary button (not ``st.toggle``) because the
    label needs to communicate the current state: 'Ver replay' opens
    the bar, 'Fechar replay' hides it. Streamlit's ``st.toggle``
    reads well only when the label describes a state noun, not a
    verb.
    """
    is_open = bool(st.session_state.get(SHOW_REPLAY_KEY, False))
    label = "Fechar replay" if is_open else "Ver replay"
    icon = "▲" if is_open else "▶"
    if st.button(
        f"{icon} {label}",
        key="toggle_replay",
        use_container_width=True,
        help=(
            "Abre a linha do tempo do atendimento com marcadores por evento"
            if not is_open
            else "Esconde a linha do tempo"
        ),
    ):
        st.session_state[SHOW_REPLAY_KEY] = not is_open
        st.rerun()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_to_date(iso_text: str) -> date | None:
    """Extract the calendar date from an ISO string; None on failure."""
    if not iso_text:
        return None
    try:
        return datetime.fromisoformat(iso_text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


render()
