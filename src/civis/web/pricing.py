"""
Provider pricing model for M4 telemetry.

The Streamlit "Métricas" page multiplies token counts by these prices to
show an estimated per-session cost. Numbers below are documented mock
values — the point is to show a cost line on the pitch deck, not to
invoice anybody.

Prices are in USD per 1 million tokens (in / out). Ollama runs locally,
so both prices are zero. Provider names are matched by prefix so a full
name like "claude-3-5-sonnet-20240620" is priced with the "claude-*"
entry — this survives Anthropic's version bumps without a code change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPricing:
    """Cost per 1M tokens, split by direction."""

    input_usd_per_million: float
    output_usd_per_million: float


# Anthropic Claude Sonnet public list price as of the 2026-Q1 catalogue.
# See docs/ROADMAP_PITCH.md §5-D for the sourcing note; numbers may drift.
CLAUDE_SONNET_PRICING = ProviderPricing(
    input_usd_per_million=3.0,
    output_usd_per_million=15.0,
)
# Local inference: no API cost. GPU electricity is out of scope for the
# per-session mock; we surface it in the copy of the metrics page instead.
LOCAL_PRICING = ProviderPricing(
    input_usd_per_million=0.0,
    output_usd_per_million=0.0,
)


# Longest-prefix match is intentional so "claude-3-5-sonnet-*" hits the
# claude entry before any shorter fallback would swallow it.
_PROVIDER_PRICING_BY_PREFIX: list[tuple[str, ProviderPricing]] = [
    ("claude", CLAUDE_SONNET_PRICING),
    ("anthropic", CLAUDE_SONNET_PRICING),
    ("ollama", LOCAL_PRICING),
    ("qwen", LOCAL_PRICING),
    ("llama", LOCAL_PRICING),
    # Explicit mock providers used in adversarial tests and the demo mode.
    ("mock", LOCAL_PRICING),
    ("fake", LOCAL_PRICING),
]


def pricing_for_provider(provider_name: str) -> ProviderPricing:
    """
    Look up pricing for a provider by longest-prefix match.

    Unknown providers return LOCAL_PRICING (zero) so the cost panel
    degrades gracefully rather than throwing on a new model id.
    """
    normalised = provider_name.strip().lower()
    for prefix, pricing in _PROVIDER_PRICING_BY_PREFIX:
        if normalised.startswith(prefix):
            return pricing
    return LOCAL_PRICING


def compute_turn_cost_usd(
    input_tokens: int,
    output_tokens: int,
    provider_name: str,
) -> float:
    """
    Estimated USD cost of a single turn's tokens under the price model.

    Rounded to 6 decimals — for a typical 400-token turn against Claude,
    that's roughly $0.005; less precision would collapse to $0.00 when
    summed and formatted.
    """
    pricing = pricing_for_provider(provider_name)
    cost = (
        input_tokens * pricing.input_usd_per_million / 1_000_000.0
        + output_tokens * pricing.output_usd_per_million / 1_000_000.0
    )
    return round(cost, 6)
