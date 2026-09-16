"""
Declarative catalog of clickable attendant actions per scenario.

Each scenario YAML can declare an `available_actions` block. The web UI
renders one button per action underneath the chat input; a button is
enabled only when every fact_key in `requires` has already been revealed
by the persona. Optionally, an action can carry `emits_document`, a
short key that maps to a template in `civis.documents.templates` — when
the trainee clicks such an action, the app renders a fake certificate
inline in the chat, so an investor sees the product ISSUING documents,
not just chatting.

Validation is strict on purpose:

    - Every action id is unique within the scenario. A typo that would
      silently produce two buttons with the same key on Streamlit is
      caught here.
    - Every fact_key referenced by `requires` must actually exist in
      the persona's facts list. This is validated in `session.scenario`
      where both blocks are visible; here we only enforce local shape.

The `emits_document` key is not validated against the document registry
at load time — that would create a circular import between
`scenarios.actions` and `documents.templates`. The web layer looks up
the renderer at click time and surfaces a friendly error if the key is
unknown.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class AgentAction(BaseModel):
    """One clickable action available to the attendant during a session.

    Fields mirror the YAML shape 1:1 so `model_validate` on the parsed
    mapping just works. `requires` is a list of fact_keys — the button
    stays disabled until every listed key is present in
    `PersonaState.revealed_fact_keys`. When empty, the button is enabled
    from turn 0.
    """

    id: str = Field(
        min_length=1,
        description=(
            "Stable identifier (snake_case). Used as the Streamlit "
            "button key, so it must be unique within a scenario."
        ),
    )
    label: str = Field(
        min_length=1,
        description="Button label in pt-BR (may include an emoji anchor).",
    )
    description: str = Field(
        min_length=1,
        description=(
            "One-line tooltip in pt-BR explaining what the action does. "
            "Shown via `st.button(..., help=...)`."
        ),
    )
    requires: list[str] = Field(
        default_factory=list,
        description=(
            "Fact keys that must be in `PersonaState.revealed_fact_keys` "
            "for the button to be enabled. Empty means always available."
        ),
    )
    emits_document: str | None = Field(
        default=None,
        description=(
            "Optional key into the document renderer registry "
            "(civis.documents.templates.DOCUMENT_RENDERERS). When set, "
            "clicking the button renders a fake document inline in the "
            "chat, in addition to recording the action turn."
        ),
    )


class AgentActionCatalog(BaseModel):
    """Ordered catalog of actions for one scenario.

    Wrapped in a dedicated model (rather than a bare `list[AgentAction]`)
    so we can attach cross-item validators — uniqueness of ids, mostly.
    Downstream code treats this as a lightweight sequence via `.actions`.
    """

    actions: list[AgentAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids_must_be_unique(self) -> AgentActionCatalog:
        """No two actions may share an id — same key on two buttons is
        a Streamlit runtime error we want caught at load time."""
        seen: set[str] = set()
        duplicates: list[str] = []
        for action in self.actions:
            if action.id in seen:
                duplicates.append(action.id)
            seen.add(action.id)
        if duplicates:
            raise ValueError(
                "Duplicate action ids in scenario available_actions: "
                f"{sorted(set(duplicates))}"
            )
        return self

    def by_id(self, action_id: str) -> AgentAction | None:
        """Return the action with the given id, or None if absent.

        Small helper the UI uses when translating a button click into
        a concrete AgentAction to execute.
        """
        for action in self.actions:
            if action.id == action_id:
                return action
        return None

    def __iter__(self):  # type: ignore[override]
        return iter(self.actions)

    def __len__(self) -> int:
        return len(self.actions)
