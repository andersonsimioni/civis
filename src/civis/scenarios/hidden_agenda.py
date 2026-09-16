"""
Mystery-shopper hidden agenda per scenario (Onda 2 M2.1).

A scenario can carry an OPTIONAL ``hidden_agenda`` block declaring a
covert conformance test: the persona plays a normal citizen throughout
the session, but on the verdict screen the app reveals that the
"citizen" was actually an auditor testing whether the attendant
followed a specific protocol.

Design decisions:

    - The block is OPTIONAL. Scenarios without it keep working
      unchanged — the reveal card simply does not render.

    - The success criteria is expressed as a small sequence of
      ordering rules over the attendant's clickable actions. For
      Onda 2 we support the single rule ``action_required`` must
      appear ``before_action`` in the action-turn stream. Richer
      rules (multiple gates, time bounds) can be added later by
      extending SuccessCriterion.

    - The persona prompt NEVER sees the hidden agenda. We keep the
      agenda on the ScenarioFile (not on PersonaProfile) and the
      persona prompt builder only reads from PersonaProfile, so
      there is no path from the YAML block to the LLM context.
      This is enforced by test: M2.2 asserts the persona prompt
      built from a hidden-agenda scenario is byte-identical to the
      same scenario without the block.

Usage from a scenario YAML file:

    hidden_agenda:
        test_id: id_check_before_issue
        description: |
            Auditor testa se atendente pede documento com foto antes
            de emitir 2ª via.
        success_criteria:
            - action_required: verify_identity
              before_action: issue_certificate_copy
        reveal_message: |
            Meu nome é <NOME>, sou auditor(a)...
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SuccessCriterion(BaseModel):
    """One ordering rule the attendant must satisfy.

    Semantics:

        "action_required" must appear in the transcript's action-turn
        stream BEFORE "before_action" appears, otherwise the audit
        result is a failure. If "before_action" never appears at all,
        the criterion is inconclusive — the attendant did not reach the
        gated action either way.

    Both fields are action IDs (matches ``AgentAction.id``); the
    ScenarioFile validator (see session.scenario) enforces they
    reference real actions declared in ``available_actions``.
    """

    action_required: str = Field(
        min_length=1,
        description=(
            "The gating action the attendant must perform first "
            "(e.g. 'verify_identity')."
        ),
    )
    before_action: str = Field(
        min_length=1,
        description=(
            "The gated action; ``action_required`` must appear "
            "strictly before this one in the action-turn stream "
            "(e.g. 'issue_certificate_copy')."
        ),
    )


class HiddenAgenda(BaseModel):
    """Mystery-shopper mission attached to a scenario.

    Only surfaces on the verdict screen, never during the chat — the
    persona prompt is built from PersonaProfile alone so an accidental
    reveal is prevented at the type level.
    """

    test_id: str = Field(
        min_length=1,
        description=(
            "Stable identifier for the audit (e.g. "
            "'id_check_before_issue'). Used in the on-disk audit "
            "outcome so a batch of runs can be aggregated per test."
        ),
    )
    description: str = Field(
        min_length=1,
        description=(
            "Short pt-BR sentence explaining what the auditor tests. "
            "Shown on the reveal card."
        ),
    )
    success_criteria: list[SuccessCriterion] = Field(
        default_factory=list,
        description=(
            "Ordering rules the attendant must satisfy. When empty, "
            "the audit is always inconclusive — a valid state used "
            "during authoring."
        ),
    )
    reveal_message: str = Field(
        min_length=1,
        description=(
            "The pt-BR line the auditor delivers on the verdict "
            "screen. May span multiple lines. Placeholders like "
            "[NOME] / [passou/falhou] are rendered verbatim so the "
            "reveal card can substitute them at display time."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_criterion_when_declared(self) -> HiddenAgenda:
        """
        An agenda without any success_criteria produces an audit that
        can never pass or fail — allowed (useful during authoring) but
        surfaced as a warning-shaped comment on the reveal card. We
        keep the model tolerant here; the scenario-level validator
        (session.scenario) enforces that the criteria that DO exist
        reference real actions.
        """
        # No hard rejection here; kept as a hook for future growth.
        return self
