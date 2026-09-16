"""
Pure aggregation math for the Métricas page.

Kept separate from the Streamlit page so the formulas are testable and
so the page module stays a thin renderer. Every function is a pure
function of TelemetryEntry lists and adversarial-report dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from civis.web.data_access import TelemetryEntry
from civis.web.pricing import compute_turn_cost_usd


@dataclass(frozen=True)
class ProviderLatency:
    """Latency stats aggregated for one provider."""

    provider_name: str
    turn_count: int
    p50_ms: int
    p95_ms: int
    max_ms: int


@dataclass(frozen=True)
class CostSummary:
    """Aggregated cost across a set of telemetry entries."""

    total_usd: float
    total_turns: int
    average_usd_per_turn: float
    average_usd_per_session: float


def latency_by_provider(entries: list[TelemetryEntry]) -> list[ProviderLatency]:
    """
    Group telemetry entries by provider_name and return latency stats
    for each. Providers are sorted by turn_count descending — the
    heaviest provider gets top billing on the page.
    """
    by_provider: dict[str, list[int]] = {}
    for row in entries:
        by_provider.setdefault(row.provider_name, []).append(row.latency_ms)

    stats: list[ProviderLatency] = []
    for name, latencies in by_provider.items():
        sorted_lat = sorted(latencies)
        stats.append(
            ProviderLatency(
                provider_name=name,
                turn_count=len(latencies),
                p50_ms=_percentile(sorted_lat, 50),
                p95_ms=_percentile(sorted_lat, 95),
                max_ms=sorted_lat[-1],
            )
        )
    stats.sort(key=lambda p: p.turn_count, reverse=True)
    return stats


def cost_summary(
    entries: list[TelemetryEntry],
    session_count: int,
) -> CostSummary:
    """
    Total USD across every entry, split into a per-turn and per-session
    average. `session_count` comes from the caller because a telemetry
    list alone cannot tell you how many sessions produced it.
    """
    total = 0.0
    for row in entries:
        total += compute_turn_cost_usd(
            row.input_tokens,
            row.output_tokens,
            row.provider_name,
        )
    total_turns = len(entries)
    return CostSummary(
        total_usd=round(total, 4),
        total_turns=total_turns,
        average_usd_per_turn=round(total / total_turns, 4) if total_turns else 0.0,
        average_usd_per_session=(
            round(total / session_count, 4) if session_count > 0 else 0.0
        ),
    )


def latency_bucket_histogram(
    entries: list[TelemetryEntry],
    bucket_ms: int = 500,
    max_buckets: int = 12,
) -> dict[str, int]:
    """
    Bucket latencies into fixed-width bins ('0-500 ms', '500-1000 ms',
    ...) so `st.bar_chart` can render a histogram without pandas
    scaffolding. Anything past `max_buckets * bucket_ms` folds into a
    single 'X+ ms' tail bucket.

    Returns an ordered dict-like { bucket_label: count }. Keys are
    formatted so the natural string sort matches the numeric order.
    """
    buckets: dict[str, int] = {}
    limit = bucket_ms * max_buckets
    for row in entries:
        if row.latency_ms >= limit:
            label = f"{limit // 1000:>2d}s+"
        else:
            bin_index = row.latency_ms // bucket_ms
            lo_ms = bin_index * bucket_ms
            hi_ms = lo_ms + bucket_ms
            label = f"{lo_ms:>4d}-{hi_ms}ms"
        buckets[label] = buckets.get(label, 0) + 1
    # Order labels by their leading digit so the chart reads left-to-right.
    return dict(sorted(buckets.items(), key=lambda kv: _label_sort_key(kv[0])))


def owasp_defense_by_category(
    adversarial_payload: dict,
) -> dict[str, dict[str, int]]:
    """
    Extract the 'by_category' map from the first target in the
    adversarial report. Structure keeps 'defended' and 'leaked' side by
    side so the page can render a stacked bar chart.
    """
    reports = adversarial_payload.get("reports", [])
    if not reports:
        return {}
    first = reports[0]
    result: dict[str, dict[str, int]] = {}
    for category, counts in first.get("by_category", {}).items():
        result[category] = {
            "defended": counts.get("defended", 0),
            "leaked": counts.get("leaked", 0),
        }
    return result


def judge_deceiver_asr_by_criterion(
    judge_deceiver_payload: dict,
) -> dict[str, float]:
    """
    Return the ASR (attack success rate) per criterion for the first
    judge target in the report. Values are floats in [0, 1].
    """
    reports = judge_deceiver_payload.get("reports", [])
    if not reports:
        return {}
    first = reports[0]
    result: dict[str, float] = {}
    for row in first.get("by_criterion", []):
        attempted = row.get("attempted", 0) or 1  # avoid ZeroDivisionError
        succeeded = row.get("succeeded", 0)
        result[row["criterion"]] = round(succeeded / attempted, 4)
    return result


# ---- helpers ---------------------------------------------------------------


def _percentile(sorted_values: list[int], percentile: int) -> int:
    """
    Nearest-rank percentile — simple, no interpolation. Rounds up to
    match the classical definition ("smallest value below which
    percentile% of the data falls").
    """
    if not sorted_values:
        return 0
    if percentile <= 0:
        return sorted_values[0]
    if percentile >= 100:
        return sorted_values[-1]
    rank = ceil(percentile / 100.0 * len(sorted_values))
    return sorted_values[rank - 1]


def _label_sort_key(label: str) -> int:
    """
    Turn a bucket label back into its leading integer so a dict sorted
    by this function orders '0-500ms' < '500-1000ms' < '5000-5500ms'.
    """
    number = ""
    for ch in label:
        if ch.isdigit():
            number += ch
        elif number:
            break
    return int(number) if number else 0
