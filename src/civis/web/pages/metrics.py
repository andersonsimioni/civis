"""
"Métricas" page skeleton — telemetry, cost and adversarial panels land in T5.

For now, we render the four intended sections as placeholders so the
navigation smoke test verifies the page mounts against the shipped
report files without exercising the aggregation math yet.
"""

from __future__ import annotations

import streamlit as st

from civis.web.data_access import load_adversarial_v1, load_judge_deceiver_v1


def render() -> None:
    """Render the Métricas page skeleton."""
    st.title("Métricas")
    st.markdown(
        "Telemetria M4, custo estimado por sessão e resumo das provas "
        "de segurança da Fase C. Painéis completos entram no passo T5."
    )

    adv = load_adversarial_v1()
    jd = load_judge_deceiver_v1()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latência p95", "aguardando", help="Painel completo em T5")
    col2.metric("Custo/sessão", "aguardando", help="Painel completo em T5")
    if adv:
        first = adv["reports"][0]
        col3.metric("M2 · Defesa", f"{first['defended']}/{first['total']}")
    else:
        col3.metric("M2 · Defesa", "—")
    if jd:
        first = jd["reports"][0]
        col4.metric("ASR JudgeDeceiver", f"{first['overall_asr'] * 100:.0f}%")
    else:
        col4.metric("ASR JudgeDeceiver", "—")


render()
