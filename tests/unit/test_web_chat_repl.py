"""
AppTest coverage for the Fase D+ chat REPL that lives inside the
"Nova sessão" Streamlit page.

The tests never touch a real LLM provider — every AppTest injects a
scripted ``FakePersonaProvider`` via the ``civis.chat.provider_factory``
session_state hook. Each test runs against a tmp ``CIVIS_SESSIONS_DIR``
so nothing under ``data/sessions/`` is read or written.

Layout of the file follows the entregável split D+.1..D+.5:

    - Landing (D+.1): three "Começar atendimento" buttons + random start.
    - Chat loop (D+.2): bubbles, input, per-turn persistence.
    - Finalize (D+.3): judge run + inline verdict view.
    - Error states (D+.4): provider crash surfaces as ``st.error``.
    - Telemetry (D+.5): turn_telemetry.json matches the CLI shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse

# Resolved once — AppTest.switch_page needs an absolute path when the
# main script lives outside the current working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"

# The three shipped scenarios the landing exposes.
_SHIPPING_SCENARIO_IDS = (
    "certificate_duplicate_confused_v1",
    "rg_urgent_aggressive_v1",
    "certificate_thirdparty_fraudster_v1",
)


# ---------------------------------------------------------------------------
# Fake provider — reused across every test
# ---------------------------------------------------------------------------


class _FakeProvider(LLMProvider):
    """
    Scripted provider that returns canned replies (or a canned verdict
    JSON when used as the judge). Also lets a test toggle it into
    "raises" mode to exercise the D+.4 error surface.
    """

    def __init__(
        self,
        name: str,
        replies: list[str],
        *,
        raises: BaseException | None = None,
    ) -> None:
        self._name = name
        self._replies = list(replies)
        self._raises = raises
        self._calls = 0
        self.captured_messages: list[list[LLMMessage]] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        if self._raises is not None:
            raise self._raises
        self.captured_messages.append(list(messages))
        content = (
            self._replies[self._calls]
            if self._calls < len(self._replies)
            else self._replies[-1] if self._replies else "..."
        )
        self._calls += 1
        return LLMResponse(
            content=content,
            input_tokens=42,
            output_tokens=13,
            latency_ms=250,
            provider_name=self._name,
        )


def _canned_verdict_json(session_id: str) -> str:
    """
    Minimal but schema-valid judge verdict JSON. The four criteria match
    the shipped rubric so parse_judge_response doesn't reject it.
    """
    return (
        "{"
        f'"session_id": "{session_id}",'
        '"overall_summary": "Atendimento simulado — verdict de teste.",'
        '"criteria": ['
        '{"criterion": "fact_verification", "score": 4,'
        ' "rationale": "Confirmou dados antes de emitir.",'
        ' "cited_turns": [{"turn_index": 0, "excerpt": "olá"}]},'
        '{"criterion": "protocol_adherence", "score": 4,'
        ' "rationale": "Seguiu o roteiro.",'
        ' "cited_turns": [{"turn_index": 0, "excerpt": "olá"}]},'
        '{"criterion": "empathy", "score": 4,'
        ' "rationale": "Tom empático.",'
        ' "cited_turns": [{"turn_index": 0, "excerpt": "olá"}]},'
        '{"criterion": "data_protection", "score": 4,'
        ' "rationale": "Não vazou honeytoken.",'
        ' "cited_turns": [{"turn_index": 0, "excerpt": "olá"}]}'
        "]}"
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def chat_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """
    Point the app at a tmp sessions folder so every test writes into
    ``tmp_path`` and never touches ``data/sessions/``.
    """
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


def _boot_landing(chat_env: Path) -> AppTest:
    """
    Boot the app on the "Nova sessão" landing with a provider factory
    already injected. Every test starts from here.
    """
    del chat_env  # only used for its side-effect (env var set by fixture)
    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    _inject_provider_factory(at, persona_replies=["Olá, sou a Iracema."])
    at.run()
    return at


def _inject_provider_factory(
    at: AppTest,
    *,
    persona_replies: list[str],
    persona_raises: BaseException | None = None,
    judge_verdict_json: str | None = None,
    judge_raises: BaseException | None = None,
) -> None:
    """
    Wire a scripted persona (and judge) into ``st.session_state`` so
    ``_build_provider`` picks them up instead of talking to Ollama.
    The judge factory only matters for D+.3 tests.
    """
    persona = _FakeProvider(
        "fake-persona", persona_replies, raises=persona_raises
    )

    def _factory(role: str) -> LLMProvider:
        if role == "persona":
            return persona
        # judge role — only reached in D+.3 finalize path.
        judge_replies = (
            [judge_verdict_json] if judge_verdict_json is not None else ["{}"]
        )
        return _FakeProvider("fake-judge", judge_replies, raises=judge_raises)

    at.session_state["civis.chat.provider_factory"] = _factory


# ---------------------------------------------------------------------------
# D+.1 — landing view
# ---------------------------------------------------------------------------


def test_landing_shows_three_scenario_buttons(chat_env: Path) -> None:
    """One 'Começar atendimento' per shipped scenario, plus the random one."""
    at = _boot_landing(chat_env)
    keys = {b.key for b in at.button if b.key}
    for scenario_id in _SHIPPING_SCENARIO_IDS:
        assert f"start_{scenario_id}" in keys
    assert "start_random" in keys


def test_landing_hides_legacy_cli_command_block(chat_env: Path) -> None:
    """
    The old 'python -m civis session --scenario ...' code block must
    be gone — Anderson explicitly asked to move that flow inline.
    """
    at = _boot_landing(chat_env)
    code_texts = " ".join(c.value for c in at.code)
    assert "python -m civis session" not in code_texts


def test_random_button_starts_a_session_from_a_shipping_scenario(
    chat_env: Path,
) -> None:
    """
    Clicking 'Sessão aleatória' picks one of the three scripted scenarios
    and flips the view state to "chat" (or the D+.1 placeholder).
    """
    at = _boot_landing(chat_env)
    random_btn = next(b for b in at.button if b.key == "start_random")
    random_btn.click()
    at.run()
    assert at.session_state["civis.chat.view"] == "chat"
    assert at.session_state["civis.chat.scenario_id"] in _SHIPPING_SCENARIO_IDS


def test_choosing_scenario_opens_chat_view_with_expected_id(
    chat_env: Path,
) -> None:
    """Clicking a specific scenario card starts that exact session."""
    at = _boot_landing(chat_env)
    picked_id = "rg_urgent_aggressive_v1"
    btn = next(b for b in at.button if b.key == f"start_{picked_id}")
    btn.click()
    at.run()
    assert at.session_state["civis.chat.view"] == "chat"
    assert at.session_state["civis.chat.scenario_id"] == picked_id
    # Metadata + transcript were written on start-up.
    session_id = at.session_state["civis.chat.session_id"]
    session_folder = chat_env / session_id
    assert (session_folder / "metadata.json").exists()
    assert (session_folder / "transcript.json").exists()
