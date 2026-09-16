"""
AppTest smoke tests for the CIVIS Streamlit app.

We don't try to test layout visually — Streamlit doesn't take screenshots
in a unit-test context. What we CAN pin is:

    - The entry point loads without raising.
    - Each of the four pages mounts on its own.
    - Key pt-BR labels appear in the rendered widget tree.
    - The empty-state copy shows up when there are no sessions on disk.
    - The metric cards on the Métricas page bind against the shipped
      reports/adversarial_v1.json and reports/judge_deceiver_pointwise_v1.json.

Every test uses tmp_path plus the demo generator so the run is
hermetic: nothing under `data/sessions/` is read or written.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# Resolved once — Streamlit's switch_page needs an absolute path when the
# main script lives outside the current working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_PATH = _REPO_ROOT / "src" / "civis" / "web" / "app.py"
_PAGES_DIR = _REPO_ROOT / "src" / "civis" / "web" / "pages"


@pytest.fixture()
def demo_sessions_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Point the app at a tmp sessions folder pre-populated with the demo
    fixture. Every test that renders past_sessions or metrics uses this.
    """
    from scripts.generate_demo_sessions import emit_all

    folder = tmp_path / "sessions"
    emit_all(folder)
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


@pytest.fixture()
def empty_sessions_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at an empty sessions folder so the empty state shows."""
    folder = tmp_path / "sessions"
    folder.mkdir()
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(folder))
    return folder


def _switch_to(at: AppTest, page_filename: str) -> AppTest:
    """Navigate the app to a given page by its file path."""
    at.switch_page(str(_PAGES_DIR / page_filename))
    at.run()
    return at


def test_app_entry_point_boots_without_exception() -> None:
    """The default page (Nova sessão) mounts on a fresh AppTest run."""
    at = AppTest.from_file(str(_APP_PATH))
    at.run()
    assert list(at.exception) == []


def test_default_page_is_new_session() -> None:
    at = AppTest.from_file(str(_APP_PATH))
    at.run()
    titles = [t.value for t in at.title]
    assert any("Nova sessão" in t for t in titles)


def test_new_session_page_shows_scenario_landing() -> None:
    """
    D.5 polish: the page renders three scripted-scenario cards plus the
    "Como executar agora" runner section. Pinning the subheader and a
    known scenario id catches accidental regressions during polish.
    """
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "new_session.py")
    subheaders = [s.value for s in at.subheader]
    assert "Como executar agora" in subheaders
    # Each card contains a copy-friendly CLI command in a code block —
    # AppTest exposes code blocks via at.code with the raw command text.
    code_texts = " ".join(c.value for c in at.code)
    assert "certificate_thirdparty_fraudster_v1" in code_texts
    assert "certificate_duplicate_confused_v1" in code_texts
    assert "rg_urgent_aggressive_v1" in code_texts


def test_past_sessions_lists_demo_fixture(demo_sessions_env: Path) -> None:
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "past_sessions.py")
    # The caption reports the exact number of sessions from the fixture.
    caption_text = " ".join(c.value for c in at.caption)
    assert "5 sessão" in caption_text
    # Session ids appear in the plain markdown listing.
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "demo_fraudster_leak_v1" in markdown_text


def test_past_sessions_shows_empty_state(empty_sessions_env: Path) -> None:
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "past_sessions.py")
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "Nenhuma sessão ainda" in markdown_text


def test_metrics_page_renders_all_four_metric_cards() -> None:
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "metrics.py")
    metric_labels = [m.label for m in at.metric]
    assert "Latência p95" in metric_labels
    assert "Custo/sessão" in metric_labels
    assert "M2 · Defesa" in metric_labels
    assert "ASR JudgeDeceiver" in metric_labels


def test_metrics_page_binds_to_shipped_adversarial_report() -> None:
    """The M2 metric should read as 'X/Y' from reports/adversarial_v1.json."""
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "metrics.py")
    m2_values = [m.value for m in at.metric if m.label == "M2 · Defesa"]
    assert len(m2_values) == 1
    # Value looks like "55/57" — non-empty digits with a slash.
    assert "/" in m2_values[0]


def test_metrics_page_binds_to_shipped_judge_deceiver_report() -> None:
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "metrics.py")
    asr_values = [m.value for m in at.metric if m.label == "ASR JudgeDeceiver"]
    assert len(asr_values) == 1
    # Value looks like "100%" — ends in a percent sign.
    assert asr_values[0].endswith("%")


def test_about_page_shows_product_pitch() -> None:
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "about.py")
    subheaders = [s.value for s in at.subheader]
    assert "Por que isso importa" in subheaders
    assert "Como navegar" in subheaders
    # The tagline appears in the h1 title.
    titles = [t.value for t in at.title]
    assert any("Cidadão virtual" in t for t in titles)


def test_metrics_page_gracefully_falls_back_when_reports_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When reports/ is empty, the M2 and ASR cards must show '—' instead
    of raising. The metrics page uses the DEFAULT_REPORTS_DIR path, so
    we CWD into a tmp folder to hide the shipped reports.
    """
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "metrics.py")
    values_by_label = {m.label: m.value for m in at.metric}
    assert values_by_label["M2 · Defesa"] == "—"
    assert values_by_label["ASR JudgeDeceiver"] == "—"


def test_sidebar_header_renders_product_identity() -> None:
    """The sidebar carries the CIVIS name and tagline as scene-setters."""
    at = AppTest.from_file(str(_APP_PATH))
    at.run()
    sidebar_md = " ".join(m.value for m in at.sidebar.markdown)
    assert "CIVIS" in sidebar_md
    assert "Cidadão virtual" in sidebar_md


# One test per page confirming the exact expected title. Pinning the
# title strings guards against accidental copy drift during polish.
@pytest.mark.parametrize(
    ("page_file", "expected_substring"),
    [
        ("new_session.py", "Nova sessão"),
        ("past_sessions.py", "Sessões passadas"),
        ("metrics.py", "Métricas"),
        ("about.py", "Cidadão virtual"),
    ],
)
def test_each_page_has_expected_title(
    demo_sessions_env: Path,
    page_file: str,
    expected_substring: str,
) -> None:
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, page_file)
    titles = [t.value for t in at.title]
    assert any(expected_substring in title for title in titles), (
        f"Expected substring '{expected_substring}' in titles={titles}"
    )


def test_metrics_page_shows_m1_hybrid_validation_placeholders() -> None:
    """
    D.3 requires the Métricas page to expose the M1 hybrid design
    (M1-A inter-model kappa + M1-C manual sample) with a placeholder
    for the study window 20/10-01/12/2026. Pinning the labels here
    catches accidental copy drift during polish.
    """
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "metrics.py")
    metric_labels = [m.label for m in at.metric]
    assert "Kappa inter-modelo" in metric_labels
    assert "Concordância criterion-a-criterion" in metric_labels
    # The subheader anchoring the whole block.
    subheaders = [s.value for s in at.subheader]
    assert "Validação (M1 híbrida)" in subheaders
    # Study window quoted in the info box, so a reader knows when data lands.
    info_text = " ".join(i.value for i in at.info)
    assert "20/10" in info_text and "01/12" in info_text



def test_env_override_takes_effect_on_past_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Two isolated tmp folders — one full, one empty — round-trip the
    env-var contract that AppTest fixtures rely on.
    """
    from scripts.generate_demo_sessions import emit_all

    full = tmp_path / "full"
    emit_all(full)
    empty = tmp_path / "empty"
    empty.mkdir()

    # First run: env points at the populated folder → caption says 5.
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(full))
    at_full = AppTest.from_file(str(_APP_PATH))
    _switch_to(at_full, "past_sessions.py")
    caption_full = " ".join(c.value for c in at_full.caption)
    assert "5 sessão" in caption_full

    # Second run: env points at the empty folder → empty state shows.
    monkeypatch.setenv("CIVIS_SESSIONS_DIR", str(empty))
    at_empty = AppTest.from_file(str(_APP_PATH))
    _switch_to(at_empty, "past_sessions.py")
    md_empty = " ".join(m.value for m in at_empty.markdown)
    assert "Nenhuma sessão ainda" in md_empty


def test_sidebar_footer_carries_attribution() -> None:
    """D.5 polish: the sidebar closes with author + course attribution."""
    at = AppTest.from_file(str(_APP_PATH))
    at.run()
    sidebar_captions = " ".join(c.value for c in at.sidebar.caption)
    assert "Anderson" in sidebar_captions
    assert "UFSC" in sidebar_captions


def test_about_page_renders_scannable_metric_row() -> None:
    """
    D.5 polish: the About page shows a four-metric summary row so a
    cold visitor gets a numeric anchor before reading the prose.
    """
    at = AppTest.from_file(str(_APP_PATH))
    _switch_to(at, "about.py")
    metric_labels = [m.label for m in at.metric]
    assert "Perfis de persona" in metric_labels
    assert "Cenários prontos" in metric_labels
    assert "Critérios da rubrica" in metric_labels
    assert "Bateria adversarial" in metric_labels




# Silence a warning caused by unused fixtures in parametrised tests.
_ = os
