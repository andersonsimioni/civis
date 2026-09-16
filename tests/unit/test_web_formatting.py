"""
Tests for civis.web.formatting.

Pure string functions — a mismatch here would ship as a subtle UI bug,
so we pin the exact output shape.
"""

from __future__ import annotations

from civis.web.formatting import (
    criterion_label,
    format_currency_usd,
    format_latency_ms,
    format_percent,
    format_score_average,
    format_score_badge_html,
    format_session_datetime,
    owasp_label,
    scenario_label,
)


def test_score_badge_html_renders_score_and_colour() -> None:
    html = format_score_badge_html(4, "#3f8f4a")
    assert "4/5" in html
    assert "#3f8f4a" in html
    assert 'civis-score-badge' in html


def test_score_badge_clamps_out_of_range_score() -> None:
    assert "0/5" in format_score_badge_html(-1, "#000")
    assert "5/5" in format_score_badge_html(999, "#000")


def test_score_average_formats_with_ptbr_separator() -> None:
    assert format_score_average([5, 5, 4, 5]) == "4.8 / 5,0"


def test_score_average_returns_dash_when_empty() -> None:
    # An empty verdict is meaningless — 0.0 would misread as a failure.
    assert format_score_average([]) == "—"


def test_latency_ms_stays_in_ms_below_one_second() -> None:
    assert format_latency_ms(850) == "850 ms"


def test_latency_ms_switches_to_seconds() -> None:
    assert format_latency_ms(1240) == "1.2 s"


def test_currency_usd_uses_more_decimals_for_small_amounts() -> None:
    assert format_currency_usd(0.0032) == "$0.0032"
    assert format_currency_usd(0.421) == "$0.421"
    assert format_currency_usd(1.24) == "$1.24"


def test_format_percent_uses_ptbr_decimal() -> None:
    assert format_percent(0.037) == "3,7%"
    assert format_percent(1.0, decimals=0) == "100%"


def test_format_session_datetime_from_session_id() -> None:
    # Session-id shape 'YYYY-MM-DD_HHMMSS' → 'DD/MM/YYYY HH:MM'.
    assert format_session_datetime("2026-11-25_141200") == "25/11/2026 14:12"


def test_format_session_datetime_from_iso() -> None:
    assert format_session_datetime("2026-11-25T14:12:00+00:00") == "25/11/2026 14:12"


def test_format_session_datetime_falls_back_to_raw() -> None:
    # Should never raise, even for malformed input.
    assert format_session_datetime("not-a-timestamp") == "not-a-timestamp"


def test_scenario_label_translates_known_id() -> None:
    assert scenario_label("certificate_duplicate_confused_v1").startswith("Segunda via")


def test_scenario_label_passes_through_unknown() -> None:
    assert scenario_label("unknown_scenario_v42") == "unknown_scenario_v42"


def test_criterion_label_translates_known_key() -> None:
    assert criterion_label("data_protection") == "Proteção de dados"


def test_owasp_label_translates_known_key() -> None:
    assert owasp_label("LLM06_sensitive_info_disclosure").startswith("LLM06")


def test_owasp_label_passes_through_unknown() -> None:
    assert owasp_label("LLM99_new") == "LLM99_new"
