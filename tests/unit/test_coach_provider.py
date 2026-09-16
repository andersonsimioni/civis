"""
Unit tests for :mod:`civis.coach.coach` (ONDA 3, C3.1).

The coach is an LLM-facing helper, so the tests use a scripted
provider that records the messages it received and returns the
canned reply of the case. That is enough to pin:

    - the coach maps 'OK' replies to ``None`` (no hint this turn);
    - the coach maps emoji-prefixed messages to the right suggestion
      type;
    - the prompt injected into the provider carries the scenario
      title, expected actions and recent transcript;
    - a blank reply also becomes ``None``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from civis.coach.coach import Coach, CoachSuggestion, _parse_reply
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse
from civis.personas.base import PersonaFact, PersonaProfile
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript, Turn

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _RecordingProvider(LLMProvider):
    """
    Provider that returns a canned reply and stores the last
    prompt it received so the tests can inspect what the coach
    actually sent.
    """

    def __init__(self, reply: str, provider_name: str = "coach-mock") -> None:
        self._reply = reply
        self._name = provider_name
        self.last_messages: list[LLMMessage] | None = None
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        self.last_messages = list(messages)
        self.call_count += 1
        return LLMResponse(
            content=self._reply,
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            provider_name=self._name,
        )


def _scenario() -> ScenarioFile:
    """Minimal scenario with a distinctive title + one expected action."""
    from civis.personas.base import PersonaKind
    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Iracema Silva",
        background="Idosa aposentada procurando a segunda via da certidão.",
        goal="Emitir uma segunda via da certidão de nascimento.",
        facts=[
            PersonaFact(key="full_name", value="Iracema Silva"),
        ],
    )
    return ScenarioFile(
        scenario_id="cen_v1",
        title="Segunda via de certidão de nascimento",
        persona=profile,
        expected_agent_actions=[
            "Verificar identidade do cidadão antes de emitir.",
        ],
    )


def _transcript(*turns: tuple[str, str]) -> SessionTranscript:
    return SessionTranscript(
        session_id="s1",
        turns=[
            Turn(
                turn_index=i,
                speaker=speaker,
                content=content,
                timestamp=datetime.now(UTC).isoformat(),
            )
            for i, (speaker, content) in enumerate(turns)
        ],
    )


# ---------------------------------------------------------------------------
# 1. 'OK' reply → no suggestion
# ---------------------------------------------------------------------------


def test_ok_reply_maps_to_none() -> None:
    """The prompt tells the model to answer 'OK' when there is no hint."""
    provider = _RecordingProvider(reply="OK")
    coach = Coach(provider=provider, scenario=_scenario())
    result = coach.suggest_next_move(_transcript(("agent", "Bom dia")))
    assert result is None
    # Verify the provider actually got called (the test would trivially
    # pass if the coach short-circuited).
    assert provider.call_count == 1


# ---------------------------------------------------------------------------
# 2. Emoji-prefixed reply → CoachSuggestion of the right type
# ---------------------------------------------------------------------------


def test_warning_reply_produces_warning_suggestion() -> None:
    """A ⚠️-prefixed reply becomes a 'warning' suggestion."""
    provider = _RecordingProvider(
        reply="⚠️ Verifique a identidade antes de emitir o documento."
    )
    coach = Coach(provider=provider, scenario=_scenario())
    result = coach.suggest_next_move(_transcript(("agent", "aqui está")))
    assert result is not None
    assert isinstance(result, CoachSuggestion)
    assert result.type == "warning"
    assert result.emoji == "⚠️"
    assert "identidade" in result.message.lower()


def test_hint_reply_produces_hint_suggestion() -> None:
    """A 💡-prefixed reply becomes a 'hint' suggestion."""
    provider = _RecordingProvider(
        reply="💡 Considere confirmar o nome da mãe antes de seguir."
    )
    coach = Coach(provider=provider, scenario=_scenario())
    result = coach.suggest_next_move(_transcript(("agent", "bom dia")))
    assert result is not None
    assert result.type == "hint"


# ---------------------------------------------------------------------------
# 3. The prompt carries the scenario + expected actions + transcript tail
# ---------------------------------------------------------------------------


def test_prompt_contains_scenario_and_transcript_context() -> None:
    """
    The system message must mention the scenario title and expected
    actions; the user message must carry the last dialogue turns.
    """
    provider = _RecordingProvider(reply="OK")
    coach = Coach(provider=provider, scenario=_scenario())
    coach.suggest_next_move(
        _transcript(
            ("agent", "Bom dia, senhora."),
            ("persona", "Bom dia, meu jovem."),
        )
    )

    assert provider.last_messages is not None
    system_content = provider.last_messages[0].content
    user_content = provider.last_messages[1].content

    # System message carries scenario title + expected action.
    assert "Segunda via de certidão de nascimento" in system_content
    assert "Verificar identidade" in system_content

    # User message carries the labelled dialogue turns.
    assert "ATENDENTE:" in user_content
    assert "CIDADÃO:" in user_content
    assert "Bom dia, senhora." in user_content


# ---------------------------------------------------------------------------
# 4. Blank / whitespace reply → None
# ---------------------------------------------------------------------------


def test_blank_reply_maps_to_none() -> None:
    """Whitespace-only replies are treated the same as 'no hint'."""
    provider = _RecordingProvider(reply="   \n\t  ")
    coach = Coach(provider=provider, scenario=_scenario())
    assert coach.suggest_next_move(_transcript(("agent", "oi"))) is None


# ---------------------------------------------------------------------------
# 5. Parser bonus: variant OK spellings + unprefixed suggestions
# ---------------------------------------------------------------------------


def test_parse_reply_variants() -> None:
    """The private parser handles common wrapping quirks."""
    # 'okay' / 'tudo certo' also mean 'no hint'.
    assert _parse_reply("okay") is None
    assert _parse_reply('"OK"') is None
    assert _parse_reply("tudo certo") is None

    # An emoji-less suggestion still parses, defaulting to 'hint'.
    parsed = _parse_reply("Peça o CPF antes de qualquer emissão.")
    assert parsed is not None
    assert parsed.type == "hint"
    assert parsed.emoji == ""
    assert "CPF" in parsed.message
