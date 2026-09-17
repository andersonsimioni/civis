"""
Scenario YAML loader.

A scenario file describes a training situation: which persona plays,
what facts it knows, and what actions the agent is expected to take
(the last one feeds the judge prompt in fase A.4).

We keep the loader separate from the orchestrator because two
consumers use it: the orchestrator (to build a PersonaState + judge
context) and the storage layer (to hash the raw bytes for drift
detection).

Phase D+++: an optional `available_actions` block declares the
clickable attendant buttons the web UI renders under the chat input.
Absent from the YAML → the field defaults to an empty catalog and the
UI simply renders no buttons (fully backwards compatible with the
Phase A-D++ scenarios).

Onda 2 T1.1: an optional `service_sla` block declares the time
budget of the session (target / warning / critical seconds). Absent
from the YAML → the field defaults to a ServiceSLA with the standard
480 / 720 / 900 numbers, so existing scenarios keep working while
still exposing a sensible SLA to the timer UI.

Onda 4 S4.1: an optional top-level ``category`` string declares which
registry-office scope the scenario covers (nascimento, casamento,
divorcio, ...). Absent from the YAML → the scenario ends up in the
``outros`` bucket. The list of accepted values lives in
:mod:`civis.scenarios.categories`.

Onda 4 S4.4: four optional top-level ``card_*`` fields drive the
landing card copy — ``card_pitch``, ``card_what_happens``,
``card_watch_for`` and ``card_icon``. When any is absent, the
discovery layer applies a persona-kind-specific fallback so an
unadorned YAML still produces a card.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from civis.personas.base import PersonaProfile
from civis.scenarios.actions import AgentActionCatalog
from civis.scenarios.categories import FALLBACK_CATEGORY, normalize_category
from civis.scenarios.hidden_agenda import HiddenAgenda
from civis.scenarios.sla import ServiceSLA


class ScenarioFile(BaseModel):
    """Parsed contents of a scenario YAML file."""

    scenario_id: str
    title: str
    persona: PersonaProfile
    expected_agent_actions: list[str] = Field(default_factory=list)
    # Phase D+++: catalog of clickable attendant actions the web UI
    # renders under the chat input. Empty by default so older scenarios
    # continue to load unchanged.
    available_actions: AgentActionCatalog = Field(
        default_factory=AgentActionCatalog
    )
    # Onda 2 T1.1: SLA thresholds driving the chat header timer and
    # the queue-complaint injector. Optional in the YAML — a scenario
    # without this block gets the shared defaults so the timer never
    # renders a bare "no SLA" state.
    service_sla: ServiceSLA = Field(default_factory=ServiceSLA)
    # Onda 2 M2.1: optional mystery-shopper mission. Absent from the
    # YAML → the field stays None and the verdict screen renders the
    # standard layout. Present → the verdict screen adds an audit
    # reveal card above the judge rubric. The persona prompt does NOT
    # read this field, so the LLM is never told it is being audited.
    hidden_agenda: HiddenAgenda | None = None
    # Onda 4 S4.1: optional canonical category — the registry-office
    # scope this scenario covers. Absent from the YAML defaults to
    # ``FALLBACK_CATEGORY`` ("outros") so the landing dropdown never
    # has a bucket-less scenario. Values are validated against
    # ``CANONICAL_CATEGORIES`` in :mod:`civis.scenarios.categories`;
    # a typo raises ``ValueError`` at load time.
    category: str = Field(
        default=FALLBACK_CATEGORY,
        description=(
            "Registry-office scope this scenario covers (nascimento, "
            "casamento, ...). See civis.scenarios.categories for the "
            "canonical set. Optional in the YAML — omitted values fall "
            "back to 'outros'."
        ),
    )
    # Onda 4 S4.4: optional per-scenario landing-card metadata.
    #   card_pitch         one-sentence hook shown as the tagline.
    #   card_what_happens  2-3 lines of narrative under "Como corre:".
    #   card_watch_for     2-3 lines under "Observe:".
    #   card_icon          single emoji anchor above the title.
    # Any missing field is filled in by
    # ``civis.scenarios.discovery.build_card_metadata`` with a
    # persona-kind-specific fallback, so an unadorned YAML still
    # produces a valid card.
    card_pitch: str | None = Field(
        default=None,
        description="One-line hook shown as the card tagline on the landing.",
    )
    card_what_happens: str | None = Field(
        default=None,
        description="2-3 lines of narrative under 'Como corre:' on the card.",
    )
    card_watch_for: str | None = Field(
        default=None,
        description="2-3 lines under 'Observe:' on the card.",
    )
    card_icon: str | None = Field(
        default=None,
        description="Single emoji anchor for the card header. Category icon used as fallback.",
    )

    @field_validator("category", mode="before")
    @classmethod
    def _category_must_be_canonical(cls, raw: object) -> str:
        """Canonicalize ``category`` before Pydantic type-checks it.

        Runs in ``mode="before"`` so a YAML that writes ``category: null``
        (explicit) or omits the key entirely (implicit ``None``) still
        lands on the fallback string instead of the Pydantic ``None``
        rejection. Any other type (list, dict, int) fails the standard
        string coercion after this hook returns.
        """
        if raw is None:
            return FALLBACK_CATEGORY
        if isinstance(raw, str):
            return normalize_category(raw)
        # Let Pydantic's default type check raise a clear error for
        # non-string values instead of silently coercing them.
        return raw  # type: ignore[return-value]

    @model_validator(mode="after")
    def _action_requires_must_reference_real_fact_keys(self) -> "ScenarioFile":
        """
        Every fact_key listed in an action's `requires` must actually
        exist in the persona's facts. Catches typos at load time — a
        wrong key would leave the button permanently disabled and the
        investor never sees the wow moment.
        """
        known_keys = {fact.key for fact in self.persona.facts}
        unknown: list[tuple[str, str]] = []
        for action in self.available_actions.actions:
            for required in action.requires:
                if required not in known_keys:
                    unknown.append((action.id, required))
        if unknown:
            details = ", ".join(
                f"action '{action_id}' requires '{key}'"
                for action_id, key in unknown
            )
            raise ValueError(
                "Scenario available_actions reference unknown persona fact "
                f"keys: {details}. Known keys: {sorted(known_keys)}."
            )
        return self

    @model_validator(mode="after")
    def _hidden_agenda_must_reference_real_actions(self) -> "ScenarioFile":
        """
        Onda 2 M2.1: every action id in a hidden_agenda's success
        criteria must match an action declared in ``available_actions``.
        A typo here would leave the audit permanently inconclusive and
        make the mystery-shopper reveal misleading, so we fail fast.
        """
        if self.hidden_agenda is None:
            return self
        known_action_ids = {action.id for action in self.available_actions.actions}
        unknown: list[tuple[str, str]] = []
        for criterion in self.hidden_agenda.success_criteria:
            if criterion.action_required not in known_action_ids:
                unknown.append(("action_required", criterion.action_required))
            if criterion.before_action not in known_action_ids:
                unknown.append(("before_action", criterion.before_action))
        if unknown:
            details = ", ".join(f"{role} '{aid}'" for role, aid in unknown)
            raise ValueError(
                "Scenario hidden_agenda references unknown action ids: "
                f"{details}. Known action ids: {sorted(known_action_ids)}."
            )
        return self


def load_scenario_from_text(raw_text: str) -> ScenarioFile:
    """Parse and validate a scenario from its YAML source string."""
    parsed = yaml.safe_load(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Scenario YAML must load into a mapping at the top level.")
    # YAML shape: `available_actions:` is a bare list. Pydantic expects
    # the wrapping AgentActionCatalog model, so unwrap here to keep the
    # authoring surface flat and readable in the YAML files.
    raw_actions = parsed.pop("available_actions", None)
    if raw_actions is not None:
        parsed["available_actions"] = {"actions": raw_actions}
    return ScenarioFile.model_validate(parsed)


def load_scenario_from_path(path: Path) -> tuple[ScenarioFile, str]:
    """
    Load and validate a scenario from disk. Returns (parsed, raw_text)
    so callers can also SHA-256 the raw bytes for drift detection.
    """
    raw_text = path.read_text(encoding="utf-8")
    return load_scenario_from_text(raw_text), raw_text


def resolve_scenario_path(
    scenario_ref: str,
    scenarios_dir: Path,
) -> Path:
    """
    Turn a user-provided reference into a concrete path.

    Accepted forms:
        - A path (absolute or relative) that points to a .yaml/.yml file
          that exists.
        - A bare scenario id ('certificate_duplicate_confused_v1'); we
          look for <scenarios_dir>/<id>.yaml.
    """
    as_path = Path(scenario_ref)
    if as_path.exists() and as_path.is_file():
        return as_path

    candidate = scenarios_dir / f"{scenario_ref}.yaml"
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        f"Could not resolve scenario reference '{scenario_ref}'. "
        f"Tried literal path and '{candidate}'."
    )
