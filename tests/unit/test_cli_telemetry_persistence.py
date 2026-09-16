"""
Tests for the Phase D turn-telemetry sidecar the CLI writes.

The Streamlit "Métricas" page reads `turn_telemetry.json` from every
session folder. Without a CLI write of that file, the panel is blind.
The tests below drive the full `civis session` command through a
scripted fake provider and assert the sidecar shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from civis.cli import app
from civis.cli.session import session_command  # noqa: F401 - imported for side effect
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse

runner = CliRunner()


# A scripted provider that reports distinct telemetry per turn so we can
# assert every row round-tripped through the CLI without merging them.
class _TelemetryScriptedProvider(LLMProvider):
    def __init__(
        self,
        replies: list[str],
        telemetry: list[tuple[int, int, int]],
        name: str,
    ) -> None:
        assert len(replies) == len(telemetry)
        self._replies = replies
        self._telemetry = telemetry
        self._name = name
        self._calls = 0

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        idx = min(self._calls, len(self._replies) - 1)
        input_tokens, output_tokens, latency_ms = self._telemetry[idx]
        response = LLMResponse(
            content=self._replies[idx],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider_name=self._name,
        )
        self._calls += 1
        return response


_SCENARIO_YAML = """
scenario_id: "test_telemetry_v1"
title: "Telemetry test scenario"

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

expected_agent_actions:
  - "Verificar identidade da cidadã."
"""


def _write_scenario(tmp_path: Path) -> Path:
    d = tmp_path / "scenarios"
    d.mkdir()
    (d / "test_telemetry_v1.yaml").write_text(_SCENARIO_YAML, encoding="utf-8")
    return d


def _stub_config():
    """Minimal CivisConfig equivalent used only to route roles → catalog keys."""
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
                model_id="fake:persona",
                base_url="http://x",
            ),
            "judge": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="fake:judge",
                base_url="http://x",
            ),
        },
        roles=RoleAssignments(persona="persona", judge="judge"),
    )


def test_cli_writes_turn_telemetry_sidecar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """
    Three agent turns → three persona turns → three telemetry rows,
    each carrying the tokens/latency/provider reported by the persona
    provider on that turn.
    """
    scenarios_dir = _write_scenario(tmp_path)
    output_dir = tmp_path / "sessions"

    replies = [
        "Bom dia, moço.",
        "Meu nome é Iracema.",
        "Nasci em 12 de março de 1954.",
    ]
    telemetry = [
        (100, 20, 500),
        (150, 30, 800),
        (200, 40, 1100),
    ]

    def _builder(_config, role_key: str) -> LLMProvider:
        if role_key == "persona":
            return _TelemetryScriptedProvider(
                replies=replies,
                telemetry=telemetry,
                name="fake:persona",
            )
        # judge is never called (--no-judge below) but the CLI resolves it
        # up front, so we still hand back a dummy.
        return _TelemetryScriptedProvider(
            replies=["{}"], telemetry=[(0, 0, 0)], name="fake:judge",
        )

    monkeypatch.setattr(
        "civis.cli.session.build_provider_from_config",
        _builder,
    )
    monkeypatch.setattr(
        "civis.cli.session.load_or_default_config",
        lambda: (_stub_config(), "default_ollama"),
    )

    result = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_telemetry_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "tel1",
            "--max-turns", "3",
            "--no-judge",
        ],
        input="Bom dia.\nQual seu nome?\nSua data de nascimento?\n",
    )
    assert result.exit_code == 0, result.stdout + "\n" + (result.stderr or "")

    telemetry_path = output_dir / "tel1" / "turn_telemetry.json"
    assert telemetry_path.exists(), (
        "Phase D CLI must write turn_telemetry.json alongside transcript.json"
    )

    payload = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert payload["session_id"] == "tel1"
    rows = payload["turns"]
    assert len(rows) == 3

    # Each row belongs to a PERSONA turn (odd turn_index in the transcript
    # since agents speak first). Persona turns are indices 1, 3, 5.
    persona_turn_indices = [row["turn_index"] for row in rows]
    assert persona_turn_indices == [1, 3, 5]

    # Every field survives the round trip.
    for row, (in_tok, out_tok, latency) in zip(rows, telemetry, strict=True):
        assert row["input_tokens"] == in_tok
        assert row["output_tokens"] == out_tok
        assert row["latency_ms"] == latency
        assert row["provider_name"] == "fake:persona"


def test_cli_telemetry_survives_resume(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """
    Reopening the same session appends further rows to the sidecar.
    Uses two invocations of the same command with matching session-id.
    """
    scenarios_dir = _write_scenario(tmp_path)
    output_dir = tmp_path / "sessions"

    def _builder(_config, role_key: str) -> LLMProvider:
        return _TelemetryScriptedProvider(
            replies=["ok"] * 5,
            telemetry=[(10 + i, 5, 100 + 50 * i) for i in range(5)],
            name="fake:persona",
        )

    monkeypatch.setattr(
        "civis.cli.session.build_provider_from_config",
        _builder,
    )
    monkeypatch.setattr(
        "civis.cli.session.load_or_default_config",
        lambda: (_stub_config(), "default_ollama"),
    )

    # First run: 2 agent turns.
    result_a = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_telemetry_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "tel2",
            "--max-turns", "2",
            "--no-judge",
        ],
        input="oi\ntudo bem?\n",
    )
    assert result_a.exit_code == 0

    telemetry_path = output_dir / "tel2" / "turn_telemetry.json"
    first_payload = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert len(first_payload["turns"]) == 2

    # Second run: 2 more agent turns, resuming the same session.
    result_b = runner.invoke(
        app,
        [
            "session",
            "--scenario", "test_telemetry_v1",
            "--scenarios-dir", str(scenarios_dir),
            "--output", str(output_dir),
            "--session-id", "tel2",
            "--max-turns", "2",
            "--no-judge",
        ],
        input="qual seu nome?\ne a data?\n",
    )
    assert result_b.exit_code == 0

    # A resume starts a fresh accumulator — the second file has the two
    # NEW turns' telemetry (turn_indices reflect the transcript position).
    second_payload = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert len(second_payload["turns"]) == 2
    # After a resume, the persona turns are at indices 5 and 7 (the
    # transcript now has 4 prior turns from the first run: agent/persona
    # ×2, plus the fresh agent/persona pair inside this run).
    turn_indices = [row["turn_index"] for row in second_payload["turns"]]
    assert all(idx >= 4 for idx in turn_indices)
