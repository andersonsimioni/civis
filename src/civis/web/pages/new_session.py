"""
"Nova sessão" page — investor-facing landing that showcases the three
scripted scenarios and points at the CLI as the runner for now.

The live REPL is Task T6 of the Phase D plan (not shipped yet). For
the pitch demo the flow is:

    1. Investor reads the scenario cards on this page.
    2. Presenter opens a terminal side by side.
    3. Presenter runs the exact command copied from the card.

Once T6 lands the same page renders the chat REPL under the cards.
Until then, the cards + copy-friendly command block already look like a
real product page — no placeholder, no 'skeleton stage' info banner.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from civis.web.formatting import scenario_label
from civis.web.theme import PRIMARY_COLOR


@dataclass(frozen=True)
class _ScenarioCard:
    """One scenario the demo tour can play against."""

    scenario_id: str
    persona_kind: str          # "confused" | "aggressive" | "fraudster"
    difficulty: str            # human-facing pt-BR ("Fácil", "Média", "Difícil")
    icon: str                  # single emoji, anchors the card visually
    pitch: str                 # one-sentence hook
    what_happens: str          # 2-3 lines of narrative
    watch_for: str             # what the trainee (and the investor) should notice


_SCENARIOS: list[_ScenarioCard] = [
    _ScenarioCard(
        scenario_id="certificate_duplicate_confused_v1",
        persona_kind="Cidadã confusa",
        difficulty="Fácil",
        icon="🧓",
        pitch=(
            "Dona Iracema quer uma segunda via de certidão, mas trocou o "
            "nome do cônjuge e nunca ouviu falar em CPF."
        ),
        what_happens=(
            "A persona chega ansiosa, mistura fatos e resiste a "
            "protocolos que soam burocráticos. O atendente precisa "
            "verificar identidade sem constranger."
        ),
        watch_for=(
            "Verificação de fatos e comunicação paciente. Este é o "
            "cenário de aquecimento — juiz deve dar nota alta se o "
            "atendente confirmar dados antes de emitir."
        ),
    ),
    _ScenarioCard(
        scenario_id="rg_urgent_aggressive_v1",
        persona_kind="Cidadão apressado",
        difficulty="Média",
        icon="⏰",
        pitch=(
            "Um cidadão exige a segunda via do RG na hora, alegando "
            "reunião de trabalho, e sobe o tom quando o atendente pede "
            "documentos."
        ),
        what_happens=(
            "Pressão emocional real: ameaça de reclamação em ouvidoria, "
            "tentativa de pular a fila. O protocolo continua o mesmo."
        ),
        watch_for=(
            "Aderência ao protocolo sob pressão. Nota alta exige recusar "
            "a exceção com firmeza e educação."
        ),
    ),
    _ScenarioCard(
        scenario_id="certificate_thirdparty_fraudster_v1",
        persona_kind="Fraudador social",
        difficulty="Difícil",
        icon="🕵️",
        pitch=(
            "Alguém tenta obter a certidão de outra pessoa por "
            "engenharia social — pretexto de \"tia doente\" e pressão "
            "emocional."
        ),
        what_happens=(
            "Honeytokens plantados no cenário; se o atendente ceder e "
            "revelar dados sensíveis, o painel de segurança detecta e "
            "reporta na página Sessões passadas."
        ),
        watch_for=(
            "Proteção de dados. Este é o cenário-teste do diferencial "
            "competitivo — juiz e detector de honeytokens trabalham "
            "juntos aqui."
        ),
    ),
]


def render() -> None:
    """Render the Nova sessão landing (three scenario cards + CLI hint)."""
    st.title("Nova sessão")
    st.markdown(
        "Escolha um dos três cenários abaixo e execute o comando de "
        "atendimento simulado no terminal. Cada rodada gera um "
        "transcript, um verdict do juiz automático e os sidecars de "
        "contradição e honeytoken — visíveis logo em seguida na aba "
        "**Sessões passadas**."
    )

    _render_scenario_cards()
    st.markdown("---")
    _render_runner_hint()
    _render_repl_status()


# ---------------------------------------------------------------------------
# Scenario cards
# ---------------------------------------------------------------------------


def _render_scenario_cards() -> None:
    """Three-column layout, one card per scripted scenario."""
    cols = st.columns(3, gap="medium")
    for col, card in zip(cols, _SCENARIOS, strict=True):
        with col:
            _render_scenario_card(card)


def _render_scenario_card(card: _ScenarioCard) -> None:
    """
    Render one scenario as a bordered card with icon, title, pitch,
    two subsections and a copy-friendly CLI command inside a code block.
    """
    diff_color = _difficulty_color(card.difficulty)
    friendly_id = scenario_label(card.scenario_id)

    st.markdown(
        f"""
        <div class="civis-scenario-card">
            <div class="civis-scenario-icon">{card.icon}</div>
            <div class="civis-scenario-title">{friendly_id}</div>
            <div class="civis-scenario-meta">
                <span class="civis-chip">{card.persona_kind}</span>
                <span class="civis-chip"
                      style="background:{diff_color};color:white;">
                    {card.difficulty}
                </span>
            </div>
            <p class="civis-scenario-pitch">{card.pitch}</p>
            <p class="civis-scenario-body"><b>Como corre:</b> {card.what_happens}</p>
            <p class="civis-scenario-body"><b>Observe:</b> {card.watch_for}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.code(
        f"python -m civis session --scenario {card.scenario_id}",
        language="bash",
    )


# ---------------------------------------------------------------------------
# Runner hint + REPL status
# ---------------------------------------------------------------------------


def _render_runner_hint() -> None:
    """Explain the pre-REPL flow: run the CLI, then refresh the sidebar."""
    st.subheader("Como executar agora")
    st.markdown(
        """
        1. **Escolha um cenário** entre os três acima e copie o comando.
        2. **Abra um terminal** na raiz do repositório e cole o comando.
        3. **Converse** com a persona pelo prompt — o CLI aceita entrada
           linha a linha. Encerre com `Ctrl+Z` (Windows) ou `Ctrl+D` (Unix).
        4. **Abra a aba Sessões passadas** desta interface — a nova
           sessão aparece no topo da lista, com verdict e citações.
        """
    )
    st.markdown(
        f"""
        <div class="civis-callout">
            <b style="color:{PRIMARY_COLOR}">Dica de demo:</b>
            durante o pitch, rode <code>certificate_thirdparty_fraudster_v1</code>.
            É o cenário onde o painel de segurança brilha — honeytokens,
            proteção de dados e o diferencial competitivo que separa
            este projeto de um simulador comum.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_repl_status() -> None:
    """
    Honest status of the in-page REPL. Kept explicit so the investor
    reading the app cold does not think this is the finished product.
    """
    with st.expander("Por que ainda não tem chat em tela cheia aqui?", expanded=False):
        st.markdown(
            """
            O chat REPL dentro da página é o **Task T6** do plano da
            Fase D e depende de integração com streaming de tokens.
            Para o pitch de 15/12/2026, a demo ao vivo roda pelo CLI —
            o mesmo caminho que o CI e os testes usam, o que garante
            que o que aparece na demo é exatamente o que roda em
            produção. O chat na página web entra no fast-follow logo
            depois do pitch.
            """
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _difficulty_color(label: str) -> str:
    """Colour chip for the difficulty label. Traffic-light semantics."""
    if label == "Fácil":
        return "#3f8f4a"
    if label == "Média":
        return "#c25a1a"
    return "#b3261e"  # Difícil


render()
