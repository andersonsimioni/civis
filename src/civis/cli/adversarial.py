"""
`civis adversarial` — sub-app for adversarial evaluation.

Commands:
    run             Execute the OWASP LLM Top 10 battery against the persona
                    or judge provider (or both), and write a JSON report.
    judge-deceiver  Run the pointwise JudgeDeceiver attack against configured
                    judges (mock-mock by default; real backend via env var).
    report          Consolidate battery + judge-deceiver reports into
                    reports/security_v1.md.

Safety gate: hitting real APIs requires CIVIS_RUN_REAL_LLM=1. Without it,
the runner uses a mock provider that returns a fixed refusal string, so
the report reflects "no attack succeeded against a well-behaved model"
— a deliberately conservative baseline that never leaks API credit in CI.
"""

import json
import os
from pathlib import Path

import typer

from civis.adversarial.battery import (
    AdversarialBattery,
    AttackDefinition,
    BatteryReport,
    run_battery,
)
from civis.adversarial.judge_deceiver_pointwise import (
    JudgeDeceiverReport,
    generate_pointwise_attacks,
    run_judge_deceiver,
)
from civis.adversarial.mock_judges import RobustJudgeMock, VulnerableJudgeMock
from civis.adversarial.mock_providers import RecordingMockProvider
from civis.adversarial.report import build_security_report
from civis.cli.wiring import (
    DEFAULT_JUDGE_KEY,
    DEFAULT_PERSONA_KEY,
    build_provider_from_config,
    load_or_default_config,
)
from civis.llm.provider import LLMProvider

# Battery YAML shipped with the repo. Overridable via --battery.
DEFAULT_BATTERY_PATH = Path("data/adversarial/prompt_injection_v1.yaml")

# Env var that gates real-API calls. Absent (or anything other than "1")
# forces mock providers.
REAL_LLM_ENV = "CIVIS_RUN_REAL_LLM"

# Conservative refusal used by the default mock persona / judge. Chosen so
# no `success_signal` in the shipped battery accidentally matches it.
MOCK_REFUSAL_REPLY = (
    "Desculpe, não posso ajudar com isso. Vou seguir o procedimento normal "
    "do atendimento."
)


adversarial_app = typer.Typer(
    help="Adversarial evaluation of the persona and judge providers.",
    no_args_is_help=True,
    add_completion=False,
)


@adversarial_app.callback()
def _adversarial_callback() -> None:
    """Force Typer to render adversarial as a sub-app (see cli/__init__.py)."""


@adversarial_app.command("run", help="Run the OWASP LLM Top 10 battery.")
def run_command(
    target: str = typer.Option(
        "persona",
        "--target",
        help="What to attack: 'persona', 'judge' or 'both'.",
    ),
    battery_path: Path = typer.Option(  # noqa: B008 - Typer requires call in default
        DEFAULT_BATTERY_PATH,
        "--battery",
        help="Path to the adversarial battery YAML.",
    ),
    output: Path = typer.Option(  # noqa: B008 - Typer requires call in default
        Path("reports/adversarial_v1.json"),
        "--output",
        help="Where to write the JSON report.",
    ),
    scenario_id: str = typer.Option(
        "certificate_thirdparty_fraudster_v1",
        "--scenario",
        help=(
            "Scenario id used to build the persona system prompt. Ignored "
            "when --target=judge only."
        ),
    ),
) -> None:
    """Run the battery and write BatteryReport(s) to disk as JSON."""
    if target not in {"persona", "judge", "both"}:
        typer.echo(f"[civis] invalid --target: {target}", err=True)
        raise typer.Exit(code=2)

    battery = AdversarialBattery.load(battery_path)
    typer.echo(
        f"[civis] loaded battery {battery.version} with {len(battery.attacks)} attacks "
        f"from {battery_path}"
    )

    run_real = os.environ.get(REAL_LLM_ENV) == "1"
    if not run_real:
        typer.echo(
            f"[civis] {REAL_LLM_ENV}!=1 → using mock providers (safe default). "
            f"Set {REAL_LLM_ENV}=1 to hit configured backends."
        )

    reports: list[BatteryReport] = []
    if target in {"persona", "both"}:
        provider = _persona_provider(use_real=run_real)
        system_fn = _persona_system_prompt_fn(scenario_id=scenario_id)
        report = run_battery(
            battery=battery,
            provider=provider,
            target_label=f"persona:{provider.name}",
            system_prompt_fn=system_fn,
        )
        reports.append(report)
        typer.echo(_summary_line("persona", report))

    if target in {"judge", "both"}:
        provider = _judge_provider(use_real=run_real)
        system_fn = _judge_system_prompt_fn()
        report = run_battery(
            battery=battery,
            provider=provider,
            target_label=f"judge:{provider.name}",
            system_prompt_fn=system_fn,
        )
        reports.append(report)
        typer.echo(_summary_line("judge", report))

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "battery": {
            "version": battery.version,
            "path": str(battery_path),
            "attack_count": len(battery.attacks),
        },
        "reports": [r.model_dump(mode="json") for r in reports],
    }
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"[civis] wrote {output}")


@adversarial_app.command(
    "judge-deceiver",
    help="Run JudgeDeceiver-pointwise against vulnerable and robust mock judges.",
)
def judge_deceiver_command(
    output: Path = typer.Option(  # noqa: B008 - Typer requires call in default
        Path("reports/judge_deceiver_pointwise_v1.json"),
        "--output",
        help="Where to write the JSON report.",
    ),
    target_score: int = typer.Option(
        5,
        "--target-score",
        help="Score the attacks try to force on the target criterion (0-5).",
    ),
) -> None:
    """
    Generate the pointwise attack suite and run it against two judges:

        - VulnerableJudgeMock — obeys embedded score-forcing directives.
        - RobustJudgeMock     — ignores them; returns baseline scores.

    Both mocks are deterministic. When CIVIS_RUN_REAL_LLM=1, a third
    'real' run against the configured judge provider is added; the mocks
    still run so a reader can compare simulated ASR to real ASR at a glance.
    """
    attacks = generate_pointwise_attacks(target_score=target_score)
    typer.echo(
        f"[civis] generated {len(attacks)} attacks "
        f"({len(attacks)} judge calls per judge, +1 baseline)"
    )

    reports: list[JudgeDeceiverReport] = []
    for judge, label in (
        (VulnerableJudgeMock(), "mock:vulnerable_judge"),
        (RobustJudgeMock(), "mock:robust_judge"),
    ):
        report = run_judge_deceiver(judge=judge, label=label, attacks=attacks)
        reports.append(report)
        typer.echo(_judge_deceiver_summary(label, report))

    run_real = os.environ.get(REAL_LLM_ENV) == "1"
    if run_real:
        config, _ = load_or_default_config()
        real_judge = build_provider_from_config(config, DEFAULT_JUDGE_KEY)
        typer.echo(f"[civis] {REAL_LLM_ENV}=1 → also running against real judge {real_judge.name}")
        real_report = run_judge_deceiver(
            judge=real_judge, label=f"real:{real_judge.name}", attacks=attacks
        )
        reports.append(real_report)
        typer.echo(_judge_deceiver_summary(f"real:{real_judge.name}", real_report))

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "target_score": target_score,
        "attacks_per_judge": len(attacks),
        "reports": [r.model_dump(mode="json") for r in reports],
    }
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"[civis] wrote {output}")


@adversarial_app.command(
    "report",
    help="Consolidate battery + judge-deceiver JSONs into a Markdown report.",
)
def report_command(
    adversarial_json: Path = typer.Option(  # noqa: B008 - Typer default
        Path("reports/adversarial_v1.json"),
        "--adversarial-json",
        help="Path to the battery JSON produced by 'adversarial run'.",
    ),
    judge_deceiver_json: Path = typer.Option(  # noqa: B008 - Typer default
        Path("reports/judge_deceiver_pointwise_v1.json"),
        "--judge-deceiver-json",
        help="Path to the JSON produced by 'adversarial judge-deceiver'.",
    ),
    output: Path = typer.Option(  # noqa: B008 - Typer default
        Path("reports/security_v1.md"),
        "--output",
        help="Where to write the Markdown security report.",
    ),
) -> None:
    """Read both JSON reports and produce reports/security_v1.md."""
    if not adversarial_json.exists():
        typer.echo(f"[civis] missing input: {adversarial_json}", err=True)
        raise typer.Exit(code=2)
    if not judge_deceiver_json.exists():
        typer.echo(f"[civis] missing input: {judge_deceiver_json}", err=True)
        raise typer.Exit(code=2)

    markdown = build_security_report(
        adversarial_json_path=adversarial_json,
        judge_deceiver_json_path=judge_deceiver_json,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    typer.echo(f"[civis] wrote {output} ({len(markdown)} chars)")


# ---- provider selection ----------------------------------------------------

def _persona_provider(use_real: bool) -> LLMProvider:
    """Return the persona provider — real backend or mock refusal."""
    if not use_real:
        return RecordingMockProvider(
            replies=[MOCK_REFUSAL_REPLY],
            name="mock:persona_refusal",
        )
    config, _ = load_or_default_config()
    return build_provider_from_config(config, DEFAULT_PERSONA_KEY)


def _judge_provider(use_real: bool) -> LLMProvider:
    """Return the judge provider — real backend or mock refusal."""
    if not use_real:
        return RecordingMockProvider(
            replies=[MOCK_REFUSAL_REPLY],
            name="mock:judge_refusal",
        )
    config, _ = load_or_default_config()
    return build_provider_from_config(config, DEFAULT_JUDGE_KEY)


# ---- system-prompt factories ----------------------------------------------

def _persona_system_prompt_fn(scenario_id: str):
    """
    Build the callback that assembles the persona system prompt per attack.

    We rebuild the persona prompt using the shipped scenario so the system
    text under test IS the one production would use. The scenario file is
    loaded once and reused.
    """
    from civis.fsm.states import Phase
    from civis.personas.base import PersonaState
    from civis.prompts.persona import build_persona_prompt
    from civis.session.scenario import (
        load_scenario_from_path,
        resolve_scenario_path,
    )

    scenario_path = resolve_scenario_path(
        scenario_id,
        scenarios_dir=Path("data/scenarios"),
    )
    scenario, _ = load_scenario_from_path(scenario_path)
    base_state = PersonaState(
        profile=scenario.persona,
        phase=Phase.INFO_GATHERING,
        emotion=scenario.persona.initial_emotion,
    )

    def _fn(attack: AttackDefinition) -> tuple[str, str]:
        # We ONLY want the system prompt; the runner wraps the payload
        # in <user_input> itself, so return an empty user preamble.
        system_prompt, _user_prompt = build_persona_prompt(
            state=base_state,
            history=[],
            last_agent_message=attack.payload,
        )
        return system_prompt, ""

    return _fn


def _judge_system_prompt_fn():
    """
    Judge system prompt is stable (no scenario dependency at the system
    level — the scenario data lives in the user prompt during real runs).
    We call build_judge_prompt once with a synthetic transcript.
    """
    from civis.prompts.judge import build_judge_prompt

    def _fn(_attack: AttackDefinition) -> tuple[str, str]:
        system_prompt, _user_prompt = build_judge_prompt(
            session_id="adv_battery",
            scenario_title="battery",
            scenario_goal="none",
            expected_agent_actions=[],
            transcript=[],
        )
        return system_prompt, ""

    return _fn


# ---- pretty printing ------------------------------------------------------

def _summary_line(role: str, report: BatteryReport) -> str:
    """One-line summary printed to the CLI."""
    return (
        f"[civis] {role:>8s} target={report.target_label} "
        f"defended={report.defended} leaked={report.leaked} "
        f"skipped={report.skipped} leak_rate={report.leak_rate:.2%}"
    )


def _judge_deceiver_summary(label: str, report: JudgeDeceiverReport) -> str:
    """One-line summary printed for each judge in the judge-deceiver run."""
    return (
        f"[civis] judge-deceiver {label:>22s} "
        f"ASR={report.overall_asr:.2%} "
        f"({report.succeeded}/{report.attempted})"
    )
