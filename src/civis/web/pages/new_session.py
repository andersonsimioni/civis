"""
"Nova sessão" page — D+.3 chat REPL with inline judge verdict.
Fase D++: persona replies stream token-by-token via ``st.write_stream``.

Three views live on this page, switched via ``st.session_state``:

    - ``"landing"`` (default): three scripted-scenario cards + a
      "Sessão aleatória" button.
    - ``"chat"``: bubble-style transcript, ``st.chat_input`` for the
      trainee, "Encerrar e avaliar" and "Cancelar" controls.
    - ``"verdict"``: the same correction panel used in
      "Sessões passadas" — rubric cards, contradictions,
      honeytoken leaks.

Session state keys (all prefixed ``civis.chat.`` so they never collide
with the filters used by the other pages):

    ``civis.chat.view``           "landing" | "chat" | "verdict"
    ``civis.chat.orchestrator``   live SessionOrchestrator
    ``civis.chat.session_id``     id of the current session on disk
    ``civis.chat.scenario_id``    e.g. "certificate_duplicate_..."
    ``civis.chat.scenario_file``  parsed ScenarioFile
    ``civis.chat.metadata``       SessionMetadata (touched every turn)
    ``civis.chat.rubric``         RubricDefinition
    ``civis.chat.judge_provider`` LLMProvider used by the judge pass
    ``civis.chat.output_dir``     Path where sidecars land
    ``civis.chat.turn_count``     int, agent turns already done
    ``civis.chat.telemetry_rows`` list[dict] persisted per turn
    ``civis.chat.max_turns``      soft cap (starts at _DEFAULT_MAX_TURNS)
    ``civis.chat.verdict``        JudgeVerdict once the judge ran
    ``civis.chat.contradictions`` dict payload for the sidecar
    ``civis.chat.honeytokens``    dict payload for the sidecar
    ``civis.chat.error``          transient error text, one rerun

Tests inject a provider factory under
``civis.chat.provider_factory`` to bypass Ollama:

    st.session_state["civis.chat.provider_factory"] = my_factory
    # signature: (role: str) -> LLMProvider

If absent, the page falls back to ``load_or_default_config`` +
``build_provider_from_config`` — the same wiring the CLI uses.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from civis.adversarial.honeytoken_detector import detect_honeytoken_leaks
from civis.cli.session import run_judge_with_validation
from civis.cli.wiring import (
    DEFAULT_JUDGE_KEY,
    DEFAULT_PERSONA_KEY,
    build_provider_from_config,
    load_or_default_config,
)
from civis.documents.templates import RenderedDocument, render_document
from civis.judge.rubric_loader import DEFAULT_RUBRIC_PATH, load_rubric_from_path
from civis.llm.provider import LLMProvider
from civis.personas.base import PersonaState
from civis.scenarios.actions import AgentAction
from civis.session.contradiction_detector import detect_contradictions
from civis.session.orchestrator import SessionOrchestrator, TurnResult
from civis.session.scenario import (
    ScenarioFile,
    load_scenario_from_path,
    resolve_scenario_path,
)
from civis.session.storage import (
    SessionMetadata,
    SessionTranscript,
    new_session_id,
    save_contradictions_json,
    save_honeytoken_leaks_json,
    save_issued_document,
    save_metadata,
    save_transcript,
    save_turn_telemetry_json,
    save_verdict_json,
    scenario_hash,
    touch_metadata,
)
from civis.web.formatting import scenario_label
from civis.web.state import get_sessions_dir
from civis.web.theme import PRIMARY_COLOR
from civis.web.verdict_view import (
    render_contradictions,
    render_honeytoken_leaks,
    render_verdict,
)

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
VERDICT_KEY = "civis.chat.verdict"
CONTRADICTIONS_KEY = "civis.chat.contradictions"
HONEYTOKENS_KEY = "civis.chat.honeytokens"
ERROR_KEY = "civis.chat.error"
PROVIDER_FACTORY_KEY = "civis.chat.provider_factory"

_VIEW_LANDING = "landing"
_VIEW_CHAT = "chat"
_VIEW_VERDICT = "verdict"

# Duplicated from cli.session on purpose: importing the CLI just for the
# constants would drag Typer into the Streamlit page.
_DEFAULT_MAX_TURNS = 12
_DEFAULT_SCENARIOS_DIR = Path("data/scenarios")

# All chat-scoped state keys, so cancel/reset paths clean up in one place.
_CHAT_STATE_KEYS: tuple[str, ...] = (
    ORCH_KEY,
    SESSION_ID_KEY,
    SCENARIO_ID_KEY,
    SCENARIO_FILE_KEY,
    METADATA_KEY,
    RUBRIC_KEY,
    JUDGE_PROVIDER_KEY,
    OUTPUT_DIR_KEY,
    TURN_COUNT_KEY,
    TELEMETRY_KEY,
    MAX_TURNS_KEY,
    VERDICT_KEY,
    CONTRADICTIONS_KEY,
    HONEYTOKENS_KEY,
    ERROR_KEY,
)


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
    """Render whichever view the state machine is in."""
    view = st.session_state.get(VIEW_KEY, _VIEW_LANDING)
    if view == _VIEW_CHAT:
        _render_chat_view()
    elif view == _VIEW_VERDICT:
        _render_verdict_view()
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
        # Force a rerun so the landing renders again and picks up the
        # error banner from ERROR_KEY. Without this, the current render
        # already consumed ERROR_KEY (with pop) before the click set it.
        st.rerun()
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
    st.session_state.pop(VERDICT_KEY, None)
    st.session_state.pop(CONTRADICTIONS_KEY, None)
    st.session_state.pop(HONEYTOKENS_KEY, None)
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
# Chat view — bubbles + input + finalize / cancel controls
# ---------------------------------------------------------------------------


def _render_chat_view() -> None:
    """Chat header + bubbles + chat_input feed line + action buttons."""
    orchestrator: SessionOrchestrator | None = st.session_state.get(ORCH_KEY)
    if orchestrator is None:
        # Someone landed here directly without a live orchestrator —
        # rebuild the landing and move on.
        st.session_state[VIEW_KEY] = _VIEW_LANDING
        st.rerun()
        return

    _render_chat_header()
    _render_chat_body(orchestrator)
    _render_chat_input(orchestrator)
    # Phase D+++: clickable action buttons live under the chat input so
    # the trainee (and the investor watching) sees the counter's toolkit
    # right next to where they type.
    _render_action_buttons(orchestrator)


def _render_chat_header() -> None:
    """Title bar with scenario label + persona chip + finalise/cancel."""
    scenario_id: str = st.session_state[SCENARIO_ID_KEY]
    scenario_file: ScenarioFile = st.session_state[SCENARIO_FILE_KEY]
    friendly_id = scenario_label(scenario_id)
    persona_kind_label = _persona_kind_label(scenario_file.persona.kind.value)

    header_left, header_center, header_right = st.columns([3, 1.3, 1.3])
    with header_left:
        st.markdown(f"### 💬 {friendly_id}")
        st.caption(
            f"Perfil: **{persona_kind_label}** · "
            f"Turnos: {st.session_state.get(TURN_COUNT_KEY, 0)} / "
            f"{st.session_state.get(MAX_TURNS_KEY, _DEFAULT_MAX_TURNS)}"
        )
    with header_center:
        if st.button(
            "Encerrar e avaliar",
            key="finalize_chat",
            type="primary",
            use_container_width=True,
        ):
            _finalize_and_render_verdict()
            return
    with header_right:
        if st.button(
            "Cancelar",
            key="cancel_chat",
            use_container_width=True,
        ):
            _cancel_session()
            return

    # One-shot error banner (e.g. provider failure on the previous turn).
    pending_error = st.session_state.pop(ERROR_KEY, None)
    if pending_error:
        st.error(pending_error)


def _render_chat_body(orchestrator: SessionOrchestrator) -> None:
    """Render every turn as a chat bubble.

    Speaker mapping:
        - "agent"   → user bubble.
        - "persona" → assistant bubble.
        - "action"  → assistant bubble with a document card (Phase D+++).
    """
    if not orchestrator.transcript.turns:
        st.info(
            "A pessoa está aguardando o seu primeiro contato. Digite abaixo "
            "como você abriria o atendimento."
        )
        return
    for turn in orchestrator.transcript.turns:
        if turn.speaker == "agent":
            with st.chat_message("user", avatar="👤"):
                st.markdown(turn.content)
        elif turn.speaker == "action":
            _render_action_turn_in_chat(turn.content)
        else:
            with st.chat_message("assistant", avatar="🧑‍💼"):
                st.markdown(turn.content)


def _render_chat_input(orchestrator: SessionOrchestrator) -> None:
    """
    Feed line: ``st.chat_input`` unless the soft cap of turns is reached,
    in which case we prompt the user to finalise or extend.
    """
    turn_count: int = st.session_state.get(TURN_COUNT_KEY, 0)
    max_turns: int = st.session_state.get(MAX_TURNS_KEY, _DEFAULT_MAX_TURNS)

    if turn_count >= max_turns:
        st.warning(
            f"Limite de {max_turns} turnos atingido. Encerre para gerar "
            f"o verdict do juiz automático, ou aumente o limite para "
            f"continuar mais alguns turnos."
        )
        cont_col, end_col = st.columns(2)
        with cont_col:
            if st.button(
                f"Continuar mesmo assim (+{_DEFAULT_MAX_TURNS})",
                key="extend_max_turns",
                use_container_width=True,
            ):
                st.session_state[MAX_TURNS_KEY] = max_turns + _DEFAULT_MAX_TURNS
                st.rerun()
        with end_col:
            if st.button(
                "Encerrar e avaliar",
                key="finalize_from_cap",
                type="primary",
                use_container_width=True,
            ):
                _finalize_and_render_verdict()
                return
        return

    agent_message = st.chat_input(
        "Digite sua resposta como atendente...",
        key="chat_input",
    )
    if agent_message:
        _handle_agent_turn(orchestrator, agent_message)


def _handle_agent_turn(
    orchestrator: SessionOrchestrator, agent_message: str
) -> None:
    """
    Run one agent turn with token streaming.

    Sequence, chosen so the trainee sees their own message before the
    persona starts talking back:

        1. Render the trainee's message as a user chat bubble (the
           transcript body above only renders turns that were on disk
           BEFORE this render pass — the new one shows here inline).
        2. Open an assistant chat bubble and pipe
           ``orchestrator.run_agent_turn_streaming(...)`` into
           ``st.write_stream`` so tokens paint as they arrive. On the
           first turn, warn about the cold-start delay via a ``st.status``
           block that auto-collapses once the stream drains.
        3. After ``st.write_stream`` returns, read ``last_result`` from
           the orchestrator, persist transcript / metadata / telemetry
           (same downstream as the non-streaming path), and rerun so the
           next input widget is ready.

    Any provider exception surfaces as a pt-BR error banner and preserves
    the chat view so the user can retry.
    """
    # Cold-start hint. Ollama loads a 7B model into RAM the first time,
    # so first-turn latency is 30-60s BEFORE the first token; we surface
    # that to the user so they don't think the page hung. The hint block
    # collapses automatically the moment the stream starts producing.
    is_first_turn = len(orchestrator.transcript.turns) == 0
    cold_start_msg = (
        "Carregando modelo... o primeiro token pode levar até 60s "
        "porque o Ollama está subindo o modelo pra memória."
    )

    try:
        # Render the trainee's message immediately so the UI feels
        # responsive even before the persona starts speaking.
        with st.chat_message("user", avatar="👤"):
            st.markdown(agent_message)

        # Stream the persona reply. st.write_stream returns the full
        # aggregated text once the generator drains — we don't need the
        # return value here because we read the reconstructed TurnResult
        # off the orchestrator itself, but the widget still renders every
        # yielded chunk in place.
        with st.chat_message("assistant", avatar="🧑‍💼"):
            if is_first_turn:
                with st.status(cold_start_msg, expanded=False):
                    st.write_stream(
                        orchestrator.run_agent_turn_streaming(agent_message)
                    )
            else:
                st.write_stream(
                    orchestrator.run_agent_turn_streaming(agent_message)
                )
    except Exception as exc:  # noqa: BLE001 - surface any provider failure to the user
        st.session_state[ERROR_KEY] = _format_provider_error(exc)
        st.rerun()
        return

    result: TurnResult | None = orchestrator.last_result
    if result is None:
        # Guard: this should never happen — the streaming generator only
        # exits without setting last_result on a mid-stream exception,
        # which we already caught above. If we still land here, treat it
        # as a soft failure so the UI recovers rather than crashing.
        st.session_state[ERROR_KEY] = (
            "A resposta da pessoa chegou vazia. Tente enviar de novo."
        )
        st.rerun()
        return

    output_dir: Path = st.session_state[OUTPUT_DIR_KEY]
    session_id: str = st.session_state[SESSION_ID_KEY]

    save_transcript(orchestrator.transcript, base=output_dir)
    metadata: SessionMetadata = touch_metadata(st.session_state[METADATA_KEY])
    st.session_state[METADATA_KEY] = metadata
    save_metadata(metadata, base=output_dir)

    if result.llm_response is not None:
        telemetry_rows: list[dict[str, Any]] = st.session_state[TELEMETRY_KEY]
        telemetry_rows.append(
            {
                "turn_index": result.persona_reply.turn_index,
                "input_tokens": result.llm_response.input_tokens,
                "output_tokens": result.llm_response.output_tokens,
                "latency_ms": result.llm_response.latency_ms,
                "provider_name": result.llm_response.provider_name,
            }
        )
        save_turn_telemetry_json(
            {"session_id": session_id, "turns": telemetry_rows},
            session_id=session_id,
            base=output_dir,
        )
        st.session_state[TELEMETRY_KEY] = telemetry_rows

    st.session_state[TURN_COUNT_KEY] = st.session_state.get(TURN_COUNT_KEY, 0) + 1
    st.rerun()


# ---------------------------------------------------------------------------
# Finalize — run detectors + judge and switch to verdict view
# ---------------------------------------------------------------------------


def _finalize_and_render_verdict() -> None:
    """
    Trigger the same end-of-session pipeline the CLI runs: contradiction
    detector, honeytoken detector, judge-with-citation-validation. Save
    every sidecar, then flip the view to "verdict".
    """
    orchestrator: SessionOrchestrator | None = st.session_state.get(ORCH_KEY)
    if orchestrator is None:
        st.session_state[VIEW_KEY] = _VIEW_LANDING
        st.rerun()
        return

    session_id: str = st.session_state[SESSION_ID_KEY]
    scenario_file: ScenarioFile = st.session_state[SCENARIO_FILE_KEY]
    output_dir: Path = st.session_state[OUTPUT_DIR_KEY]
    judge_provider: LLMProvider = st.session_state[JUDGE_PROVIDER_KEY]
    rubric = st.session_state[RUBRIC_KEY]

    # Contradictions + honeytokens are cheap and deterministic — always run.
    contradiction_report = detect_contradictions(
        turn_events=list(orchestrator.turn_events)
    )
    save_contradictions_json(
        contradiction_report.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )
    honeytoken_report = detect_honeytoken_leaks(
        transcript=orchestrator.transcript,
        scenario=scenario_file,
    )
    save_honeytoken_leaks_json(
        honeytoken_report.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )
    st.session_state[CONTRADICTIONS_KEY] = contradiction_report.model_dump(mode="json")
    st.session_state[HONEYTOKENS_KEY] = honeytoken_report.model_dump(mode="json")

    if not orchestrator.transcript.turns:
        st.session_state[ERROR_KEY] = (
            "Nada para avaliar ainda — a sessão foi encerrada sem "
            "nenhum turno. Volte à landing e comece uma nova conversa."
        )
        st.session_state.pop(VERDICT_KEY, None)
        st.session_state[VIEW_KEY] = _VIEW_VERDICT
        st.rerun()
        return

    try:
        with st.spinner(
            "Rodando juiz automático... (pode levar 30-90s, juiz avalia toda a "
            "transcrição contra a rubrica)"
        ):
            verdict, citation_report = run_judge_with_validation(
                session_id=session_id,
                scenario=scenario_file,
                transcript=orchestrator.transcript,
                judge_provider=judge_provider,
                rubric=rubric,
            )
    except Exception as exc:  # noqa: BLE001 - surface any judge failure to the user
        st.session_state[ERROR_KEY] = (
            "O juiz automático falhou. " + _format_provider_error(exc)
        )
        # Stay in chat so the user can retry or cancel.
        st.rerun()
        return

    save_verdict_json(
        verdict.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )
    st.session_state[VERDICT_KEY] = verdict
    if not citation_report.ok:
        st.session_state[ERROR_KEY] = (
            f"O juiz retornou {len(citation_report.issues)} citação(ões) que "
            "podem estar imprecisas — inspecione o verdict antes de usar."
        )
    st.session_state[VIEW_KEY] = _VIEW_VERDICT
    st.rerun()


def _render_verdict_view() -> None:
    """Render the correction panel inline once the judge has run."""
    session_id: str = st.session_state.get(SESSION_ID_KEY, "—")
    scenario_id: str = st.session_state.get(SCENARIO_ID_KEY, "")
    friendly_id = scenario_label(scenario_id) if scenario_id else "sessão"

    st.subheader("Sessão finalizada — verdict")
    st.caption(f"Sessão `{session_id}` · {friendly_id}")

    verdict = st.session_state.get(VERDICT_KEY)
    output_dir: Path | None = st.session_state.get(OUTPUT_DIR_KEY)
    if verdict is not None and output_dir is not None:
        st.success(f"Sessão salva em `{output_dir / session_id}/`.")

    pending_warning = st.session_state.pop(ERROR_KEY, None)
    if pending_warning:
        st.warning(pending_warning)

    if verdict is not None:
        render_verdict(verdict)
    else:
        st.info(
            "Não há verdict para exibir — a sessão foi encerrada sem "
            "turnos suficientes ou o juiz falhou."
        )
    render_contradictions(st.session_state.get(CONTRADICTIONS_KEY))
    render_honeytoken_leaks(st.session_state.get(HONEYTOKENS_KEY))

    st.markdown("---")
    if st.button("Nova sessão", key="restart_from_verdict", type="primary"):
        _reset_chat_state()
        st.rerun()


# ---------------------------------------------------------------------------
# Cancel + reset helpers
# ---------------------------------------------------------------------------


def _cancel_session() -> None:
    """
    Abandon the chat without running the judge. The transcript + metadata
    already saved on disk stay — the user can still reopen the session in
    "Sessões passadas" and re-run the judge from the CLI if they want.
    """
    _reset_chat_state()
    st.rerun()


def _reset_chat_state() -> None:
    """Drop every ``civis.chat.*`` key and go back to the landing view."""
    for key in _CHAT_STATE_KEYS:
        st.session_state.pop(key, None)
    st.session_state[VIEW_KEY] = _VIEW_LANDING


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


def _persona_kind_label(kind_value: str) -> str:
    """Map internal ``PersonaKind`` values to pt-BR labels for the header."""
    mapping = {
        "confused": "Cidadã confusa",
        "aggressive": "Cidadão apressado",
        "fraudster": "Fraudador social",
    }
    return mapping.get(kind_value, kind_value)


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



# ---------------------------------------------------------------------------
# Phase D+++ — action buttons + inline document emission
# ---------------------------------------------------------------------------
#
# The chat view exposes a grid of clickable actions ("verify identity",
# "issue certificate copy", ...) under the chat input. Each action is
# declared in the scenario YAML as an AgentAction. A button is enabled
# only when every fact_key in ``requires`` has been revealed by the
# persona. On click, the action is executed by :func:`_execute_action`
# — a new turn (speaker="action") is appended to the transcript and,
# when the action carries ``emits_document``, a fake document is
# rendered inline in the chat and persisted under
# ``data/sessions/<sid>/issued_documents/<doc_id>.md``.
#
# Design decisions:
#   * The action turn's ``content`` is a JSON payload. A single string
#     field on ``Turn`` is enough to carry action_id + label + optional
#     rendered document. The orchestrator strips these turns from the
#     history it feeds to the persona prompt.
#   * The document body is stored inside the JSON payload AND as a
#     standalone .md file. The chat card renders directly from the JSON
#     so a rerun without re-reading disk still shows the paper. The .md
#     file exists so replay / audit tooling can grep across sessions.
#   * We DO NOT trigger a persona reply after an action. The action is
#     a silent counter act — the next natural turn from the trainee is
#     when the persona speaks again.


def _render_action_buttons(orchestrator: SessionOrchestrator) -> None:
    """Grid of clickable action buttons underneath the chat input.

    A button is disabled (with a helpful tooltip) when its declared
    ``requires`` are not yet fully revealed. Scenarios with an empty
    ``available_actions`` list render nothing so Phase A-D++ demos are
    unaffected.
    """
    scenario_file: ScenarioFile = st.session_state[SCENARIO_FILE_KEY]
    catalog = scenario_file.available_actions
    if len(catalog) == 0:
        return

    revealed: set[str] = set(orchestrator.state.revealed_fact_keys)

    # Small caption above the grid so an investor understands what the
    # row of buttons means — no chrome, just one line.
    st.markdown(
        "<div class='civis-action-grid-label'>Ações do atendente</div>",
        unsafe_allow_html=True,
    )

    # Grid of up to 4 buttons per row.
    columns_per_row = 4
    actions = list(catalog)
    for row_start in range(0, len(actions), columns_per_row):
        row = actions[row_start : row_start + columns_per_row]
        cols = st.columns(len(row), gap="small")
        for col, action in zip(cols, row, strict=True):
            with col:
                _render_single_action_button(action, revealed, orchestrator)


def _render_single_action_button(
    action: AgentAction,
    revealed_fact_keys: set[str],
    orchestrator: SessionOrchestrator,
) -> None:
    """Render one button and wire its click to :func:`_execute_action`.

    The tooltip explains WHY a disabled button is disabled (which fact
    keys are still missing) — critical for the demo: an investor sees
    the button greyed out, hovers, and understands the mechanic in a
    second.
    """
    missing = [key for key in action.requires if key not in revealed_fact_keys]
    disabled = bool(missing)

    if disabled:
        help_text = (
            f"{action.description} — bloqueado até revelar: "
            + ", ".join(missing)
        )
    else:
        help_text = action.description

    if st.button(
        action.label,
        key=f"action_{action.id}",
        help=help_text,
        disabled=disabled,
        use_container_width=True,
    ):
        _execute_action(action, orchestrator)


def _execute_action(
    action: AgentAction,
    orchestrator: SessionOrchestrator,
) -> None:
    """Record the action as a new transcript turn (+ optional document).

    Defence-in-depth: even though the button is rendered disabled when
    requires aren't met, we re-check the gate here so a stale rerun or
    a scripted test can't bypass it.
    """
    revealed = set(orchestrator.state.revealed_fact_keys)
    missing = [key for key in action.requires if key not in revealed]
    if missing:
        st.session_state[ERROR_KEY] = (
            f"Ação '{action.label}' bloqueada — ainda faltam: {', '.join(missing)}."
        )
        st.rerun()
        return

    session_id: str = st.session_state[SESSION_ID_KEY]
    output_dir: Path = st.session_state[OUTPUT_DIR_KEY]

    document_payload: dict[str, str] | None = None
    if action.emits_document:
        try:
            rendered = _render_action_document(
                action.emits_document,
                orchestrator=orchestrator,
                session_id=session_id,
            )
        except KeyError as exc:
            st.session_state[ERROR_KEY] = (
                f"Template de documento desconhecido: {exc}. "
                "Revise o campo 'emits_document' do cenário."
            )
            st.rerun()
            return

        # Persist the document as a standalone .md so replay tooling
        # can grep across sessions.
        doc_path = save_issued_document(
            session_id=session_id,
            document_id=rendered.id,
            body=rendered.body,
            base=output_dir,
        )
        document_payload = {
            "id": rendered.id,
            "title": rendered.title,
            "body": rendered.body,
            "path": str(doc_path),
        }

    turn_content = _action_turn_content(
        action=action,
        document=document_payload,
    )
    orchestrator.transcript.append("action", turn_content)
    # Emit a TurnEvent too so replayers see the action in the observable
    # stream. Action events carry no facts / observed values.
    orchestrator._emit_turn_event(
        turn_index=orchestrator.transcript.turns[-1].turn_index,
        speaker="action",
        content=turn_content,
        newly_revealed_fact_keys=[],
        observed_fact_values={},
    )

    save_transcript(orchestrator.transcript, base=output_dir)
    metadata: SessionMetadata = touch_metadata(st.session_state[METADATA_KEY])
    st.session_state[METADATA_KEY] = metadata
    save_metadata(metadata, base=output_dir)

    st.rerun()


def _render_action_document(
    template_id: str,
    *,
    orchestrator: SessionOrchestrator,
    session_id: str,
) -> RenderedDocument:
    """Look up the template and render it against the persona facts.

    Facts are pulled from the scenario's persona (not from revealed
    facts alone) so the document is complete even for keys the persona
    never volunteered — the button gate already ensured the trainee did
    ask for the important ones.
    """
    persona = orchestrator.scenario.persona
    persona_facts: dict[str, str] = {"name": persona.name}
    for fact in persona.facts:
        if fact.is_secret:
            continue
        persona_facts.setdefault(fact.key, fact.value)
    return render_document(template_id, persona_facts, session_id)


def _action_turn_content(
    *,
    action: AgentAction,
    document: dict[str, str] | None,
) -> str:
    """Serialise the action turn payload as a JSON string.

    The chosen shape keeps the historic viewer (``web.chat_view``) and
    the live viewer here in sync: both parse the same JSON.
    """
    payload: dict[str, Any] = {
        "action_id": action.id,
        "label": action.label,
    }
    if document is not None:
        payload["document"] = document
    return json.dumps(payload, ensure_ascii=False)


def _render_action_turn_in_chat(content: str) -> None:
    """Live-view renderer for one action turn inside the chat body.

    Mirrors ``civis.web.chat_view._render_action_html`` (historic view)
    but uses ``st.chat_message`` so it aligns with the live streaming
    UX. The document body sits inside a ``<pre>`` styled by the
    ``.civis-document`` CSS class defined in theme.py.
    """
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        payload = {"label": content}

    label = str(payload.get("label", payload.get("action_id", "ação")))
    document = payload.get("document") or None

    with st.chat_message("assistant", avatar="🏛️"):
        st.markdown(f"**Ação:** {escape(label)}", unsafe_allow_html=True)
        if isinstance(document, dict):
            title = escape(str(document.get("title", "Documento emitido")))
            body = escape(str(document.get("body", "")))
            st.markdown(
                f"<div class='civis-document'>"
                f"  <div class='civis-document-title'>{title}</div>"
                f"  <pre class='civis-document-body'>{body}</pre>"
                f"</div>",
                unsafe_allow_html=True,
            )

render()
