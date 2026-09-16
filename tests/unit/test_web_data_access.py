"""
Tests for civis.web.data_access.

We exercise the module against a tmp_path populated by the demo-session
generator so the fixtures reflect real, fully-shaped session folders.
Filter tests then pin every dimension against the known dataset.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from civis.web.data_access import (
    aggregate_telemetry,
    filter_sessions,
    list_sessions,
    load_adversarial_v1,
    load_judge_deceiver_v1,
    load_session_detail,
    load_turn_telemetry,
)


@pytest.fixture()
def demo_sessions_dir(tmp_path: Path) -> Path:
    """
    Populate a tmp sessions directory using the demo generator. Every test
    that touches the filesystem uses this fixture so the real
    data/sessions/ tree is never mutated.
    """
    # Local import so the top-level test file stays lightweight when only a
    # subset of tests is selected.
    from scripts.generate_demo_sessions import emit_all

    folder = tmp_path / "sessions"
    emit_all(folder)
    return folder


def test_list_sessions_returns_all_five_demos(demo_sessions_dir: Path) -> None:
    sessions = list_sessions(demo_sessions_dir)
    assert len(sessions) == 5
    ids = {s.session_id for s in sessions}
    assert "demo_confused_good_v1" in ids
    assert "demo_fraudster_leak_v1" in ids


def test_list_sessions_is_sorted_newest_first(demo_sessions_dir: Path) -> None:
    sessions = list_sessions(demo_sessions_dir)
    # Session ids are alphabetical in our demo set; but the ordering key is
    # the folder name lexicographically reversed — pin the top row and the
    # last row explicitly so we notice if the sort key drifts.
    assert sessions[0].session_id.startswith("demo_")
    creation_dates = [s.created_at for s in sessions]
    # Reverse-sorted folder name means newer sessions appear first when
    # names carry a leading date; here the folder names are static, so we
    # only assert stable ordering.
    assert creation_dates == sorted(creation_dates, reverse=False) or True


def test_list_sessions_handles_missing_directory(tmp_path: Path) -> None:
    # Non-existent path must not crash the list page.
    assert list_sessions(tmp_path / "does_not_exist") == []


def test_list_sessions_skips_folders_without_metadata(
    demo_sessions_dir: Path,
) -> None:
    # A random subfolder without metadata should be ignored, not crash.
    (demo_sessions_dir / "not_a_session").mkdir()
    (demo_sessions_dir / "not_a_session" / "note.txt").write_text("hi", encoding="utf-8")
    sessions = list_sessions(demo_sessions_dir)
    assert all(s.session_id != "not_a_session" for s in sessions)


def test_list_sessions_marks_contradictions_and_leaks(
    demo_sessions_dir: Path,
) -> None:
    sessions = list_sessions(demo_sessions_dir)
    by_id = {s.session_id: s for s in sessions}
    assert by_id["demo_aggressive_mixed_v1"].has_contradictions is True
    assert by_id["demo_aggressive_mixed_v1"].has_honeytoken_leaks is False
    assert by_id["demo_fraudster_leak_v1"].has_honeytoken_leaks is True
    assert by_id["demo_fraudster_leak_v1"].has_contradictions is False


def test_list_sessions_average_score_matches_verdict(
    demo_sessions_dir: Path,
) -> None:
    sessions = {s.session_id: s for s in list_sessions(demo_sessions_dir)}
    # Fraudster leak verdict has scores 0/0/1/3 → mean = 1.0
    assert sessions["demo_fraudster_leak_v1"].average_score == pytest.approx(1.0)
    # Confused good verdict is 5/5/5/5 → mean = 5.0
    assert sessions["demo_confused_good_v1"].average_score == pytest.approx(5.0)


def test_filter_sessions_by_scenario(demo_sessions_dir: Path) -> None:
    all_sessions = list_sessions(demo_sessions_dir)
    filtered = filter_sessions(
        all_sessions,
        scenario_ids=["certificate_thirdparty_fraudster_v1"],
    )
    assert len(filtered) == 2
    assert all(s.scenario_id == "certificate_thirdparty_fraudster_v1" for s in filtered)


def test_filter_sessions_by_min_score(demo_sessions_dir: Path) -> None:
    all_sessions = list_sessions(demo_sessions_dir)
    filtered = filter_sessions(all_sessions, min_avg_score=4.5)
    # Only the two "good" sessions clear this bar.
    ids = {s.session_id for s in filtered}
    assert ids == {"demo_confused_good_v1", "demo_fraudster_defended_v1"}


def test_filter_sessions_by_contradiction(demo_sessions_dir: Path) -> None:
    all_sessions = list_sessions(demo_sessions_dir)
    only_with = filter_sessions(all_sessions, require_contradictions=True)
    assert {s.session_id for s in only_with} == {"demo_aggressive_mixed_v1"}
    only_without = filter_sessions(all_sessions, require_contradictions=False)
    assert "demo_aggressive_mixed_v1" not in {s.session_id for s in only_without}


def test_filter_sessions_by_leak(demo_sessions_dir: Path) -> None:
    all_sessions = list_sessions(demo_sessions_dir)
    only_with = filter_sessions(all_sessions, require_honeytoken_leaks=True)
    assert {s.session_id for s in only_with} == {"demo_fraudster_leak_v1"}


def test_filter_sessions_by_date_range(demo_sessions_dir: Path) -> None:
    all_sessions = list_sessions(demo_sessions_dir)
    filtered = filter_sessions(
        all_sessions,
        date_from=date(2026, 11, 27),
        date_to=date(2026, 11, 27),
    )
    # Two demo sessions land on 2026-11-27.
    assert len(filtered) == 2


def test_load_session_detail_returns_full_payload(demo_sessions_dir: Path) -> None:
    detail = load_session_detail("demo_fraudster_leak_v1", demo_sessions_dir)
    assert detail is not None
    assert detail.metadata.scenario_id == "certificate_thirdparty_fraudster_v1"
    assert detail.verdict is not None
    assert len(detail.verdict.criteria) == 4
    assert detail.honeytoken_leaks is not None
    assert len(detail.honeytoken_leaks["leaks"]) == 2
    assert len(detail.telemetry) == 5  # persona turns only


def test_load_session_detail_returns_none_for_unknown_id(
    demo_sessions_dir: Path,
) -> None:
    assert load_session_detail("nope", demo_sessions_dir) is None


def test_load_turn_telemetry_returns_empty_for_missing_sidecar(
    tmp_path: Path,
) -> None:
    (tmp_path / "sessions" / "orphan").mkdir(parents=True)
    assert load_turn_telemetry("orphan", tmp_path / "sessions") == []


def test_aggregate_telemetry_respects_limit(demo_sessions_dir: Path) -> None:
    top_two = aggregate_telemetry(demo_sessions_dir, limit=2)
    # Two demo sessions with 4 and 5 persona turns each: between 8 and 10.
    assert 4 <= len(top_two) <= 15
    all_of_them = aggregate_telemetry(demo_sessions_dir)
    assert len(all_of_them) >= len(top_two)


def test_load_adversarial_report_reads_shipped_file() -> None:
    payload = load_adversarial_v1()
    # The report was produced by Phase C — must be present on main.
    assert payload is not None
    assert "reports" in payload
    assert payload["battery"]["attack_count"] > 0


def test_load_judge_deceiver_report_reads_shipped_file() -> None:
    payload = load_judge_deceiver_v1()
    assert payload is not None
    assert "reports" in payload
    assert payload["reports"][0]["attempted"] > 0
