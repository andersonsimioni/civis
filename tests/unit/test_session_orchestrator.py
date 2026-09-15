"""
Session orchestrator tests.

Uses a scripted FakePersonaProvider so we exercise the full turn loop
without any LLM. Two things the acceptance criterion of A.2 demands:

    - 10 turns run to completion without crashing.
    - Facts are not revealed twice: once absorbed into
      state.revealed_fact_keys, they don't show up in
      newly_revealed_fact_keys on subsequent turns.
"""

from civis.fsm.states import EmotionalState, Phase
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse
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
