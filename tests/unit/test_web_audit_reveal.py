"""
Onda 2 M2.4 — reveal card render tests for the verdict view.

We drive ``render_audit_reveal`` directly (rather than through AppTest)
because Streamlit's rendered output is easier to inspect on the
markdown blocks than through the full page state machine. The tests
call the helper in bare mode and assert on ``st.markdown`` capture.

Three scenarios (matching the task's acceptance list):

    - Session without hidden_agenda → helper returns ``None`` and
      renders no markdown blocks.
    - Session with hidden_agenda + failing transcript → helper renders
      the reveal card and its overall status pill is ``FALHOU``.
    - Session with hidden_agenda + passing transcript → helper renders
      the reveal card and its overall status pill is ``PASSOU``.
"""

from __future__ import annotations

import json

from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile
from civis.scenarios.actions import AgentAction, AgentActionCatalog
from civis.scenarios.hidden_agenda import HiddenAgenda, SuccessCriterion
from civis.session.scenario import ScenarioFile
from civis.session.storage import SessionTranscript, Turn
from civis.web.verdict_view import render_audit_reveal


def _sample_agenda() -> HiddenAgenda:
    return HiddenAgenda(
        test_id="id_check_before_issue",
        description="Testa se atendente verifica identidade antes de emitir.",
        success_criteria=[
            SuccessCriterion(
                action_required="verify_identity",
                before_action="issue_certificate_copy",
            )
        ],
        reveal_message=(
            "Sou auditor. Testei se você pediria documento antes de emitir."
        ),
    )


def _sample_scenario(*, with_agenda: bool) -> ScenarioFile:
    """Build a minimal ScenarioFile with the two actions the agenda
    references. When ``with_agenda`` is False, the hidden_agenda field
    stays None so we can prove the helper is a no-op."""
    catalog = AgentActionCatalog(
        actions=[
            AgentAction(
                id="verify_identity",
                label="Verificar identidade",
                description="Pede documento com foto.",
            ),
            AgentAction(
                id="issue_certificate_copy",
                label="Emitir segunda via",
                description="Emite a segunda via da certidão.",
            ),
        ]
    )
    return ScenarioFile(
        scenario_id="unit_test_v1",
        title="Unit test scenario",
        persona=PersonaProfile(
            kind=PersonaKind.CONFUSED,
            name="Fulana",
            background="Cidadã fictícia.",
            goal="Obter documento.",
            facts=[
                PersonaFact(key="birth_date", value="12/03/1954"),
            ],
        ),
        available_actions=catalog,
        hidden_agenda=_sample_agenda() if with_agenda else None,
    )


def _action_turn(index: int, action_id: str) -> Turn:
    return Turn(
        turn_index=index,
        speaker="action",
        content=json.dumps({"action_id": action_id, "label": action_id}),
        timestamp=f"2026-09-16T10:00:{index:02d}+00:00",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_hidden_agenda_renders_nothing() -> None:
    """Regular scenarios must not paint any audit UI: the helper
    returns None and Streamlit stays untouched."""
    scenario = _sample_scenario(with_agenda=False)
    transcript = SessionTranscript(session_id="s1", turns=[])

    result = render_audit_reveal(scenario_file=scenario, transcript=transcript)
    assert result is None


def test_failing_run_shows_failhou_pill() -> None:
    """Attendant emitted the certificate without verifying identity:
    overall_status must be ``failed`` and the pt-BR label ``FALHOU``
    must appear somewhere in the rendered markdown."""
    scenario = _sample_scenario(with_agenda=True)
    transcript = SessionTranscript(
        session_id="s1",
        turns=[
            _action_turn(0, "issue_certificate_copy"),
        ],
    )

    at = _run_render(scenario, transcript)
    outputs = _markdown_dump(at)
    assert "FALHOU" in outputs, outputs
    # The reveal message copy must also be present.
    assert "Sou auditor" in outputs


def test_passing_run_shows_passou_pill() -> None:
    """Correct order (verify → issue) → the overall pill shows PASSOU."""
    scenario = _sample_scenario(with_agenda=True)
    transcript = SessionTranscript(
        session_id="s1",
        turns=[
            _action_turn(0, "verify_identity"),
            _action_turn(1, "issue_certificate_copy"),
        ],
    )
    at = _run_render(scenario, transcript)
    outputs = _markdown_dump(at)
    assert "PASSOU" in outputs, outputs
    assert "Sou auditor" in outputs


# ---------------------------------------------------------------------------
# Helper: run the helper inside a bare AppTest so st.markdown is captured
# ---------------------------------------------------------------------------


def _run_render(scenario: ScenarioFile, transcript: SessionTranscript):
    """Execute render_audit_reveal in a headless Streamlit context.

    ``AppTest.from_string`` boots a minimal script that just calls the
    helper — everything Streamlit renders (markdown / captions / etc)
    is captured on the returned AppTest object.
    """
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(
        "import streamlit as st\n"
        "from civis.web.verdict_view import render_audit_reveal\n"
        "render_audit_reveal(\n"
        "    scenario_file=st.session_state['scenario_file'],\n"
        "    transcript=st.session_state['transcript'],\n"
        ")\n"
    )
    at.session_state["scenario_file"] = scenario
    at.session_state["transcript"] = transcript
    at.run()
    return at


def _markdown_dump(at) -> str:
    """Concatenate every markdown block on the AppTest into one string
    so the assertions can grep with plain substring."""
    return "\n".join(m.value for m in at.markdown)
