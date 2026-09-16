"""
AppTest cases for the real-time coach UI (ONDA 3, C3.2 and C3.3).

We reuse the "Nova sessão" fake-provider harness pattern from
:mod:`tests.unit.test_web_chat_repl` — the coach reuses the judge
provider, so wiring the fake judge factory covers the coach too.

Assertions:

    1. The sidebar coach toggle exists and defaults off.
    2. With the toggle ON, after one persona reply the coach bubble
       appears with the model's suggestion.
    3. With the toggle OFF, no coach bubble appears no matter what
       the fake judge returns.
    4. A coach that never returns (timeout path) does not block the
       chat — the turn still commits and the toggle stays on.
    5. A coach whose provider raises degrades to 'no suggestion' —
       again, the turn commits normally.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from civis.coach.coach import Coach, CoachSuggestion
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse
from civis.session.storage import SessionTranscript, Turn
from civis.web.coach_view import compute_suggestion

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"

_AGENT_FIXTURE_MESSAGE = "Bom dia, senhora, sou o atendente."


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------


class _FakeProvider(LLMProvider):
    """Scripted provider matching the one in test_web_chat_repl."""

    def __init__(self, name: str, replies: list[str]) -> None:
        self._name = name
        self._replies = list(replies)
        self._calls = 0

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        content = (
            self._replies[self._calls]
            if self._calls < len(self._replies)
            else self._replies[-1]
        )
        self._calls += 1
        return LLMResponse(
            content=content,
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            provider_name=self._name,
        )


class _SlowProvider(LLMProvider):
    """Provider whose complete() sleeps longer than the coach timeout."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds

    @property
    def name(self) -> str:
        return "slow-coach"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        time.sleep(self._delay)
        return LLMResponse(
            content="⚠️ este texto nunca deve aparecer",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            provider_name=self.name,
        )


class _RaisingProvider(LLMProvider):
    """Provider whose complete() always raises."""

    @property
    def name(self) -> str:
        return "raising-coach"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        raise RuntimeError("coach provider offline")


# ---------------------------------------------------------------------------
# Helper: mirror test_web_chat_repl's inject + start pattern
# ---------------------------------------------------------------------------


def _inject_factory(
    at: AppTest,
    *,
    persona_reply: str,
    judge_reply: str,
) -> None:
    """
    Wire a factory that returns the fake persona for role='persona' and
    the fake judge for anything else. The coach uses the same factory
    (role='judge'), so setting the judge reply also sets the coach reply.
    """
    def _factory(role: str) -> LLMProvider:
        if role == "persona":
            return _FakeProvider("fake-persona", [persona_reply])
        return _FakeProvider("fake-judge", [judge_reply])

    at.session_state["civis.chat.provider_factory"] = _factory


@pytest.fixture()
def chat_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CIVIS_SESSIONS_DIR at a tmp folder."""
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


def _start_chat(
    *,
    persona_reply: str = "Olá.",
    judge_reply: str = "OK",
    scenario_id: str = "certificate_duplicate_confused_v1",
) -> AppTest:
    """Boot 'Nova sessão' → click 'Começar' → return the AppTest in chat view."""
    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    _inject_factory(at, persona_reply=persona_reply, judge_reply=judge_reply)
    at.run()
    btn = next(b for b in at.button if b.key == f"start_{scenario_id}")
    btn.click()
    at.run()
    return at


# ---------------------------------------------------------------------------
# 1. Toggle exists in the sidebar, default off
# ---------------------------------------------------------------------------


def test_coach_toggle_defaults_off(chat_env: Path) -> None:
    """The sidebar exposes a coach toggle, wired to COACH_ENABLED_KEY."""
    del chat_env
    at = _start_chat()
    toggles = [t for t in at.toggle if t.key == "civis.coach_enabled"]
    assert len(toggles) == 1, "expected exactly one 'civis.coach_enabled' toggle"
    assert toggles[0].value is False


# ---------------------------------------------------------------------------
# 2. Toggle ON + agent turn → coach bubble appears with the suggestion
# ---------------------------------------------------------------------------


def test_coach_shows_suggestion_when_enabled(chat_env: Path) -> None:
    """
    Enable the coach, send one agent turn, and verify the coach
    bubble ends up in the markdown stream.
    """
    del chat_env
    at = _start_chat(
        persona_reply="Boa tarde. Vim buscar minha certidão.",
        judge_reply="💡 Considere verificar a identidade antes de emitir.",
    )
    # Flip the toggle on.
    toggle = next(t for t in at.toggle if t.key == "civis.coach_enabled")
    toggle.set_value(True).run()

    # Type one agent message.
    at.chat_input[0].set_value(_AGENT_FIXTURE_MESSAGE).run()

    # The coach bubble carries the class 'civis-coach-bubble' and the
    # suggestion text.
    dump = "\n".join(m.value for m in at.markdown)
    assert "civis-coach-bubble" in dump
    assert "verificar a identidade" in dump


# ---------------------------------------------------------------------------
# 3. Toggle OFF → no coach bubble even if the judge returns a suggestion
# ---------------------------------------------------------------------------


def test_coach_stays_silent_when_disabled(chat_env: Path) -> None:
    """
    With the toggle off, the coach bubble must not render even
    though the fake judge would happily produce a suggestion.
    """
    del chat_env
    at = _start_chat(
        persona_reply="Boa tarde.",
        judge_reply="💡 Deveria aparecer? Nao.",
    )
    # Toggle stays off. Send one agent turn.
    at.chat_input[0].set_value(_AGENT_FIXTURE_MESSAGE).run()
    dump = "\n".join(m.value for m in at.markdown)
    assert "civis-coach-bubble" not in dump


# ---------------------------------------------------------------------------
# 4 + 5. Non-blocking behaviour: timeout and provider error degrade to None
# ---------------------------------------------------------------------------


def _transcript() -> SessionTranscript:
    return SessionTranscript(
        session_id="s1",
        turns=[
            Turn(turn_index=0, speaker="agent", content="oi", timestamp="2026-09-16T10:00:00+00:00"),
            Turn(turn_index=1, speaker="persona", content="oi", timestamp="2026-09-16T10:00:01+00:00"),
        ],
    )


def _dummy_scenario():
    from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile
    from civis.session.scenario import ScenarioFile
    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="X",
        background="b",
        goal="g",
        facts=[PersonaFact(key="k", value="v")],
    )
    return ScenarioFile(
        scenario_id="cen",
        title="Cen",
        persona=profile,
        expected_agent_actions=["A"],
    )


def test_compute_suggestion_returns_none_on_timeout() -> None:
    """A coach that takes longer than the timeout yields None."""
    coach = Coach(provider=_SlowProvider(delay_seconds=1.5), scenario=_dummy_scenario())
    started = time.perf_counter()
    result = compute_suggestion(coach, _transcript(), timeout_seconds=0.3)
    elapsed = time.perf_counter() - started
    assert result is None
    # The call must return roughly at the timeout, NOT wait the full
    # provider delay. Allow a generous 1.0s ceiling to keep the test
    # stable on slow CI machines.
    assert elapsed < 1.0


def test_compute_suggestion_returns_none_on_provider_error() -> None:
    """A raising provider degrades to a silent no-suggestion."""
    coach = Coach(provider=_RaisingProvider(), scenario=_dummy_scenario())
    result = compute_suggestion(coach, _transcript(), timeout_seconds=2.0)
    assert result is None


def test_compute_suggestion_returns_suggestion_when_provider_responds() -> None:
    """Happy path: a working provider yields a CoachSuggestion."""
    provider = _FakeProvider("mock", ["⚠️ atenção: identidade não confirmada"])
    coach = Coach(provider=provider, scenario=_dummy_scenario())
    result = compute_suggestion(coach, _transcript(), timeout_seconds=2.0)
    assert isinstance(result, CoachSuggestion)
    assert result.type == "warning"
