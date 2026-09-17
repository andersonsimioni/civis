"""
Canonical set of categories for scenario classification.

Onda 4 (S4.1) introduces an optional ``category`` field on
``ScenarioFile`` so the landing UI can group / filter scenarios by
what they cover in a real registry office (nascimento, casamento,
divorcio, ...). This module owns:

    * ``CANONICAL_CATEGORIES``    — the closed set of accepted values.
    * ``FALLBACK_CATEGORY``       — the bucket a scenario ends up in when
                                    the YAML omits ``category``.
    * ``CATEGORY_LABELS``         — pt-BR labels for the UI dropdown.
    * ``CATEGORY_ICONS``          — one-emoji anchors for the cards.
    * ``normalize_category``      — validation helper used by the
                                    ScenarioFile model validator.

Keeping the list here (instead of an Enum) buys forward compatibility:
adding a new category later is a single-line change and does not force
callers to import a new symbol just to reference the string value.
"""

from __future__ import annotations

# Closed set — anything outside this list rejected at load time.
# Order matters for the UI dropdown (list-order = display-order).
CANONICAL_CATEGORIES: tuple[str, ...] = (
    "nascimento",
    "casamento",
    "obito",
    "divorcio",
    "reconhecimento_paternidade",
    "alteracao_nome",
    "uniao_estavel",
    "averbacao",
    "retificacao",
    "emancipacao",
    "outros",
)

# What we bucket a scenario into when the YAML omits ``category``.
# ``"outros"`` is the safe default — it never claims a scope the
# author did not commit to.
FALLBACK_CATEGORY: str = "outros"

# pt-BR labels used by the landing dropdown.
CATEGORY_LABELS: dict[str, str] = {
    "nascimento": "Nascimento",
    "casamento": "Casamento",
    "obito": "Óbito",
    "divorcio": "Divórcio",
    "reconhecimento_paternidade": "Reconhecimento de paternidade",
    "alteracao_nome": "Alteração de nome",
    "uniao_estavel": "União estável",
    "averbacao": "Averbação",
    "retificacao": "Retificação",
    "emancipacao": "Emancipação",
    "outros": "Outros",
}

# One-emoji anchors per category — shown on the card header and in the
# category dropdown so the eye scans faster than reading labels.
CATEGORY_ICONS: dict[str, str] = {
    "nascimento": "👶",
    "casamento": "🤝",
    "obito": "⚰️",
    "divorcio": "✂️",
    "reconhecimento_paternidade": "🧬",
    "alteracao_nome": "✍️",
    "uniao_estavel": "💞",
    "averbacao": "📎",
    "retificacao": "🩹",
    "emancipacao": "🕊️",
    "outros": "📂",
}


def normalize_category(raw: str | None) -> str:
    """Return a canonical category value or raise ``ValueError``.

    ``None`` and the empty string map to the fallback bucket (``outros``)
    so a scenario without an explicit ``category`` still sorts into a
    valid drawer.

    Any other value must appear in :data:`CANONICAL_CATEGORIES`; a typo
    is a load-time error, not a silent mis-bucket.
    """
    if raw is None or raw == "":
        return FALLBACK_CATEGORY
    if raw not in CANONICAL_CATEGORIES:
        raise ValueError(
            f"Unknown scenario category '{raw}'. "
            f"Canonical values: {list(CANONICAL_CATEGORIES)}."
        )
    return raw
