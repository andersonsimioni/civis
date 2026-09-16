"""
Tests for the pure aggregation functions in civis.web.metrics_calc.

These functions are the math behind the Métricas page: latency
percentiles per provider, cost summaries, histogram bucketing, and
extraction of security-report fields for M2 and JudgeDeceiver-pointwise.
Kept separate from the page renderer so we can pin their behaviour
without spinning up AppTest.
"""

from __future__ import annotations

from civis.web.data_access import TelemetryEntry
from civis.web.metrics_calc import (
    ProviderLatency,
    _label_sort_key,
    _percentile,
    cost_summary,
    judge_deceiver_asr_by_criterion,
    latency_bucket_histogram,
    latency_by_provider,
    owasp_defense_by_category,
)


def _entry(
    turn_index: int = 1,
    input_tokens: int = 100,
    output_tokens: int = 20,
    latency_ms: int = 500,
    provider_name: str = "ollama-llama3.1",
) -> TelemetryEntry:
    """Factory that fills sensible defaults so each test names only what matters."""
    return TelemetryEntry(
        turn_index=turn_index,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        provider_name=provider_name,
    )


# ---------------------------------------------------------------------------
# latency_by_provider
# ---------------------------------------------------------------------------


def test_latency_by_provider_returns_empty_list_for_no_entries() -> None:
    assert latency_by_provider([]) == []


def test_latency_by_provider_groups_by_name() -> None:
    entries = [
        _entry(latency_ms=100, provider_name="ollama"),
        _entry(latency_ms=200, provider_name="ollama"),
        _entry(latency_ms=500, provider_name="claude"),
    ]
    stats = latency_by_provider(entries)
    names = {s.provider_name for s in stats}
    assert names == {"ollama", "claude"}


def test_latency_by_provider_sorts_heaviest_first() -> None:
    """Ollama has 3 turns, claude has 1 → ollama comes first."""
    entries = [
        _entry(latency_ms=100, provider_name="ollama"),
        _entry(latency_ms=200, provider_name="ollama"),
        _entry(latency_ms=300, provider_name="ollama"),
        _entry(latency_ms=500, provider_name="claude"),
    ]
    stats = latency_by_provider(entries)
    assert stats[0].provider_name == "ollama"
    assert stats[0].turn_count == 3
    assert stats[1].provider_name == "claude"


def test_latency_by_provider_percentiles_match_nearest_rank() -> None:
    """Ten sorted latencies → p50=5th value, p95=10th value (nearest rank)."""
    entries = [
        _entry(latency_ms=lat, provider_name="ollama")
        for lat in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    ]
    stats = latency_by_provider(entries)
    assert len(stats) == 1
    stat = stats[0]
    assert isinstance(stat, ProviderLatency)
    assert stat.turn_count == 10
    # ceil(50/100 * 10) = 5 → sorted_lat[4] = 500
    assert stat.p50_ms == 500
    # ceil(95/100 * 10) = 10 → sorted_lat[9] = 1000
    assert stat.p95_ms == 1000
    assert stat.max_ms == 1000


def test_latency_by_provider_single_entry_reports_that_value_everywhere() -> None:
    """Degenerate case: 1 latency turns into p50 = p95 = max."""
    stats = latency_by_provider([_entry(latency_ms=750)])
    assert len(stats) == 1
    stat = stats[0]
    assert stat.p50_ms == 750
    assert stat.p95_ms == 750
    assert stat.max_ms == 750


# ---------------------------------------------------------------------------
# cost_summary
# ---------------------------------------------------------------------------


def test_cost_summary_returns_zero_for_no_entries() -> None:
    summary = cost_summary([], session_count=0)
    assert summary.total_usd == 0.0
    assert summary.total_turns == 0
    assert summary.average_usd_per_turn == 0.0
    assert summary.average_usd_per_session == 0.0


def test_cost_summary_ollama_stays_free() -> None:
    """Local providers price at zero → totals stay zero regardless of tokens."""
    entries = [
        _entry(input_tokens=1000, output_tokens=200, provider_name="ollama-llama3.1"),
        _entry(input_tokens=2000, output_tokens=300, provider_name="ollama-qwen"),
    ]
    summary = cost_summary(entries, session_count=2)
    assert summary.total_usd == 0.0
    assert summary.total_turns == 2
    assert summary.average_usd_per_session == 0.0


def test_cost_summary_claude_priced_via_pricing_module() -> None:
    """One Claude turn with 1M input + 1M output = $3 + $15 = $18."""
    entries = [
        _entry(input_tokens=1_000_000, output_tokens=1_000_000, provider_name="claude-3-5-sonnet"),
    ]
    summary = cost_summary(entries, session_count=1)
    assert summary.total_usd == 18.0
    assert summary.average_usd_per_turn == 18.0
    assert summary.average_usd_per_session == 18.0


def test_cost_summary_handles_zero_session_count_gracefully() -> None:
    """Guard against ZeroDivisionError when caller has entries but no sessions."""
    entries = [_entry(input_tokens=100, output_tokens=20, provider_name="claude")]
    summary = cost_summary(entries, session_count=0)
    # No session count → per-session drops to 0 rather than crashing.
    assert summary.average_usd_per_session == 0.0
    # per-turn keeps working — one turn produced some cost.
    assert summary.average_usd_per_turn > 0.0


# ---------------------------------------------------------------------------
# latency_bucket_histogram
# ---------------------------------------------------------------------------


def test_latency_bucket_histogram_empty_input_returns_empty_dict() -> None:
    assert latency_bucket_histogram([]) == {}


def test_latency_bucket_histogram_bins_are_left_inclusive_right_exclusive() -> None:
    """500 → '500-1000ms' (goes into next bucket, not the 0-500 one)."""
    entries = [
        _entry(latency_ms=0),
        _entry(latency_ms=499),
        _entry(latency_ms=500),
        _entry(latency_ms=999),
        _entry(latency_ms=1000),
    ]
    hist = latency_bucket_histogram(entries, bucket_ms=500, max_buckets=12)
    # 0 and 499 fall in bucket 0; 500 and 999 fall in bucket 1; 1000 in bucket 2.
    total_first = sum(count for label, count in hist.items() if "0-500" in label)
    assert total_first == 2


def test_latency_bucket_histogram_tail_bucket_absorbs_overflow() -> None:
    """Anything past bucket_ms * max_buckets collapses into the '<X>s+' label."""
    entries = [
        _entry(latency_ms=100),
        _entry(latency_ms=20_000),
        _entry(latency_ms=30_000),
    ]
    hist = latency_bucket_histogram(entries, bucket_ms=500, max_buckets=12)
    tail_labels = [label for label in hist if label.endswith("s+")]
    assert len(tail_labels) == 1
    assert hist[tail_labels[0]] == 2  # 20s and 30s both land in the tail.


def test_latency_bucket_histogram_preserves_left_to_right_order() -> None:
    """Keys returned in ascending order so st.bar_chart renders naturally."""
    entries = [
        _entry(latency_ms=2500),
        _entry(latency_ms=100),
        _entry(latency_ms=1200),
    ]
    hist = latency_bucket_histogram(entries, bucket_ms=500, max_buckets=12)
    leading_numbers = [_label_sort_key(k) for k in hist]
    assert leading_numbers == sorted(leading_numbers)


# ---------------------------------------------------------------------------
# owasp_defense_by_category
# ---------------------------------------------------------------------------


def test_owasp_defense_by_category_empty_payload() -> None:
    assert owasp_defense_by_category({}) == {}
    assert owasp_defense_by_category({"reports": []}) == {}


def test_owasp_defense_by_category_extracts_first_target() -> None:
    payload = {
        "reports": [
            {
                "by_category": {
                    "LLM01_prompt_injection": {"defended": 8, "leaked": 2},
                    "LLM06_sensitive_info_disclosure": {"defended": 10, "leaked": 0},
                }
            },
            # Second target is intentionally ignored — page shows only the first.
            {"by_category": {"LLM01_prompt_injection": {"defended": 0, "leaked": 5}}},
        ]
    }
    result = owasp_defense_by_category(payload)
    assert set(result.keys()) == {
        "LLM01_prompt_injection",
        "LLM06_sensitive_info_disclosure",
    }
    assert result["LLM01_prompt_injection"] == {"defended": 8, "leaked": 2}
    assert result["LLM06_sensitive_info_disclosure"] == {"defended": 10, "leaked": 0}


def test_owasp_defense_by_category_defaults_missing_counts_to_zero() -> None:
    payload = {"reports": [{"by_category": {"LLM01_prompt_injection": {}}}]}
    result = owasp_defense_by_category(payload)
    assert result == {"LLM01_prompt_injection": {"defended": 0, "leaked": 0}}


# ---------------------------------------------------------------------------
# judge_deceiver_asr_by_criterion
# ---------------------------------------------------------------------------


def test_judge_deceiver_asr_by_criterion_empty_payload() -> None:
    assert judge_deceiver_asr_by_criterion({}) == {}
    assert judge_deceiver_asr_by_criterion({"reports": []}) == {}


def test_judge_deceiver_asr_by_criterion_computes_success_ratio() -> None:
    payload = {
        "reports": [
            {
                "by_criterion": [
                    {"criterion": "protocol_adherence", "attempted": 10, "succeeded": 7},
                    {"criterion": "data_protection", "attempted": 5, "succeeded": 1},
                ]
            }
        ]
    }
    result = judge_deceiver_asr_by_criterion(payload)
    assert result["protocol_adherence"] == 0.7
    assert result["data_protection"] == 0.2


def test_judge_deceiver_asr_by_criterion_zero_attempted_does_not_crash() -> None:
    """Guard against ZeroDivisionError when a criterion has no attempts."""
    payload = {
        "reports": [
            {
                "by_criterion": [
                    {"criterion": "communication", "attempted": 0, "succeeded": 0}
                ]
            }
        ]
    }
    result = judge_deceiver_asr_by_criterion(payload)
    # attempted=0 falls back to 1 in the divisor; succeeded=0 → 0.0 ASR.
    assert result["communication"] == 0.0


# ---------------------------------------------------------------------------
# _percentile helper (internal but load-bearing)
# ---------------------------------------------------------------------------


def test_percentile_handles_empty_list() -> None:
    assert _percentile([], 50) == 0


def test_percentile_clamps_lower_and_upper_bounds() -> None:
    values = [10, 20, 30, 40]
    assert _percentile(values, 0) == 10
    assert _percentile(values, 100) == 40
    # Negative or >100 clamp too (defensive).
    assert _percentile(values, -5) == 10
    assert _percentile(values, 150) == 40
