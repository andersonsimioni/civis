"""
"Nova sessão" page — D+.1 landing: clickable scenario cards + random start.

The old copy-CLI-command flow was ripped out on Anderson's request:
the trainee now conducts the whole simulation inside the browser,
starting from this landing. The full chat REPL, the "Encerrar e
avaliar" flow and the inline verdict view land in D+.2..D+.5.

Session state keys (all prefixed ``civis.chat.`` so they never collide
with the filters used by the other pages):

    ``civis.chat.view``           "landing" | "chat" | "verdict"
    ``civis.chat.error``          transient error text, cleared after one
                                  rerun

Tests inject a provider factory under
``civis.chat.provider_factory`` to bypass Ollama:

    st.session_state["civis.chat.provider_factory"] = my_factory
    # signature: (role: str) -> LLMProvider

If absent, the page falls back to ``load_or_default_config`` +
``build_provider_from_config`` — the same wiring the CLI uses.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import streamlit as st

from civis.cli.wiring import (
    DEFAULT_JUDGE_KEY,
    DEFAULT_PERSONA_KEY,
    build_provider_from_config,
    load_or_default_config,
)
from civis.judge.rubric_loader import DEFAULT_RUBRIC_PATH, load_rubric_from_path
from civis.llm.provider import LLMProvider
from civis.personas.base import PersonaState
from civis.session.orchestrator import SessionOrchestrator
from civis.session.scenario import (
    load_scenario_from_path,
    resolve_scenario_path,
)
from civis.session.storage import (
    SessionMetadata,
    SessionTranscript,
    new_session_id,
    save_metadata,
    save_transcript,
    scenario_hash,
)
from civis.web.formatting import scenario_label
from civis.web.state import get_sessions_dir
from civis.web.theme import PRIMARY_COLOR

# ---------------------------------------------------------------------------
# View + state constants
# ---------------------------------------------------------------------------

VIEW_KEY = "civis.chat.view"
ORCH_KEY = "civis.chat.orchestrator"
SESSION_ID_KEY = "civis.chat.session_id"
SCENARIO_ID_KEY = "civis.chat.scenario_id"
SCENARIO_FILE_KEY = "civis.chat.scenario_file"
METADATA_KEY = "civis.chat.metadata"
RUBRIC_KEY = "civis.chat.rubric"
JUDGE_PROVIDER_KEY = "civis.chat.judge_provider"
OUTPUT_DIR_KEY = "civis.chat.output_dir"
TURN_COUNT_KEY = "civis.chat.turn_count"
TELEMETRY_KEY = "civis.chat.telemetry_rows"
MAX_TURNS_KEY = "civis.chat.max_turns"
ERROR_KEY = "civis.chat.error"
PROVIDER_FACTORY_KEY = "civis.chat.provider_factory"

_VIEW_LANDING = "landing"
_VIEW_CHAT = "chat"

# Duplicated from cli.session on purpose: importing the CLI just for the
# constants would drag Typer into the Streamlit page.
_DEFAULT_MAX_TURNS = 12
_DEFAULT_SCENARIOS_DIR = Path("data/scenarios")


# ---------------------------------------------------------------------------
# Scenario catalogue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ScenarioCard:
    """One scenario the demo tour can play against."""

    scenario_id: str
    persona_kind: str          # pt-BR label
    difficulty: str            # pt-BR ("Fácil", "Média", "Difícil")
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render() -> None:
    """Render whichever view the state machine is in.

    Chat + verdict views land in D+.2 and D+.3; for now, anything other
    than landing falls back to the landing so we never leave the user
    stuck on a half-implemented view.
    """
    view = st.session_state.get(VIEW_KEY, _VIEW_LANDING)
    if view == _VIEW_CHAT:
        _render_chat_placeholder()
    else:
        _render_landing_view()


# ---------------------------------------------------------------------------
# Landing view — three clickable scenario cards + random button
# ---------------------------------------------------------------------------


def _render_landing_view() -> None:
    """The default view: pick a scripted scenario or roll the dice."""
    st.title("Nova sessão")
    st.markdown(
        "Escolha um dos três cenários abaixo para iniciar o atendimento "
        "direto na tela. Cada rodada é gravada como transcript + verdict "
        "do juiz automático + sidecars de contradição e honeytoken — "
        "tudo revisitável depois na aba **Sessões passadas**."
    )

    # If a previous start-up failed, surface the message once and clear.
    pending_error = st.session_state.pop(ERROR_KEY, None)
    if pending_error:
        st.error(pending_error)

    _render_scenario_cards()
    st.markdown("---")
    _render_random_launch()


def _render_scenario_cards() -> None:
    """Three-column layout, one card per scripted scenario."""
    cols = st.columns(3, gap="medium")
    for col, card in zip(cols, _SCENARIOS, strict=True):
        with col:
            _render_scenario_card(card)


def _render_scenario_card(card: _ScenarioCard) -> None:
    """One scenario as a bordered card with a primary-CTA start button."""
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
    if st.button(
        "Começar atendimento",
        key=f"start_{card.scenario_id}",
        type="primary",
        use_container_width=True,
    ):
        _start_session(card.scenario_id)


def _render_random_launch() -> None:
    """
    "Sessão aleatória" affordance: rolls a die across the three scripted
    scenarios and starts the session with no further click.
    """
    left, right = st.columns([3, 1])
    with left:
        st.markdown(
            f"<div class='civis-callout'>"
            f"<b style='color:{PRIMARY_COLOR}'>Não quer escolher?</b> "
            f"Clique em <b>Sessão aleatória</b> e a plataforma sorteia um "
            f"dos três cenários — bom pra treinar sem saber o que vem pela "
            f"frente, como no atendimento real."
            f"</div>",
            unsafe_allow_html=True,
        )
    with right:
        if st.button(
            "🎲 Sessão aleatória",
            key="start_random",
            use_container_width=True,
        ):
            picked = random.choice(_SCENARIOS)
            _start_session(picked.scenario_id)


def _render_chat_placeholder() -> None:
    """
    Temporary placeholder shown until the D+.2 chat view lands. Keeps the
    landing accessible via a "Voltar" so users are never trapped.
    """
    scenario_id = st.session_state.get(SCENARIO_ID_KEY, "—")
    st.title("Sessão iniciada")
    st.info(
        f"Cenário `{scenario_id}` iniciado. A conversa em tempo real "
        f"aparece aqui na próxima etapa (D+.2)."
    )
    if st.button("← Voltar à landing", key="back_to_landing_from_placeholder"):
        st.session_state[VIEW_KEY] = _VIEW_LANDING
        st.rerun()


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------


def _start_session(scenario_id: str) -> None:
    """
    Resolve scenario + rubric, build providers, create the on-disk
    session and stash the live orchestrator in session_state. Any failure
    is caught here so the landing survives.
    """
    try:
        scenario_path = resolve_scenario_path(
            scenario_id, scenarios_dir=_DEFAULT_SCENARIOS_DIR
        )
        scenario_file, scenario_raw = load_scenario_from_path(scenario_path)
        rubric = load_rubric_from_path(DEFAULT_RUBRIC_PATH)
        persona_provider = _build_provider(DEFAULT_PERSONA_KEY)
        judge_provider = _build_provider(DEFAULT_JUDGE_KEY)
    except Exception as exc:  # noqa: BLE001 - narrow-catch not useful; surface any startup failure
        st.session_state[ERROR_KEY] = (
            "Não foi possível iniciar a sessão. "
            f"{_format_provider_error(exc)}"
        )
        return

    # New session on disk. output_dir respects the CIVIS_SESSIONS_DIR env
    # var so AppTest fixtures redirect writes into tmp_path.
    output_dir = get_sessions_dir()
    session_id = new_session_id()
    transcript = SessionTranscript(session_id=session_id)
    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat()
    metadata = SessionMetadata(
        session_id=session_id,
        scenario_id=scenario_file.scenario_id,
        scenario_hash=scenario_hash(scenario_raw),
        persona_provider_name=persona_provider.name,
        judge_provider_name=judge_provider.name,
        created_at=now_iso,
        last_updated_at=now_iso,
    )
    save_metadata(metadata, base=output_dir)
    save_transcript(transcript, base=output_dir)

    initial_state = PersonaState(
        profile=scenario_file.persona,
        emotion=scenario_file.persona.initial_emotion,
    )
    orchestrator = SessionOrchestrator(
        scenario=scenario_file,
        persona_provider=persona_provider,
        transcript=transcript,
        state=initial_state,
    )

    st.session_state[ORCH_KEY] = orchestrator
    st.session_state[SESSION_ID_KEY] = session_id
    st.session_state[SCENARIO_ID_KEY] = scenario_file.scenario_id
    st.session_state[SCENARIO_FILE_KEY] = scenario_file
    st.session_state[METADATA_KEY] = metadata
    st.session_state[RUBRIC_KEY] = rubric
    st.session_state[JUDGE_PROVIDER_KEY] = judge_provider
    st.session_state[OUTPUT_DIR_KEY] = output_dir
    st.session_state[TURN_COUNT_KEY] = 0
    st.session_state[TELEMETRY_KEY] = []
    st.session_state[MAX_TURNS_KEY] = _DEFAULT_MAX_TURNS
    st.session_state[VIEW_KEY] = _VIEW_CHAT
    st.rerun()


def _build_provider(role_key: str) -> LLMProvider:
    """
    Resolve a role-name to a concrete provider. Tests inject a factory
    under ``civis.chat.provider_factory`` so AppTest never touches Ollama;
    production falls back to the same wiring the CLI uses.
    """
    factory: Callable[[str], LLMProvider] | None = st.session_state.get(
        PROVIDER_FACTORY_KEY
    )
    if factory is not None:
        return factory(role_key)
    config, _source = load_or_default_config()
    return build_provider_from_config(config, role_key)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _difficulty_color(label: str) -> str:
    """Colour chip for the difficulty label. Traffic-light semantics."""
    if label == "Fácil":
        return "#3f8f4a"
    if label == "Média":
        return "#c25a1a"
    return "#b3261e"  # Difícil


def _format_provider_error(exc: BaseException) -> str:
    """
    Translate a raw provider/judge exception into an actionable pt-BR
    hint. Falls back to ``type: message`` when we don't recognise it.
    """
    message = str(exc).lower()
    if "connection" in message or "refused" in message or "econnrefused" in message:
        return (
            "Não consegui falar com o modelo. Verifique se o Ollama está "
            "rodando (`ollama serve`) ou se a API key do provider está "
            "configurada."
        )
    if "api key" in message or "unauthorized" in message or "401" in message:
        return (
            "API key inválida ou ausente. Rode `civis config` para "
            "configurar o provider."
        )
    if "timeout" in message or "timed out" in message:
        return (
            "O modelo demorou demais para responder. Tente de novo, "
            "diminua o max_tokens, ou troque para um modelo mais leve."
        )
    return f"{type(exc).__name__}: {exc}"


render()
