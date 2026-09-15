"""
`civis session` end-to-end tests.

Uses Typer's CliRunner + a scripted fake provider (installed via
monkeypatch on civis.cli.session.build_provider_from_config) so we
exercise the full command without any HTTP or Ollama running.

What these tests must guarantee:

    - `--help` renders (basic CLI wiring is intact).
    - A full session with `--no-judge` writes transcript.json +
      metadata.json under the chosen output dir.
    - A full session including the judge writes verdict.json with a
      valid JudgeVerdict payload.
    - Resuming with the same session_id against an unchanged scenario
      reopens and continues the transcript.
    - Resuming against a mutated scenario file fails cleanly (exit 2).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from civis.cli import app
from civis.cli.session import session_command  # noqa: F401 - imported for side effect
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse

runner = CliRunner()


# ---- fake providers -------------------------------------------------------

class _ScriptedProvider(LLMProvider):
    """LLMProvider that returns pre-baked replies in order."""

    def __init__(self, replies: list[str], name: str) -> None:
        self._replies = replies
        self._name = name
        self._calls = 0

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        content = (
            self._replies[self._calls]
            if self._calls < len(self._replies)
            else "..."
        )
        self._calls += 1
        return LLMResponse(
            content=content,
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            provider_name=self._name,
        )


_PERSONA_REPLIES = [
    "Bom dia, moço. Vim buscar a segunda via da minha certidão.",
    "Meu nome é Iracema Silva.",
    "Nasci em 12 de março de 1954.",
    "Minha mãe se chama Maria das Graças Silva.",
]

_JUDGE_REPLY = json.dumps(
    {
        "session_id": "will_be_overridden",
        "criteria": [
            {
                "criterion": "fact_verification",
                "score": 3,
                "rationale": "Pediu nome mas não filiação.",
                "cited_turns": [
                    {"turn_index": 2, "excerpt": "Qual seu nome completo?"}
                ],
            },
            {
                "criterion": "data_protection",
                "score": 5,
                "rationale": "Nada sensível foi vazado.",
                "cited_turns": [],
            },
            {
                "criterion": "protocol_adherence",
                "score": 4,
                "rationale": "Cumprimentou e verificou dados básicos.",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "Bom dia."}
                ],
            },
            {
                "criterion": "communication",
                "score": 4,
                "rationale": "Tom claro e cordial.",
                "cited_turns": [
                    {"turn_index": 0, "excerpt": "Bom dia."}
                ],
            },
        ],
        "overall_summary": "Atendimento cordial, verificação parcial.",
    },
    ensure_ascii=False,
)


def _fake_provider_factory(replies_by_role: dict[str, list[str]]):
    """
    Return a stub for build_provider_from_config that hands out a scripted
    provider per role. The CLI calls this twice: once for 'persona', once
    for 'judge'.
    """
    def _builder(_config, role_key: str) -> LLMProvider:
        name = f"fake:{role_key}"
        replies = replies_by_role.get(role_key, [])
        return _ScriptedProvider(replies=replies, name=name)
    return _builder


# ---- fixtures --------------------------------------------------------------

_SCENARIO_YAML = """
scenario_id: "test_cli_v1"
title: "CLI test scenario"

persona:
  kind: "confused"
  name: "Dona Iracema"
  background: |
    Cidadã idosa fictícia.
  goal: |
    Obter uma segunda via.
  initial_emotion: "anxious"
  facts:
    - key: "birth_date"
      value: "12 de março de 1954"
      is_secret: false
    - key: "mother_name"
      value: "Maria das Graças Silva"
      is_secret: false

expected_agent_actions:
  - "Verificar identidade da cidadã."
"""


def _write_scenario(tmp_path: Path) -> Path:
    d = tmp_path / "scenarios"
    d.mkdir()
    target = d / "test_cli_v1.yaml"
    target.write_text(_SCENARIO_YAML, encoding="utf-8")
    return d


# ---- help ------------------------------------------------------------------

def test_help_renders():
    result = runner.invoke(app, ["session", "--help"])
    assert result.exit_code == 0
    assert "--scenario" in result.stdout
    assert "--session-id" in result.stdout


# ---- happy path: no judge --------------------------------------------------

def test_session_writes_transcript_and_metadata_without_judge(
    tmp_path: Path,
    monkeypatch,
):
    scenarios_dir = _write_scenario(tmp_path)
    output_dir = tmp_path / "sessions"

    # Force default (no config on disk).
    monkeypatch.setattr("civis.cli.session.build_provider_from_config",
                        _fake_provider_factory({"persona": _PERSONA_REPLIES}))
    # Also force load_or_default_config so we never touch the user's real
    # config file (which may or may not exist).
    monkeypatch.setattr(
        "civis.cli.session.load_or_default_config",
        lambda: (_stub_config(), "default_ollama"),
    )

    result = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_cli_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "s1",
            "--max-turns", "3",
            "--no-judge",
        ],
        input="Bom dia, em que posso ajudar?\nMe diga seu nome.\nSua data de nascimento?\n",
    )

    assert result.exit_code == 0, result.stdout + "\n" + (result.stderr or "")

    session_dir = output_dir / "s1"
    assert (session_dir / "transcript.json").exists()
    assert (session_dir / "metadata.json").exists()
    assert not (session_dir / "verdict.json").exists()

    transcript = json.loads((session_dir / "transcript.json").read_text(encoding="utf-8"))
    assert transcript["session_id"] == "s1"
    # 3 agent turns + 3 persona replies.
    assert len(transcript["turns"]) == 6


# ---- happy path: with judge -----------------------------------------------

def test_session_runs_judge_and_writes_verdict(tmp_path: Path, monkeypatch):
    scenarios_dir = _write_scenario(tmp_path)
    output_dir = tmp_path / "sessions"

    monkeypatch.setattr(
        "civis.cli.session.build_provider_from_config",
        _fake_provider_factory({
            "persona": _PERSONA_REPLIES,
            "judge": [_JUDGE_REPLY],
        }),
    )
    monkeypatch.setattr(
        "civis.cli.session.load_or_default_config",
        lambda: (_stub_config(), "default_ollama"),
    )

    result = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_cli_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "s2",
            "--max-turns", "3",
        ],
        input="Bom dia.\nQual seu nome completo?\nSua data de nascimento?\n",
    )

    assert result.exit_code == 0, result.stdout + "\n" + (result.stderr or "")

    verdict_path = output_dir / "s2" / "verdict.json"
    assert verdict_path.exists()

    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["session_id"] == "s2"  # forced to caller value
    assert len(verdict["criteria"]) == 4


# ---- resume ---------------------------------------------------------------

def test_resume_same_session_appends_to_transcript(tmp_path: Path, monkeypatch):
    scenarios_dir = _write_scenario(tmp_path)
    output_dir = tmp_path / "sessions"

    monkeypatch.setattr(
        "civis.cli.session.build_provider_from_config",
        _fake_provider_factory({"persona": _PERSONA_REPLIES + _PERSONA_REPLIES}),
    )
    monkeypatch.setattr(
        "civis.cli.session.load_or_default_config",
        lambda: (_stub_config(), "default_ollama"),
    )

    # First run: 2 agent turns.
    r1 = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_cli_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "resumable",
            "--max-turns", "5",
            "--no-judge",
        ],
        input="Bom dia.\nSeu nome?\n",
    )
    assert r1.exit_code == 0
    first_transcript = json.loads(
        (output_dir / "resumable" / "transcript.json").read_text(encoding="utf-8")
    )
    assert len(first_transcript["turns"]) == 4

    # Second run: same id, 1 more agent turn.
    r2 = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_cli_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "resumable",
            "--max-turns", "5",
            "--no-judge",
        ],
        input="Sua data de nascimento?\n",
    )
    assert r2.exit_code == 0
    second_transcript = json.loads(
        (output_dir / "resumable" / "transcript.json").read_text(encoding="utf-8")
    )
    # 4 prior turns + 2 new turns (1 agent + 1 persona).
    assert len(second_transcript["turns"]) == 6


def test_resume_fails_clearly_when_scenario_changed(tmp_path: Path, monkeypatch):
    scenarios_dir = _write_scenario(tmp_path)
    output_dir = tmp_path / "sessions"

    monkeypatch.setattr(
        "civis.cli.session.build_provider_from_config",
        _fake_provider_factory({"persona": _PERSONA_REPLIES}),
    )
    monkeypatch.setattr(
        "civis.cli.session.load_or_default_config",
        lambda: (_stub_config(), "default_ollama"),
    )

    # First run to seed the session with the current scenario hash.
    r1 = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_cli_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "drifty",
            "--max-turns", "2",
            "--no-judge",
        ],
        input="Bom dia.\n",
    )
    assert r1.exit_code == 0

    # Mutate the scenario file — reopening must refuse.
    scenario_file = scenarios_dir / "test_cli_v1.yaml"
    scenario_file.write_text(
        _SCENARIO_YAML.replace("Iracema", "Adalgisa"), encoding="utf-8"
    )

    r2 = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_cli_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "drifty",
            "--max-turns", "2",
            "--no-judge",
        ],
        input="Bom dia.\n",
    )
    # Exit code 2 per the CLI contract for scenario drift.
    assert r2.exit_code == 2
    # Message mentions the drift.
    combined = (r2.stdout or "") + (r2.stderr or "")
    assert "changed" in combined.lower() or "hash mismatch" in combined.lower()


# ---- helpers --------------------------------------------------------------

def _stub_config():
    """Minimal valid CivisConfig — bypasses the real load path in tests."""
    from civis.config.models import (
        CivisConfig,
        ModelEntry,
        ProviderKind,
        RoleAssignments,
    )
    return CivisConfig(
        models={
            "persona": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="fake-persona-model",
                base_url="http://localhost:11434",
            ),
            "judge": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="fake-judge-model",
                base_url="http://localhost:11434",
            ),
        },
        roles=RoleAssignments(persona="persona", judge="judge"),
    )
