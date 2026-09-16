"""
`civis certify` end-to-end tests (Onda-1 F2.3).

Uses Typer's CliRunner to invoke the command with a tmp_path
`--sessions-dir` populated with synthetic verdict.json files.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from civis.cli import app
from civis.cli.certify import certify_command  # noqa: F401 - import for wiring side effect
from civis.judge.rubric import MAX_SCORE, CriterionKind

runner = CliRunner()


def _write_verdict(session_dir: Path, score: int) -> None:
    """Uniform-score verdict.json for tests — easy to reason about."""
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_dir.name,
        "criteria": [
            {
                "criterion": c.value,
                "score": score,
                "rationale": "synthetic",
                "cited_turns": [],
            }
            for c in CriterionKind
        ],
        "overall_summary": "synthetic verdict.",
    }
    (session_dir / "verdict.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _populate(sessions_root: Path, n: int, score: int) -> None:
    for i in range(n):
        _write_verdict(sessions_root / f"sess_{i:03d}", score)


# ---- happy paths ----------------------------------------------------------

def test_certify_writes_bronze_pdf(tmp_path: Path):
    sessions_root = tmp_path / "sessions"
    _populate(sessions_root, n=5, score=3)  # normalised mean = 0.6, exactly bronze.
    out = tmp_path / "cert_bronze.pdf"

    result = runner.invoke(
        app,
        [
            "certify",
            "--agent-name",
            "Bianca Braga",
            "--output",
            str(out),
            "--sessions-dir",
            str(sessions_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.is_file()
    data = out.read_bytes()
    assert data.startswith(b"%PDF-")
    assert b"BRONZE" in data
    assert b"Bianca Braga" in data
    assert "level: BRONZE" in result.output


def test_certify_writes_gold_pdf_with_more_sessions(tmp_path: Path):
    sessions_root = tmp_path / "sessions"
    _populate(sessions_root, n=30, score=MAX_SCORE)  # mean = 1.0 → GOLD.
    out = tmp_path / "cert_gold.pdf"

    result = runner.invoke(
        app,
        [
            "certify",
            "--agent-name",
            "Guilherme Ouro",
            "--output",
            str(out),
            "--sessions-dir",
            str(sessions_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.is_file()
    data = out.read_bytes()
    assert b"OURO" in data
    assert "level: GOLD" in result.output
    # Session count and mean score surface in the CLI output too.
    assert "sessions: 30" in result.output
    assert "mean: 1.00" in result.output


# ---- not-eligible path ----------------------------------------------------

def test_certify_reports_not_eligible_with_ptbr_message(tmp_path: Path):
    """
    Four sessions with perfect scores still miss BRONZE (floor is 5).
    The error message must quote the actual counts AND the BRONZE floor.
    """
    sessions_root = tmp_path / "sessions"
    _populate(sessions_root, n=4, score=MAX_SCORE)
    out = tmp_path / "should_not_be_created.pdf"

    result = runner.invoke(
        app,
        [
            "certify",
            "--agent-name",
            "Prematuro Perez",
            "--output",
            str(out),
            "--sessions-dir",
            str(sessions_root),
        ],
    )

    assert result.exit_code == 1
    # PDF must not have been written.
    assert not out.exists()
    # pt-BR error message that names the attendant, quotes the aggregate
    # and the BRONZE floor.
    combined = result.output + (result.stderr or "")
    assert "Prematuro Perez" in combined
    assert "não é elegível" in combined
    assert "4 sessões" in combined
    # Floor mentioned.
    assert "bronze" in combined.lower()
    assert "5 sessões" in combined


# ---- defensive checks ------------------------------------------------------

def test_certify_missing_sessions_dir_reports_not_eligible(tmp_path: Path):
    """
    A non-existent --sessions-dir must yield the same friendly "not
    eligible" message (zero sessions found), not a crash.
    """
    missing = tmp_path / "nowhere"
    out = tmp_path / "cert.pdf"

    result = runner.invoke(
        app,
        [
            "certify",
            "--agent-name",
            "Fulano",
            "--output",
            str(out),
            "--sessions-dir",
            str(missing),
        ],
    )

    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "não é elegível" in combined
    assert "0 sessões" in combined


def test_certify_rejects_empty_agent_name(tmp_path: Path):
    """Empty --agent-name is an input error (exit 2)."""
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    out = tmp_path / "cert.pdf"

    result = runner.invoke(
        app,
        [
            "certify",
            "--agent-name",
            "   ",  # whitespace only
            "--output",
            str(out),
            "--sessions-dir",
            str(sessions_root),
        ],
    )

    assert result.exit_code == 2
    combined = result.output + (result.stderr or "")
    assert "--agent-name" in combined


def test_certify_help_is_wired():
    """`civis certify --help` renders the command description."""
    result = runner.invoke(app, ["certify", "--help"])
    assert result.exit_code == 0
    assert "certify" in result.output.lower()
    assert "--agent-name" in result.output
    assert "--sessions-dir" in result.output
    assert "--output" in result.output
