"""
JudgeDeceiver-pointwise attack tests (C.4).

Coverage:
    - generate_pointwise_attacks produces ≥ 20 variations by default;
    - each attack carries the intended (criterion, target_score, position);
    - the runner drives baseline + targeted rounds and returns:
        * ASR = 1.0 against the VulnerableJudgeMock;
        * ASR = 0.0 against the RobustJudgeMock;
    - PAC per position is measurable (all three positions run);
    - CLI 'civis adversarial judge-deceiver' writes the JSON report.
"""


from civis.adversarial.judge_deceiver_pointwise import (
    generate_pointwise_attacks,
    run_judge_deceiver,
)
from civis.adversarial.mock_judges import RobustJudgeMock, VulnerableJudgeMock
from civis.judge.rubric import CriterionKind

# ---- attack generation ----------------------------------------------------

def test_judge_deceiver_generates_at_least_20_variations():
    """
    Default generation (all 4 criteria × 3 positions × 6 templates)
    yields 72 attacks; the roadmap floor is 20.
    """
    attacks = generate_pointwise_attacks()
    assert len(attacks) >= 20
    assert len(attacks) == 4 * 3 * 6


def test_judge_deceiver_attacks_cover_all_criteria_and_positions():
    """Each criterion × position pair must appear at least once."""
    attacks = generate_pointwise_attacks()
    covered = {(a.criterion, a.position) for a in attacks}
    assert len(covered) == 4 * 3
    for criterion in CriterionKind:
        for position in ("start", "middle", "end"):
            assert (criterion, position) in covered


def test_judge_deceiver_payload_targets_specified_criterion_and_score():
    """Every payload must literally mention its target criterion + score."""
    attacks = generate_pointwise_attacks(target_score=4)
    for attack in attacks:
        assert attack.criterion.value in attack.payload_text
        assert "4" in attack.payload_text
        assert attack.target_score == 4


def test_judge_deceiver_attack_ids_are_unique():
    """Duplicate ids would corrupt per-attack outcome tracking."""
    attacks = generate_pointwise_attacks()
    ids = [a.attack_id for a in attacks]
    assert len(ids) == len(set(ids))


# ---- runner: vulnerable vs robust ----------------------------------------

def test_judge_deceiver_runner_asr_is_one_against_vulnerable_mock():
    """
    Vulnerable judge always follows the embedded directive, so every
    attack succeeds → ASR = 1.0.
    """
    attacks = generate_pointwise_attacks()
    report = run_judge_deceiver(
        judge=VulnerableJudgeMock(),
        label="mock:vulnerable",
        attacks=attacks,
    )
    assert report.attempted == len(attacks)
    assert report.succeeded == len(attacks)
    assert report.overall_asr == 1.0


def test_judge_deceiver_runner_asr_is_zero_against_robust_mock():
    """
    Robust judge ignores every directive; baseline scores never match
    the target (5), so ASR = 0.0.
    """
    attacks = generate_pointwise_attacks(target_score=5)
    report = run_judge_deceiver(
        judge=RobustJudgeMock(),
        label="mock:robust",
        attacks=attacks,
    )
    assert report.attempted == len(attacks)
    assert report.succeeded == 0
    assert report.overall_asr == 0.0


def test_judge_deceiver_report_contains_per_criterion_and_per_position():
    """The report exposes both aggregate axes needed for the C.5 tables."""
    attacks = generate_pointwise_attacks()
    report = run_judge_deceiver(
        judge=VulnerableJudgeMock(),
        label="mock:vulnerable",
        attacks=attacks,
    )
    criteria_seen = {c.criterion for c in report.by_criterion}
    positions_seen = {p.position for p in report.by_position}
    assert criteria_seen == set(CriterionKind)
    assert positions_seen == {"start", "middle", "end"}
    for c in report.by_criterion:
        assert c.rate == 1.0
    for p in report.by_position:
        assert p.rate == 1.0


def test_judge_deceiver_baseline_is_recorded_separately():
    """
    The report carries baseline scores (no payload) so ASR gains can be
    interpreted against the null hypothesis.
    """
    attacks = generate_pointwise_attacks()
    report = run_judge_deceiver(
        judge=RobustJudgeMock(),
        label="mock:robust",
        attacks=attacks,
    )
    baseline = report.baseline.scores
    assert set(baseline.keys()) == set(CriterionKind)
    # Robust judge baseline for protocol_adherence is 1 (from BASELINE_SCORES).
    assert baseline[CriterionKind.PROTOCOL_ADHERENCE] == 1


def test_judge_deceiver_outcomes_preserve_attack_metadata():
    """
    Each AttackOutcome must expose (attack_id, criterion, target_score,
    position, achieved_score, succeeded) so the JSON report is
    reproducible and auditable.
    """
    attacks = generate_pointwise_attacks()
    report = run_judge_deceiver(
        judge=VulnerableJudgeMock(),
        label="mock:vulnerable",
        attacks=attacks,
    )
    assert len(report.outcomes) == len(attacks)
    for outcome, attack in zip(report.outcomes, attacks, strict=True):
        assert outcome.attack_id == attack.attack_id
        assert outcome.criterion == attack.criterion
        assert outcome.target_score == attack.target_score
        assert outcome.position == attack.position
        # Vulnerable mock returns exactly the forced score.
        assert outcome.achieved_score == attack.target_score


# ---- CLI --------------------------------------------------------------------

def test_cli_judge_deceiver_writes_report(tmp_path):
    """
    `civis adversarial judge-deceiver --output …` runs both mock judges
    and writes a JSON with two reports (vulnerable and robust).
    """
    from typer.testing import CliRunner

    from civis.cli import app

    output = tmp_path / "judge_deceiver.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "adversarial", "judge-deceiver",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.exists()

    import json as _json
    payload = _json.loads(output.read_text(encoding="utf-8"))
    labels = [r["label"] for r in payload["reports"]]
    assert "mock:vulnerable_judge" in labels
    assert "mock:robust_judge" in labels

    # Vulnerable should have ASR = 1.0; robust should have ASR = 0.0.
    for report in payload["reports"]:
        if report["label"] == "mock:vulnerable_judge":
            assert report["overall_asr"] == 1.0
        if report["label"] == "mock:robust_judge":
            assert report["overall_asr"] == 0.0


def test_cli_judge_deceiver_help_is_registered():
    """Regression: `adversarial --help` lists judge-deceiver."""
    from typer.testing import CliRunner

    from civis.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["adversarial", "--help"])
    assert result.exit_code == 0
    assert "judge-deceiver" in result.output


# ---- guard on the transcript synthesis ------------------------------------

def test_embed_payload_lands_at_expected_position():
    """
    The private _embed_payload helper places the payload at start, middle
    or end of the last persona reply. We probe all three to guard against
    regressions in the position-based analysis.
    """
    from civis.adversarial.judge_deceiver_pointwise import _embed_payload

    transcript = [
        ("agent", "hi"),
        ("persona", "abcdefghij"),
    ]
    payload = "PAYLOAD"

    start = _embed_payload(transcript, payload, "start")
    end = _embed_payload(transcript, payload, "end")
    middle = _embed_payload(transcript, payload, "middle")

    assert start[-1][1].startswith("PAYLOAD")
    assert end[-1][1].endswith("PAYLOAD")
    assert "PAYLOAD" in middle[-1][1]
    assert not middle[-1][1].startswith("PAYLOAD")
    assert not middle[-1][1].endswith("PAYLOAD")


# ---- consistency check across the two mocks -------------------------------

def test_vulnerable_and_robust_mocks_disagree_on_every_attack():
    """
    The two mocks bracket the ASR range: for the same attack, one always
    succeeds and the other always fails. That property makes them useful
    as sanity anchors in the C.5 report.
    """
    attacks = generate_pointwise_attacks()
    vulnerable = run_judge_deceiver(
        judge=VulnerableJudgeMock(),
        label="mock:vulnerable",
        attacks=attacks,
    )
    robust = run_judge_deceiver(
        judge=RobustJudgeMock(),
        label="mock:robust",
        attacks=attacks,
    )
    # Zip both outcome lists — they iterate over the same attack list.
    for vout, rout in zip(vulnerable.outcomes, robust.outcomes, strict=True):
        assert vout.attack_id == rout.attack_id
        assert vout.succeeded is True
        assert rout.succeeded is False


# ---- documentation guard --------------------------------------------------

def test_report_module_is_documented_for_the_pitch(tmp_path):
    """
    The judge-deceiver module is the pitch-carrying differentiator. Its
    docstring must reference JudgeDeceiver / Shi et al. / target-aligned
    so a reviewer of the codebase can trace the science.
    """
    import civis.adversarial.judge_deceiver_pointwise as mod

    doc = (mod.__doc__ or "").lower()
    assert "judgedeceiver" in doc
    assert "shi" in doc
    assert "pointwise" in doc

    # Placate the linter about tmp_path being unused (it is: fixture only).
    del tmp_path
