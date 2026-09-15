"""
Scenario YAML loader.

A scenario file describes a training situation: which persona plays,
what facts it knows, and what actions the agent is expected to take
(the last one feeds the judge prompt in fase A.4).

We keep the loader separate from the orchestrator because two
consumers use it: the orchestrator (to build a PersonaState + judge
context) and the storage layer (to hash the raw bytes for drift
detection).
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from civis.personas.base import PersonaProfile


class ScenarioFile(BaseModel):
    """Parsed contents of a scenario YAML file."""

    scenario_id: str
    title: str
    persona: PersonaProfile
    expected_agent_actions: list[str] = Field(default_factory=list)


def load_scenario_from_text(raw_text: str) -> ScenarioFile:
    """Parse and validate a scenario from its YAML source string."""
    parsed = yaml.safe_load(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Scenario YAML must load into a mapping at the top level.")
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
