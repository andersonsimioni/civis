"""
Human-facing formatters for the CIVIS Streamlit UI.

Pure string functions — no Streamlit imports — so every helper is unit
tested without spinning up an app. All output is pt-BR because the
audience is a Brazilian counter clerk (or a Brazilian investor).
"""

from __future__ import annotations

from datetime import datetime


def format_score_badge_html(score: int, color: str) -> str:
    """
    Return an HTML span that renders a score pill (0-5) on a coloured
    background. Callers embed the result in st.markdown(unsafe_allow_html).
    """
    safe_score = max(0, min(5, int(score)))
    return (
        f'<span class="civis-score-badge" style="background:{color};">'
        f"{safe_score}/5</span>"
    )


def format_score_average(scores: list[int]) -> str:
    """
    Average of a list of integer scores, formatted as 'X.X / 5.0'. Empty
    list returns '—' — 'zero' would misread as a real judgement.
    """
    if not scores:
        return "—"
    return f"{sum(scores) / len(scores):.1f} / 5,0"


def format_latency_ms(latency_ms: int | float) -> str:
    """
    Render latency in the most natural unit. Under one second we keep ms,
    otherwise seconds with one decimal — matches how humans quote them.
    """
    ms = float(latency_ms)
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000.0:.1f} s"


def format_currency_usd(amount_usd: float) -> str:
    """
    US-dollar amount with '$' and locale-friendly precision.

    Rules:
        - Under 1 cent: 4 decimals ($0.0032).
        - Under $1:      3 decimals ($0.421).
        - Otherwise:     2 decimals ($1.24).
    """
    if amount_usd < 0.01:
        return f"${amount_usd:.4f}"
    if amount_usd < 1.0:
        return f"${amount_usd:.3f}"
    return f"${amount_usd:.2f}"


def format_percent(fraction: float, decimals: int = 1) -> str:
    """0.037 → '3,7%' with pt-BR decimal separator."""
    text = f"{fraction * 100:.{decimals}f}"
    return text.replace(".", ",") + "%"


def format_session_datetime(iso_or_id: str) -> str:
    """
    Turn either an ISO timestamp or a session id ('YYYY-MM-DD_HHMMSS')
    into a friendly pt-BR string. Fallback is the raw value so we never
    break rendering because of a malformed timestamp.
    """
    # Try session-id shape first — that's what we get from filesystem listing.
    if len(iso_or_id) == 17 and iso_or_id[10] == "_":
        try:
            dt = datetime.strptime(iso_or_id, "%Y-%m-%d_%H%M%S")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return iso_or_id
    try:
        dt = datetime.fromisoformat(iso_or_id.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso_or_id


# pt-BR display labels for scenario ids. Kept in one place so pages agree.
SCENARIO_LABELS: dict[str, str] = {
    "certificate_duplicate_confused_v1": "Segunda via de certidão — confusa",
    "rg_urgent_aggressive_v1": "Segunda via de RG — agressivo",
    "certificate_thirdparty_fraudster_v1": "Certidão para terceiro — fraudador",
}


def scenario_label(scenario_id: str) -> str:
    """Return the friendly label for a scenario id, or the id itself."""
    return SCENARIO_LABELS.get(scenario_id, scenario_id)


# pt-BR criterion labels — the rubric enum values are English keys.
CRITERION_LABELS: dict[str, str] = {
    "fact_verification": "Verificação de dados",
    "data_protection": "Proteção de dados",
    "protocol_adherence": "Aderência ao protocolo",
    "communication": "Comunicação",
}


def criterion_label(criterion_key: str) -> str:
    """Return the pt-BR label for a rubric criterion key."""
    return CRITERION_LABELS.get(criterion_key, criterion_key)


# pt-BR OWASP LLM Top 10 labels. Only the categories that actually appear
# in the shipped bateria are covered; unknown keys pass through.
OWASP_LABELS: dict[str, str] = {
    "LLM01_prompt_injection": "LLM01 · Prompt injection",
    "LLM02_insecure_output_handling": "LLM02 · Saída insegura",
    "LLM06_sensitive_info_disclosure": "LLM06 · Vazamento de dados",
    "LLM07_insecure_plugin_design": "LLM07 · Plugins inseguros",
    "LLM10_model_theft": "LLM10 · Roubo de modelo",
}


def owasp_label(category_key: str) -> str:
    """Return the pt-BR label for an OWASP LLM category key."""
    return OWASP_LABELS.get(category_key, category_key)
