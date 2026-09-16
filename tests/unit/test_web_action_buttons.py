"""
AppTest coverage for the Phase D+++ action buttons + inline document
emission on the "Nova sessão" page.

Follows the same test scaffolding as ``test_web_chat_repl.py``: a
scripted ``_FakeProvider`` is injected via
``civis.chat.provider_factory``; the CIVIS_SESSIONS_DIR env var
redirects writes to ``tmp_path``.

Split into two blocks:

    - D+++.3: buttons render + disabled state reflects `requires`.
    - D+++.4: click handler appends the action turn, optionally
      persists an issued document, and re-checks the gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"


class _FakeProvider(LLMProvider):
    """Minimal scripted provider — reused across every test in this file."""

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
            else self._replies[-1] if self._replies else "..."
        )
        self._calls += 1
        return LLMResponse(
            content=content,
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            provider_name=self._name,
        )


@pytest.fixture()
def chat_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the app at a tmp sessions folder for the duration of the test."""
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


def _inject_factory(at: AppTest, persona_replies: list[str]) -> None:
    """Wire a scripted persona provider so no LLM call reaches the network."""

    def _factory(role: str) -> LLMProvider:
        if role == "persona":
            return _FakeProvider("fake-persona", persona_replies)
        return _FakeProvider("fake-judge", ["{}"])

    at.session_state["civis.chat.provider_factory"] = _factory


def _start_scenario(
    chat_env: Path,
    *,
    scenario_id: str = "certificate_duplicate_confused_v1",
    persona_replies: list[str] | None = None,
) -> AppTest:
    """Boot the landing, click the scenario's start button, and land in chat."""
    del chat_env
    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    _inject_factory(at, persona_replies or ["Oi."])
    at.run()
    btn = next(b for b in at.button if b.key == f"start_{scenario_id}")
    btn.click()
    at.run()
    return at


def _submit_agent_turn(at: AppTest, message: str) -> None:
    """Push one agent message through the chat_input widget."""
    at.chat_input[0].set_value(message).run()


# ---------------------------------------------------------------------------
# D+++.3 — buttons render + disabled reflects requires
# ---------------------------------------------------------------------------


def test_action_buttons_render_below_chat_input_for_confused_scenario(
    chat_env: Path,
) -> None:
    """
    The confused scenario declares 4 actions. All four buttons must be
    rendered with their expected keys.
    """
    at = _start_scenario(chat_env)
    button_keys = {b.key for b in at.button if b.key}
    assert "action_verify_identity" in button_keys
    assert "action_explain_procedure" in button_keys
    assert "action_issue_certificate_copy" in button_keys
    assert "action_end_service" in button_keys


def test_action_button_disabled_when_requires_not_met(chat_env: Path) -> None:
    """
    "Emitir 2ª via de certidão" declares requires=[birth_date, mother_name].
    On session start, no facts are revealed → the button is disabled.
    Then we synthesise the reveal by writing both keys into the
    orchestrator's PersonaState and rerun → it becomes enabled.
    """
    at = _start_scenario(chat_env)
    # Button starts disabled.
    issue_btn = next(b for b in at.button if b.key == "action_issue_certificate_copy")
    assert issue_btn.disabled is True

    # Simulate revealed facts by mutating the orchestrator state directly.
    orch = at.session_state["civis.chat.orchestrator"]
    orch.state = orch.state.model_copy(
        update={"revealed_fact_keys": {"birth_date", "mother_name"}}
    )
    at.run()

    issue_btn = next(b for b in at.button if b.key == "action_issue_certificate_copy")
    assert issue_btn.disabled is False


def test_action_buttons_absent_when_scenario_declares_none(
    chat_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A scenario without an `available_actions` block must render zero
    action_* buttons — retro-compat check.
    """
    # Craft a bare scenario in a scratch scenarios dir and point the
    # app at it via monkeypatch.chdir + a tmp data/scenarios folder.
    scratch = tmp_path / "root"
    scratch_scenarios = scratch / "data" / "scenarios"
    scratch_scenarios.mkdir(parents=True)
    (scratch_scenarios / "bare_v1.yaml").write_text(
        """\
scenario_id: "bare_v1"
title: "Sem ações"
persona:
  kind: "confused"
  name: "Fulana"
  background: |
    b
  goal: |
    g
  initial_emotion: "anxious"
  facts:
    - key: "birth_date"
      value: "12 de março de 1954"
      is_secret: false
expected_agent_actions:
  - "x"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(scratch)
    # Re-point sessions dir under the same scratch so paths stay tidy.
    (chat_env / "kept-empty").mkdir(exist_ok=True)

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    _inject_factory(at, ["Oi."])
    at.run()
    # Directly bypass the landing card wiring by driving _start_session
    # via the same code path a bare scenario id would trigger. The
    # `bare_v1` scenario has no shipped card, so simulate the click by
    # invoking the internal starter through session_state.
    from civis.web.pages import new_session as ns_module

    ns_module._start_session("bare_v1")
    at.run()

    action_keys = [b.key for b in at.button if b.key and b.key.startswith("action_")]
    assert action_keys == []


def test_action_button_click_records_action_turn_in_transcript(
    chat_env: Path,
) -> None:
    """
    Clicking verify_identity (no requires) appends one action turn to
    the transcript on disk.
    """
    at = _start_scenario(chat_env)
    session_id = at.session_state["civis.chat.session_id"]

    click_btn = next(b for b in at.button if b.key == "action_verify_identity")
    click_btn.click()
    at.run()

    transcript_payload = json.loads(
        (chat_env / session_id / "transcript.json").read_text(encoding="utf-8")
    )
    action_turns = [t for t in transcript_payload["turns"] if t["speaker"] == "action"]
    assert len(action_turns) == 1
    payload = json.loads(action_turns[0]["content"])
    assert payload["action_id"] == "verify_identity"
    assert "document" not in payload  # no emits_document on this action
