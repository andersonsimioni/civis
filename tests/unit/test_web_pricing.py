"""
Tests for civis.web.pricing.

Cost model is a mock — the tests pin the prefixes and formulae so the
metrics page never silently drifts to zero for a known provider.
"""

from __future__ import annotations

from civis.web.pricing import (
    CLAUDE_SONNET_PRICING,
    LOCAL_PRICING,
    compute_turn_cost_usd,
    pricing_for_provider,
)


def test_claude_prefix_maps_to_sonnet_pricing() -> None:
    assert pricing_for_provider("claude-3-5-sonnet-20240620") == CLAUDE_SONNET_PRICING


def test_anthropic_prefix_maps_to_sonnet_pricing() -> None:
    assert pricing_for_provider("anthropic-claude-3-5") == CLAUDE_SONNET_PRICING


def test_ollama_prefix_maps_to_local_pricing() -> None:
    assert pricing_for_provider("ollama-llama3.1-8b") == LOCAL_PRICING


def test_unknown_provider_defaults_to_local_pricing() -> None:
    # A brand-new model id should not throw or add a false cost.
    assert pricing_for_provider("gpt-x-hypothetical") == LOCAL_PRICING


def test_case_insensitive_prefix_match() -> None:
    assert pricing_for_provider("Claude-3-Opus") == CLAUDE_SONNET_PRICING


def test_compute_turn_cost_matches_pricing_formula() -> None:
    # 1_000 in + 500 out against Claude Sonnet
    # = 1000 * 3 / 1e6 + 500 * 15 / 1e6 = 0.003 + 0.0075 = 0.0105 USD
    cost = compute_turn_cost_usd(1_000, 500, "claude-3-5-sonnet")
    assert cost == 0.0105


def test_compute_turn_cost_is_zero_for_local_provider() -> None:
    assert compute_turn_cost_usd(1_000, 500, "ollama-qwen2.5") == 0.0


def test_compute_turn_cost_rounded_to_6_decimals() -> None:
    # 1 input token against Sonnet = 3e-6; keep at least 6 decimals.
    cost = compute_turn_cost_usd(1, 0, "claude-3-5-sonnet")
    assert cost == 0.000003
