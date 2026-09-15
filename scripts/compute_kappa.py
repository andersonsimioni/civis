"""
Compute Cohen's kappa for the CIVIS judge-vs-human agreement study.

The study protocol (docs/study_protocol.md) defines:
    - 30+ sessions, each scored on 4 criteria on a 0-5 ordinal scale
    - 3 raters: automated judge, human evaluator 1, human evaluator 2
    - Target: kappa >= 0.6 (Landis & Koch "substantial")

This script reads three CSVs in the format of data/study/evaluator_template.csv
and reports:
    - Per-criterion kappa for each rater pair
    - Aggregated kappa (N-weighted mean across criteria)
    - Unweighted, linear-weighted, and quadratic-weighted variants
    - Bootstrap 95% CI on the aggregate

Quadratic-weighted kappa is the primary reported metric because the score
scale is ordinal: disagreeing by 1 point is much less serious than
disagreeing by 4, and quadratic weights encode exactly that.

Usage:
    # Real data:
    python scripts/compute_kappa.py \\
        --judge data/study/judge_output_v1.csv \\
        --evaluator-1 data/study/evaluator_1_v1.csv \\
        --evaluator-2 data/study/evaluator_2_v1.csv \\
        --report reports/study_v1.md

    # Synthetic self-test (no external files needed):
    python scripts/compute_kappa.py --demo

Dependencies: standard library only. Deliberately no sklearn to keep this
runnable from a fresh clone with just Python 3.12.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

# Score scale from the rubric. Kept as constants (not magic numbers) so a
# future v2 rubric with a different scale needs a single edit.
SCORE_MIN = 0
SCORE_MAX = 5
SCORE_RANGE = tuple(range(SCORE_MIN, SCORE_MAX + 1))

# Criteria expected in every CSV. Order does not matter for kappa; this is
# just the canonical list used when writing the per-criterion report.
CRITERIA = (
    "fact_verification",
    "data_protection",
    "protocol_adherence",
    "communication",
)


@dataclass(frozen=True)
class Score:
    """One (session, criterion) row from a rater's CSV."""

    session_id: str
    criterion: str
    score: int


def load_scores(path: Path) -> dict[tuple[str, str], int]:
    """
    Read a rater CSV into a {(session_id, criterion): score} dict.

    Rows with empty `score` are skipped silently — that lets a partially-
    filled sheet be checked mid-study without crashing. Rows with invalid
    scores (out of range or non-integer) raise, because that is a data
    quality bug the coordinator must fix.
    """
    out: dict[tuple[str, str], int] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            raw = (row.get("score") or "").strip()
            if not raw:
                continue
            try:
                score = int(raw)
            except ValueError as exc:
                raise ValueError(
                    f"{path.name}:{row_num}: score '{raw}' is not an integer."
                ) from exc
            if score < SCORE_MIN or score > SCORE_MAX:
                raise ValueError(
                    f"{path.name}:{row_num}: score {score} outside "
                    f"[{SCORE_MIN}, {SCORE_MAX}]."
                )
            key = (row["session_id"], row["criterion"])
            if key in out:
                raise ValueError(
                    f"{path.name}:{row_num}: duplicate ({key[0]}, {key[1]})."
                )
            out[key] = score
    return out


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------

def _confusion(a: Sequence[int], b: Sequence[int]) -> list[list[int]]:
    """Confusion matrix over SCORE_RANGE. rows = rater A, cols = rater B."""
    n = len(SCORE_RANGE)
    matrix = [[0] * n for _ in range(n)]
    for x, y in zip(a, b, strict=True):
        matrix[x - SCORE_MIN][y - SCORE_MIN] += 1
    return matrix


def _kappa_from_confusion(matrix: list[list[int]], weighting: str) -> float:
    """
    Compute Cohen's kappa from a confusion matrix.

    weighting:
        - "unweighted": disagreements all count equally.
        - "linear": disagreement weight scales linearly with |i - j|.
        - "quadratic": disagreement weight scales with (i - j)^2. Primary
          metric for ordinal scales like ours.

    Formula (weighted): kappa = 1 - sum(w_ij * O_ij) / sum(w_ij * E_ij)
    where O is the observed frequency matrix (normalized), E is the
    expected frequency matrix under independence, and w_ij is the
    disagreement weight (0 on the diagonal).
    """
    n = len(matrix)
    total = sum(sum(row) for row in matrix)
    if total == 0:
        # No overlapping observations — kappa undefined. Return NaN so the
        # caller can flag this rather than showing a bogus 0 or 1.
        return float("nan")

    # Marginals for the expected matrix under independence.
    row_totals = [sum(row) for row in matrix]
    col_totals = [sum(matrix[r][c] for r in range(n)) for c in range(n)]

    # Weight matrix. Diagonal is 0 (perfect agreement, no penalty).
    max_diff = n - 1
    weights = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            diff = abs(i - j)
            if weighting == "unweighted":
                weights[i][j] = 0.0 if diff == 0 else 1.0
            elif weighting == "linear":
                weights[i][j] = diff / max_diff
            elif weighting == "quadratic":
                weights[i][j] = (diff / max_diff) ** 2
            else:
                raise ValueError(f"Unknown weighting: {weighting}")

    # Observed and expected disagreement, weighted.
    observed = sum(
        weights[i][j] * matrix[i][j]
        for i in range(n)
        for j in range(n)
    ) / total
    expected = sum(
        weights[i][j] * row_totals[i] * col_totals[j] / total
        for i in range(n)
        for j in range(n)
    ) / total

    if expected == 0:
        # All agreement expected by chance already — kappa undefined.
        return float("nan")
    return 1 - observed / expected


def cohen_kappa(
    a: Sequence[int],
    b: Sequence[int],
    weighting: str = "quadratic",
) -> float:
    """Public entry point: Cohen's kappa on two aligned score sequences."""
    return _kappa_from_confusion(_confusion(a, b), weighting)


# ---------------------------------------------------------------------------
# Study-level aggregation
# ---------------------------------------------------------------------------

@dataclass
class PairResult:
    """Kappa results for one rater pair, across all criteria."""

    name: str  # e.g. "judge vs evaluator_1"
    per_criterion: dict[str, float]  # {criterion: quadratic kappa}
    aggregate_quadratic: float
    aggregate_linear: float
    aggregate_unweighted: float
    aggregate_ci_low: float  # bootstrap 95% CI on quadratic
    aggregate_ci_high: float
    n_pairs: int  # total (session, criterion) rows compared


def _align(
    rater_x: dict[tuple[str, str], int],
    rater_y: dict[tuple[str, str], int],
    criterion: str | None = None,
) -> tuple[list[int], list[int]]:
    """
    Extract aligned score lists from two rater dicts.

    If `criterion` is given, only rows with that criterion are used.
    Rows present in one rater but not the other are dropped silently —
    partial coverage during collection is allowed.
    """
    keys_x = set(rater_x.keys())
    keys_y = set(rater_y.keys())
    shared = keys_x & keys_y
    if criterion is not None:
        shared = {k for k in shared if k[1] == criterion}
    ordered = sorted(shared)
    return [rater_x[k] for k in ordered], [rater_y[k] for k in ordered]


def _bootstrap_ci(
    a: Sequence[int],
    b: Sequence[int],
    weighting: str,
    n_samples: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Bootstrap 95% CI on kappa by resampling (a[i], b[i]) pairs with
    replacement. NaN samples (undefined kappa on a degenerate resample)
    are dropped rather than propagating.
    """
    rng = random.Random(seed)
    n = len(a)
    if n == 0:
        return float("nan"), float("nan")

    samples: list[float] = []
    for _ in range(n_samples):
        indices = [rng.randrange(n) for _ in range(n)]
        resampled_a = [a[i] for i in indices]
        resampled_b = [b[i] for i in indices]
        k = cohen_kappa(resampled_a, resampled_b, weighting=weighting)
        if k == k:  # not NaN
            samples.append(k)

    if not samples:
        return float("nan"), float("nan")

    samples.sort()
    low = samples[int(0.025 * len(samples))]
    high = samples[int(0.975 * len(samples))]
    return low, high


def compute_pair(
    name: str,
    rater_x: dict[tuple[str, str], int],
    rater_y: dict[tuple[str, str], int],
) -> PairResult:
    """Compute per-criterion and aggregate kappa for one rater pair."""
    per_criterion: dict[str, float] = {}
    for criterion in CRITERIA:
        x, y = _align(rater_x, rater_y, criterion=criterion)
        per_criterion[criterion] = cohen_kappa(x, y, weighting="quadratic")

    all_x, all_y = _align(rater_x, rater_y)
    quadratic = cohen_kappa(all_x, all_y, weighting="quadratic")
    linear = cohen_kappa(all_x, all_y, weighting="linear")
    unweighted = cohen_kappa(all_x, all_y, weighting="unweighted")
    ci_low, ci_high = _bootstrap_ci(all_x, all_y, weighting="quadratic")

    return PairResult(
        name=name,
        per_criterion=per_criterion,
        aggregate_quadratic=quadratic,
        aggregate_linear=linear,
        aggregate_unweighted=unweighted,
        aggregate_ci_low=ci_low,
        aggregate_ci_high=ci_high,
        n_pairs=len(all_x),
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_kappa(k: float) -> str:
    """Format kappa for display. NaN prints as '—' (undefined)."""
    if k != k:
        return "—"
    return f"{k:+.3f}" if k < 0 else f"{k:.3f}"


def interpret(k: float) -> str:
    """Landis & Koch 1977 verbal interpretation."""
    if k != k:
        return "indefinido"
    if k < 0:
        return "pior que acaso"
    if k <= 0.20:
        return "leve"
    if k <= 0.40:
        return "razoável"
    if k <= 0.60:
        return "moderada"
    if k <= 0.80:
        return "substancial"
    return "quase perfeita"


def render_report(results: list[PairResult]) -> str:
    """Markdown report ready to drop into reports/study_v*.md."""
    lines: list[str] = []
    lines.append("# CIVIS — Relatório do Estudo de Concordância")
    lines.append("")
    lines.append("Gerado por `scripts/compute_kappa.py`.")
    lines.append("")

    for result in results:
        lines.append(f"## {result.name}")
        lines.append("")
        lines.append(f"**N de linhas comparadas:** {result.n_pairs}")
        lines.append("")
        lines.append("### Kappa por critério (quadratic weighted)")
        lines.append("")
        lines.append("| Critério | Kappa | Interpretação |")
        lines.append("|---|---|---|")
        for criterion, k in result.per_criterion.items():
            lines.append(
                f"| {criterion} | {format_kappa(k)} | {interpret(k)} |"
            )
        lines.append("")
        lines.append("### Agregado (todas as sessões, todos os critérios)")
        lines.append("")
        lines.append("| Ponderação | Kappa |")
        lines.append("|---|---|")
        lines.append(
            f"| **quadratic (primária)** | "
            f"**{format_kappa(result.aggregate_quadratic)}** "
            f"({interpret(result.aggregate_quadratic)}) |"
        )
        lines.append(f"| linear | {format_kappa(result.aggregate_linear)} |")
        lines.append(f"| unweighted | {format_kappa(result.aggregate_unweighted)} |")
        lines.append("")
        lines.append(
            f"**IC 95% (bootstrap, quadratic):** "
            f"[{format_kappa(result.aggregate_ci_low)}, "
            f"{format_kappa(result.aggregate_ci_high)}]"
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Demo (self-test with synthetic data)
# ---------------------------------------------------------------------------

def _demo_data(
    n_sessions: int = 30,
    noise: float = 0.5,
    seed: int = 7,
) -> tuple[dict, dict, dict]:
    """
    Generate synthetic data where judge and human evaluators mostly agree,
    with `noise` controlling how often the human deviates by 1 point.
    Used to sanity-check the pipeline end-to-end without needing real CSVs.
    """
    rng = random.Random(seed)

    def perturb(true_score: int) -> int:
        if rng.random() < noise:
            delta = rng.choice([-1, 1])
            return max(SCORE_MIN, min(SCORE_MAX, true_score + delta))
        return true_score

    judge: dict[tuple[str, str], int] = {}
    evaluator_1: dict[tuple[str, str], int] = {}
    evaluator_2: dict[tuple[str, str], int] = {}

    for i in range(1, n_sessions + 1):
        session_id = f"synth_session_{i:03d}"
        for criterion in CRITERIA:
            # Truth centered around 3 (the middle of the scale).
            truth = rng.randint(SCORE_MIN + 1, SCORE_MAX - 1)
            key = (session_id, criterion)
            judge[key] = perturb(truth)
            evaluator_1[key] = perturb(truth)
            evaluator_2[key] = perturb(truth)

    return judge, evaluator_1, evaluator_2


def _run_demo(report_path: Path | None = None) -> int:
    """Run the demo path; return process exit code."""
    print("Running compute_kappa.py in demo mode (synthetic data).")
    judge, e1, e2 = _demo_data()
    results = [
        compute_pair("Juiz automático vs Avaliador 1", judge, e1),
        compute_pair("Juiz automático vs Avaliador 2", judge, e2),
        compute_pair("Avaliador 1 vs Avaliador 2 (sanity)", e1, e2),
    ]
    report = render_report(results)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        print(f"Demo report written to {report_path}")
    else:
        print(report)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    parser.add_argument("--judge", type=Path, help="CSV with judge scores.")
    parser.add_argument("--evaluator-1", type=Path, help="CSV with evaluator 1 scores.")
    parser.add_argument("--evaluator-2", type=Path, help="CSV with evaluator 2 scores.")
    parser.add_argument("--report", type=Path, help="Where to write the Markdown report.")
    parser.add_argument("--demo", action="store_true", help="Run on synthetic data.")
    args = parser.parse_args(argv)

    if args.demo:
        return _run_demo(report_path=args.report)

    required = [args.judge, args.evaluator_1, args.evaluator_2]
    if any(p is None for p in required):
        parser.error(
            "Real-mode requires --judge, --evaluator-1 and --evaluator-2, "
            "or use --demo for a synthetic self-test."
        )

    judge = load_scores(args.judge)
    e1 = load_scores(args.evaluator_1)
    e2 = load_scores(args.evaluator_2)

    results = [
        compute_pair("Juiz automático vs Avaliador 1", judge, e1),
        compute_pair("Juiz automático vs Avaliador 2", judge, e2),
        compute_pair("Avaliador 1 vs Avaliador 2 (sanity)", e1, e2),
    ]

    report = render_report(results)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
        print(f"Report written to {args.report}")
    else:
        print(report)

    # Verdict summary to stdout for CI-style piping.
    quadratic_kappas = [r.aggregate_quadratic for r in results[:2]]
    target = 0.6
    if all(k >= target for k in quadratic_kappas if k == k):
        print("\n[PASS] Both judge-vs-human kappas >= 0.6 (substantial).")
        return 0
    print(f"\n[FAIL] At least one judge-vs-human kappa below {target}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
