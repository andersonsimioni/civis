"""
CIVIS web UI — Streamlit app package.

Layout (Phase D):
    app.py             Entry point. `streamlit run src/civis/web/app.py`
                       wires the navigation tree.
    theme.py           Page config, palette, and shared CSS/copy constants.
    data_access.py     Pure read functions over data/sessions/ and reports/.
                       Never imports Streamlit — keeps unit tests fast.
    formatting.py      Human-facing formatters (currency, latency, badges).
    pricing.py         Cost model for M4 telemetry (Anthropic + Ollama).
    chat_view.py       Streamlit render of a transcript with turn highlight.
    verdict_view.py    Streamlit render of the judge verdict cards.
    pages/             One module per top-level page in the navigation.

Public UI language: pt-BR (the trainee is a Brazilian counter clerk).
Code, docstrings and identifiers: English.
"""
