"""
`civis certify` — issue a PDF certificate for an attendant.

Reads verdict.json files under `--sessions-dir` (default `data/sessions/`),
runs the aggregation from civis.certification.eligibility, and — if the
aggregate meets at least the BRONZE threshold — renders the PDF via
civis.certification.pdf_generator.

Exit codes:
    0 — certificate written.
    1 — attendant not eligible (fewer than 5 qualifying sessions or the
        mean is below 0.60). The error message quotes both the current
        aggregate and the BRONZE floor so the user can act on it.
    2 — invalid CLI input (empty --agent-name, missing --sessions-dir).

Usage:
    python -m civis certify --agent-name "Fulana de Tal" --output cert.pdf
    python -m civis certify --agent-name "..." --sessions-dir data/study_v2
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import typer

from civis.certification.eligibility import (
    compute_eligibility,
    discover_session_dirs,
    level_requirements,
)
from civis.certification.pdf_generator import (
    CertificateContext,
    generate_certificate_number,
    render_certificate_pdf,
)

# Default location of the on-disk session store. Mirrors the same constant
# in civis.cli.session so `civis session` and `civis certify` agree by
# default without any argument.
DEFAULT_SESSIONS_DIR = Path("data/sessions")


def certify_command(
    agent_name: str = typer.Option(
        ...,
        "--agent-name",
        help="Full name of the attendant printed on the certificate.",
    ),
    output: Path | None = typer.Option(  # noqa: B008 - Typer requires call in default
        None,
        "--output",
        help=(
            "Where to write the PDF. Defaults to "
            "cert_<YYYY-MM-DD_HHMMSS>.pdf in the current directory."
        ),
    ),
    sessions_dir: Path = typer.Option(  # noqa: B008 - Typer requires call in default
        DEFAULT_SESSIONS_DIR,
        "--sessions-dir",
        help="Directory containing one subdirectory per session.",
    ),
) -> None:
    """
    Issue a proficiency certificate PDF based on the attendant's recorded
    sessions.
    """
    # -- validate input ---------------------------------------------------
    name_clean = agent_name.strip()
    if not name_clean:
        typer.echo(
            "[civis] --agent-name não pode ficar vazio.",
            err=True,
        )
        raise typer.Exit(code=2)

    # -- aggregate --------------------------------------------------------
    session_dirs = discover_session_dirs(sessions_dir)
    eligibility = compute_eligibility(session_dirs)

    if eligibility.level is None:
        _print_not_eligible_message(
            name=name_clean,
            n_sessions=eligibility.n_sessions,
            mean_score=eligibility.mean_score,
        )
        raise typer.Exit(code=1)

    # -- render + write ---------------------------------------------------
    output_path = output or _default_output_path()
    context = CertificateContext(
        agent_name=name_clean,
        eligibility=eligibility,
        issued_on=date.today(),
        certificate_number=generate_certificate_number(),
        # kappa is a study-level statistic (M1 aggregation), not something we
        # compute per attendant. Left None → the PDF prints the fallback line.
        inter_model_agreement=None,
    )
    pdf_bytes = render_certificate_pdf(context)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)

    typer.echo(
        f"[civis] certificate written to {output_path} "
        f"(level: {eligibility.level.value.upper()}, "
        f"sessions: {eligibility.n_sessions}, "
        f"mean: {eligibility.mean_score:.2f})"
    )


# ---- helpers ---------------------------------------------------------------

def _default_output_path() -> Path:
    """
    Timestamp the default filename so consecutive runs don't overwrite each
    other. `datetime.now(UTC)` keeps the format identical to what
    session_storage.new_session_id() uses elsewhere in the codebase.
    """
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    return Path(f"cert_{stamp}.pdf")


def _print_not_eligible_message(
    name: str,
    n_sessions: int,
    mean_score: float,
) -> None:
    """
    Explain WHY the attendant is not eligible. Quotes the actual aggregate
    numbers and the BRONZE floor so the user can plan the next step —
    "run more sessions" vs "improve mean score" is a different fix.
    """
    # BRONZE is the lowest tier by construction: level_requirements() is
    # ordered highest-to-lowest, so the last entry is the floor.
    bronze_level, bronze_min_sessions, bronze_min_score = level_requirements()[-1]

    typer.echo(
        f"[civis] {name} não é elegível: apenas {n_sessions} "
        f"sessões com nota {mean_score:.2f} "
        f"(mínimo {bronze_level.value}: {bronze_min_sessions} sessões, "
        f">={bronze_min_score:.2f}).",
        err=True,
    )
