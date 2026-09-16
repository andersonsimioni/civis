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
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from civis.personas.base import PersonaProfile
from civis.scenarios.actions import AgentActionCatalog
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
