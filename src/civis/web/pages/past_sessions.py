"""
"Sessões passadas" page skeleton — filters + drill-down land in T3-T4.

For now, we list the sessions we can see on disk so the smoke test can
assert the page mounts against the demo fixture without hitting the
full transcript renderer.
"""

from __future__ import annotations

import streamlit as st

from civis.web.data_access import list_sessions
from civis.web.formatting import scenario_label
from civis.web.state import get_sessions_dir


def render() -> None:
    """Render the Sessões passadas page (skeleton stage — full panel in T3)."""
    st.title("Sessões passadas")
    sessions = list_sessions(get_sessions_dir())
    if not sessions:
        st.markdown(
            '<div class="civis-empty">'
            "Nenhuma sessão ainda. Clique em <b>Nova sessão</b> para começar, "
            "ou execute <code>civis session</code> no terminal para gerar uma."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(sessions)} sessão(ões) na pasta atual.")
    for row in sessions:
        st.write(
            f"- **{row.session_id}** · {scenario_label(row.scenario_id)} · "
            f"{row.total_turns} turnos"
        )
    st.info(
        "Filtros e painel de correção lado a lado entram nos passos T3–T4 "
        "do plano da Fase D."
    )


render()
