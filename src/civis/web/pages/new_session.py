"""
"Nova sessão" page skeleton — full REPL wired in T6.

For now, we render the scenario selector and a call-to-action so the
navigation smoke test hits every page without a KeyError.
"""

from __future__ import annotations

import streamlit as st


def render() -> None:
    """Render the Nova sessão page (skeleton stage — full REPL in T6)."""
    st.title("Nova sessão")
    st.markdown(
        "Escolha um cenário e comece um atendimento simulado. "
        "O modo demo dispensa modelos remotos e permite testar a "
        "interface sem depender de Ollama ou Anthropic."
    )
    st.info(
        "REPL em construção — página completa entra em T6 do plano da Fase D. "
        "Enquanto isso, use `civis session --scenario ...` pelo terminal."
    )


render()
