"""
Flexible fact-value matching for the persona-reply "did she confirm it?"
check that drives:

- ``PersonaState.revealed_fact_keys`` (which then unlocks action buttons
  in the web UI via the ``requires`` gate).
- Contradiction detection (needs to know when the persona claims a
  different value for a fact she already stated).

Original behaviour was literal substring match (lowercased). It broke on
the very first thing users try: a persona (or a paraphrase-happy model
like DeepSeek Chat) says "12/03/1954" instead of the YAML's
"12 de março de 1954" and the button stays greyed out.

We layer three matchers, cheapest first, and short-circuit on the first
hit:

1. **Normalized substring**: strips diacritics, lowercases, collapses
   whitespace/punctuation. Handles casing, accents, quote marks.
2. **Date-shape match**: if the fact value parses as a date ("12 de
   março de 1954"), we accept the reply if any of a small set of
   canonical variants appears (12/03/1954, 12-03-1954, "12 março 1954",
   digits-only DDMMYYYY, etc.), plus the day+month+year triple.
3. **Multi-word overlap**: for long values (names, addresses), accept
   when ≥60% of the meaningful word tokens overlap. Prevents "Maria das
   Graças Silva" from failing when the persona says "Maria das Graças".

Facts can override the whole thing with an explicit
``revealed_patterns`` list — any of those strings, matched against the
normalized reply, counts as a hit. Escape hatch for weird cases the
heuristics miss.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from datetime import date

# Portuguese month names (lowercase, no diacritics because we normalize
# before comparing) — enough to parse "12 de março de 1954" and produce
# the alternate forms the persona is likely to emit.
_MONTHS_PT: dict[str, int] = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_MONTH_NAME_BY_NUM: dict[int, str] = {v: k for k, v in _MONTHS_PT.items()}

# Word-overlap threshold for multi-word values (names, addresses).
# Empirically 0.6 stops "Maria das Graças" vs "Maria das Graças Silva
# Pereira" from failing while still rejecting "Maria Silva" (which
# would be a different person).
_WORD_OVERLAP_THRESHOLD = 0.6

# Below this word count we don't attempt overlap matching — a two-word
# name is either a substring hit or nothing, otherwise "de" alone would
# match half the transcripts.
_MIN_WORDS_FOR_OVERLAP = 3

# Only alphanumerics survive normalization; everything else collapses to
# a single space so "12/03/1954" and "12 03 1954" become the same string
# after normalize_text.
_KEEP_ALPHANUM = re.compile(r"[^\w\s]", flags=re.UNICODE)
_COLLAPSE_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """
    Lowercase, strip diacritics, collapse punctuation and whitespace.

        >>> normalize_text("12 de Março de 1954!")
        '12 de marco de 1954'
        >>> normalize_text("Florianópolis, SC")
        'florianopolis sc'
    """
    lowered = text.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    ascii_only = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    punct_stripped = _KEEP_ALPHANUM.sub(" ", ascii_only)
    return _COLLAPSE_WS.sub(" ", punct_stripped).strip()


# ---------------------------------------------------------------------------
# Date parsing / expansion
# ---------------------------------------------------------------------------

# "12 de março de 1954" (normalize_text already stripped the diacritic
# on março → marco).
_DATE_LONG_PT = re.compile(
    r"\b(?P<day>\d{1,2})\s+de\s+(?P<month>\w+)\s+de\s+(?P<year>\d{4})\b"
)
# "12/03/1954", "12-03-1954", "12.03.1954"
_DATE_NUMERIC = re.compile(
    r"\b(?P<day>\d{1,2})[/\-\.\s](?P<month>\d{1,2})[/\-\.\s](?P<year>\d{4})\b"
)


def _parse_date_from_value(normalized_value: str) -> date | None:
    """
    Try to parse a date out of an already-normalized fact value. Returns
    None if the value doesn't look like a date — the caller falls back to
    other matchers.
    """
    m = _DATE_LONG_PT.search(normalized_value)
    if m:
        month_name = m.group("month")
        month_num = _MONTHS_PT.get(month_name)
        if month_num is None:
            return None
        try:
            return date(int(m.group("year")), month_num, int(m.group("day")))
        except ValueError:
            return None
    m = _DATE_NUMERIC.search(normalized_value)
    if m:
        try:
            return date(int(m.group("year")), int(m.group("month")), int(m.group("day")))
        except ValueError:
            return None
    return None


def _date_variants(d: date) -> Sequence[str]:
    """
    Enumerate the normalized textual variants of a date the persona is
    likely to emit. All returned strings are already normalize_text-shape
    (lowercase, no diacritics, single spaces) so callers can substring-
    match directly against a normalized reply.
    """
    dd = f"{d.day:02d}"
    mm = f"{d.month:02d}"
    yyyy = f"{d.year:04d}"
    yy = yyyy[-2:]
    month_name = _MONTH_NAME_BY_NUM[d.month]
    return (
        f"{dd} {mm} {yyyy}",            # "12 03 1954" (after / removal)
        f"{d.day} {mm} {yyyy}",          # "12 03 1954" without leading zero
        f"{dd} {mm} {yy}",               # "12 03 54"
        f"{dd} de {month_name} de {yyyy}",  # "12 de marco de 1954"
        f"{d.day} de {month_name} de {yyyy}",
        f"{d.day} de {month_name}",       # covers "12 de março" alone if year already stated
        f"{dd}{mm}{yyyy}",                # "12031954" digits-only
    )


# ---------------------------------------------------------------------------
# Multi-word overlap (for names and addresses)
# ---------------------------------------------------------------------------

# Portuguese connective words we ignore when computing overlap. Without
# this "Maria das Graças Silva" vs the reply "Maria Silva" would count 2
# of 4 tokens as a match; with it, only content words count.
_STOPWORDS_PT = frozenset({
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os",
    "em", "no", "na", "nos", "nas",
})


def _content_words(normalized_text: str) -> set[str]:
    return {w for w in normalized_text.split() if w and w not in _STOPWORDS_PT}


def _word_overlap_hit(normalized_value: str, normalized_reply: str) -> bool:
    """
    True when at least _WORD_OVERLAP_THRESHOLD fraction of the value's
    content words appear in the reply. Only applies to multi-word values.
    """
    value_words = _content_words(normalized_value)
    if len(value_words) < _MIN_WORDS_FOR_OVERLAP:
        return False
    reply_words = _content_words(normalized_reply)
    if not reply_words:
        return False
    hits = sum(1 for w in value_words if w in reply_words)
    return (hits / len(value_words)) >= _WORD_OVERLAP_THRESHOLD


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fact_value_appears_in_reply(
    fact_value: str,
    reply: str,
    revealed_patterns: Sequence[str] | None = None,
) -> bool:
    """
    Return True when ``reply`` seems to confirm ``fact_value``.

    Cheapest matcher first:
      1. Explicit ``revealed_patterns`` — the YAML author's escape hatch.
      2. Normalized substring — case/diacritic/punctuation-tolerant.
      3. Date variants — for values that parse as a date.
      4. Word overlap — for multi-word values (names, addresses).
    """
    if not fact_value or not reply:
        return False

    normalized_reply = normalize_text(reply)
    normalized_value = normalize_text(fact_value)

    # 1. Author-supplied patterns win outright.
    if revealed_patterns:
        for pattern in revealed_patterns:
            if pattern and normalize_text(pattern) in normalized_reply:
                return True

    # 2. Straight normalized substring.
    if normalized_value and normalized_value in normalized_reply:
        return True

    # 3. Date-aware match. Strict: if the value IS a date, we require
    #    an exact date-variant hit. Falling through to word overlap here
    #    would let "15 de março de 1954" match "12 de março de 1954" on
    #    the shared words {marco, 1954} — a wrong-date false positive.
    parsed = _parse_date_from_value(normalized_value)
    if parsed is not None:
        return any(
            variant in normalized_reply for variant in _date_variants(parsed)
        )

    # 4. Word overlap for multi-word values (names, addresses).
    return _word_overlap_hit(normalized_value, normalized_reply)
