"""
Unit tests for :mod:`civis.web.supervisor` — the multi-session
aggregator that feeds the supervisor dashboard (ONDA 3, D2.1).

Every test writes a handful of session folders under ``tmp_path`` and
runs :func:`compute_supervisor_metrics` against them. The fixtures
mirror the on-disk layout the CLI and the web session page produce.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from civis.judge.rubric import (
    CriterionKind,
    CriterionVerdict,
    JudgeVerdict,
)
from civis.session.storage import (
    SessionMetadata,
    SessionTranscript,
    save_metadata,
    save_transcript,
    save_verdict_json,
)
from civis.web.supervisor import (
    ANONYMOUS_AGENT,
    compute_supervisor_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_session(
    base: Path,
    *,
    session_id: str,
    scenario_id: str = "cen_v1",
    agent_name: str | None = None,
    created_at: str = "2026-09-16T10:00:00+00:00",
    scores: dict[CriterionKind, int] | None = None,
) -> None:
    """
    Write metadata + transcript + optional verdict for one session
    under ``base``. Omit ``scores`` to leave the session unrated.
    """
    metadata = SessionMetadata(
        session_id=session_id,
        scenario_id=scenario_id,
        scenario_hash="0" * 64,
        persona_provider_name="fake-persona",
        judge_provider_name="fake-judge",
        created_at=created_at,
        last_updated_at=created_at,
        agent_name=agent_name,
    )
    save_metadata(metadata, base=base)
    save_transcript(SessionTranscript(session_id=session_id), base=base)

    if scores is None:
        return
    verdict = JudgeVerdict(
        session_id=session_id,
        criteria=[
            CriterionVerdict(
                criterion=criterion,
                score=score,
                rationale="test",
                cited_turns=[],
            )
            for criterion, score in scores.items()
        ],
        overall_summary="test",
    )
    save_verdict_json(verdict.model_dump(mode="json"), session_id, base=base)


# ---------------------------------------------------------------------------
# 1. Empty folder returns zero-valued metrics without exploding
# ---------------------------------------------------------------------------


def test_empty_sessions_dir_returns_empty_metrics(tmp_path: Path) -> None:
    """No sessions on disk → every count is 0, means are None."""
    metrics = compute_supervisor_metrics(tmp_path)
    assert metrics.total_sessions == 0
    assert metrics.unique_agents == 0
    assert metrics.mean_score is None
    assert metrics.score_distribution == {
        "fact_verification": 0.0,
        "data_protection": 0.0,
        "protocol_adherence": 0.0,
        "communication": 0.0,
    }
    assert metrics.sessions_over_time == []
    assert metrics.worst_sessions == []
    assert metrics.best_sessions == []


# ---------------------------------------------------------------------------
# 2. Counts and unique agents
# ---------------------------------------------------------------------------


def test_counts_sessions_and_unique_agents(tmp_path: Path) -> None:
    """Three sessions across two attendants → 3 total, 2 unique."""
    _write_session(tmp_path, session_id="s1", agent_name="alice", scores={
        CriterionKind.FACT_VERIFICATION: 4,
        CriterionKind.DATA_PROTECTION: 5,
        CriterionKind.PROTOCOL_ADHERENCE: 3,
        CriterionKind.COMMUNICATION: 4,
    })
    _write_session(tmp_path, session_id="s2", agent_name="alice", scores={
        CriterionKind.FACT_VERIFICATION: 2,
        CriterionKind.DATA_PROTECTION: 3,
        CriterionKind.PROTOCOL_ADHERENCE: 3,
        CriterionKind.COMMUNICATION: 2,
    })
    _write_session(tmp_path, session_id="s3", agent_name="bob", scores={
        CriterionKind.FACT_VERIFICATION: 5,
        CriterionKind.DATA_PROTECTION: 5,
        CriterionKind.PROTOCOL_ADHERENCE: 5,
        CriterionKind.COMMUNICATION: 5,
    })

    metrics = compute_supervisor_metrics(tmp_path)
    assert metrics.total_sessions == 3
    assert metrics.unique_agents == 2
    assert metrics.agent_session_counts == {"alice": 2, "bob": 1}


# ---------------------------------------------------------------------------
# 3. Mean score and per-criterion breakdown
# ---------------------------------------------------------------------------


def test_mean_score_and_score_distribution(tmp_path: Path) -> None:
    """
    Two rated sessions. Overall mean = mean of per-session averages.
    Per-criterion distribution = mean of that criterion across every
    rated session.
    """
    _write_session(tmp_path, session_id="a", agent_name="alice", scores={
        CriterionKind.FACT_VERIFICATION: 4,
        CriterionKind.DATA_PROTECTION: 4,
        CriterionKind.PROTOCOL_ADHERENCE: 4,
        CriterionKind.COMMUNICATION: 4,
    })
    _write_session(tmp_path, session_id="b", agent_name="alice", scores={
        CriterionKind.FACT_VERIFICATION: 2,
        CriterionKind.DATA_PROTECTION: 2,
        CriterionKind.PROTOCOL_ADHERENCE: 2,
        CriterionKind.COMMUNICATION: 2,
    })
    metrics = compute_supervisor_metrics(tmp_path)
    assert metrics.mean_score == pytest.approx(3.0)
    assert metrics.score_distribution["fact_verification"] == pytest.approx(3.0)
    assert metrics.score_distribution["communication"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# 4. Sessions without a verdict count in the total, not in the mean
# ---------------------------------------------------------------------------


def test_unrated_sessions_do_not_poison_the_mean(tmp_path: Path) -> None:
    """
    Two sessions: one rated 5/5, one unrated. Total is 2, mean is
    5.0 (the unrated one contributes nothing to the score aggregate).
    """
    _write_session(tmp_path, session_id="rated", agent_name="alice", scores={
        CriterionKind.FACT_VERIFICATION: 5,
        CriterionKind.DATA_PROTECTION: 5,
        CriterionKind.PROTOCOL_ADHERENCE: 5,
        CriterionKind.COMMUNICATION: 5,
    })
    _write_session(tmp_path, session_id="unrated", agent_name="alice", scores=None)

    metrics = compute_supervisor_metrics(tmp_path)
    assert metrics.total_sessions == 2
    assert metrics.mean_score == pytest.approx(5.0)
    # Unrated session shows up in neither ranking.
    ids = {r.session_id for r in metrics.best_sessions + metrics.worst_sessions}
    assert "unrated" not in ids


# ---------------------------------------------------------------------------
# 5. Rankings, dates and legacy-metadata fallback
# ---------------------------------------------------------------------------


def test_rankings_dates_and_legacy_metadata_fallback(tmp_path: Path) -> None:
    """
    Sessions written on two different dates, one with legacy metadata
    (agent_name field missing entirely). The aggregator must:

        - group session counts by their creation date;
        - treat a missing agent_name as 'anonymous';
        - order worst_sessions ascending by score and best_sessions
          descending.
    """
    _write_session(
        tmp_path,
        session_id="d1_low",
        agent_name="carol",
        created_at="2026-09-14T09:00:00+00:00",
        scores={
            CriterionKind.FACT_VERIFICATION: 1,
            CriterionKind.DATA_PROTECTION: 1,
            CriterionKind.PROTOCOL_ADHERENCE: 1,
            CriterionKind.COMMUNICATION: 1,
        },
    )
    _write_session(
        tmp_path,
        session_id="d1_high",
        agent_name="carol",
        created_at="2026-09-14T11:00:00+00:00",
        scores={
            CriterionKind.FACT_VERIFICATION: 5,
            CriterionKind.DATA_PROTECTION: 5,
            CriterionKind.PROTOCOL_ADHERENCE: 5,
            CriterionKind.COMMUNICATION: 5,
        },
    )
    # Legacy: hand-write a metadata.json that lacks 'agent_name'.
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "metadata.json").write_text(
        json.dumps(
            {
                "session_id": "legacy",
                "scenario_id": "cen_v1",
                "scenario_hash": "0" * 64,
                "persona_provider_name": "fake",
                "judge_provider_name": "fake",
                "created_at": "2026-09-15T09:00:00+00:00",
                "last_updated_at": "2026-09-15T09:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (legacy_dir / "transcript.json").write_text(
        json.dumps({"session_id": "legacy", "turns": []}),
        encoding="utf-8",
    )

    metrics = compute_supervisor_metrics(tmp_path)

    # Session counts per date.
    by_date = dict(metrics.sessions_over_time)
    assert by_date[date(2026, 9, 14)] == 2
    assert by_date[date(2026, 9, 15)] == 1

    # Anonymous fallback.
    assert ANONYMOUS_AGENT in metrics.agent_session_counts
    assert metrics.unique_agents == 2  # 'carol' + 'anonymous'

    # Worst is the low session; best is the high one.
    assert metrics.worst_sessions[0].session_id == "d1_low"
    assert metrics.best_sessions[0].session_id == "d1_high"
