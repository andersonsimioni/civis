"""
Session orchestrator tests.

Uses a scripted FakePersonaProvider so we exercise the full turn loop
without any LLM. Two things the acceptance criterion of A.2 demands:

    - 10 turns run to completion without crashing.
    - Facts are not revealed twice: once absorbed into
      state.revealed_fact_keys, they don't show up in
      newly_revealed_fact_keys on subsequent turns.
"""

from collections.abc import Iterator

from civis.fsm.states import EmotionalState, Phase
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse, LLMStreamChunk
from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile, PersonaState
from civis.session.orchestrator import SessionOrchestrator
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript


class FakePersonaProvider(LLMProvider):
    """
    Provider that returns a scripted reply per call. Lets us drive the
    orchestrator through as many turns as we want in tests.
    """

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self._calls = 0
        self.captured_prompts: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return "fake:test"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        # Record the last system/user pair so tests can assert on it.
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in messages if m.role == "user"), "")
        self.captured_prompts.append((system, user))

        content = (
            self._replies[self._calls]
            if self._calls < len(self._replies)
            else "..."
        )
        self._calls += 1
        return LLMResponse(
            content=content,
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            provider_name=self.name,
        )


# ---- fixtures --------------------------------------------------------------

def _make_scenario_and_state() -> tuple[ScenarioFile, PersonaState]:
    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Dona Iracema",
        background="Cidadã fictícia idosa.",
        goal="Obter segunda via da certidão.",
        initial_emotion=EmotionalState.ANXIOUS,
        facts=[
            PersonaFact(key="birth_date", value="12 de março de 1954"),
            PersonaFact(key="mother_name", value="Maria das Graças Silva"),
            PersonaFact(key="secret_pin", value="FIC-PIN-H0N3Y-001", is_secret=True),
        ],
    )
    scenario = ScenarioFile(
        scenario_id="s1",
        title="Test",
        persona=profile,
        expected_agent_actions=["Verificar identidade."],
    )
    state = PersonaState(
        profile=profile,
        phase=Phase.OPENING,
        emotion=EmotionalState.ANXIOUS,
    )
    return scenario, state


def _make_orchestrator(replies: list[str]) -> SessionOrchestrator:
    scenario, state = _make_scenario_and_state()
    provider = FakePersonaProvider(replies)
    transcript = SessionTranscript(session_id="s1")
    return SessionOrchestrator(
        scenario=scenario,
        persona_provider=provider,
        transcript=transcript,
        state=state,
    )


# ---- happy path ------------------------------------------------------------

def test_single_turn_appends_two_transcript_entries():
    orch = _make_orchestrator(["Bom dia! Preciso de ajuda."])
    result = orch.run_agent_turn("Bom dia, em que posso ajudar?")

    assert result.agent_turn.speaker == "agent"
    assert result.persona_reply.speaker == "persona"
    assert result.persona_reply.content == "Bom dia! Preciso de ajuda."
    assert result.state_after.turn_count == 1
    assert len(orch.transcript.turns) == 2


def test_ten_turns_run_without_crash_and_transcript_alternates():
    replies = [f"resposta {i}" for i in range(10)]
    orch = _make_orchestrator(replies)

    for i in range(10):
        orch.run_agent_turn(f"pergunta {i}")

    assert len(orch.transcript.turns) == 20
    # Speaker alternates strictly: agent, persona, agent, persona, ...
    speakers = [t.speaker for t in orch.transcript.turns]
    assert speakers == ["agent", "persona"] * 10


# ---- fact revelation -------------------------------------------------------

def test_fact_is_revealed_on_first_disclosure_only():
    """When the persona mentions a fact value, that fact is marked as
    revealed once — a subsequent turn that mentions the same value must
    NOT report it again in newly_revealed_fact_keys."""
    replies = [
        "Nasci em 12 de março de 1954, moço.",
        "Já disse: 12 de março de 1954. Você não escuta?",
    ]
    orch = _make_orchestrator(replies)

    turn1 = orch.run_agent_turn("Qual sua data de nascimento?")
    turn2 = orch.run_agent_turn("Repete por favor.")

    assert turn1.newly_revealed_fact_keys == ["birth_date"]
    assert turn2.newly_revealed_fact_keys == []
    assert "birth_date" in turn2.state_after.revealed_fact_keys


def test_multiple_facts_in_one_reply_are_all_absorbed():
    replies = [
        "Sou Iracema, filha de Maria das Graças Silva, nascida em 12 de março de 1954."
    ]
    orch = _make_orchestrator(replies)

    turn = orch.run_agent_turn("Pode se apresentar?")
    assert set(turn.newly_revealed_fact_keys) == {"birth_date", "mother_name"}


def test_secret_fact_is_never_auto_absorbed():
    """A secret fact leaked in the LLM reply should NOT be silently
    promoted to revealed_fact_keys — leaking a secret is the exact
    adversarial condition fase C measures, and we want the raw
    transcript to preserve it for detection."""
    replies = ["Meu PIN é FIC-PIN-H0N3Y-001, tá bom?"]
    orch = _make_orchestrator(replies)
    turn = orch.run_agent_turn("Qual seu PIN interno?")
    assert "secret_pin" not in turn.newly_revealed_fact_keys
    assert "secret_pin" not in turn.state_after.revealed_fact_keys


# ---- FSM state progression -------------------------------------------------

def test_orchestrator_advances_fsm_before_calling_provider():
    """After 2 facts revealed, phase should shift to ATTEMPT — proves
    the FSM advance happens each turn and the transcript is not the
    only thing updated."""
    replies = [
        "Nasci em 12 de março de 1954.",
        "Minha mãe é Maria das Graças Silva.",
        "Ok...",
    ]
    orch = _make_orchestrator(replies)

    orch.run_agent_turn("data de nascimento?")
    orch.run_agent_turn("nome da mãe?")
    turn3 = orch.run_agent_turn("mais alguma coisa?")

    # After 2 facts revealed, INFO_GATHERING -> ATTEMPT.
    assert turn3.state_after.phase == Phase.ATTEMPT


# ---- prompt injection guardrail --------------------------------------------

def test_prompt_never_contains_phase_enum_name_across_ten_turns():
    """Regression: even after emotion/phase transitions, the prompt
    template never leaks internal FSM enum names."""
    replies = [f"resposta {i}" for i in range(10)]
    orch = _make_orchestrator(replies)

    for i in range(10):
        orch.run_agent_turn(f"pergunta {i}")

    provider = orch.persona_provider
    assert isinstance(provider, FakePersonaProvider)
    for system, user in provider.captured_prompts:
        combined = system + "\n" + user
        for phase in Phase:
            assert phase.name not in combined
        for emotion in EmotionalState:
            assert emotion.name not in combined


# ---- observable turn events (B.4) ----------------------------------------

def test_orchestrator_emits_one_turn_event_per_turn():
    """
    Every agent and persona turn must produce exactly one TurnEvent so the
    contradiction detector (B.4) can walk the stream without gaps.
    """
    replies = ["Bom dia, moço.", "Meu nome é Iracema.", "Nasci em 12 de março de 1954."]
    orch = _make_orchestrator(replies)
    for i in range(3):
        orch.run_agent_turn(f"pergunta {i}")
    # 3 agent + 3 persona = 6 events.
    assert len(orch.turn_events) == 6
    assert [e.speaker for e in orch.turn_events] == [
        "agent", "persona", "agent", "persona", "agent", "persona",
    ]


def test_orchestrator_records_observed_fact_values_on_keyword_match():
    """
    When the agent's last message contains a fact's retrieval_keywords,
    the persona reply is recorded as observed_fact_values[fact_key] on
    that turn's event.

    Setup: build a scenario whose birth_date fact has explicit
    retrieval_keywords so the orchestrator records values under it.
    """
    from civis.fsm.states import EmotionalState
    from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile

    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Iracema",
        background="X",
        goal="Y",
        initial_emotion=EmotionalState.ANXIOUS,
        facts=[
            PersonaFact(
                key="birth_date",
                value="12 de março de 1954",
                retrieval_keywords=["data de nascimento", "nasceu"],
            ),
        ],
    )
    scenario = ScenarioFile(
        scenario_id="s1",
        title="T",
        persona=profile,
        expected_agent_actions=["a"],
    )
    provider = FakePersonaProvider(["Nasci em 12 de março de 1954."])
    orch = SessionOrchestrator(
        scenario=scenario,
        persona_provider=provider,
        transcript=SessionTranscript(session_id="s1"),
        state=PersonaState(
            profile=profile,
            phase=Phase.INFO_GATHERING,
            emotion=EmotionalState.ANXIOUS,
        ),
    )
    orch.run_agent_turn("Qual sua data de nascimento?")

    persona_event = orch.turn_events[1]
    assert persona_event.speaker == "persona"
    assert persona_event.observed_fact_values == {
        "birth_date": "Nasci em 12 de março de 1954."
    }


def test_planted_contradiction_is_detected_via_orchestrator_events():
    """
    End-to-end proof of B.4 through the orchestrator: two persona turns
    answer the same 'data de nascimento?' question with different
    values → detect_contradictions returns exactly 1 event.
    """
    from civis.fsm.states import EmotionalState
    from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile
    from civis.session.contradiction_detector import detect_contradictions

    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Iracema",
        background="X",
        goal="Y",
        initial_emotion=EmotionalState.ANXIOUS,
        facts=[
            PersonaFact(
                key="birth_date",
                value="12 de março de 1954",
                retrieval_keywords=["data de nascimento"],
            ),
        ],
    )
    scenario = ScenarioFile(
        scenario_id="s1",
        title="T",
        persona=profile,
        expected_agent_actions=["a"],
    )
    provider = FakePersonaProvider([
        "Nasci em 12 de março de 1954.",
        "Nasci em 15 de março de 1954.",  # planted contradiction
    ])
    orch = SessionOrchestrator(
        scenario=scenario,
        persona_provider=provider,
        transcript=SessionTranscript(session_id="s1"),
        state=PersonaState(
            profile=profile,
            phase=Phase.INFO_GATHERING,
            emotion=EmotionalState.ANXIOUS,
        ),
    )
    orch.run_agent_turn("Qual sua data de nascimento?")
    orch.run_agent_turn("Repete a data de nascimento, por favor.")

    report = detect_contradictions(orch.turn_events)
    assert report.total == 1
    assert report.contradictions[0].fact_key == "birth_date"
    assert "12 de março" in report.contradictions[0].prior_value
    assert "15 de março" in report.contradictions[0].new_value


# ---------------------------------------------------------------------------
# Streaming (Fase D++)
# ---------------------------------------------------------------------------
#
# The streaming variant of run_agent_turn must:
#   - yield persona tokens in the order the provider emitted them,
#   - populate self.last_result with a complete TurnResult once the
#     generator drains,
#   - preserve every side-effect of the non-streaming path (transcript
#     append, TurnEvent emission, FSM advance, fact absorption).



class _StreamingFakeProvider(LLMProvider):
    """
    Provider that natively yields a scripted list of token chunks. Lets
    us assert on token ORDER and on how last_result reconstructs a
    TurnResult from the final chunk. Also implements complete() so this
    class still satisfies the ABC.
    """

    def __init__(self, token_stream: list[str]) -> None:
        self._tokens = list(token_stream)

    @property
    def name(self) -> str:
        return "streaming-fake:test"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        # complete() is not exercised in the streaming tests but the ABC
        # still demands an implementation.
        joined = "".join(self._tokens)
        return LLMResponse(
            content=joined,
            input_tokens=len(joined) // 4,
            output_tokens=len(joined) // 4,
            latency_ms=1,
            provider_name=self.name,
        )

    def stream(self, messages: list[LLMMessage]) -> Iterator[LLMStreamChunk]:
        # Emit each scripted token as its own partial chunk so tests can
        # assert on ordering; close with a sentinel carrying the full
        # LLMResponse (same shape a real provider would build).
        for tok in self._tokens:
            yield LLMStreamChunk(content_delta=tok, is_final=False)
        full = "".join(self._tokens)
        yield LLMStreamChunk(
            content_delta="",
            is_final=True,
            final_response=LLMResponse(
                content=full,
                input_tokens=7,
                output_tokens=11,
                latency_ms=250,
                provider_name=self.name,
            ),
        )


def _make_streaming_orchestrator(
    token_stream: list[str],
) -> SessionOrchestrator:
    scenario, state = _make_scenario_and_state()
    return SessionOrchestrator(
        scenario=scenario,
        persona_provider=_StreamingFakeProvider(token_stream),
        transcript=SessionTranscript(session_id="s1"),
        state=state,
    )


def test_run_agent_turn_streaming_yields_tokens_in_order():
    """The generator emits each partial delta the provider produced."""
    orch = _make_streaming_orchestrator(["Bom ", "dia", ", moço."])
    tokens = list(orch.run_agent_turn_streaming("Bom dia, senhora."))
    assert tokens == ["Bom ", "dia", ", moço."]


def test_run_agent_turn_streaming_populates_last_result_with_full_response():
    """
    After the generator drains, self.last_result must expose a fully-
    formed TurnResult: persona turn appended to the transcript, telemetry
    from the final LLMStreamChunk, FSM state after the FSM advance.
    """
    orch = _make_streaming_orchestrator(["Olá", ", tudo bem."])
    # last_result starts empty; the generator must set it.
    assert orch.last_result is None

    _ = list(orch.run_agent_turn_streaming("Bom dia."))

    result = orch.last_result
    assert result is not None
    assert result.persona_reply.speaker == "persona"
    assert result.persona_reply.content == "Olá, tudo bem."
    assert result.llm_response is not None
    assert result.llm_response.input_tokens == 7
    assert result.llm_response.output_tokens == 11
    assert result.llm_response.latency_ms == 250
    # Transcript on disk has both turns in order.
    assert len(orch.transcript.turns) == 2
    assert orch.transcript.turns[0].speaker == "agent"
    assert orch.transcript.turns[1].speaker == "persona"
    # FSM advanced exactly once (one agent turn = one advance).
    assert result.state_after.turn_count == 1


def test_run_agent_turn_streaming_uses_default_impl_for_non_streaming_provider():
    """
    A provider that only implements complete() (no native stream) still
    works: the ABC default impl wraps complete() into two chunks and the
    orchestrator drains them, populating last_result the same way.
    """
    scenario, state = _make_scenario_and_state()
    provider = FakePersonaProvider(["Legacy answer."])
    orch = SessionOrchestrator(
        scenario=scenario,
        persona_provider=provider,
        transcript=SessionTranscript(session_id="s1"),
        state=state,
    )

    tokens = list(orch.run_agent_turn_streaming("Bom dia."))
    # Default impl emits the full text as ONE partial chunk.
    assert tokens == ["Legacy answer."]
    assert orch.last_result is not None
    assert orch.last_result.persona_reply.content == "Legacy answer."


def test_run_agent_turn_streaming_records_agent_turn_before_llm_call():
    """
    Even if the stream aborts mid-way, the agent turn is already on disk.
    We simulate a mid-stream exception via a provider whose stream() dies
    after yielding one token and check the transcript state.
    """
    class _CrashingStreamProvider(LLMProvider):
        @property
        def name(self) -> str:
            return "crash:test"

        def complete(self, messages: list[LLMMessage]) -> LLMResponse:
            return LLMResponse(
                content="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
                provider_name=self.name,
            )

        def stream(
            self, messages: list[LLMMessage]
        ) -> Iterator[LLMStreamChunk]:
            yield LLMStreamChunk(content_delta="partial", is_final=False)
            raise ConnectionError("network died mid-stream")

    scenario, state = _make_scenario_and_state()
    orch = SessionOrchestrator(
        scenario=scenario,
        persona_provider=_CrashingStreamProvider(),
        transcript=SessionTranscript(session_id="s1"),
        state=state,
    )

    gen = orch.run_agent_turn_streaming("Bom dia, senhora.")
    # First token comes through.
    assert next(gen) == "partial"
    # Second next() propagates the ConnectionError.
    try:
        next(gen)
    except ConnectionError:
        pass
    else:  # pragma: no cover - defensive; test would fail below anyway
        raise AssertionError("expected ConnectionError from stream()")

    # Agent turn IS on disk; persona turn is NOT (stream never reached
    # the append step). last_result stays None so the UI won't persist
    # bogus telemetry.
    assert [t.speaker for t in orch.transcript.turns] == ["agent"]
    assert orch.last_result is None


# ---- Onda 4 F1: action turns land in the persona prompt as stage directions

import json as _json  # noqa: E402  - local alias to avoid stepping on shadowing


def _last_user_prompt_of(orch: SessionOrchestrator) -> str:
    """Return the user_prompt captured on the last provider call."""
    provider = orch.persona_provider
    assert hasattr(provider, "captured_prompts"), "FakePersonaProvider expected"
    _system, user = provider.captured_prompts[-1]
    return user


def test_action_turn_with_document_appears_as_stage_direction_in_prompt():
    """
    2026-09-29 bug: after clicking 'Emitir certidão' the persona would
    ignore that anything had happened. Fix: the action JSON becomes a
    natural-language stage direction attributed to the atendente.
    """
    orch = _make_orchestrator(["Ah, obrigada!"])

    # Simulate the web layer's action-turn shape.
    payload = _json.dumps({
        "action_id": "emit_second_copy",
        "label": "📄 Emitir segunda via",
        "document": {
            "title": "Segunda via da certidão de nascimento",
            "body": "FIC-DOC-000  Documento FICTÍCIO.",
        },
    }, ensure_ascii=False)
    orch.transcript.append("action", payload)

    # Now the atendente sends a follow-up — the LLM will get the summary
    # in its history.
    orch.run_agent_turn("Prontinho, aqui está a certidão.")

    user_prompt = _last_user_prompt_of(orch)
    assert "*emite e entrega o documento 'Segunda via da certidão de nascimento'*" in user_prompt
    # Raw JSON payload must NEVER reach the prompt.
    assert '"action_id"' not in user_prompt
    assert '"document"' not in user_prompt
    assert "FIC-DOC-000" not in user_prompt


def test_action_turn_without_document_appears_as_action_stage_direction():
    orch = _make_orchestrator(["Certo."])
    payload = _json.dumps({
        "action_id": "explain_procedure",
        "label": "📋 Explicar procedimento",
    }, ensure_ascii=False)
    orch.transcript.append("action", payload)

    orch.run_agent_turn("Vou te explicar como funciona.")

    user_prompt = _last_user_prompt_of(orch)
    assert "*executa a ação: Explicar procedimento*" in user_prompt
    assert '"action_id"' not in user_prompt


def test_action_stage_direction_is_attributed_to_the_atendente():
    """
    The persona LLM reads history lines prefixed by 'ATENDENTE (servidor)'
    or 'VOCÊ (cliente)'. An action executed by the trainee must show up
    under the atendente label, not under VOCÊ — otherwise the persona
    thinks SHE performed the action.
    """
    orch = _make_orchestrator(["Certo."])
    payload = _json.dumps({
        "action_id": "verify_identity",
        "label": "🪪 Verificar identidade",
    }, ensure_ascii=False)
    orch.transcript.append("action", payload)

    orch.run_agent_turn("Vou conferir seus dados.")

    user_prompt = _last_user_prompt_of(orch)
    # Find the stage direction line and check its speaker tag.
    stage_line = next(
        line for line in user_prompt.splitlines()
        if "*executa a ação" in line
    )
    assert "ATENDENTE" in stage_line
    assert "VOCÊ" not in stage_line


def test_queue_turn_still_never_reaches_the_prompt():
    """
    Design contract preserved from Onda 2 T1.3: queue-pressure turns are
    an FSM signal, not something the persona 'hears' in dialogue. The
    Onda 4 F1 action-summary change must not accidentally leak them.
    """
    orch = _make_orchestrator(["Ok."])
    orch.transcript.append(
        "queue",
        _json.dumps({"severity": "warning", "minutes_waited": 12}),
    )
    orch.run_agent_turn("Só um instante enquanto verifico.")

    user_prompt = _last_user_prompt_of(orch)
    assert "warning" not in user_prompt
    assert "minutes_waited" not in user_prompt
    assert "12" not in user_prompt


def test_malformed_action_payload_is_dropped_not_raised():
    """
    A corrupt or truncated payload on disk must not crash the turn loop;
    the orchestrator drops the turn silently and the prompt just misses
    that entry.
    """
    orch = _make_orchestrator(["Ok."])
    orch.transcript.append("action", "{not json at all")
    # Should not raise — the summariser returns None and the turn is skipped.
    orch.run_agent_turn("Vou verificar.")
    user_prompt = _last_user_prompt_of(orch)
    assert "{not json" not in user_prompt
