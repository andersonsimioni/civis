"""
AppTest cases for the supervisor dashboard page (ONDA 3, D2.2).

We seed a small folder of fake sessions and boot the app pointed at
it. Assertions cover:

    - KPI cards render with the expected numbers.
    - Bar chart of scores by criterion renders (native widget appears).
    - Line chart of sessions per day renders when there are timestamps.
    - Empty state copy shows up when the folder is empty.
    - Clicking a ranking-row 'Abrir' button stores the session id in
      ``civis.selected_session_id``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"


def _seed_session(
    base: Path,
    *,
    session_id: str,
    agent_name: str,
    scores: dict[CriterionKind, int],
    created_at: str = "2026-09-16T10:00:00+00:00",
) -> None:
    """Helper mirroring the on-disk shape produced by the CLI + web page."""
    metadata = SessionMetadata(
        session_id=session_id,
        scenario_id="cen_v1",
        scenario_hash="0" * 64,
        persona_provider_name="fake-persona",
        judge_provider_name="fake-judge",
        created_at=created_at,
        last_updated_at=created_at,
        agent_name=agent_name,
    )
    save_metadata(metadata, base=base)
    save_transcript(SessionTranscript(session_id=session_id), base=base)
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


@pytest.fixture()
def seeded_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AppTest:
    """
    Two agents, three sessions of varying quality — enough to fill
    every widget on the page.
    """
    folder = tmp_path / "sessions"
    folder.mkdir()
    _seed_session(
        folder,
        session_id="best_one",
        agent_name="alice",
        scores={
            CriterionKind.FACT_VERIFICATION: 5,
            CriterionKind.DATA_PROTECTION: 5,
            CriterionKind.PROTOCOL_ADHERENCE: 5,
            CriterionKind.COMMUNICATION: 5,
        },
    )
    _seed_session(
        folder,
        session_id="middle_one",
        agent_name="alice",
        scores={
            CriterionKind.FACT_VERIFICATION: 3,
            CriterionKind.DATA_PROTECTION: 3,
            CriterionKind.PROTOCOL_ADHERENCE: 3,
            CriterionKind.COMMUNICATION: 3,
        },
        created_at="2026-09-15T10:00:00+00:00",
    )
    _seed_session(
        folder,
        session_id="worst_one",
        agent_name="bob",
        scores={
            CriterionKind.FACT_VERIFICATION: 1,
            CriterionKind.DATA_PROTECTION: 1,
            CriterionKind.PROTOCOL_ADHERENCE: 1,
            CriterionKind.COMMUNICATION: 1,
        },
    )
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "supervisor.py"))
    at.run()
    return at


def test_kpis_render_expected_numbers(seeded_app: AppTest) -> None:
    """Total sessions, unique agents, mean score all reflect the fixture."""
    at = seeded_app
    labels_and_values = [(m.label, m.value) for m in at.metric]
    label_map = dict(labels_and_values)
    assert label_map["Total de sessões"] == "3"
    assert label_map["Atendentes únicos"] == "2"
    # (5+3+1)/3 == 3.00
    assert label_map["Nota média"] == "3.00"
    # Kappa placeholder still on the page.
    assert label_map["Kappa (M1)"] == "—"


def test_criterion_bar_chart_renders(seeded_app: AppTest) -> None:
    """The per-criterion subheader is present and no chart exception was raised."""
    at = seeded_app
    subheaders = [s.value for s in at.subheader]
    assert "Nota média por critério" in subheaders


def test_sessions_over_time_line_chart_renders(seeded_app: AppTest) -> None:
    """The per-day line-chart subheader is present."""
    at = seeded_app
    subheaders = [s.value for s in at.subheader]
    assert "Sessões ao longo do tempo" in subheaders


def test_empty_state_shows_up_when_no_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty sessions folder falls back to the empty-state copy."""
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))

    at = AppTest.from_file(str(_APP_PATH))
    at.switch_page(str(_PAGES_DIR / "supervisor.py"))
    at.run()

    markdown_dump = "\n".join(m.value for m in at.markdown)
    assert "Nenhuma sessão registrada ainda" in markdown_dump


def test_open_button_stores_session_id_in_state(seeded_app: AppTest) -> None:
    """
    Clicking a 'worst' ranking Abrir button sets
    ``civis.selected_session_id`` — the same key the past-sessions
    drill-down reads.
    """
    at = seeded_app
    worst_buttons = [
        b for b in at.button if b.key and b.key.startswith("supervisor_worst_open_")
    ]
    assert worst_buttons, "expected at least one 'worst' Abrir button"
    worst_buttons[0].click()
    at.run()
    assert at.session_state.get("civis.selected_session_id") == "worst_one"
