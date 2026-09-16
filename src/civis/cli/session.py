"""
`civis session` — run one training session end to end.

Usage examples:

    # Fresh session, interactive REPL.
    python -m civis session --scenario certificate_duplicate_confused_v1

    # Non-interactive: pipe agent turns from a file.
    python -m civis session \
        --scenario certificate_duplicate_confused_v1 \
        < agent_script.txt

    # Custom output directory.
    python -m civis session --scenario ... --output data/study_v1/

    # Resume a prior session by id (fails if the scenario file changed).
    python -m civis session --scenario ... --session-id 2026-09-15_143012

Behaviour:
    - Reads config via civis.config.store.load(); if none exists yet,
      falls back to a two-model Ollama setup (persona: qwen2.5:7b,
      judge: llama3.1:8b) and prints a notice about it.
    - Every agent line becomes one turn. Empty line or EOF closes the
      session. Also stops automatically after --max-turns.
    - On close, unless --no-judge, the judge scores the session and
      writes verdict.json alongside the transcript. The judge run also
      validates citations (B.2) and computes a contradiction report
      (B.4); both are persisted alongside the verdict. Fase C.2 adds
      honeytoken_leaks.json — a security sidecar that runs whether or
      not the judge is enabled.
"""

from datetime import UTC, datetime
from pathlib import Path

import typer

from civis.adversarial.honeytoken_detector import detect_honeytoken_leaks
from civis.cli.wiring import (
    DEFAULT_JUDGE_KEY,
    DEFAULT_PERSONA_KEY,
    build_default_config,
    build_provider_from_config,
    load_or_default_config,
)
from civis.judge.citation_validator import (
    CitationValidationReport,
    validate_verdict_citations,
)
from civis.judge.rubric import JudgeVerdict
from civis.judge.rubric_loader import (
    DEFAULT_RUBRIC_PATH,
    RubricDefinition,
    load_rubric_from_path,
)
from civis.llm.provider import LLMMessage, LLMProvider
from civis.personas.base import PersonaState
from civis.prompts.judge import JudgeParseError, build_judge_prompt, parse_judge_response
from civis.session.contradiction_detector import (
    detect_contradictions,
)
from civis.session.orchestrator import SessionOrchestrator
from civis.session.scenario import ScenarioFile, load_scenario_from_path, resolve_scenario_path
from civis.session.storage import (
    ScenarioDriftError,
    SessionMetadata,
    SessionTranscript,
    ensure_scenario_matches,
    load_metadata,
    load_transcript,
    new_session_id,
    save_contradictions_json,
    save_honeytoken_leaks_json,
    save_metadata,
    save_transcript,
    save_turn_telemetry_json,
    save_verdict_json,
    scenario_hash,
    session_dir,
    session_exists,
    touch_metadata,
)

# Default location of the scenarios directory when the user gives a bare id.
DEFAULT_SCENARIOS_DIR = Path("data/scenarios")
# Default location of the on-disk session store.
DEFAULT_OUTPUT_DIR = Path("data/sessions")
# Default cap on agent turns per session. The FSM auto-progresses to
# RESOLUTION around turn 8, so ~12 gives a small buffer for wrap-up.
DEFAULT_MAX_TURNS = 12


def session_command(
    scenario: str = typer.Option(
        ...,
        "--scenario",
        help=(
            "Scenario id (looked up under data/scenarios/) or direct "
            "path to a .yaml file."
        ),
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help=(
            "Session id to create or resume. Defaults to a fresh "
            "'YYYY-MM-DD_HHMMSS' timestamp."
        ),
    ),
    output_dir: Path = typer.Option(  # noqa: B008 - Typer requires call in default
        DEFAULT_OUTPUT_DIR,
        "--output",
        help="Directory to hold data/sessions/<id>/ (created if missing).",
    ),
    scenarios_dir: Path = typer.Option(  # noqa: B008 - Typer requires call in default
        DEFAULT_SCENARIOS_DIR,
        "--scenarios-dir",
        help="Directory searched when --scenario is a bare id.",
    ),
    rubric_path: Path = typer.Option(  # noqa: B008 - Typer requires call in default
        DEFAULT_RUBRIC_PATH,
        "--rubric",
        help="Path to the rubric YAML file the judge scores against.",
    ),
    max_turns: int = typer.Option(
        DEFAULT_MAX_TURNS,
        "--max-turns",
        help="Stop the session automatically after this many agent turns.",
    ),
    skip_judge: bool = typer.Option(
        False,
        "--no-judge",
        help="Skip the judge pass at the end; only the transcript is saved.",
    ),
) -> None:
    """Run one CIVIS training session end to end."""
    # -- resolve scenario --------------------------------------------------
    scenario_path = resolve_scenario_path(scenario, scenarios_dir=scenarios_dir)
    scenario_file, scenario_raw = load_scenario_from_path(scenario_path)

    # -- resolve config + providers ---------------------------------------
    config, config_source = load_or_default_config()
    persona_provider = build_provider_from_config(config, DEFAULT_PERSONA_KEY)
    judge_provider = (
        None if skip_judge else build_provider_from_config(config, DEFAULT_JUDGE_KEY)
    )

    # -- load rubric (required unless judge is skipped) -------------------
    rubric: RubricDefinition | None = None
    if not skip_judge:
        try:
            rubric = load_rubric_from_path(rubric_path)
        except FileNotFoundError as exc:
            typer.echo(f"[civis] rubric not found: {rubric_path} ({exc})", err=True)
            raise typer.Exit(code=2) from exc

    typer.echo(f"[civis] scenario: {scenario_file.scenario_id} ({scenario_path})")
    typer.echo(f"[civis] config source: {config_source}")
    typer.echo(f"[civis] persona provider: {persona_provider.name}")
    if judge_provider:
        typer.echo(f"[civis] judge provider:   {judge_provider.name}")
        typer.echo(f"[civis] rubric:           {rubric.rubric_id if rubric else '-'}")
    else:
        typer.echo("[civis] judge disabled (--no-judge).")

    # -- new or resume session --------------------------------------------
    session_id = session_id or new_session_id()
    if session_exists(session_id, base=output_dir):
        prior_metadata = load_metadata(session_id, base=output_dir)
        assert prior_metadata is not None
        try:
            ensure_scenario_matches(prior_metadata, current_scenario_text=scenario_raw)
        except ScenarioDriftError as exc:
            typer.echo(f"[civis] refusing to resume: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        transcript = load_transcript(session_id, base=output_dir)
        assert transcript is not None
        metadata = prior_metadata
        typer.echo(
            f"[civis] resuming session {session_id} "
            f"({len(transcript.turns)} prior turns)."
        )
    else:
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
        typer.echo(f"[civis] new session: {session_id}")

    save_metadata(metadata, base=output_dir)
    save_transcript(transcript, base=output_dir)

    # -- rebuild orchestrator state ---------------------------------------
    # If resuming, replay revealed facts from the transcript so the
    # FSM state agrees with what's already on disk.
    initial_state = _rebuild_state_from_transcript(scenario_file, transcript)

    orchestrator = SessionOrchestrator(
        scenario=scenario_file,
        persona_provider=persona_provider,
        transcript=transcript,
        state=initial_state,
    )

    typer.echo(
        f"[civis] hit Ctrl+D (Unix) / Ctrl+Z (Win) or empty line to end. "
        f"Max {max_turns} agent turns."
    )
    typer.echo("")

    # -- turn loop --------------------------------------------------------
    # Accumulate per-turn LLM telemetry so the M4 metrics panel in the
    # Streamlit UI can compute latency p95 and cost. One entry per persona
    # turn (agent turns cost no tokens). Written after each turn so a
    # crash mid-session does not lose the data collected so far.
    telemetry_rows: list[dict] = []
    agent_turns_done = 0
    while agent_turns_done < max_turns:
        try:
            line = _read_agent_line()
        except EOFError:
            break
        if not line.strip():
            break

        try:
            result = orchestrator.run_agent_turn(line)
        except Exception as exc:  # noqa: BLE001 - surface LLM errors to the user
            typer.echo(f"[civis] provider error: {exc}", err=True)
            break

        typer.echo(f"[persona] {result.persona_reply.content}")
        typer.echo("")

        # Persist after every turn so a crash mid-session doesn't lose work.
        save_transcript(orchestrator.transcript, base=output_dir)
        metadata = touch_metadata(metadata)
        save_metadata(metadata, base=output_dir)

        # Per-turn telemetry sidecar (Phase D). run_agent_turn always
        # attaches result.llm_response for a successful turn, so a missing
        # response only happens if the provider stubbed None; guard for
        # that so the CLI does not crash.
        if result.llm_response is not None:
            telemetry_rows.append({
                "turn_index": result.persona_reply.turn_index,
                "input_tokens": result.llm_response.input_tokens,
                "output_tokens": result.llm_response.output_tokens,
                "latency_ms": result.llm_response.latency_ms,
                "provider_name": result.llm_response.provider_name,
            })
            save_turn_telemetry_json(
                {"session_id": session_id, "turns": telemetry_rows},
                session_id=session_id,
                base=output_dir,
            )

        agent_turns_done += 1

    typer.echo(f"[civis] session closed after {agent_turns_done} agent turns.")

    # -- contradiction report (B.4) ---------------------------------------
    # Always produce the contradiction report — cheap, deterministic,
    # useful even when the judge is disabled.
    contradiction_report = detect_contradictions(
        turn_events=list(orchestrator.turn_events),
    )
    contradictions_path = save_contradictions_json(
        contradiction_report.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )
    typer.echo(
        f"[civis] contradictions: {contradiction_report.total} "
        f"({contradiction_report.contradictions_per_100_turns:.2f} per 100 turns) "
        f"-> {contradictions_path}"
    )

    # -- honeytoken leak report (C.2) -------------------------------------
    # Also always produced. Zero honeytokens in the scenario ⇒ report has
    # total=0 and no leaks; the file exists for pipeline consistency.
    honeytoken_report = detect_honeytoken_leaks(
        transcript=orchestrator.transcript,
        scenario=scenario_file,
    )
    honeytokens_path = save_honeytoken_leaks_json(
        honeytoken_report.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )
    typer.echo(
        f"[civis] honeytoken leaks: {honeytoken_report.total} "
        f"-> {honeytokens_path}"
    )

    # -- judge pass -------------------------------------------------------
    if judge_provider is None:
        typer.echo(f"[civis] transcript at {output_dir / session_id / 'transcript.json'}")
        return

    if not orchestrator.transcript.turns:
        typer.echo("[civis] transcript is empty, skipping judge pass.")
        return

    typer.echo("[civis] running judge pass ...")
    verdict, citation_report = run_judge_with_validation(
        session_id=session_id,
        scenario=scenario_file,
        transcript=orchestrator.transcript,
        judge_provider=judge_provider,
        rubric=rubric,
    )
    verdict_path = save_verdict_json(
        verdict.model_dump(mode="json"),
        session_id=session_id,
        base=output_dir,
    )
    typer.echo(f"[civis] verdict written to {verdict_path}")
    if not citation_report.ok:
        # Retry already happened inside run_judge_with_validation; if we
        # got here with issues remaining, surface them so the human
        # reviewer knows some quotes may be fabricated.
        typer.echo(
            f"[civis] warning: {len(citation_report.issues)} citation issue(s) remain "
            f"after retry — inspect verdict.json.",
            err=True,
        )
        _save_citation_issues(citation_report, session_id, output_dir)


# ---- helpers ---------------------------------------------------------------

def run_judge_with_validation(
    session_id: str,
    scenario: ScenarioFile,
    transcript: SessionTranscript,
    judge_provider: LLMProvider,
    rubric: RubricDefinition | None,
) -> tuple[JudgeVerdict, CitationValidationReport]:
    """
    Run the judge LLM, parse its response, and validate every citation
    against the transcript. If any citation fails validation, retry once
    with a stricter prompt that caps the citation range and warns against
    paraphrasing. Returns (verdict, report_from_final_attempt).

    Exposed as a top-level helper so the E2E test in B.3 can drive it
    without instantiating the Typer command.
    """
    turn_pairs = [(t.speaker, t.content) for t in transcript.turns]

    verdict = _call_judge_and_parse(
        session_id=session_id,
        scenario=scenario,
        turn_pairs=turn_pairs,
        judge_provider=judge_provider,
        rubric=rubric,
        max_turn_index=None,
    )
    report = validate_verdict_citations(verdict, turn_pairs)
    if report.ok:
        return verdict, report

    # Retry once with an explicit citation cap. B.2 acceptance: after one
    # retry we accept whatever came back and let the caller decide how to
    # surface residual issues.
    verdict = _call_judge_and_parse(
        session_id=session_id,
        scenario=scenario,
        turn_pairs=turn_pairs,
        judge_provider=judge_provider,
        rubric=rubric,
        max_turn_index=max(len(turn_pairs) - 1, 0),
    )
    report = validate_verdict_citations(verdict, turn_pairs)
    return verdict, report


def _call_judge_and_parse(
    session_id: str,
    scenario: ScenarioFile,
    turn_pairs: list[tuple[str, str]],
    judge_provider: LLMProvider,
    rubric: RubricDefinition | None,
    max_turn_index: int | None,
) -> JudgeVerdict:
    """Assemble the judge prompt, call the provider, parse the response."""
    system_prompt, user_prompt = build_judge_prompt(
        session_id=session_id,
        scenario_title=scenario.title,
        scenario_goal=scenario.persona.goal,
        expected_agent_actions=scenario.expected_agent_actions,
        transcript=turn_pairs,
        rubric=rubric,
        max_turn_index=max_turn_index,
    )
    response = judge_provider.complete([
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_prompt),
    ])
    try:
        return parse_judge_response(response.content, session_id=session_id)
    except JudgeParseError as exc:
        # Save the raw output so the user can inspect what went wrong.
        typer.echo(f"[civis] judge parse failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc


def _save_citation_issues(
    report: CitationValidationReport,
    session_id: str,
    output_dir: Path,
) -> Path:
    """
    Persist unresolved citation issues so the human reviewer can inspect
    them without re-running the parser. Written next to verdict.json.
    """
    target = session_dir(output_dir, session_id) / "citation_issues.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    target.write_text(
        _json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def _read_agent_line() -> str:
    """
    Read one line from stdin, showing a small prompt when we're on a TTY.
    Raises EOFError when stdin is closed (Ctrl+D / Ctrl+Z / end of pipe).
    """
    return input("[agent] ")


def _rebuild_state_from_transcript(
    scenario,
    transcript: SessionTranscript,
) -> PersonaState:
    """
    Build a PersonaState consistent with what's already on disk. We
    replay each persona reply through the fact-detection logic so
    revealed_fact_keys matches the reality of the transcript.

    turn_count is set to the number of AGENT turns already recorded,
    so the next advance_turn call increments to the correct value.
    """
    from civis.session.orchestrator import SessionOrchestrator as _Orch

    state = PersonaState(
        profile=scenario.persona,
        emotion=scenario.persona.initial_emotion,
    )

    if not transcript.turns:
        return state

    # Reuse the orchestrator's revealed-facts detector so behaviour
    # stays identical between a fresh session and a resumed one. We
    # create a throwaway orchestrator, bind the transcript, and only
    # call the private helper — no provider calls happen here.
    tmp = _Orch(
        scenario=scenario,
        persona_provider=None,  # type: ignore[arg-type]
        transcript=transcript,
        state=state,
    )
    # Walk both persona replies (to reveal facts) and agent turns (to
    # advance the FSM). Order in the transcript matches the live loop.
    from civis.fsm.engine import advance_turn as _adv

    for turn in transcript.turns:
        if turn.speaker == "agent":
            tmp.state = _adv(tmp.state)
        else:
            tmp._absorb_revealed_facts(turn.content, last_agent_message=None)

    return tmp.state


# Re-export so tests can build a minimal config without duplicating keys.
__all__ = [
    "DEFAULT_MAX_TURNS",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_SCENARIOS_DIR",
    "build_default_config",
    "run_judge_with_validation",
    "session_command",
]
