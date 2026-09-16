"""
Tests for the Onda 2 M2.3 mystery-shopper outcome evaluator.

Covers the acceptance list in the task:

    - Positive: attendant verified identity BEFORE emitting → passed.
    - Negative: attendant emitted WITHOUT verifying first → failed.
    - Order-inverted: verified AFTER emitting → still failed.
    - Edge (never emitted): the gated action never fires →
      inconclusive.
    - Aggregation: any 'failed' pulls the overall status down; all
      passed → overall passed; else → overall inconclusive.
"""

from __future__ import annotations

import json

from civis.scenarios.audit_check import evaluate_hidden_agenda
from civis.scenarios.hidden_agenda import HiddenAgenda, SuccessCriterion
from civis.session.storage import SessionTranscript, Turn

# Reusable timestamps — we only care about ordering, not real times.
_TS_A = "2026-09-16T10:00:00+00:00"
_TS_B = "2026-09-16T10:00:05+00:00"
_TS_C = "2026-09-16T10:00:10+00:00"
_TS_D = "2026-09-16T10:00:15+00:00"


def _action_turn(index: int, action_id: str, timestamp: str) -> Turn:
    """Build one speaker='action' turn with a valid JSON payload.

    Mirrors the shape produced by
    ``civis.web.pages.new_session._action_turn_content``.
    """
    content = json.dumps({"action_id": action_id, "label": action_id})
    return Turn(
        turn_index=index,
        speaker="action",
        content=content,
        timestamp=timestamp,
    )


def _speech_turn(index: int, speaker: str, content: str, timestamp: str) -> Turn:
    """Build one non-action turn — used to prove the evaluator ignores
    speech and queue events."""
    return Turn(
        turn_index=index,
        speaker=speaker,
        content=content,
        timestamp=timestamp,
    )


def _fixture_agenda() -> HiddenAgenda:
    """The audit under test throughout this module: verify identity
    must come BEFORE issuing the certificate copy."""
    return HiddenAgenda(
        test_id="id_check_before_issue",
        description="descrição",
        success_criteria=[
            SuccessCriterion(
                action_required="verify_identity",
                before_action="issue_certificate_copy",
            )
        ],
        reveal_message="reveal",
    )


# ---------------------------------------------------------------------------
# Positive: correct order → passed
# ---------------------------------------------------------------------------


def test_verified_before_issue_yields_passed() -> None:
    """Ordering satisfied → the criterion (and overall) is passed."""
    transcript = SessionTranscript(
        session_id="s1",
        turns=[
            _speech_turn(0, "agent", "Bom dia.", _TS_A),
            _speech_turn(1, "persona", "Oi.", _TS_A),
            _action_turn(2, "verify_identity", _TS_B),
            _action_turn(3, "issue_certificate_copy", _TS_C),
        ],
    )
    outcome = evaluate_hidden_agenda(_fixture_agenda(), transcript)
    assert outcome.overall_status == "passed"
    assert len(outcome.criteria_outcomes) == 1
    assert outcome.criteria_outcomes[0].status == "passed"


# ---------------------------------------------------------------------------
# Negative: emitted without verifying → failed
# ---------------------------------------------------------------------------


def test_issued_without_verifying_yields_failed() -> None:
    """Gated action fired without the gate → failed."""
    transcript = SessionTranscript(
        session_id="s1",
        turns=[
            _speech_turn(0, "agent", "Certo.", _TS_A),
            _action_turn(1, "issue_certificate_copy", _TS_B),
        ],
    )
    outcome = evaluate_hidden_agenda(_fixture_agenda(), transcript)
    assert outcome.overall_status == "failed"
    assert outcome.criteria_outcomes[0].status == "failed"


# ---------------------------------------------------------------------------
# Order-inverted: verified AFTER issuing → still failed
# ---------------------------------------------------------------------------


def test_verifying_after_issue_still_fails() -> None:
    """The auditor cares about ORDER; verifying after the fact is a
    failure, not a save."""
    transcript = SessionTranscript(
        session_id="s1",
        turns=[
            _action_turn(0, "issue_certificate_copy", _TS_A),
            _action_turn(1, "verify_identity", _TS_B),
        ],
    )
    outcome = evaluate_hidden_agenda(_fixture_agenda(), transcript)
    assert outcome.overall_status == "failed"


# ---------------------------------------------------------------------------
# Edge: gated action never happened → inconclusive
# ---------------------------------------------------------------------------


def test_never_issued_yields_inconclusive() -> None:
    """The gated action never fires → we cannot say the attendant
    failed the audit (they may still have been about to click), so we
    mark the outcome inconclusive."""
    transcript = SessionTranscript(
        session_id="s1",
        turns=[
            _speech_turn(0, "agent", "Bom dia.", _TS_A),
            _action_turn(1, "verify_identity", _TS_B),
            _action_turn(2, "explain_procedure", _TS_C),
            _action_turn(3, "end_service", _TS_D),
        ],
    )
    outcome = evaluate_hidden_agenda(_fixture_agenda(), transcript)
    assert outcome.overall_status == "inconclusive"
    assert outcome.criteria_outcomes[0].status == "inconclusive"


# ---------------------------------------------------------------------------
# Aggregation: mixed criteria
# ---------------------------------------------------------------------------


def test_overall_status_pulls_worst_criterion_down() -> None:
    """Two criteria — one passes, one fails → overall is failed."""
    agenda = HiddenAgenda(
        test_id="multi_test",
        description="two rules",
        success_criteria=[
            SuccessCriterion(
                action_required="verify_identity",
                before_action="issue_certificate_copy",
            ),
            SuccessCriterion(
                action_required="explain_procedure",
                before_action="issue_certificate_copy",
            ),
        ],
        reveal_message="reveal",
    )
    transcript = SessionTranscript(
        session_id="s1",
        turns=[
            _action_turn(0, "verify_identity", _TS_A),
            # explain_procedure never fires before the issue
            _action_turn(1, "issue_certificate_copy", _TS_B),
        ],
    )
    outcome = evaluate_hidden_agenda(agenda, transcript)
    assert outcome.overall_status == "failed"
    statuses = [c.status for c in outcome.criteria_outcomes]
    assert statuses == ["passed", "failed"]
