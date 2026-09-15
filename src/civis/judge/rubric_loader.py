"""
Declarative rubric loader.

The rubric is externalised in data/rubrics/*.yaml so both the LLM judge
and the human evaluators in the Phase E study calibrate against the same
level-by-level descriptions. This module reads a rubric file, validates
its shape with Pydantic, and hands it to the judge prompt builder.

Usage:
    rubric = load_rubric_from_path(Path("data/rubrics/counter_v1.yaml"))
    system, user = build_judge_prompt(..., rubric=rubric)

Design rules:
    - Every CriterionKind must have 6 level descriptions (0..5). A missing
      level is a validation error at load time, not a silent None injected
      into the prompt at runtime.
    - Level keys are strings ("0".."5") in the YAML because YAML integer
      keys become quoted strings anyway once round-tripped; keeping them
      strings avoids surprises.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from civis.judge.rubric import MAX_SCORE, MIN_SCORE, CriterionKind

# Required set of level keys — every criterion must define exactly these.
REQUIRED_LEVEL_KEYS: frozenset[str] = frozenset(
    str(i) for i in range(MIN_SCORE, MAX_SCORE + 1)
)


class CriterionRubric(BaseModel):
    """
    Per-criterion rubric definition: a short summary + one description per
    score level in [0, 5]. All strings in the rubric's declared language
    (currently pt-BR).
    """

    summary: str = Field(description="One-paragraph summary of the criterion.")
    levels: dict[str, str] = Field(
        description="Map from level key ('0'..'5') to level description.",
    )

    @model_validator(mode="after")
    def _every_level_present(self) -> "CriterionRubric":
        provided = set(self.levels.keys())
        if provided != REQUIRED_LEVEL_KEYS:
            missing = REQUIRED_LEVEL_KEYS - provided
            extra = provided - REQUIRED_LEVEL_KEYS
            raise ValueError(
                f"Criterion rubric must define exactly levels "
                f"{sorted(REQUIRED_LEVEL_KEYS)}; "
                f"missing={sorted(missing)}, extra={sorted(extra)}."
            )
        for key, text in self.levels.items():
            if not text or not text.strip():
                raise ValueError(f"Level '{key}' description is empty.")
        return self

    def level_description(self, score: int) -> str:
        """Return the pt-BR description for a given integer score in [0, 5]."""
        return self.levels[str(score)]


class RubricDefinition(BaseModel):
    """
    Complete rubric definition loaded from disk. One entry per rubric
    criterion (CriterionKind). Extra criteria in the file are rejected —
    prompt and Pydantic model must move in lockstep.
    """

    rubric_id: str = Field(description="Stable id (e.g. 'counter_v1').")
    title: str
    language: str = Field(description="ISO code of the descriptions (e.g. 'pt-BR').")
    criteria: dict[CriterionKind, CriterionRubric]

    @model_validator(mode="after")
    def _all_criteria_present(self) -> "RubricDefinition":
        expected = set(CriterionKind)
        provided = set(self.criteria.keys())
        if provided != expected:
            missing = expected - provided
            extra = provided - expected
            raise ValueError(
                f"Rubric must define exactly the criteria {sorted(k.value for k in expected)}; "
                f"missing={sorted(k.value for k in missing)}, "
                f"extra={sorted(str(k) for k in extra)}."
            )
        return self

    def criterion(self, kind: CriterionKind) -> CriterionRubric:
        """Fetch one criterion's rubric by CriterionKind."""
        return self.criteria[kind]


# ---- loading helpers -------------------------------------------------------

def load_rubric_from_text(raw_text: str) -> RubricDefinition:
    """Parse and validate a rubric from its YAML source string."""
    parsed = yaml.safe_load(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Rubric YAML must load into a mapping at the top level.")
    return RubricDefinition.model_validate(parsed)


def load_rubric_from_path(path: Path) -> RubricDefinition:
    """Load and validate a rubric from disk."""
    raw_text = path.read_text(encoding="utf-8")
    return load_rubric_from_text(raw_text)


# Default rubric shipped with the repo. Callers that want a custom rubric
# pass their own path explicitly to load_rubric_from_path.
DEFAULT_RUBRIC_PATH = Path("data/rubrics/counter_v1.yaml")


def load_default_rubric() -> RubricDefinition:
    """Load the default rubric shipped under data/rubrics/counter_v1.yaml."""
    return load_rubric_from_path(DEFAULT_RUBRIC_PATH)
