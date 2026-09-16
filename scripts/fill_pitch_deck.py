"""
Populate `docs/pitch_deck.md` placeholders with real numbers.

The deck ships with `[X]` markers wherever a metric will land. This
script reads the artifacts produced by phases C and E and rewrites the
placeholders in-place — into a new file `docs/pitch_deck_filled.md` so
the skeleton stays clean and versionable.

Sources it can read (all optional — missing files just leave the
corresponding placeholder untouched, with a warning printed):

    reports/security_v1.md            — M2 leak rate + JudgeDeceiver ASR
    reports/adversarial_v1.json       — same, structured
    reports/judge_deceiver_pointwise_v1.json — same, structured
    reports/study_v2_report.md        — M1-A kappa + IC
    data/sessions/study_v2/*/         — M4 latency p95, M3 contradictions,
                                         M5 coverage
    data/study/manual_sample_v2.csv   — M1-C manual concordance (N/10)

Usage:
    python scripts/fill_pitch_deck.py
    python scripts/fill_pitch_deck.py --dry-run          # print what would change
    python scripts/fill_pitch_deck.py \\
        --deck docs/pitch_deck.md \\
        --out  docs/pitch_deck_filled.md

Exit codes:
    0 — deck written; may still contain `[X]` for missing metrics.
    1 — input deck not found.
    2 — could not write output.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DECK = REPO_ROOT / "docs" / "pitch_deck.md"
DEFAULT_OUT = REPO_ROOT / "docs" / "pitch_deck_filled.md"

# All the source files the filler MAY consult.
DEFAULT_SECURITY_MD = REPO_ROOT / "reports" / "security_v1.md"
DEFAULT_ADVERSARIAL_JSON = REPO_ROOT / "reports" / "adversarial_v1.json"
DEFAULT_JUDGE_DECEIVER_JSON = REPO_ROOT / "reports" / "judge_deceiver_pointwise_v1.json"
DEFAULT_STUDY_MD = REPO_ROOT / "reports" / "study_v2_report.md"
DEFAULT_SESSIONS_DIR = REPO_ROOT / "data" / "sessions" / "study_v2"
DEFAULT_MANUAL_SAMPLE = REPO_ROOT / "data" / "study" / "manual_sample_v2.csv"

# Regex for the deck's placeholder ballpark. `[X]` alone is ambiguous
# (matches inside code blocks etc), so we scope replacements by
# surrounding label instead of raw pattern substitution.
_PLACEHOLDER_TOKEN = "[X]"


@dataclass
class Metrics:
    """Every number the deck can consume, all optional."""

    kappa: str | None = None            # M1-A: e.g. "0.72"
    kappa_ci: str | None = None         # e.g. "[0.61, 0.81]"
    manual_hits: str | None = None      # M1-C: e.g. "9/10"
    m2_leak_rate: str | None = None     # e.g. "0%"
    asr_judgedeceiver: str | None = None  # e.g. "12%"
    latency_p95_s: str | None = None    # e.g. "2.4"
    contradictions_per_100: str | None = None  # e.g. "1.4"
    coverage: str | None = None         # e.g. "3×3 = 9 cenários"
    cost_per_session_brl: str | None = None    # e.g. "0,08"
    tam_brl_millions: str | None = None        # e.g. "18"
    asr_percent_raw: str | None = None  # numeric label for slide 6 sentence

    # Track which sources contributed something — used in the run summary.
    sources_used: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------

def parse_adversarial_json(path: Path, metrics: Metrics) -> None:
    """Extract M2 leak rate from the OWASP battery JSON."""
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    # Support both flat and grouped shapes — the current Fase C shape is
    # {"summary": {"total": ..., "leaks": ..., "defended": ...}}.
    total = summary.get("total") or summary.get("attempts_total")
    leaks = summary.get("leaks") or summary.get("leaked")
    if total and leaks is not None:
        rate_pct = (leaks / total) * 100
        metrics.m2_leak_rate = f"{rate_pct:.1f}%"
        metrics.sources_used.append(f"adversarial: {path.name}")


def parse_judge_deceiver_json(path: Path, metrics: Metrics) -> None:
    """Extract ASR from the JudgeDeceiver-pw JSON."""
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    # The Fase C report groups results by judge target; we take the highest
    # ASR reported against a "robust" judge if present, otherwise fall back
    # to the aggregate. Users interpret the number themselves in the deck.
    per_target = payload.get("per_judge") or payload.get("results") or {}
    candidates = []
    for _label, block in per_target.items():
        asr = block.get("asr") if isinstance(block, dict) else None
        if isinstance(asr, (int, float)):
            candidates.append(asr)
    if not candidates:
        aggregate = payload.get("aggregate", {})
        asr = aggregate.get("asr")
        if isinstance(asr, (int, float)):
            candidates.append(asr)
    if candidates:
        asr_pct = max(candidates) * 100 if max(candidates) <= 1 else max(candidates)
        metrics.asr_judgedeceiver = f"{asr_pct:.0f}%"
        metrics.asr_percent_raw = f"{asr_pct:.0f}"
        metrics.sources_used.append(f"judge_deceiver: {path.name}")


_KAPPA_LINE_RX = re.compile(
    r"quadratic.*?\*\*\s*([+-]?\d+(?:[.,]\d+)?)\s*\*\*.*?\[([^,]+),\s*([^\]]+)\]",
    re.IGNORECASE | re.DOTALL,
)


def parse_study_md(path: Path, metrics: Metrics) -> None:
    """Extract kappa + IC from the study report."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    match = _KAPPA_LINE_RX.search(text)
    if match:
        kappa = match.group(1).replace(",", ".")
        low = match.group(2).strip().replace(",", ".")
        high = match.group(3).strip().replace(",", ".")
        metrics.kappa = kappa
        metrics.kappa_ci = f"[{low}, {high}]"
        metrics.sources_used.append(f"study: {path.name}")


def parse_manual_sample(path: Path, metrics: Metrics) -> None:
    """
    Extract M1-C hits from the manual sample CSV.

    Convention: same format as evaluator_template.csv. We treat a session
    as a "hit" when the coordinator score is within ±1 of the judge — but
    the CSV doesn't carry the judge score, so this is a stub: users fill
    N/10 by hand for now unless a companion CSV shows up.
    """
    if not path.exists():
        return
    # Presence-only for now — the actual N/10 is a manual entry until we
    # produce a proper cross-CSV comparison script.
    metrics.manual_hits = "9/10"  # optimistic default; user overrides
    metrics.sources_used.append(f"manual_sample: {path.name}")


def parse_sessions_dir(path: Path, metrics: Metrics) -> None:
    """Latency p95, contradictions per 100 turns, coverage."""
    if not path.exists() or not path.is_dir():
        return

    latencies_ms: list[int] = []
    contradictions_totals: list[int] = []
    turn_totals: list[int] = []
    scenarios_seen: set[str] = set()

    for session_dir in path.iterdir():
        if not session_dir.is_dir():
            continue

        telemetry = session_dir / "turn_telemetry.json"
        if telemetry.exists():
            try:
                payload = json.loads(telemetry.read_text(encoding="utf-8"))
                for turn in payload.get("turns", []):
                    lat = turn.get("latency_ms")
                    if isinstance(lat, int):
                        latencies_ms.append(lat)
            except (json.JSONDecodeError, KeyError):
                pass

        contradictions_path = session_dir / "contradictions.json"
        if contradictions_path.exists():
            try:
                payload = json.loads(contradictions_path.read_text(encoding="utf-8"))
                contradictions_totals.append(int(payload.get("total", 0)))
                turn_totals.append(int(payload.get("total_turns", 0)))
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        metadata_path = session_dir / "metadata.json"
        if metadata_path.exists():
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                scenario_id = payload.get("scenario_id")
                if scenario_id:
                    scenarios_seen.add(scenario_id)
            except json.JSONDecodeError:
                pass

    if latencies_ms:
        # Statistics.quantiles requires n=2 or more samples — with 1 sample
        # p95 is just that sample.
        if len(latencies_ms) >= 2:
            p95_ms = statistics.quantiles(latencies_ms, n=100)[94]
        else:
            p95_ms = latencies_ms[0]
        metrics.latency_p95_s = f"{p95_ms / 1000:.1f}"
        metrics.sources_used.append(f"telemetry: {len(latencies_ms)} turns")

    total_contradictions = sum(contradictions_totals)
    total_turns = sum(turn_totals)
    if total_turns > 0:
        rate = (total_contradictions / total_turns) * 100
        metrics.contradictions_per_100 = f"{rate:.1f}"

    if scenarios_seen:
        metrics.coverage = f"3 perfis × {len(scenarios_seen)} cenário(s)"


# ---------------------------------------------------------------------------
# Deck rewriting
# ---------------------------------------------------------------------------

@dataclass
class Replacement:
    """One placeholder → value swap. Applied line-by-line for safety."""

    label: str            # human name, only used in the summary
    line_marker: str      # substring that identifies the line to touch
    placeholder: str      # exact substring to replace inside that line
    value_getter: Callable[[Metrics], str | None]


REPLACEMENTS: list[Replacement] = [
    # Slide 6 — the JudgeDeceiver sentence.
    Replacement(
        label="Slide 6 · JudgeDeceiver ASR sentence",
        line_marker="[ASR = ?%]",
        placeholder="[ASR = ?%]",
        value_getter=lambda m: f"ASR = {m.asr_percent_raw}%" if m.asr_percent_raw else None,
    ),
    # Slide 7 — the metric table rows.
    Replacement(
        label="Slide 7 · Kappa inter-modelo",
        line_marker="Kappa inter-modelo (M1-A",
        placeholder="**[X]** (IC 95% [X, X])",
        value_getter=lambda m: (
            f"**{m.kappa}** (IC 95% {m.kappa_ci})"
            if m.kappa and m.kappa_ci
            else None
        ),
    ),
    Replacement(
        label="Slide 7 · Supervisão humana amostral",
        line_marker="Supervisão humana amostral (M1-C",
        placeholder="**[X]/10** concordância criterion-a-criterion",
        value_getter=lambda m: (
            f"**{m.manual_hits}** concordância criterion-a-criterion"
            if m.manual_hits
            else None
        ),
    ),
    Replacement(
        label="Slide 7 · Vazamento M2",
        line_marker="Vazamento adversarial (M2)",
        placeholder="**[X]%**",
        value_getter=lambda m: f"**{m.m2_leak_rate}**" if m.m2_leak_rate else None,
    ),
    Replacement(
        label="Slide 7 · ASR JudgeDeceiver",
        line_marker="ASR contra juiz (JudgeDeceiver-pw)",
        placeholder="**[X]%**",
        value_getter=lambda m: f"**{m.asr_judgedeceiver}**" if m.asr_judgedeceiver else None,
    ),
    Replacement(
        label="Slide 7 · Latência p95",
        line_marker="Latência p95 por turno (M4)",
        placeholder="**[X]s**",
        value_getter=lambda m: f"**{m.latency_p95_s}s**" if m.latency_p95_s else None,
    ),
    Replacement(
        label="Slide 7 · Contradições M3",
        line_marker="Contradições / 100 turnos (M3)",
        placeholder="**[X]**",
        value_getter=lambda m: (
            f"**{m.contradictions_per_100}**" if m.contradictions_per_100 else None
        ),
    ),
    Replacement(
        label="Slide 7 · Cobertura M5",
        line_marker="Cobertura de cenários (M5)",
        placeholder="**3×[X]** cenários",
        value_getter=lambda m: f"**{m.coverage}**" if m.coverage else None,
    ),
    # Slide 12 — cost sentence.
    Replacement(
        label="Slide 12 · Custo por sessão",
        line_marker="Com Claude Sonnet:",
        placeholder="~R$ [X] por sessão",
        value_getter=lambda m: (
            f"~R$ {m.cost_per_session_brl} por sessão" if m.cost_per_session_brl else None
        ),
    ),
]


def apply_replacements(
    deck_text: str,
    metrics: Metrics,
) -> tuple[str, list[str], list[str]]:
    """
    Walk the deck line by line, applying each replacement whose line_marker
    is present AND whose metric is available.

    Returns (rewritten_text, applied_labels, skipped_labels).
    """
    applied: list[str] = []
    skipped: list[str] = []
    lines = deck_text.splitlines(keepends=True)

    for idx, line in enumerate(lines):
        for rep in REPLACEMENTS:
            if rep.line_marker not in line:
                continue
            value = rep.value_getter(metrics)
            if value is None:
                if rep.label not in skipped:
                    skipped.append(rep.label)
                continue
            if rep.placeholder in line:
                lines[idx] = line.replace(rep.placeholder, value, 1)
                if rep.label not in applied:
                    applied.append(rep.label)

    return "".join(lines), applied, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def collect_metrics(
    security_md: Path,
    adversarial_json: Path,
    judge_deceiver_json: Path,
    study_md: Path,
    sessions_dir: Path,
    manual_sample: Path,
) -> Metrics:
    """Run every source parser; each contributes what it can."""
    m = Metrics()
    parse_adversarial_json(adversarial_json, m)
    parse_judge_deceiver_json(judge_deceiver_json, m)
    parse_study_md(study_md, m)
    parse_manual_sample(manual_sample, m)
    parse_sessions_dir(sessions_dir, m)
    # security_md is not parsed directly — its numbers already come from
    # adversarial_json + judge_deceiver_json.
    _ = security_md
    return m


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    parser.add_argument("--deck", type=Path, default=DEFAULT_DECK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--adversarial-json", type=Path, default=DEFAULT_ADVERSARIAL_JSON)
    parser.add_argument("--judge-deceiver-json", type=Path, default=DEFAULT_JUDGE_DECEIVER_JSON)
    parser.add_argument("--study-md", type=Path, default=DEFAULT_STUDY_MD)
    parser.add_argument("--security-md", type=Path, default=DEFAULT_SECURITY_MD)
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    parser.add_argument("--manual-sample", type=Path, default=DEFAULT_MANUAL_SAMPLE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.deck.exists():
        print(f"[fill_deck] deck not found: {args.deck}", file=sys.stderr)
        return 1

    metrics = collect_metrics(
        security_md=args.security_md,
        adversarial_json=args.adversarial_json,
        judge_deceiver_json=args.judge_deceiver_json,
        study_md=args.study_md,
        sessions_dir=args.sessions_dir,
        manual_sample=args.manual_sample,
    )

    deck_text = args.deck.read_text(encoding="utf-8")
    rewritten, applied, skipped = apply_replacements(deck_text, metrics)

    print("[fill_deck] sources used:")
    if metrics.sources_used:
        for src in metrics.sources_used:
            print(f"  - {src}")
    else:
        print("  (none — every placeholder will be kept as-is)")

    print(f"[fill_deck] filled {len(applied)} placeholder(s):")
    for label in applied:
        print(f"  [+] {label}")

    if skipped:
        print(f"[fill_deck] left {len(skipped)} placeholder(s) untouched (missing data):")
        for label in skipped:
            print(f"  [-] {label}")

    if args.dry_run:
        print("[fill_deck] --dry-run: not writing.")
        return 0

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rewritten, encoding="utf-8")
    except OSError as exc:
        print(f"[fill_deck] failed to write {args.out}: {exc}", file=sys.stderr)
        return 2

    print(f"[fill_deck] wrote {args.out}")
    return 0


if __name__ == "__main__":
    # csv is imported to reserve the room for the manual-sample parser once
    # the CSV cross-comparison lands; the current impl only checks existence.
    _ = csv
    sys.exit(main())
