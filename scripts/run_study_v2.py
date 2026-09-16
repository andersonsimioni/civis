"""
Automate the M1-A hybrid validation study (Phase E execution).

Pipeline the coordinator runs to produce the inter-model kappa reported
in slide 7 of the investor pitch. Four subcommands, run in order:

    1. generate  — produce N training sessions driven by a synthetic
                   LLM agent so we control diversity and reproducibility.
                   Uses the DEFAULT judge (Ollama) to score each session.
    2. rejudge   — re-run the judge pass over each existing transcript
                   using a SECOND provider (typically Claude via a
                   dedicated config.toml). Writes verdict_<suffix>.json
                   next to the original verdict.json.
    3. export-csvs — walk the sessions dir and materialize two rater
                   CSVs (one per judge) in the format compute_kappa.py
                   expects.
    4. analyze   — invoke compute_kappa.py on the two CSVs and drop the
                   final Markdown report in reports/.

Usage:

    # Full pipeline with Claude as the second judge (needs ANTHROPIC_API_KEY):
    python scripts/run_study_v2.py generate --n-sessions 30
    python scripts/run_study_v2.py rejudge \
        --judge-config data/configs/config.claude-judge.example.toml
    python scripts/run_study_v2.py export-csvs
    python scripts/run_study_v2.py analyze

    # Dry run without hitting any real LLM (validates plumbing only):
    python scripts/run_study_v2.py generate --n-sessions 3 --dry-run

The synthetic agent is documented in data/study/agent_personalities.md.
Three personalities are drawn round-robin: strict, lax, neutral. Each
generates a distinctly different transcript, which is what gives the
two judges something to disagree on.
"""

from __future__ import annotations

import csv
import json
import random
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer

# Import via sys.path append — the script lives outside the src package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# E402 (imports after sys.path munging) is intentional here — the script
# is meant to run from a clone without `pip install -e`, so we set up the
# import path first, then import.
from civis.adversarial.honeytoken_detector import detect_honeytoken_leaks  # noqa: E402
from civis.cli.session import run_judge_with_validation  # noqa: E402
from civis.cli.wiring import (  # noqa: E402
    DEFAULT_JUDGE_KEY,
    DEFAULT_PERSONA_KEY,
    build_provider_from_config,
    load_or_default_config,
)
from civis.config.store import load as load_config_from_path  # noqa: E402
from civis.judge.rubric_loader import DEFAULT_RUBRIC_PATH, load_rubric_from_path  # noqa: E402
from civis.llm.provider import LLMMessage, LLMProvider  # noqa: E402
from civis.personas.base import PersonaState  # noqa: E402
from civis.session.contradiction_detector import detect_contradictions  # noqa: E402
from civis.session.orchestrator import SessionOrchestrator  # noqa: E402
from civis.session.scenario import (  # noqa: E402
    load_scenario_from_path,
    resolve_scenario_path,
)
from civis.session.storage import (  # noqa: E402
    SessionMetadata,
    SessionTranscript,
    save_contradictions_json,
    save_honeytoken_leaks_json,
    save_metadata,
    save_transcript,
    save_verdict_json,
    scenario_hash,
    session_dir,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Three shipping scenarios rotated round-robin across sessions so the study
# balances coverage across persona kinds (confused / aggressive / fraudster).
DEFAULT_SCENARIOS: tuple[str, ...] = (
    "certificate_duplicate_confused_v1",
    "rg_urgent_aggressive_v1",
    "certificate_thirdparty_fraudster_v1",
)

# Three synthetic-agent personalities. See data/study/agent_personalities.md
# for the rationale — the goal is diverse-enough transcripts that the two
# judges have real material to (dis)agree on.
AGENT_PERSONALITY_KEYS: tuple[str, ...] = ("strict", "lax", "neutral")

AGENT_PERSONALITY_PROMPTS: dict[str, str] = {
    "strict": (
        "Você é um atendente de balcão de cartório de registro civil. "
        "Você é rigoroso: sempre verifica identidade primeiro (nome completo, "
        "documento com foto, dado de fluência), sempre segue o protocolo passo "
        "a passo, nunca abre exceção. Você é formal mas cortês."
    ),
    "lax": (
        "Você é um atendente de balcão de cartório de registro civil. "
        "Você é apressado e informal: quer resolver rápido, às vezes pula "
        "passos de verificação se a pessoa parece de boa-fé, usa linguagem "
        "coloquial. Você tenta ajudar mas nem sempre segue à risca."
    ),
    "neutral": (
        "Você é um atendente de balcão de cartório de registro civil. "
        "Você é competente e balanceado: verifica o necessário sem exagero, "
        "explica o procedimento com clareza, mantém tom profissional. Você "
        "segue o protocolo mas sem ser burocrático."
    ),
}

# Fixed number of agent turns per session. Matches the FSM auto-progression
# window (RESOLUTION at ~turn 8) plus a small buffer for closing pleasantries.
TURNS_PER_SESSION = 8

# Default destinations (all relative to the repo root at runtime).
DEFAULT_SESSIONS_DIR = Path("data/sessions/study_v2")
DEFAULT_STUDY_DIR = Path("data/study")
DEFAULT_REPORT_PATH = Path("reports/study_v2_report.md")

# CSV column layout — must match data/study/evaluator_template.csv exactly.
CSV_COLUMNS = ("session_id", "criterion", "score", "qualitative_note", "evaluated_at")


app = typer.Typer(help="Automate the M1-A hybrid validation study.")


# ---------------------------------------------------------------------------
# Synthetic agent
# ---------------------------------------------------------------------------

@dataclass
class SyntheticAgent:
    """
    LLM-backed synthetic training agent. Produces the next agent line
    given the transcript so far. Personality is fixed per session — that's
    what makes the transcripts distinguishable.
    """

    personality: str
    provider: LLMProvider

    def next_line(
        self,
        scenario_title: str,
        transcript_so_far: list[tuple[str, str]],
        turn_number: int,
    ) -> str:
        """Ask the LLM for the next agent utterance."""
        system_prompt = (
            f"{AGENT_PERSONALITY_PROMPTS[self.personality]}\n\n"
            "Você está atendendo uma pessoa no balcão. Reflita a personalidade "
            "acima em CADA fala. Responda apenas com o texto que você diria "
            "em voz alta, sem prefixos, aspas ou meta-comentário."
        )
        rendered_transcript = _render_transcript_for_prompt(transcript_so_far)
        user_prompt = (
            f"Cenário: {scenario_title}\n\n"
            f"Conversa até agora:\n{rendered_transcript}\n\n"
            f"Sua próxima fala (turno {turn_number}):"
        )
        response = self.provider.complete([
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ])
        # Strip whitespace and any accidental role prefix — some smaller
        # models like to prepend "Atendente:" even when told not to.
        return _clean_agent_reply(response.content)


def _render_transcript_for_prompt(turns: list[tuple[str, str]]) -> str:
    """Human-readable rendering of transcript for the agent's own context."""
    if not turns:
        return "(conversa ainda não começou — você fala primeiro)"
    lines = []
    for speaker, content in turns:
        label = "Você" if speaker == "agent" else "Pessoa"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def _clean_agent_reply(raw: str) -> str:
    """Strip prefix contamination that small models sometimes add."""
    text = raw.strip()
    for prefix in ("Você:", "Atendente:", "Servidor:", "Agent:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text


# ---------------------------------------------------------------------------
# Session generation
# ---------------------------------------------------------------------------

def _new_session_id(index: int, personality: str, scenario_id: str) -> str:
    """
    Deterministic per-session id. Encodes index + personality + scenario
    so a reviewer can navigate to a specific transcript by name.
    """
    scenario_short = scenario_id.split("_")[0]
    return f"study_v2_{index:03d}_{personality}_{scenario_short}"


def _pick_scenario(index: int, scenarios: tuple[str, ...]) -> str:
    """Round-robin across scenarios so kinds stay balanced."""
    return scenarios[index % len(scenarios)]


def _pick_personality(index: int) -> str:
    """Round-robin across personalities."""
    return AGENT_PERSONALITY_KEYS[index % len(AGENT_PERSONALITY_KEYS)]


def _run_one_session(
    session_index: int,
    scenario_id: str,
    personality: str,
    persona_provider: LLMProvider,
    judge_provider: LLMProvider | None,
    output_dir: Path,
) -> Path:
    """
    Run one full session (synthetic agent + persona + judge) end to end.
    Returns the session directory path.
    """
    scenario_path = resolve_scenario_path(scenario_id, scenarios_dir=Path("data/scenarios"))
    scenario_file, scenario_raw = load_scenario_from_path(scenario_path)
    session_id = _new_session_id(session_index, personality, scenario_id)

    transcript = SessionTranscript(session_id=session_id)
    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat()
    metadata = SessionMetadata(
        session_id=session_id,
        scenario_id=scenario_file.scenario_id,
        scenario_hash=scenario_hash(scenario_raw),
        persona_provider_name=persona_provider.name,
        judge_provider_name=judge_provider.name if judge_provider else None,
        created_at=now_iso,
        last_updated_at=now_iso,
    )
    save_metadata(metadata, base=output_dir)
    save_transcript(transcript, base=output_dir)

    state = PersonaState(
        profile=scenario_file.persona,
        emotion=scenario_file.persona.initial_emotion,
    )
    orchestrator = SessionOrchestrator(
        scenario=scenario_file,
        persona_provider=persona_provider,
        transcript=transcript,
        state=state,
    )

    synthetic_agent = SyntheticAgent(
        personality=personality,
        provider=persona_provider,
    )

    typer.echo(f"[study_v2] running {session_id} ({personality} × {scenario_id})...")

    for turn_number in range(1, TURNS_PER_SESSION + 1):
        transcript_pairs = [(t.speaker, t.content) for t in orchestrator.transcript.turns]
        agent_line = synthetic_agent.next_line(
            scenario_title=scenario_file.title,
            transcript_so_far=transcript_pairs,
            turn_number=turn_number,
        )
        if not agent_line:
            # A blank reply from the model — bail so we don't record noise.
            typer.echo(
                f"[study_v2] {session_id}: empty agent line at turn "
                f"{turn_number}, stopping."
            )
            break
        try:
            orchestrator.run_agent_turn(agent_line)
        except Exception as exc:  # noqa: BLE001 - surface LLM errors to caller
            typer.echo(
                f"[study_v2] {session_id}: provider error at turn {turn_number}: {exc}",
                err=True,
            )
            break
        save_transcript(orchestrator.transcript, base=output_dir)

    # Contradiction + honeytoken sidecars mirror what the CLI writes so the
    # analytics UI treats these sessions the same as human-driven ones.
    contradiction_report = detect_contradictions(turn_events=list(orchestrator.turn_events))
    save_contradictions_json(
        contradiction_report.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )
    honeytoken_report = detect_honeytoken_leaks(
        transcript=orchestrator.transcript,
        scenario=scenario_file,
    )
    save_honeytoken_leaks_json(
        honeytoken_report.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )

    # Judge pass with the FIRST (default) judge.
    if judge_provider is not None and orchestrator.transcript.turns:
        rubric = load_rubric_from_path(DEFAULT_RUBRIC_PATH)
        verdict, _report = run_judge_with_validation(
            session_id=session_id,
            scenario=scenario_file,
            transcript=orchestrator.transcript,
            judge_provider=judge_provider,
            rubric=rubric,
        )
        save_verdict_json(
            verdict.model_dump(mode="json"),
            session_id=session_id,
            base=output_dir,
        )

    return session_dir(output_dir, session_id)


# ---------------------------------------------------------------------------
# Subcommand: generate
# ---------------------------------------------------------------------------

@app.command()
def generate(
    n_sessions: int = typer.Option(30, "--n-sessions", help="How many sessions to run."),
    output_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_SESSIONS_DIR,
        "--output-dir",
        help="Where to store the sessions.",
    ),
    seed: int = typer.Option(42, "--seed", help="Seed the rotation for reproducibility."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Skip LLM calls; only prove the pipeline wiring works.",
    ),
) -> None:
    """
    Generate N training sessions driven by synthetic LLM agents, scored
    by the DEFAULT judge (from your active config.toml or the Ollama-dual
    fallback). Sessions land in --output-dir with the full sidecar suite:
    transcript.json, metadata.json, contradictions.json,
    honeytoken_leaks.json, verdict.json.
    """
    if dry_run:
        typer.echo("[study_v2] dry-run: skipping LLM calls.")
        typer.echo(
            f"[study_v2] would generate {n_sessions} sessions "
            f"({TURNS_PER_SESSION} turns each), rotating scenarios "
            f"{DEFAULT_SCENARIOS} and personalities {AGENT_PERSONALITY_KEYS}."
        )
        return

    config, source = load_or_default_config()
    typer.echo(f"[study_v2] config source: {source}")
    persona_provider = build_provider_from_config(config, DEFAULT_PERSONA_KEY)
    judge_provider = build_provider_from_config(config, DEFAULT_JUDGE_KEY)
    typer.echo(f"[study_v2] persona provider: {persona_provider.name}")
    typer.echo(f"[study_v2] judge provider:   {judge_provider.name}")

    # Seed only controls scenario/personality shuffle if we want randomization
    # beyond round-robin later; kept explicit for reproducibility of any
    # future non-deterministic choice.
    random.seed(seed)

    for index in range(n_sessions):
        scenario_id = _pick_scenario(index, DEFAULT_SCENARIOS)
        personality = _pick_personality(index)
        _run_one_session(
            session_index=index,
            scenario_id=scenario_id,
            personality=personality,
            persona_provider=persona_provider,
            judge_provider=judge_provider,
            output_dir=output_dir,
        )

    typer.echo(f"[study_v2] generated {n_sessions} sessions under {output_dir}")


# ---------------------------------------------------------------------------
# Subcommand: rejudge
# ---------------------------------------------------------------------------

@app.command()
def rejudge(
    sessions_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_SESSIONS_DIR,
        "--sessions-dir",
        help="Directory holding the sessions to re-judge.",
    ),
    judge_config: Path = typer.Option(  # noqa: B008
        ...,
        "--judge-config",
        help="Path to a config.toml whose 'judge' role points at the SECOND provider.",
    ),
    output_suffix: str = typer.Option(
        "_claude",
        "--output-suffix",
        help="Suffix appended to verdict.json (e.g. verdict_claude.json).",
    ),
) -> None:
    """
    Re-run the judge pass over each session in --sessions-dir using a
    DIFFERENT judge provider (typically Claude). Writes the new verdicts
    as verdict<suffix>.json next to the original verdict.json so the
    original is preserved for comparison.

    The --judge-config file must define a 'judge' role and any API-key
    env vars referenced by that role must be set in your environment.
    """
    if not sessions_dir.exists():
        typer.echo(f"[study_v2] sessions dir not found: {sessions_dir}", err=True)
        raise typer.Exit(code=2)

    config = load_config_from_path(judge_config)
    if config is None:
        typer.echo(f"[study_v2] judge config not found: {judge_config}", err=True)
        raise typer.Exit(code=2)
    judge_provider = build_provider_from_config(config, DEFAULT_JUDGE_KEY)
    typer.echo(f"[study_v2] second judge provider: {judge_provider.name}")

    rubric = load_rubric_from_path(DEFAULT_RUBRIC_PATH)

    for session_path in sorted(sessions_dir.iterdir()):
        if not session_path.is_dir():
            continue
        transcript_path = session_path / "transcript.json"
        metadata_path = session_path / "metadata.json"
        if not transcript_path.exists() or not metadata_path.exists():
            continue

        metadata_raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        transcript_raw = json.loads(transcript_path.read_text(encoding="utf-8"))
        session_id = metadata_raw["session_id"]
        scenario_id = metadata_raw["scenario_id"]

        # Re-hydrate scenario + transcript enough to run the judge.
        scenario_path = resolve_scenario_path(scenario_id, scenarios_dir=Path("data/scenarios"))
        scenario_file, _raw = load_scenario_from_path(scenario_path)
        transcript = SessionTranscript.model_validate(transcript_raw)
        if not transcript.turns:
            typer.echo(f"[study_v2] {session_id}: empty transcript, skipping.")
            continue

        typer.echo(f"[study_v2] re-judging {session_id}...")
        try:
            verdict, _report = run_judge_with_validation(
                session_id=session_id,
                scenario=scenario_file,
                transcript=transcript,
                judge_provider=judge_provider,
                rubric=rubric,
            )
        except Exception as exc:  # noqa: BLE001 - surface LLM errors to caller
            typer.echo(f"[study_v2] {session_id}: judge error: {exc}", err=True)
            continue

        # Write next to the original verdict.json so downstream code can
        # find both by convention.
        target = session_path / f"verdict{output_suffix}.json"
        target.write_text(
            json.dumps(verdict.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        typer.echo(f"[study_v2] wrote {target}")


# ---------------------------------------------------------------------------
# Subcommand: export-csvs
# ---------------------------------------------------------------------------

def _load_verdict_scores(verdict_path: Path) -> list[dict]:
    """Extract (criterion, score) rows from a single verdict.json."""
    if not verdict_path.exists():
        return []
    raw = json.loads(verdict_path.read_text(encoding="utf-8"))
    return [
        {
            "session_id": raw["session_id"],
            "criterion": cv["criterion"],
            "score": cv["score"],
            "qualitative_note": _first_line(cv.get("rationale") or ""),
            "evaluated_at": "",  # left blank — verdicts have no timestamp
        }
        for cv in raw.get("criteria", [])
    ]


def _first_line(text: str) -> str:
    """First non-empty line of `text`, trimmed."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _write_rater_csv(rows: list[dict], target: Path) -> None:
    """Write rows in the exact schema of evaluator_template.csv."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


@app.command("export-csvs")
def export_csvs(
    sessions_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_SESSIONS_DIR,
        "--sessions-dir",
        help="Directory holding the sessions.",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_STUDY_DIR,
        "--output-dir",
        help="Where to write the two rater CSVs.",
    ),
    second_judge_suffix: str = typer.Option(
        "_claude",
        "--second-judge-suffix",
        help="Suffix of the second judge's verdict files (e.g. verdict_claude.json).",
    ),
) -> None:
    """
    Consolidate each session's verdicts into two rater CSVs in the exact
    format compute_kappa.py accepts. Writes:

        <output-dir>/judge_ollama_v2.csv   (from verdict.json)
        <output-dir>/judge_claude_v2.csv   (from verdict<suffix>.json)
    """
    ollama_rows: list[dict] = []
    claude_rows: list[dict] = []

    for session_path in sorted(sessions_dir.iterdir()):
        if not session_path.is_dir():
            continue
        ollama_rows.extend(_load_verdict_scores(session_path / "verdict.json"))
        claude_rows.extend(
            _load_verdict_scores(session_path / f"verdict{second_judge_suffix}.json")
        )

    ollama_csv = output_dir / "judge_ollama_v2.csv"
    claude_csv = output_dir / f"judge{second_judge_suffix}_v2.csv"
    _write_rater_csv(ollama_rows, ollama_csv)
    _write_rater_csv(claude_rows, claude_csv)

    typer.echo(f"[study_v2] wrote {ollama_csv} ({len(ollama_rows)} rows)")
    typer.echo(f"[study_v2] wrote {claude_csv} ({len(claude_rows)} rows)")


# ---------------------------------------------------------------------------
# Subcommand: analyze
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    ollama_csv: Path = typer.Option(  # noqa: B008
        DEFAULT_STUDY_DIR / "judge_ollama_v2.csv",
        "--ollama-csv",
    ),
    claude_csv: Path = typer.Option(  # noqa: B008
        DEFAULT_STUDY_DIR / "judge_claude_v2.csv",
        "--claude-csv",
    ),
    report_path: Path = typer.Option(  # noqa: B008
        DEFAULT_REPORT_PATH,
        "--report",
    ),
) -> None:
    """
    Invoke compute_kappa.py on the two rater CSVs and drop the final
    Markdown report where the pitch deck can pick it up.

    Passes both CSVs into --evaluator-1 and --evaluator-2 so the script
    computes all three pairs (judge-vs-judge is the M1-A metric; the
    'sanity' pair is a redundant tautology on this dataset but keeps
    the reporting format identical to compute_kappa's shape).
    """
    kappa_script = _REPO_ROOT / "scripts" / "compute_kappa.py"
    if not kappa_script.exists():
        typer.echo(f"[study_v2] compute_kappa.py not found at {kappa_script}", err=True)
        raise typer.Exit(code=2)

    cmd = [
        sys.executable,
        str(kappa_script),
        "--judge",
        str(ollama_csv),
        "--evaluator-1",
        str(claude_csv),
        "--evaluator-2",
        str(claude_csv),
        "--report",
        str(report_path),
    ]
    typer.echo(f"[study_v2] {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    raise typer.Exit(code=result.returncode)


if __name__ == "__main__":
    app()
