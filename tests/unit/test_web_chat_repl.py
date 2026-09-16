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

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse
from civis.web.data_access import load_turn_telemetry

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

# A short excerpt that shows up verbatim in every fixture agent turn —
# the citation validator wants substring matches against a real turn.
_AGENT_FIXTURE_MESSAGE = "Bom dia, senhora, sou o atendente."
_JUDGE_CITATION_EXCERPT = "Bom dia"


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


def _canned_verdict_json(*, excerpt: str) -> str:
    """
    Minimal but schema-valid judge verdict JSON. The four criteria match
    the shipped rubric so parse_judge_response doesn't reject it, and
    the citation ``excerpt`` must be a verbatim substring of the agent
    turn used in tests (see ``_AGENT_FIXTURE_MESSAGE``). ``session_id``
    inside the payload is a placeholder — parse_judge_response overrides
    it with the caller's id.
    """
    safe_excerpt = excerpt.replace('"', '\\"')
    citation = (
        '"cited_turns": [{"turn_index": 0, "excerpt": "'
        + safe_excerpt
        + '"}]'
    )
    return (
        "{"
        '"session_id": "placeholder-id",'
        '"overall_summary": "Atendimento simulado — verdict de teste.",'
        '"criteria": ['
        '{"criterion": "fact_verification", "score": 4,'
        ' "rationale": "Confirmou dados antes de emitir.",'
        f' {citation}}},'
        '{"criterion": "data_protection", "score": 4,'
        ' "rationale": "Não vazou honeytoken.",'
        f' {citation}}},'
        '{"criterion": "protocol_adherence", "score": 4,'
        ' "rationale": "Seguiu o roteiro.",'
        f' {citation}}},'
        '{"criterion": "communication", "score": 4,'
        ' "rationale": "Tom claro e respeitoso.",'
        f' {citation}}}'
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
    judge_replies: list[str] | None = None,
    judge_raises: BaseException | None = None,
) -> None:
    """
    Wire a scripted persona (and judge) into ``st.session_state`` so
    ``_build_provider`` picks them up instead of talking to Ollama.
    The judge factory only matters for D+.3 tests.

    Both providers are captured lazily: the factory returns a fresh
    ``_FakeProvider`` on each call so the persona (built at
    _start_session) and the judge (built at _start_session too, then
    reused across citation-validator retries) each get their own reply
    stream.
    """
    def _factory(role: str) -> LLMProvider:
        if role == "persona":
            return _FakeProvider(
                "fake-persona", persona_replies, raises=persona_raises
            )
        # judge role — only reached in D+.3 finalize path.
        default_judge = ["{}", "{}"]
        return _FakeProvider(
            "fake-judge",
            judge_replies if judge_replies is not None else default_judge,
            raises=judge_raises,
        )

    at.session_state["civis.chat.provider_factory"] = _factory


def _start_scenario(
    chat_env: Path,
    *,
    scenario_id: str = "certificate_duplicate_confused_v1",
    persona_replies: list[str] | None = None,
    persona_raises: BaseException | None = None,
    judge_replies: list[str] | None = None,
    judge_raises: BaseException | None = None,
) -> AppTest:
    """
    Boot the landing, wire a fake provider, and click the "Começar" button
    for a specific scenario. Returns the AppTest already advanced into
    the chat view.
    """
    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    _inject_provider_factory(
        at,
        persona_replies=persona_replies or ["Olá, sou a Iracema."],
        persona_raises=persona_raises,
        judge_replies=judge_replies,
        judge_raises=judge_raises,
    )
    at.run()
    btn = next(b for b in at.button if b.key == f"start_{scenario_id}")
    btn.click()
    at.run()
    return at


def _submit_one_turn(at: AppTest, agent_message: str = _AGENT_FIXTURE_MESSAGE) -> None:
    """Type ``agent_message`` into the chat_input and advance one turn."""
    at.chat_input[0].set_value(agent_message).run()


def _session_state_get(at: AppTest, key: str) -> object | None:
    """
    Safe read of a session_state key from AppTest. ``st.session_state``
    exposes ``.get()`` inside the app but AppTest's ``SafeSessionState``
    wrapper does not; membership + subscript is the portable path.
    """
    if key in at.session_state:
        return at.session_state[key]
    return None


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
    and flips the view state to "chat".
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


# ---------------------------------------------------------------------------
# D+.2 — chat view: header, bubbles, input, per-turn persistence, cancel
# ---------------------------------------------------------------------------


def test_chat_view_renders_header_with_scenario_label(chat_env: Path) -> None:
    """After starting a session, the chat view shows the scenario title."""
    at = _start_scenario(chat_env, scenario_id="rg_urgent_aggressive_v1")
    # The friendly scenario label is used as an H3 markdown.
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "Segunda via de RG" in markdown_text
    # Header carries Encerrar and Cancelar buttons.
    button_keys = {b.key for b in at.button if b.key}
    assert "finalize_chat" in button_keys
    assert "cancel_chat" in button_keys


def test_agent_message_produces_persona_bubble_and_persists_turn(
    chat_env: Path,
) -> None:
    """
    Typing into ``st.chat_input`` runs one persona turn: two chat_message
    bubbles appear (agent + persona) and transcript.json now has 2 turns.
    """
    at = _start_scenario(
        chat_env,
        persona_replies=["Ah, obrigada, meu filho, estou muito confusa hoje."],
    )
    session_id = at.session_state["civis.chat.session_id"]

    _submit_one_turn(at)

    # Two chat bubbles rendered.
    assert len(at.chat_message) >= 2
    # Transcript on disk has both turns.
    transcript_payload = json.loads(
        (chat_env / session_id / "transcript.json").read_text(encoding="utf-8")
    )
    assert len(transcript_payload["turns"]) == 2
    assert transcript_payload["turns"][0]["speaker"] == "agent"
    assert transcript_payload["turns"][1]["speaker"] == "persona"
    # Turn count in state matches (one agent turn was recorded).
    assert at.session_state["civis.chat.turn_count"] == 1


def test_cancel_button_clears_chat_state_and_returns_to_landing(
    chat_env: Path,
) -> None:
    """Clicking 'Cancelar' drops every civis.chat.* key and goes back."""
    at = _start_scenario(chat_env)
    assert at.session_state["civis.chat.view"] == "chat"

    cancel_btn = next(b for b in at.button if b.key == "cancel_chat")
    cancel_btn.click()
    at.run()

    assert at.session_state["civis.chat.view"] == "landing"
    # Orchestrator and session id were dropped.
    assert "civis.chat.orchestrator" not in at.session_state
    assert "civis.chat.session_id" not in at.session_state


def test_reaching_max_turns_hides_input_and_offers_finalize(
    chat_env: Path,
) -> None:
    """
    After the soft cap, the plain chat_input goes away and we surface
    'Continuar mesmo assim' + 'Encerrar e avaliar' buttons.
    """
    at = _start_scenario(chat_env)
    # Force the state right into the "cap reached" arm.
    at.session_state["civis.chat.turn_count"] = 12
    at.session_state["civis.chat.max_turns"] = 12
    at.run()

    button_keys = {b.key for b in at.button if b.key}
    assert "extend_max_turns" in button_keys
    assert "finalize_from_cap" in button_keys
    # No free-typing input in this arm.
    assert len(at.chat_input) == 0
    # Warning copy is present.
    warning_text = " ".join(w.value for w in at.warning)
    assert "Limite" in warning_text


# ---------------------------------------------------------------------------
# D+.3 — finalize: judge run + inline verdict view
# ---------------------------------------------------------------------------


def test_finalize_button_runs_judge_and_renders_verdict_view(
    chat_env: Path,
) -> None:
    """
    After one real agent turn, clicking 'Encerrar e avaliar' saves the
    verdict + sidecars to disk and switches to the verdict view.
    """
    verdict_json = _canned_verdict_json(excerpt=_JUDGE_CITATION_EXCERPT)
    at = _start_scenario(
        chat_env,
        persona_replies=["Alô, tudo bem sim, obrigada."],
        # The citation validator can call the judge twice on retry; give
        # both attempts the same schema-valid verdict.
        judge_replies=[verdict_json, verdict_json],
    )
    session_id = at.session_state["civis.chat.session_id"]

    _submit_one_turn(at, agent_message=_AGENT_FIXTURE_MESSAGE)

    # Click the persistent 'Encerrar e avaliar' button.
    finalize_btn = next(b for b in at.button if b.key == "finalize_chat")
    finalize_btn.click()
    at.run()

    assert at.session_state["civis.chat.view"] == "verdict"
    # Every sidecar exists on disk.
    session_folder = chat_env / session_id
    assert (session_folder / "verdict.json").exists()
    assert (session_folder / "contradictions.json").exists()
    assert (session_folder / "honeytoken_leaks.json").exists()
    # The finalise subheader is rendered.
    subheaders = [s.value for s in at.subheader]
    assert any("finalizada" in s.lower() for s in subheaders)


def test_finalize_with_zero_turns_shows_warning_and_no_verdict(
    chat_env: Path,
) -> None:
    """Finalising an empty transcript surfaces a warning, no judge call."""
    at = _start_scenario(chat_env)
    session_id = at.session_state["civis.chat.session_id"]

    finalize_btn = next(b for b in at.button if b.key == "finalize_chat")
    finalize_btn.click()
    at.run()

    assert at.session_state["civis.chat.view"] == "verdict"
    # No verdict.json produced.
    assert not (chat_env / session_id / "verdict.json").exists()
    # The verdict view shows the "no verdict" info message.
    info_text = " ".join(i.value for i in at.info)
    assert "Não há verdict" in info_text


def test_restart_button_from_verdict_view_returns_to_landing(
    chat_env: Path,
) -> None:
    """'Nova sessão' on the verdict view resets civis.chat.* state."""
    at = _start_scenario(chat_env)
    at.session_state["civis.chat.view"] = "verdict"
    at.run()

    restart_btn = next(b for b in at.button if b.key == "restart_from_verdict")
    restart_btn.click()
    at.run()

    assert at.session_state["civis.chat.view"] == "landing"
    assert "civis.chat.orchestrator" not in at.session_state



# ---------------------------------------------------------------------------
# D+.4 — loading spinners and provider error states
# ---------------------------------------------------------------------------


def test_persona_provider_failure_shows_actionable_error_in_ptbr(
    chat_env: Path,
) -> None:
    """
    A ConnectionError from the persona provider must NOT crash the app:
    the chat view stays live, and a pt-BR error banner tells the user
    what to try (Ollama offline, API key, etc.).
    """
    at = _start_scenario(
        chat_env,
        persona_raises=ConnectionError("connection refused by localhost:11434"),
    )
    # An agent turn now raises inside the orchestrator.
    _submit_one_turn(at)

    assert at.session_state["civis.chat.view"] == "chat"
    error_text = " ".join(e.value for e in at.error)
    assert "Ollama" in error_text or "API key" in error_text
    # The transcript on disk still has the agent turn (recorded before
    # the LLM call) but no persona reply.
    session_id = at.session_state["civis.chat.session_id"]
    transcript_payload = json.loads(
        (chat_env / session_id / "transcript.json").read_text(encoding="utf-8")
    )
    # The initial (empty) transcript was saved at start_session; the
    # failing turn did not re-persist a persona turn, so we should still
    # have zero persona turns on disk.
    persona_turns = [t for t in transcript_payload["turns"] if t["speaker"] == "persona"]
    assert persona_turns == []


def test_start_session_with_missing_scenario_stays_on_landing(
    chat_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    If the scenario yaml can't be resolved, the start-session flow flags
    an st.error on the landing without flipping the view.
    """
    # Point scenarios lookup at an empty folder so resolve_scenario_path fails.
    empty_scenarios = tmp_path / "scenarios"
    empty_scenarios.mkdir()
    monkeypatch.chdir(tmp_path)  # so 'data/scenarios' resolves under tmp

    at = _boot_landing(chat_env)
    btn = next(b for b in at.button if b.key == "start_certificate_duplicate_confused_v1")
    btn.click()
    at.run()

    view = _session_state_get(at, "civis.chat.view") or "landing"
    assert view == "landing"
    error_text = " ".join(e.value for e in at.error)
    assert "Não foi possível iniciar a sessão" in error_text



# ---------------------------------------------------------------------------
# D+.5 — telemetry sidecar matches the CLI + Metrics page consumer
# ---------------------------------------------------------------------------


def test_web_chat_persists_turn_telemetry_in_cli_compatible_shape(
    chat_env: Path,
) -> None:
    """
    After one persona turn, the web chat writes turn_telemetry.json with
    the exact shape data_access.load_turn_telemetry (used by the Métricas
    page) expects: turn_index / input_tokens / output_tokens / latency_ms
    / provider_name.
    """
    at = _start_scenario(
        chat_env,
        persona_replies=["Oi, tudo bem, obrigada."],
    )
    session_id = at.session_state["civis.chat.session_id"]

    _submit_one_turn(at)

    telemetry = load_turn_telemetry(session_id, sessions_dir=chat_env)
    assert len(telemetry) == 1
    entry = telemetry[0]
    assert entry.turn_index == 1  # 0 is the agent turn, 1 is the persona turn
    assert entry.input_tokens == 42  # from the fake provider
    assert entry.output_tokens == 13
    assert entry.latency_ms == 250
    assert entry.provider_name == "fake-persona"
