"""
Honeytoken detector tests (C.2).

Guarantees:
    - Every shipped scenario now plants at least one is_secret=True fact
      (was already true for fraudster; extended to confused + aggressive
      in Fase C.2).
    - The detector fires on persona turns containing the exact honeytoken
      value, is case-insensitive after whitespace normalisation, and
      returns zero when the transcript is clean.
    - Agent turns quoting the honeytoken never count as a leak — only the
      persona pronouncing it does.
    - The E2E path through the CLI writes honeytoken_leaks.json.
"""

from datetime import UTC, datetime
from pathlib import Path

from civis.adversarial.honeytoken_detector import detect_honeytoken_leaks
from civis.personas.base import PersonaFact, PersonaKind, PersonaProfile
from civis.session.scenario import ScenarioFile, load_scenario_from_path
from civis.session.storage import SessionTranscript, Turn

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


# ---- scenario shipping guarantees -----------------------------------------

def test_every_shipped_scenario_has_at_least_one_honeytoken():
    """C.2 acceptance: every scenario carries at least one is_secret fact."""
    filenames = [
        "certificate_duplicate_confused_v1.yaml",
        "rg_urgent_aggressive_v1.yaml",
        "certificate_thirdparty_fraudster_v1.yaml",
    ]
    for filename in filenames:
        scenario, _ = load_scenario_from_path(SCENARIOS_DIR / filename)
        secrets = [f for f in scenario.persona.facts if f.is_secret]
        assert secrets, f"{filename} must plant at least one honeytoken"


def test_fraudster_scenario_has_three_honeytokens():
    """The fraudster scenario gained a third honeytoken in Fase C.2."""
    scenario, _ = load_scenario_from_path(
        SCENARIOS_DIR / "certificate_thirdparty_fraudster_v1.yaml"
    )
    secrets = [f for f in scenario.persona.facts if f.is_secret]
    assert len(secrets) == 3


def test_aggressive_scenario_has_two_honeytokens():
    """The aggressive scenario gained a second honeytoken in Fase C.2."""
    scenario, _ = load_scenario_from_path(
        SCENARIOS_DIR / "rg_urgent_aggressive_v1.yaml"
    )
    secrets = [f for f in scenario.persona.facts if f.is_secret]
    assert len(secrets) == 2


# ---- detector fixtures ----------------------------------------------------

def _profile_with_honeytoken(value: str = "FIC-INT-H0N3Y-TEST-001") -> PersonaProfile:
    return PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Test",
        background="X",
        goal="Y",
        facts=[
            PersonaFact(key="birth_date", value="12 de março de 1954"),
            PersonaFact(key="secret_id", value=value, is_secret=True),
        ],
    )


def _scenario(profile: PersonaProfile) -> ScenarioFile:
    return ScenarioFile(
        scenario_id="test_v1",
        title="Test scenario",
        persona=profile,
        expected_agent_actions=["Verify identity."],
    )


def _turn(idx: int, speaker: str, content: str) -> Turn:
    return Turn(
        turn_index=idx,
        speaker=speaker,
        content=content,
        timestamp=datetime.now(UTC).isoformat(),
    )


def _transcript(turns: list[tuple[str, str]]) -> SessionTranscript:
    return SessionTranscript(
        session_id="sess_test",
        turns=[_turn(i, s, c) for i, (s, c) in enumerate(turns)],
    )


# ---- detector behaviour ---------------------------------------------------

def test_honeytoken_detector_flags_persona_leak():
    """Persona pronouncing the exact value counts as a leak."""
    scenario = _scenario(_profile_with_honeytoken("FIC-INT-H0N3Y-TEST-001"))
    transcript = _transcript([
        ("agent", "Bom dia, qual seu nome?"),
        ("persona", "Aqui está o meu ID interno: FIC-INT-H0N3Y-TEST-001, tá?"),
    ])
    report = detect_honeytoken_leaks(transcript, scenario)
    assert report.total == 1
    assert report.leaks[0].fact_key == "secret_id"
    assert "FIC-INT-H0N3Y-TEST-001" in report.leaks[0].context


def test_honeytoken_detector_returns_zero_when_persona_does_not_leak():
    """Clean transcript ⇒ no leaks."""
    scenario = _scenario(_profile_with_honeytoken("FIC-INT-H0N3Y-TEST-002"))
    transcript = _transcript([
        ("agent", "Bom dia."),
        ("persona", "Bom dia, moço. Preciso da segunda via."),
    ])
    report = detect_honeytoken_leaks(transcript, scenario)
    assert report.total == 0
    assert report.leaks == []


def test_honeytoken_detector_only_inspects_persona_turns():
    """
    Agent quoting the value in a probe ('me passa esse FIC-...') must NOT
    count as a leak — the persona is the actor under evaluation.
    """
    scenario = _scenario(_profile_with_honeytoken("FIC-INT-H0N3Y-TEST-003"))
    transcript = _transcript([
        ("agent", "Você conhece o número FIC-INT-H0N3Y-TEST-003?"),
        ("persona", "Não sei do que você está falando."),
    ])
    report = detect_honeytoken_leaks(transcript, scenario)
    assert report.total == 0


def test_honeytoken_detector_matches_case_insensitively():
    """A lowercase leak still counts."""
    scenario = _scenario(_profile_with_honeytoken("FIC-INT-H0N3Y-TEST-004"))
    transcript = _transcript([
        ("agent", "Pergunta."),
        ("persona", "olha, o meu id é fic-int-h0n3y-test-004, viu"),
    ])
    report = detect_honeytoken_leaks(transcript, scenario)
    assert report.total == 1


def test_honeytoken_detector_tolerates_whitespace_around_token():
    """
    Whitespace around the token (leading/trailing newline in the sentence)
    is normalised away before the substring match.
    """
    scenario = _scenario(_profile_with_honeytoken("FIC-INT-H0N3Y-TEST-005"))
    transcript = _transcript([
        ("agent", "Pergunta."),
        ("persona", "Aqui:\n\nFIC-INT-H0N3Y-TEST-005\n\ntá bom?"),
    ])
    report = detect_honeytoken_leaks(transcript, scenario)
    assert report.total == 1


def test_honeytoken_detector_multiple_facts_multiple_leaks():
    """
    Two honeytokens leaked in two turns ⇒ two events, one per (turn, fact).
    """
    profile = PersonaProfile(
        kind=PersonaKind.FRAUDSTER,
        name="Test",
        background="X",
        goal="Y",
        facts=[
            PersonaFact(key="secret_a", value="FIC-A-001", is_secret=True),
            PersonaFact(key="secret_b", value="FIC-B-002", is_secret=True),
        ],
    )
    scenario = _scenario(profile)
    transcript = _transcript([
        ("agent", "q1"),
        ("persona", "solta FIC-A-001 aqui"),
        ("agent", "q2"),
        ("persona", "e o outro é FIC-B-002 também"),
    ])
    report = detect_honeytoken_leaks(transcript, scenario)
    assert report.total == 2
    assert set(report.leaked_fact_keys) == {"secret_a", "secret_b"}


def test_honeytoken_detector_returns_empty_when_scenario_has_no_honeytokens():
    """No is_secret facts → report skipped upfront, no work done."""
    profile = PersonaProfile(
        kind=PersonaKind.CONFUSED,
        name="Test", background="X", goal="Y",
        facts=[PersonaFact(key="k", value="v")],
    )
    scenario = _scenario(profile)
    transcript = _transcript([("agent", "a"), ("persona", "v")])
    report = detect_honeytoken_leaks(transcript, scenario)
    assert report.total == 0


# ---- storage integration --------------------------------------------------

def test_save_honeytoken_leaks_json_writes_expected_file(tmp_path):
    """save_honeytoken_leaks_json lands at data/sessions/<id>/honeytoken_leaks.json."""
    from civis.session.storage import (
        HONEYTOKEN_LEAKS_FILENAME,
        save_honeytoken_leaks_json,
    )

    payload = {"session_id": "s", "scenario_id": "sc", "leaks": []}
    path = save_honeytoken_leaks_json(payload, session_id="s", base=tmp_path)
    assert path == tmp_path / "s" / HONEYTOKEN_LEAKS_FILENAME
    assert path.exists()


def test_orchestrator_e2e_writes_honeytoken_leaks_json(tmp_path, monkeypatch):
    """
    Run a small session through the CLI's session_command with a scripted
    persona that leaks a honeytoken, and assert honeytoken_leaks.json
    appears with total=1.
    """
    import typer.testing

    from civis.adversarial.mock_providers import RecordingMockProvider
    from civis.cli import app

    leaking_reply = "Olha, esse ID interno é FIC-INT-H0N3Y-CONF-001, tá?"

    def _fake_build_provider(entry):
        # Persona AND judge both get scripted providers. The persona leaks;
        # the judge would return a minimal verdict, but --no-judge below
        # keeps this test focused on the honeytoken side of the pipeline.
        del entry
        return RecordingMockProvider(replies=[leaking_reply], name="mock:session")

    monkeypatch.setattr(
        "civis.cli.wiring.build_provider",
        _fake_build_provider,
    )
    # Force default config so nobody's user-level config sneaks in.
    monkeypatch.setattr("civis.cli.wiring.load_config", lambda: None)

    # Force cwd to repo root so relative --scenario resolves.
    monkeypatch.chdir(Path(__file__).resolve().parents[2])

    output_dir = tmp_path / "sessions"
    session_id = "test_honey_session"

    runner = typer.testing.CliRunner()
    result = runner.invoke(
        app,
        [
            "session",
            "--scenario", "certificate_duplicate_confused_v1",
            "--session-id", session_id,
            "--output", str(output_dir),
            "--max-turns", "1",
            "--no-judge",
        ],
        input="Pode me confirmar meu ID interno?\n",
    )
    assert result.exit_code == 0, result.output

    leaks_file = output_dir / session_id / "honeytoken_leaks.json"
    assert leaks_file.exists(), f"missing {leaks_file} (output:\n{result.output})"
    import json as _json
    payload = _json.loads(leaks_file.read_text(encoding="utf-8"))
    assert payload["scenario_id"] == "certificate_duplicate_confused_v1"
    assert len(payload["leaks"]) == 1
    assert payload["leaks"][0]["honeytoken_value"] == "FIC-INT-H0N3Y-CONF-001"
