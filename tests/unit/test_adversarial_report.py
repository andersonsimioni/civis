"""
Security report generator tests (C.5).

Verifies:
    - The generator renders every required section header.
    - Numbers embedded in the report come from the input JSONs (not made up).
    - The CLI subcommand writes the file to disk.
"""

import json
from pathlib import Path

from civis.adversarial.report import SECTIONS, build_security_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _adversarial_fixture() -> dict:
    """Minimal adversarial JSON with one persona and one judge report."""
    return {
        "battery": {"version": "v1", "path": "x", "attack_count": 57},
        "reports": [
            {
                "battery_version": "v1",
                "target_label": "persona:mock:persona_refusal",
                "total": 57,
                "defended": 55,
                "leaked": 0,
                "skipped": 2,
                "leak_rate": 0.0,
                "by_category": {
                    "LLM01_prompt_injection": {"defended": 36, "leaked": 0, "skipped": 0},
                    "LLM06_sensitive_info_disclosure": {"defended": 14, "leaked": 0, "skipped": 0},
                },
                "by_severity": {
                    "high": {"defended": 28, "leaked": 0, "skipped": 0},
                    "medium": {"defended": 18, "leaked": 0, "skipped": 0},
                },
                "results": [],
            },
            {
                "battery_version": "v1",
                "target_label": "judge:mock:judge_refusal",
                "total": 57,
                "defended": 50,
                "leaked": 5,
                "skipped": 2,
                "leak_rate": 0.09090909,
                "by_category": {},
                "by_severity": {},
                "results": [],
            },
        ],
    }


def _judge_deceiver_fixture() -> dict:
    """Minimal JudgeDeceiver JSON with vulnerable + robust mocks."""
    return {
        "target_score": 5,
        "attacks_per_judge": 72,
        "reports": [
            {
                "label": "mock:vulnerable_judge",
                "baseline": {
                    "scores": {
                        "fact_verification": 1,
                        "data_protection": 1,
                        "protocol_adherence": 1,
                        "communication": 2,
                    }
                },
                "attempted": 72,
                "succeeded": 72,
                "overall_asr": 1.0,
                "by_criterion": [
                    {
                        "criterion": "protocol_adherence",
                        "target_scores_attempted": [5],
                        "attempted": 18,
                        "succeeded": 18,
                    },
                ],
                "by_position": [
                    {"position": "start", "attempted": 24, "succeeded": 24},
                    {"position": "middle", "attempted": 24, "succeeded": 24},
                    {"position": "end", "attempted": 24, "succeeded": 24},
                ],
                "outcomes": [],
            },
            {
                "label": "mock:robust_judge",
                "baseline": {
                    "scores": {
                        "fact_verification": 1,
                        "data_protection": 1,
                        "protocol_adherence": 1,
                        "communication": 2,
                    }
                },
                "attempted": 72,
                "succeeded": 0,
                "overall_asr": 0.0,
                "by_criterion": [],
                "by_position": [],
                "outcomes": [],
            },
        ],
    }


# ---- section coverage -----------------------------------------------------

def test_report_generator_renders_all_required_sections(tmp_path):
    """C.5 acceptance: every mandated section header is present."""
    adv_path = tmp_path / "adv.json"
    jd_path = tmp_path / "jd.json"
    _write_json(adv_path, _adversarial_fixture())
    _write_json(jd_path, _judge_deceiver_fixture())

    markdown = build_security_report(adv_path, jd_path)
    for section in SECTIONS:
        assert section in markdown, f"missing section: {section}"


def test_report_generator_includes_title_and_author():
    """Regression: the header block carries the title and the author line."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as td:
        adv_path = Path(td) / "adv.json"
        jd_path = Path(td) / "jd.json"
        _write_json(adv_path, _adversarial_fixture())
        _write_json(jd_path, _judge_deceiver_fixture())
        markdown = build_security_report(adv_path, jd_path)

    assert "# Relatório de segurança CIVIS" in markdown
    assert "Anderson Simioni" in markdown


# ---- numbers ---------------------------------------------------------------

def test_report_generator_embeds_real_numbers_from_json(tmp_path):
    """
    Given ASR 100% and 0% in the inputs, the report must render those
    numbers verbatim in the executive summary and results tables.
    """
    adv_path = tmp_path / "adv.json"
    jd_path = tmp_path / "jd.json"
    _write_json(adv_path, _adversarial_fixture())
    _write_json(jd_path, _judge_deceiver_fixture())
    markdown = build_security_report(adv_path, jd_path)

    # Executive summary mentions the ASR range.
    assert "0.0%" in markdown
    assert "100.0%" in markdown
    # M2 leak_rate for the judge in fixture is ~9.09% — must appear as such.
    assert "9.09%" in markdown or "9.1%" in markdown
    # Attack count from adversarial fixture flows to the methodology.
    assert "57 ataques" in markdown


def test_report_generator_tables_use_criterion_and_position_axes(tmp_path):
    """Both axes needed by slide 6/7 of the pitch deck must be present."""
    adv_path = tmp_path / "adv.json"
    jd_path = tmp_path / "jd.json"
    _write_json(adv_path, _adversarial_fixture())
    _write_json(jd_path, _judge_deceiver_fixture())
    markdown = build_security_report(adv_path, jd_path)

    # Criterion header row.
    assert "| Critério | tentativas | sucessos | ASR |" in markdown
    # Position header row.
    assert "| Posição | tentativas | sucessos | ASR |" in markdown
    # Actual criterion value.
    assert "protocol_adherence" in markdown
    # Position values.
    assert "start" in markdown
    assert "middle" in markdown
    assert "end" in markdown


# ---- CLI wiring -----------------------------------------------------------

def test_cli_report_writes_markdown(tmp_path):
    """
    `civis adversarial report --output …` reads the two JSONs and writes
    the Markdown file to the requested path.
    """
    from typer.testing import CliRunner

    from civis.cli import app

    adv_path = tmp_path / "adv.json"
    jd_path = tmp_path / "jd.json"
    _write_json(adv_path, _adversarial_fixture())
    _write_json(jd_path, _judge_deceiver_fixture())

    output = tmp_path / "sec.md"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "adversarial", "report",
            "--adversarial-json", str(adv_path),
            "--judge-deceiver-json", str(jd_path),
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    for section in SECTIONS:
        assert section in text


def test_cli_report_errors_when_input_missing(tmp_path):
    """Missing input should exit with code 2 and a clear message."""
    from typer.testing import CliRunner

    from civis.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "adversarial", "report",
            "--adversarial-json", str(tmp_path / "nope.json"),
            "--judge-deceiver-json", str(tmp_path / "nope2.json"),
            "--output", str(tmp_path / "out.md"),
        ],
    )
    assert result.exit_code == 2


# ---- shipped reports guard ------------------------------------------------

def test_shipped_security_report_exists_and_has_all_sections():
    """
    The shipped reports/security_v1.md must exist and cover every section
    — otherwise the pitch deck loses its data source.
    """
    shipped = Path(__file__).resolve().parents[2] / "reports" / "security_v1.md"
    assert shipped.exists(), "reports/security_v1.md must ship with the branch"
    text = shipped.read_text(encoding="utf-8")
    for section in SECTIONS:
        assert section in text, f"shipped report missing section: {section}"
