"""
"Sobre" page — 3-4 paragraphs of product context for anyone who opens the
app cold (an investor who followed the deck link before the demo).

The copy is intentionally in pt-BR and avoids jargon: this is what the
first visitor reads if they don't click anywhere else.

Structure: `render()` holds the logic (testable), and the module tail
calls it so this file also works as a standalone Streamlit page target
for `st.Page` and `AppTest.switch_page`.
"""

from __future__ import annotations

import streamlit as st

from civis.web.theme import APP_TAGLINE, APP_TITLE, PRIMARY_COLOR


def render() -> None:
    """Render the About page."""
    st.title(f"{APP_TITLE} — {APP_TAGLINE}")

    st.markdown(
        f"""
        O **{APP_TITLE}** é um simulador conversacional que treina atendentes
        de balcão registral (cartórios, postos de identificação, secretarias
        de cidadania) em situações realistas: cidadão confuso, cidadão
        apressado e — a mais crítica — o **golpista** que tenta obter
        documentos alheios por engenharia social.

        Cada sessão coloca o atendente frente a uma persona operada por um
        modelo de linguagem restrito por uma máquina de estados. Ao final,
        um segundo modelo — que **nunca é o mesmo** que operou a persona —
        pontua a interação segundo uma rubrica pública de quatro critérios
        e cita literalmente os turnos que suportam cada nota.
        """
    )

    st.subheader("Por que isso importa")
    st.markdown(
        """
        Simuladores conversacionais existem. O que este projeto faz de
        diferente é medir explicitamente **se o próprio juiz automático
        pode ser manipulado pela persona que ele está avaliando** — o
        ataque JudgeDeceiver adaptado para juízos por rubrica, publicado
        aqui pela primeira vez. Sem essa medição, uma nota alta pode ser
        marketing; com ela, é evidência.
        """
    )

    st.subheader("Como navegar")
    st.markdown(
        """
        - **Nova sessão** — abre um atendimento simulado, com seleção de
          cenário. Modo demo dispensa modelo remoto.
        - **Sessões passadas** — lista tudo o que já foi corrido, com
          filtros por cenário, data, nota, contradição e vazamento.
          Clique em uma linha para ver o painel de correção lado a lado.
        - **Métricas** — latência p95, custo estimado por sessão, e o
          resumo dos relatórios adversariais da Fase C (M2 e ASR do
          JudgeDeceiver-pointwise).
        """
    )

    st.markdown("---")
    st.caption(
        "Projeto acadêmico INE5448 · UFSC · Anderson Simioni Assunção · "
        f"paleta primária {PRIMARY_COLOR}"
    )


# When Streamlit's runtime loads this file as a page target (via
# st.Page(path)), the module body executes — render() must be called
# here for content to appear.
render()
