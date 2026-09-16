"""
Certification eligibility tests (Onda-1 F2.1).

Uses synthetic verdict.json files under tmp_path so we can craft precise
score distributions. The judge's own tests already cover JudgeVerdict
validation — here we only care that `compute_eligibility` awards the
right level given the aggregate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from civis.certification.eligibility import (
    CertificationEligibility,
    CertificationLevel,
    compute_eligibility,
    discover_session_dirs,
)
from civis.judge.rubric import MAX_SCORE, CriterionKind


def _write_verdict(
    session_dir: Path,
    per_criterion_scores: dict[CriterionKind, int],
    session_id: str | None = None,
) -> None:
    """
    Write a minimal verdict.json into `session_dir` with the given scores.
    Judge shape follows civis.judge.rubric.JudgeVerdict.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id or session_dir.name,
        "criteria": [
            {
                "criterion": criterion.value,
                "score": score,
                "rationale": f"synthetic verdict for {criterion.value}",
                "cited_turns": [],
            }
            for criterion, score in per_criterion_scores.items()
        ],
        "overall_summary": "synthetic verdict for tests.",
    }
    (session_dir / "verdict.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _make_sessions(
    root: Path,
    n: int,
    scores: dict[CriterionKind, int],
) -> list[Path]:
    """Create N sessions under `root` all sharing the same per-criterion scores."""
    dirs: list[Path] = []
    for i in range(n):
        session_dir = root / f"session_{i:03d}"
        _write_verdict(session_dir, scores)
        dirs.append(session_dir)
    return dirs


# All-fives on every criterion => normalised mean = 1.0. Handy for "over
# any threshold" cases; the exact score becomes the only variable.
ALL_FIVES: dict[CriterionKind, int] = {c: MAX_SCORE for c in CriterionKind}


# ---- basic tier awarding ---------------------------------------------------

def test_bronze_awarded_at_five_sessions_and_60_percent(tmp_path: Path):
    """5 sessions with mean 3/5 = 0.6 hits BRONZE exactly on the boundary."""
    sessions = _make_sessions(
        tmp_path,
        n=5,
        scores={c: 3 for c in CriterionKind},
    )
    result = compute_eligibility(sessions)
    assert isinstance(result, CertificationEligibility)
    assert result.level == CertificationLevel.BRONZE
    assert result.n_sessions == 5
    assert result.mean_score == pytest.approx(0.6)


def test_silver_awarded_at_fifteen_sessions_and_70_percent(tmp_path: Path):
    sessions = _make_sessions(
        tmp_path,
        n=15,
        scores={
            CriterionKind.FACT_VERIFICATION: 4,
            CriterionKind.DATA_PROTECTION: 3,
            CriterionKind.PROTOCOL_ADHERENCE: 4,
            CriterionKind.COMMUNICATION: 3,
        },
    )
    # per-session mean = (0.8 + 0.6 + 0.8 + 0.6) / 4 = 0.7.
    result = compute_eligibility(sessions)
    assert result.level == CertificationLevel.SILVER
    assert result.n_sessions == 15
    assert result.mean_score == pytest.approx(0.7)


def test_gold_awarded_at_thirty_sessions_and_80_percent(tmp_path: Path):
    sessions = _make_sessions(tmp_path, n=30, scores=ALL_FIVES)
    result = compute_eligibility(sessions)
    assert result.level == CertificationLevel.GOLD
    assert result.n_sessions == 30
    assert result.mean_score == pytest.approx(1.0)


# ---- non-eligible edges ----------------------------------------------------

def test_not_eligible_when_fewer_than_five_sessions(tmp_path: Path):
    """Four excellent sessions still miss BRONZE — the floor is 5."""
    sessions = _make_sessions(tmp_path, n=4, scores=ALL_FIVES)
    result = compute_eligibility(sessions)
    assert result.level is None
    assert result.n_sessions == 4
    assert result.mean_score == pytest.approx(1.0)


def test_not_eligible_when_mean_below_bronze_threshold(tmp_path: Path):
    """
    Twenty sessions with mean = 0.4 (score of 2 on every criterion) miss
    every level. Session count alone does not grant certification.
    """
    sessions = _make_sessions(
        tmp_path,
        n=20,
        scores={c: 2 for c in CriterionKind},
    )
    result = compute_eligibility(sessions)
    assert result.level is None
    assert result.n_sessions == 20
    assert result.mean_score == pytest.approx(0.4)


def test_no_sessions_returns_empty_report(tmp_path: Path):
    """Empty input list => level=None, no crash, all zeroes."""
    result = compute_eligibility([])
    assert result.level is None
    assert result.n_sessions == 0
    assert result.mean_score == 0.0
    assert result.per_criterion_mean == {}


# ---- robustness on the filesystem ------------------------------------------

def test_sessions_without_verdict_are_skipped(tmp_path: Path):
    """
    A session directory without verdict.json (e.g. --no-judge run) should
    be silently ignored, not crash the aggregation.
    """
    good = _make_sessions(tmp_path, n=5, scores=ALL_FIVES)
    # Add three "still running" directories with no verdict.
    for i in range(3):
        (tmp_path / f"incomplete_{i}").mkdir()
    result = compute_eligibility(good + list(tmp_path.glob("incomplete_*")))
    assert result.level == CertificationLevel.GOLD or result.level == CertificationLevel.BRONZE
    # 5 good sessions + all_fives => BRONZE (5 sessions is exactly the
    # bronze floor; needs 15 for SILVER, 30 for GOLD).
    assert result.level == CertificationLevel.BRONZE
    assert result.n_sessions == 5


def test_malformed_verdict_json_is_skipped(tmp_path: Path):
    """A bogus verdict.json does not sink the aggregation of the good ones."""
    good = _make_sessions(tmp_path, n=5, scores=ALL_FIVES)
    bad_dir = tmp_path / "malformed"
    bad_dir.mkdir()
    (bad_dir / "verdict.json").write_text("{not-json", encoding="utf-8")
    result = compute_eligibility(good + [bad_dir])
    assert result.n_sessions == 5
    assert result.level == CertificationLevel.BRONZE


def test_per_criterion_mean_is_computed(tmp_path: Path):
    """
    per_criterion_mean must reflect each criterion's own average, not
    the session-level mean, so certificate rendering can show a breakdown.
    """
    sessions = _make_sessions(
        tmp_path,
        n=5,
        scores={
            CriterionKind.FACT_VERIFICATION: 5,       # 1.0
            CriterionKind.DATA_PROTECTION: 4,          # 0.8
            CriterionKind.PROTOCOL_ADHERENCE: 3,       # 0.6
            CriterionKind.COMMUNICATION: 2,            # 0.4
        },
    )
    result = compute_eligibility(sessions)
    assert result.per_criterion_mean["fact_verification"] == pytest.approx(1.0)
    assert result.per_criterion_mean["data_protection"] == pytest.approx(0.8)
    assert result.per_criterion_mean["protocol_adherence"] == pytest.approx(0.6)
    assert result.per_criterion_mean["communication"] == pytest.approx(0.4)


# ---- helper: discover_session_dirs -----------------------------------------

def test_discover_session_dirs_returns_sorted_subdirs(tmp_path: Path):
    for name in ("zeta", "alpha", "mu"):
        (tmp_path / name).mkdir()
    (tmp_path / "not_a_dir.txt").write_text("ignore me", encoding="utf-8")
    result = discover_session_dirs(tmp_path)
    assert [p.name for p in result] == ["alpha", "mu", "zeta"]


def test_discover_session_dirs_missing_root_returns_empty(tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    assert discover_session_dirs(missing) == []
