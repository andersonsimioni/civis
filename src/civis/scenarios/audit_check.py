"""
Mystery-shopper outcome evaluator (Onda 2 M2.3).

Given a scenario's ``HiddenAgenda`` and the on-disk transcript, decide
whether the attendant satisfied each ordering criterion. The reveal
card on the verdict screen (M2.4) reads this outcome and paints the
corresponding status pill.

We walk ONLY the ``speaker == "action"`` turns because the audit is
expressed as an ordering rule over the attendant's clickable actions.
Speech turns (agent / persona) and queue events are ignored — the
attendant might narrate "vou pedir seu documento" without ever
clicking the button, and the audit should call that a failure.

Outcomes per criterion:

    passed         action_required appeared strictly before before_action.
    failed         before_action appeared but action_required did not
                   appear before it.
    inconclusive   before_action never appeared in the transcript.
                   The attendant did not reach the gated action either
                   way, so there is nothing to grade.

The overall outcome aggregates the per-criterion results with the
same "worst wins" rule human graders use:

    any failed        → overall "failed"
    all passed        → overall "passed"
    otherwise         → overall "inconclusive"
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from civis.scenarios.hidden_agenda import HiddenAgenda, SuccessCriterion
from civis.session.storage import SessionTranscript


class CriterionOutcome(BaseModel):
    """Result of one ordering criterion against the transcript."""

    action_required: str = Field(
        description="Copy of the gating action id, for display."
    )
    before_action: str = Field(
        description="Copy of the gated action id, for display."
    )
    status: str = Field(
        pattern="^(passed|failed|inconclusive)$",
        description=(
            "One of: 'passed' (rule satisfied), 'failed' (gated "
            "action executed without the required one first), or "
            "'inconclusive' (gated action never happened)."
        ),
    )
    reason: str = Field(
        description=(
            "Short pt-BR sentence explaining WHY this status — used "
            "on the reveal card so the trainee sees not only the "
            "verdict but the concrete evidence."
        ),
    )


class AuditOutcome(BaseModel):
    """Aggregated result of an entire hidden agenda evaluation."""

    test_id: str = Field(
        description="Copy of HiddenAgenda.test_id for downstream aggregation."
    )
    overall_status: str = Field(
        pattern="^(passed|failed|inconclusive)$",
        description=(
            "'failed' if any criterion failed; 'passed' if every "
            "criterion passed; otherwise 'inconclusive'."
        ),
    )
    criteria_outcomes: list[CriterionOutcome] = Field(
        default_factory=list,
        description="One entry per criterion in HiddenAgenda.success_criteria.",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_hidden_agenda(
    agenda: HiddenAgenda,
    transcript: SessionTranscript,
) -> AuditOutcome:
    """Score every criterion in ``agenda`` against ``transcript``.

    The two inputs are cheap value objects — this function never
    touches disk. Callers hand it whatever transcript is on hand
    (live orchestrator's or the one loaded from disk on the verdict
    screen) and read the returned AuditOutcome to render the reveal
    card.
    """
    action_sequence = _extract_action_ids(transcript)

    per_criterion = [
        _evaluate_criterion(criterion, action_sequence)
        for criterion in agenda.success_criteria
    ]

    overall = _aggregate_overall_status(per_criterion)

    return AuditOutcome(
        test_id=agenda.test_id,
        overall_status=overall,
        criteria_outcomes=per_criterion,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _extract_action_ids(transcript: SessionTranscript) -> list[str]:
    """Ordered list of action ids the attendant clicked during the session.

    Action turns carry a JSON payload (see
    ``civis.web.pages.new_session._action_turn_content``): we parse it
    and pull the ``action_id`` field. Payloads that are malformed or
    missing the id are silently skipped — the transcript could have
    been hand-edited during authoring and we should not crash the
    verdict screen on a stray artefact.
    """
    ordered: list[str] = []
    for turn in transcript.turns:
        if turn.speaker != "action":
            continue
        try:
            payload = json.loads(turn.content)
        except (ValueError, TypeError):
            continue
        action_id = payload.get("action_id") if isinstance(payload, dict) else None
        if isinstance(action_id, str) and action_id:
            ordered.append(action_id)
    return ordered


def _evaluate_criterion(
    criterion: SuccessCriterion,
    action_sequence: list[str],
) -> CriterionOutcome:
    """Score one ordering criterion against the action sequence.

    Ordering semantics (see module docstring):

        - Neither present → inconclusive.
        - Only ``action_required`` present, ``before_action`` never
          fires → inconclusive: the gated action was not attempted, so
          the attendant did not "give the auditor grounds to grade".
        - ``before_action`` present without any prior
          ``action_required`` → failed.
        - First index of ``action_required`` strictly less than the
          first index of ``before_action`` → passed.

    We compare indices (not "did action_required happen at all")
    because the trainee might click ``verify_identity`` AFTER emitting,
    and that should still be a failure — the auditor cares about
    order, not presence.
    """
    required_index = _first_index(action_sequence, criterion.action_required)
    gated_index = _first_index(action_sequence, criterion.before_action)

    if gated_index is None:
        return CriterionOutcome(
            action_required=criterion.action_required,
            before_action=criterion.before_action,
            status="inconclusive",
            reason=(
                f"O(a) atendente não executou '{criterion.before_action}' "
                "durante o atendimento, então o critério não pôde ser "
                "avaliado."
            ),
        )

    if required_index is None or required_index >= gated_index:
        # gated_index is present but required either never fired or
        # fired only AFTER gated. Both fail the ordering rule.
        return CriterionOutcome(
            action_required=criterion.action_required,
            before_action=criterion.before_action,
            status="failed",
            reason=(
                f"O(a) atendente executou '{criterion.before_action}' "
                f"sem executar '{criterion.action_required}' antes."
            ),
        )

    return CriterionOutcome(
        action_required=criterion.action_required,
        before_action=criterion.before_action,
        status="passed",
        reason=(
            f"O(a) atendente executou '{criterion.action_required}' "
            f"antes de '{criterion.before_action}', na ordem esperada."
        ),
    )


def _first_index(sequence: list[str], target: str) -> int | None:
    """Return the first index of ``target`` in ``sequence`` (or None)."""
    for i, value in enumerate(sequence):
        if value == target:
            return i
    return None


def _aggregate_overall_status(criteria: list[CriterionOutcome]) -> str:
    """Fold per-criterion statuses into a single overall label.

    Rules (documented at the top of the module):
        - Empty list → inconclusive (agenda with no criteria).
        - Any 'failed' → 'failed'.
        - All 'passed' → 'passed'.
        - Otherwise → 'inconclusive'.
    """
    if not criteria:
        return "inconclusive"

    statuses = {c.status for c in criteria}
    if "failed" in statuses:
        return "failed"
    if statuses == {"passed"}:
        return "passed"
    return "inconclusive"
