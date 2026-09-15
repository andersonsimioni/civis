"""
Rubric loader tests.

Guarantees:
    - The shipped counter_v1.yaml loads and validates.
    - Every CriterionKind must appear exactly once; missing/extra
      criteria are rejected at load time.
    - Every criterion must define levels '0'..'5'; missing/extra
      levels are rejected at load time.
    - Level descriptions come back verbatim (used by the judge prompt
      builder).
"""

from pathlib import Path

import pytest

from civis.judge.rubric import CriterionKind
from civis.judge.rubric_loader import (
    DEFAULT_RUBRIC_PATH,
    RubricDefinition,
    load_default_rubric,
    load_rubric_from_path,
    load_rubric_from_text,
)

# ---- shipped rubric --------------------------------------------------------

def test_shipped_counter_v1_rubric_loads_and_validates():
    rubric = load_rubric_from_path(DEFAULT_RUBRIC_PATH)
    assert isinstance(rubric, RubricDefinition)
    assert rubric.rubric_id == "counter_v1"
    assert rubric.language == "pt-BR"
    # All four rubric criteria must be defined.
    assert set(rubric.criteria.keys()) == set(CriterionKind)
    # Every criterion carries a non-empty summary and 6 level descriptions.
    for kind in CriterionKind:
        criterion = rubric.criterion(kind)
        assert criterion.summary.strip()
        for score in range(6):
            assert criterion.level_description(score).strip()


def test_load_default_rubric_matches_direct_load():
    a = load_default_rubric()
    b = load_rubric_from_path(DEFAULT_RUBRIC_PATH)
    assert a.model_dump() == b.model_dump()


# ---- validation failures ---------------------------------------------------

def _minimal_valid_criteria_text() -> str:
    """A YAML fragment with all four criteria, each carrying all 6 levels."""
    lines = ["rubric_id: 't'", "title: 't'", "language: 'pt-BR'", "criteria:"]
    for kind in CriterionKind:
        lines.append(f"  {kind.value}:")
        lines.append("    summary: 's'")
        lines.append("    levels:")
        for score in range(6):
            lines.append(f"      \"{score}\": 'desc {score}'")
    return "\n".join(lines)


def test_rejects_missing_criterion():
    lines = ["rubric_id: 't'", "title: 't'", "language: 'pt-BR'", "criteria:"]
    for kind in list(CriterionKind)[:-1]:  # drop the last criterion
        lines.append(f"  {kind.value}:")
        lines.append("    summary: 's'")
        lines.append("    levels:")
        for score in range(6):
            lines.append(f"      \"{score}\": 'd'")
    text = "\n".join(lines)
    with pytest.raises(ValueError, match="missing="):
        load_rubric_from_text(text)


def test_rejects_missing_level():
    lines = ["rubric_id: 't'", "title: 't'", "language: 'pt-BR'", "criteria:"]
    for kind in CriterionKind:
        lines.append(f"  {kind.value}:")
        lines.append("    summary: 's'")
        lines.append("    levels:")
        # Only define levels 0..4 — missing "5".
        for score in range(5):
            lines.append(f"      \"{score}\": 'd'")
    text = "\n".join(lines)
    with pytest.raises(ValueError, match="missing="):
        load_rubric_from_text(text)


def test_rejects_extra_level():
    lines = ["rubric_id: 't'", "title: 't'", "language: 'pt-BR'", "criteria:"]
    for kind in CriterionKind:
        lines.append(f"  {kind.value}:")
        lines.append("    summary: 's'")
        lines.append("    levels:")
        for score in range(6):
            lines.append(f"      \"{score}\": 'd'")
        lines.append("      \"6\": 'extra'")
    text = "\n".join(lines)
    with pytest.raises(ValueError, match="extra="):
        load_rubric_from_text(text)


def test_rejects_empty_level_description():
    """A blank level description is a silent regression that would hide a
    rubric level from the judge — reject it at load time."""
    text = _minimal_valid_criteria_text().replace(
        "\"5\": 'desc 5'", "\"5\": ''"
    )
    with pytest.raises(ValueError, match="empty"):
        load_rubric_from_text(text)


def test_rejects_non_mapping_top_level():
    with pytest.raises(ValueError, match="mapping"):
        load_rubric_from_text("- not a mapping\n- just a list")


# ---- level descriptions surface in prompt ---------------------------------

def test_level_description_returns_exact_yaml_text(tmp_path: Path):
    """
    Level descriptions come back verbatim (no reflowing) so what the human
    evaluators read in study/rubric_evaluator.md matches what the judge
    reads in the prompt.
    """
    rubric = load_default_rubric()
    fact_verification = rubric.criterion(CriterionKind.FACT_VERIFICATION)
    # Sanity check: level 5 mentions the "sem exceção" clause from the source.
    level_5 = fact_verification.level_description(5)
    assert "sem exceção" in level_5.lower()
