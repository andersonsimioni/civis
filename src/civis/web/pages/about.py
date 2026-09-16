"""
"Sobre" page — product context for anyone who opens the app cold
(an investor who followed the deck link before the demo).

The copy is intentionally in pt-BR and avoids jargon: this is what the
first visitor reads if they don't click anywhere else.

Structure: `render()` holds the logic (testable), and the module tail
calls it so this file also works as a standalone Streamlit page target
for `st.Page` and `AppTest.switch_page`.
"""

from __future__ import annotations

import streamlit as st

from civis.web.theme import (
    ACCENT_COLOR,
    APP_TAGLINE,
    APP_TITLE,
    PRIMARY_COLOR,
    PRIMARY_COLOR_DEEP,
)


def render() -> None:
    """Render the About page."""
    st.title(f"{APP_TITLE} — {APP_TAGLINE}")
    st.markdown(
        """
        <div style="color:#5b6473; font-size:1.02rem; margin-bottom:1.2rem;">
            Simulador conversacional com juiz automático auditado —
            treinamento de atendimento a cidadãos em serviços públicos
            de identidade e registro.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        O **{APP_TITLE}** treina atendentes de balcão registral
        (cartórios, postos de identificação, secretarias de cidadania)
        em situações realistas: cidadão confuso, cidadão apressado e
        — a mais crítica — o **golpista** que tenta obter documentos
        alheios por engenharia social.

        Cada sessão coloca o atendente frente a uma persona operada
        por um modelo de linguagem restrito por uma máquina de estados.
        Ao final, um segundo modelo — que **nunca é o mesmo** que
        operou a persona — pontua a interação segundo uma rubrica
        pública de quatro critérios e cita literalmente os turnos que
        suportam cada nota.
        """
    )

    st.subheader("Por que isso importa")
    st.markdown(
        """
        <div class="civis-callout">
            Simuladores conversacionais existem. O que este projeto faz
            de diferente é medir explicitamente <b>se o próprio juiz
            automático pode ser manipulado pela persona que ele está
            avaliando</b> — o ataque JudgeDeceiver adaptado para juízos
            por rubrica, publicado aqui pela primeira vez. Sem essa
            medição, uma nota alta pode ser marketing; com ela, é
            evidência.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Como navegar")

    nav_col_1, nav_col_2 = st.columns(2)
    with nav_col_1:
        st.markdown(
            """
            **🎬 Nova sessão**  \n
            Três cenários prontos: cidadã confusa, cidadão apressado e
            fraudador. Cada cartão traz um comando pronto para copiar
            e rodar no terminal.

            **🗂️ Sessões passadas**  \n
            Lista filtrável por cenário, data, nota, contradição e
            vazamento. Cada linha abre um painel de correção lado a
            lado — transcript à esquerda, rubrica com citações
            clicáveis à direita.
            """
        )
    with nav_col_2:
        st.markdown(
            """
            **📊 Métricas**  \n
            Latência p95, custo estimado por sessão, validação M1
            híbrida (kappa inter-modelo + amostragem manual) e o
            resumo dos relatórios adversariais da Fase C — M2 (OWASP)
            e ASR do JudgeDeceiver-pointwise.

            **ℹ️ Sobre**  \n
            Você está aqui. Fecha o ciclo: quem visita o app cold sai
            entendendo o produto sem precisar de explicação oral.
            """
        )

    st.subheader("Números que contam a história")
    metrics_a, metrics_b, metrics_c, metrics_d = st.columns(4)
    metrics_a.metric("Perfis de persona", "3", help="Confuso, apressado, fraudador.")
    metrics_b.metric("Cenários prontos", "3", help="Um por perfil, versionados.")
    metrics_c.metric(
        "Critérios da rubrica",
        "4",
        help="Verificação, proteção de dados, protocolo, comunicação.",
    )
    metrics_d.metric(
        "Bateria adversarial",
        "≥ 50",
        help="Ataques OWASP LLM Top 10 categorizados e reproduzíveis.",
    )

    st.markdown("---")
    st.caption(
        f"Projeto acadêmico INE5448 · UFSC · Anderson Simioni Assunção · "
        f"paleta primária <span style='color:{PRIMARY_COLOR}'>■</span> {PRIMARY_COLOR} · "
        f"acento <span style='color:{ACCENT_COLOR}'>■</span> {ACCENT_COLOR} · "
        f"identidade em azul acadêmico <span style='color:{PRIMARY_COLOR_DEEP}'>■</span> "
        f"{PRIMARY_COLOR_DEEP}.",
        unsafe_allow_html=True,
    )


# When Streamlit's runtime loads this file as a page target (via
# st.Page(path)), the module body executes — render() must be called
# here for content to appear.
render()
