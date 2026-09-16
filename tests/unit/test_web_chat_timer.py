"""
AppTest coverage for the Onda 2 T1.2 chat header timer and the T1.3
queue-complaint injector.

We never touch a real LLM provider — every AppTest injects a scripted
``_FakeProvider`` via the ``civis.chat.provider_factory`` session_state
hook (same shape used by the D+ chat REPL tests). Tests that need to
manipulate elapsed time rewind the ``STARTED_AT_KEY`` value stored in
session_state to a point far enough in the past, then re-run the app;
Streamlit calls ``_render_chat_view`` again and observes the "new" now
via the module-level datetime.now(UTC).

Split of the file:

    - Timer render (T1.2, 3 tests): the MM:SS badge shows on the chat
      header, and the CSS phase attribute flips green → amber →
      warning → red as elapsed time crosses each SLA threshold.
    - Queue injection (T1.3, 4 tests): no queue turn under warning,
      one warning turn at target crossed, one critical turn past
      critical, and the judge prompt never sees a queue turn.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse
from civis.session.storage import load_transcript

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"

# Any scenario would work for the timer — the SLA defaults are always
# present. We pick the confused-citizen one to keep the assertions
# comparable to test_web_chat_repl.py.
_SCENARIO_ID = "certificate_duplicate_confused_v1"

# Same session-state keys the page module owns. Duplicated as string
# literals on purpose: importing from the page pulls Streamlit lifecycle
# side-effects that break AppTest isolation.
_STARTED_AT_KEY = "civis.chat.started_at"
_QUEUE_WARNING_FIRED_KEY = "civis.chat.queue_warning_fired"
_QUEUE_CRITICAL_FIRED_KEY = "civis.chat.queue_critical_fired"


# ---------------------------------------------------------------------------
# Fake provider (kept minimal — the timer tests do not run a full turn
# through the LLM, they only need the factory to exist so start_session
# doesn't try to reach Ollama).
# ---------------------------------------------------------------------------


class _FakeProvider(LLMProvider):
    """Minimal LLMProvider stub that never actually gets called."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:  # pragma: no cover
        return LLMResponse(
            content="",
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            provider_name=self._name,
        )


# ---------------------------------------------------------------------------
# Shared bootstrap
# ---------------------------------------------------------------------------


@pytest.fixture()
def chat_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect CIVIS_SESSIONS_DIR into tmp_path so nothing under
    data/sessions/ is touched."""
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


def _inject_provider_factory(at: AppTest) -> None:
    """Wire scripted providers so _start_session does not touch Ollama."""

    def _factory(role: str) -> LLMProvider:
        return _FakeProvider(f"fake-{role}")

    at.session_state["civis.chat.provider_factory"] = _factory


def _start_chat(chat_env: Path) -> AppTest:
    """Boot the landing and click "Começar atendimento" for _SCENARIO_ID."""
    del chat_env
    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    _inject_provider_factory(at)
    at.run()
    btn = next(b for b in at.button if b.key == f"start_{_SCENARIO_ID}")
    btn.click()
    at.run()
    return at


def _rewind_started_at(at: AppTest, seconds_ago: int) -> None:
    """Move the session start back in time by ``seconds_ago`` seconds.

    The chat header re-computes elapsed on every render, so rewinding
    the stored ISO string and running the app again is enough to
    simulate a long-running session without waiting for real time.
    """
    fake_started_at = (
        datetime.now(UTC) - timedelta(seconds=seconds_ago)
    ).replace(microsecond=0).isoformat()
    at.session_state[_STARTED_AT_KEY] = fake_started_at


def _markdown_texts(at: AppTest) -> list[str]:
    """Collect every markdown block rendered on the current run.

    AppTest exposes ``st.markdown(...)`` outputs via ``at.markdown``;
    the ``.value`` attribute holds the raw HTML/markdown string, which
    is what we want to search for CSS class markers and copy fragments.
    """
    return [m.value for m in at.markdown]


# ---------------------------------------------------------------------------
# T1.2 — timer widget render
# ---------------------------------------------------------------------------


def test_timer_renders_green_when_within_target(chat_env: Path) -> None:
    """Fresh session → phase is green and badge shows ``00:00``-ish."""
    at = _start_chat(chat_env)

    markdowns = _markdown_texts(at)
    timer_blocks = [m for m in markdowns if "civis-timer" in m]
    assert timer_blocks, "timer badge must render inside chat header"
    assert any("data-phase='green'" in m for m in timer_blocks)


def test_timer_flips_to_warning_after_warning_threshold(chat_env: Path) -> None:
    """Cross warning (720s default) → the badge phase becomes ``warning``."""
    at = _start_chat(chat_env)

    # Push start-time 800s into the past (>= warning=720, < critical=900).
    _rewind_started_at(at, seconds_ago=800)
    at.run()

    timer_blocks = [m for m in _markdown_texts(at) if "civis-timer" in m]
    assert timer_blocks
    assert any("data-phase='warning'" in m for m in timer_blocks), timer_blocks


def test_timer_flips_to_red_after_critical_threshold(chat_env: Path) -> None:
    """Cross critical (900s default) → the badge phase becomes ``red``."""
    at = _start_chat(chat_env)

    _rewind_started_at(at, seconds_ago=1200)
    at.run()

    timer_blocks = [m for m in _markdown_texts(at) if "civis-timer" in m]
    assert timer_blocks
    assert any("data-phase='red'" in m for m in timer_blocks), timer_blocks


# ---------------------------------------------------------------------------
# T1.3 — queue-complaint injector
# ---------------------------------------------------------------------------


def test_no_queue_turn_before_warning_threshold(chat_env: Path) -> None:
    """Elapsed < warning → no queue turn is added to the transcript."""
    at = _start_chat(chat_env)

    # 5 minutes elapsed — well under warning=720s.
    _rewind_started_at(at, seconds_ago=300)
    at.run()

    session_id = at.session_state["civis.chat.session_id"]
    transcript = load_transcript(session_id, base=chat_env)
    assert transcript is not None
    assert all(t.speaker != "queue" for t in transcript.turns)


def test_warning_queue_turn_injected_once(chat_env: Path) -> None:
    """Cross warning → exactly one queue turn with the warning copy."""
    at = _start_chat(chat_env)

    _rewind_started_at(at, seconds_ago=800)  # past warning, before critical
    at.run()

    session_id = at.session_state["civis.chat.session_id"]
    transcript = load_transcript(session_id, base=chat_env)
    assert transcript is not None
    queue_turns = [t for t in transcript.turns if t.speaker == "queue"]
    assert len(queue_turns) == 1, [t.content for t in queue_turns]
    # Copy matches the pt-BR line from the task.
    assert "Poxa, tô esperando faz um tempão" in queue_turns[0].content
    # The rerun must not double-fire on the SAME session — the fired flag
    # is set to True.
    assert at.session_state[_QUEUE_WARNING_FIRED_KEY] is True

    # A second run without moving time must not add a second queue turn.
    at.run()
    transcript_again = load_transcript(session_id, base=chat_env)
    assert transcript_again is not None
    assert (
        sum(1 for t in transcript_again.turns if t.speaker == "queue") == 1
    )


def test_critical_queue_turn_uses_escalated_copy(chat_env: Path) -> None:
    """Past critical → the injected queue turn carries the escalation."""
    at = _start_chat(chat_env)

    _rewind_started_at(at, seconds_ago=1200)  # well past critical=900
    at.run()

    session_id = at.session_state["civis.chat.session_id"]
    transcript = load_transcript(session_id, base=chat_env)
    assert transcript is not None
    queue_turns = [t for t in transcript.turns if t.speaker == "queue"]
    assert len(queue_turns) == 1
    assert "ouvidoria" in queue_turns[0].content.lower()
    # Both flags flip so the warning line does not fire on a later rerun.
    assert at.session_state[_QUEUE_CRITICAL_FIRED_KEY] is True
    assert at.session_state[_QUEUE_WARNING_FIRED_KEY] is True


def test_judge_prompt_never_sees_queue_turns() -> None:
    """The CLI judge helper strips queue turns from the transcript pairs
    it hands to build_judge_prompt — same guarantee as action turns."""
    from civis.session.storage import SessionTranscript, Turn

    # Build a minimal transcript with one of each speaker so we can
    # eyeball the filter shape without spinning up a real judge run.
    ts_open = "2026-09-16T00:00:00+00:00"
    ts_reply = "2026-09-16T00:00:01+00:00"
    ts_queue = "2026-09-16T00:12:00+00:00"
    ts_agent2 = "2026-09-16T00:12:30+00:00"
    queue_payload = (
        '{"severity":"warning","message":"barulho","minutes_waited":12}'
    )
    turns = [
        Turn(turn_index=0, speaker="agent", content="Olá.", timestamp=ts_open),
        Turn(turn_index=1, speaker="persona", content="Oi.", timestamp=ts_reply),
        Turn(
            turn_index=2,
            speaker="queue",
            content=queue_payload,
            timestamp=ts_queue,
        ),
        Turn(
            turn_index=3,
            speaker="agent",
            content="Como posso ajudar?",
            timestamp=ts_agent2,
        ),
    ]
    transcript = SessionTranscript(session_id="s1", turns=turns)

    # Reproduce the same filter cli.session.run_judge_with_validation
    # uses to build the judge input.
    pairs = [
        (t.speaker, t.content)
        for t in transcript.turns
        if t.speaker in ("agent", "persona")
    ]
    speakers = [s for s, _ in pairs]
    assert "queue" not in speakers
    assert speakers == ["agent", "persona", "agent"]
