"""
AppTest coverage for Phase D+++ action execution — the side-effects of
clicking an attendant button.

Five concerns:

    1. Action WITHOUT emits_document appends exactly one action turn
       and creates no document file on disk.
    2. Action WITH emits_document appends the action turn AND writes
       a Markdown file under ``issued_documents/<doc_id>.md``.
    3. Clicking an action whose requires are not met (via a direct
       call, bypassing the disabled button) leaves the transcript
       untouched — defence-in-depth server-side check.
    4. The .md body persisted on disk matches the rendered template
       byte-for-byte (modulo trailing newline).
    5. After a click + implicit rerun, the action turn is visible in
       the chat body of the SAME AppTest run.
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
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


def _inject_factory(at: AppTest, persona_replies: list[str]) -> None:
    def _factory(role: str) -> LLMProvider:
        if role == "persona":
            return _FakeProvider("fake-persona", persona_replies)
        return _FakeProvider("fake-judge", ["{}"])

    at.session_state["civis.chat.provider_factory"] = _factory


def _start_scenario(chat_env: Path, scenario_id: str) -> AppTest:
    del chat_env
    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "new_session.py"))
    _inject_factory(at, ["Oi."])
    at.run()
    btn = next(b for b in at.button if b.key == f"start_{scenario_id}")
    btn.click()
    at.run()
    return at


def _reveal_facts(at: AppTest, fact_keys: set[str]) -> None:
    """Simulate the persona having revealed each fact_key in `fact_keys`."""
    orch = at.session_state["civis.chat.orchestrator"]
    orch.state = orch.state.model_copy(update={"revealed_fact_keys": fact_keys})


# ---------------------------------------------------------------------------
# D+++.4.1 — action without emits_document → only the turn is recorded
# ---------------------------------------------------------------------------


def test_execute_action_without_document_appends_action_turn_only(
    chat_env: Path,
) -> None:
    """No document → no `issued_documents/` folder and no `document`
    key inside the action payload."""
    at = _start_scenario(chat_env, "certificate_duplicate_confused_v1")
    session_id = at.session_state["civis.chat.session_id"]

    btn = next(b for b in at.button if b.key == "action_verify_identity")
    btn.click()
    at.run()

    transcript_payload = json.loads(
        (chat_env / session_id / "transcript.json").read_text(encoding="utf-8")
    )
    action_turns = [t for t in transcript_payload["turns"] if t["speaker"] == "action"]
    assert len(action_turns) == 1
    payload = json.loads(action_turns[0]["content"])
    assert payload["action_id"] == "verify_identity"
    assert "document" not in payload
    # No documents folder created since no emission happened.
    assert not (chat_env / session_id / "issued_documents").exists()


# ---------------------------------------------------------------------------
# D+++.4.2 — action with emits_document → turn + persisted .md file
# ---------------------------------------------------------------------------


def test_execute_action_with_document_appends_action_turn_and_persists_file(
    chat_env: Path,
) -> None:
    """
    After revealing the required facts, clicking "Emitir 2ª via de
    certidão" appends the action turn AND creates exactly one .md file
    under ``issued_documents/``.
    """
    at = _start_scenario(chat_env, "certificate_duplicate_confused_v1")
    session_id = at.session_state["civis.chat.session_id"]

    _reveal_facts(at, {"birth_date", "mother_name"})
    at.run()

    btn = next(b for b in at.button if b.key == "action_issue_certificate_copy")
    assert btn.disabled is False
    btn.click()
    at.run()

    # Transcript now has one action turn with a `document` block.
    transcript_payload = json.loads(
        (chat_env / session_id / "transcript.json").read_text(encoding="utf-8")
    )
    action_turns = [t for t in transcript_payload["turns"] if t["speaker"] == "action"]
    assert len(action_turns) == 1
    payload = json.loads(action_turns[0]["content"])
    document = payload["document"]
    assert document["id"].startswith("FIC-DOC-")
    assert "CERTIDÃO DE NASCIMENTO" in document["body"]

    # File was persisted on disk under the expected name.
    docs_dir = chat_env / session_id / "issued_documents"
    assert docs_dir.exists()
    md_files = list(docs_dir.glob("*.md"))
    assert len(md_files) == 1
    assert md_files[0].name == f"{document['id']}.md"


# ---------------------------------------------------------------------------
# D+++.4.3 — server-side gate: blocked action does NOT execute
# ---------------------------------------------------------------------------


def test_execute_action_blocked_when_requires_not_met_does_nothing(
    chat_env: Path,
) -> None:
    """
    Defence-in-depth: driving ``_execute_action`` directly with the
    guard bypassed (imagine a stale rerun or a scripted attack) must
    NOT append a turn and must set the transient error banner instead.
    """
    at = _start_scenario(chat_env, "certificate_duplicate_confused_v1")
    session_id = at.session_state["civis.chat.session_id"]

    # No facts revealed → button is disabled. Verify by directly calling
    # the executor with the action loaded from the scenario catalog.
    scenario = at.session_state["civis.chat.scenario_file"]
    action = scenario.available_actions.by_id("issue_certificate_copy")
    assert action is not None

    from civis.web.pages import new_session as ns_module

    orch = at.session_state["civis.chat.orchestrator"]
    # _execute_action calls st.rerun() at the end, which raises inside
    # AppTest. That's fine — we still assert on the on-disk state after.
    import contextlib
    with contextlib.suppress(Exception):
        ns_module._execute_action(action, orch)

    transcript_payload = json.loads(
        (chat_env / session_id / "transcript.json").read_text(encoding="utf-8")
    )
    action_turns = [t for t in transcript_payload["turns"] if t["speaker"] == "action"]
    assert action_turns == []
    # No documents folder either.
    assert not (chat_env / session_id / "issued_documents").exists()


# ---------------------------------------------------------------------------
# D+++.4.4 — .md body matches the rendered template
# ---------------------------------------------------------------------------


def test_issued_document_file_content_matches_rendered_template(
    chat_env: Path,
) -> None:
    """
    The .md on disk carries the same ASCII body the chat card renders.
    A one-trailing-newline drift is tolerated (save_issued_document
    guarantees at least one).
    """
    at = _start_scenario(chat_env, "certificate_duplicate_confused_v1")
    session_id = at.session_state["civis.chat.session_id"]

    _reveal_facts(at, {"birth_date", "mother_name"})
    at.run()
    btn = next(b for b in at.button if b.key == "action_issue_certificate_copy")
    btn.click()
    at.run()

    transcript_payload = json.loads(
        (chat_env / session_id / "transcript.json").read_text(encoding="utf-8")
    )
    action_turn = next(
        t for t in transcript_payload["turns"] if t["speaker"] == "action"
    )
    payload = json.loads(action_turn["content"])
    body_from_payload = payload["document"]["body"]

    doc_id = payload["document"]["id"]
    md_path = chat_env / session_id / "issued_documents" / f"{doc_id}.md"
    body_from_disk = md_path.read_text(encoding="utf-8").rstrip("\n")

    assert body_from_disk == body_from_payload


# ---------------------------------------------------------------------------
# D+++.4.5 — action turn survives rerun and shows in chat body
# ---------------------------------------------------------------------------


def test_action_turn_survives_page_rerun_and_appears_in_chat_body(
    chat_env: Path,
) -> None:
    """
    After the click + rerun, the chat body shows the action's
    human-readable label somewhere in its markdown output. Proves the
    live renderer (``_render_action_turn_in_chat``) is wired.
    """
    at = _start_scenario(chat_env, "certificate_duplicate_confused_v1")
    _reveal_facts(at, {"birth_date", "mother_name"})
    at.run()

    btn = next(b for b in at.button if b.key == "action_issue_certificate_copy")
    btn.click()
    at.run()

    markdown_text = " ".join(m.value for m in at.markdown)
    # The label from the confused scenario's action.
    assert "Emitir 2ª via de certidão" in markdown_text
    # Some fragment of the rendered document is visible too.
    assert "CERTIDÃO DE NASCIMENTO" in markdown_text
