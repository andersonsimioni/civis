"""
Tests for the flexible fact-value matcher — the piece that decides
whether a persona reply confirmed a fact and unlocks the action button
gated by it.

Kept small on purpose: matcher is heuristic, and we want to pin the
important behaviours (dates in multiple formats, case/diacritics,
name overlap) without over-specifying the fuzzy edges.
"""

from __future__ import annotations

import pytest

from civis.session.fact_matching import (
    fact_value_appears_in_reply,
    normalize_text,
)

# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("Olá MUNDO") == "ola mundo"

    def test_strips_diacritics(self):
        assert normalize_text("Florianópolis") == "florianopolis"
        assert normalize_text("março") == "marco"
        assert normalize_text("Graças") == "gracas"

    def test_collapses_punctuation_and_whitespace(self):
        assert normalize_text("12/03/1954") == "12 03 1954"
        assert normalize_text("Rua X,  n° 12.") == "rua x n 12"

    def test_empty_stays_empty(self):
        assert normalize_text("") == ""


# ---------------------------------------------------------------------------
# fact_value_appears_in_reply — the actual gate
# ---------------------------------------------------------------------------

class TestFactValueAppearsInReply:
    # --- Trivial cases -----------------------------------------------------

    def test_empty_inputs_return_false(self):
        assert fact_value_appears_in_reply("", "anything") is False
        assert fact_value_appears_in_reply("something", "") is False

    def test_literal_substring_hits(self):
        assert fact_value_appears_in_reply(
            "Maria Silva", "Meu nome é Maria Silva."
        ) is True

    # --- Normalization -----------------------------------------------------

    def test_diacritic_insensitive(self):
        # The YAML has "Florianópolis, SC"; persona says without accent.
        assert fact_value_appears_in_reply(
            "Florianópolis, SC", "eu nasci em Florianopolis SC"
        ) is True

    def test_case_insensitive(self):
        assert fact_value_appears_in_reply("SILVA", "silva") is True

    def test_punctuation_insensitive(self):
        assert fact_value_appears_in_reply(
            "R. XV de Novembro, 100", "rua XV de Novembro 100"
        ) is True

    # --- Date-shape matching -----------------------------------------------

    @pytest.mark.parametrize("reply", [
        "nasci em 12/03/1954",
        "12-03-1954",
        "12.03.1954",
        "12 03 1954",
        "meu aniversário é 12 de março de 1954",
        "doze de março de 1954, isso mesmo",  # word form not covered — falls to next matcher
    ])
    def test_date_variants_match_written_form(self, reply):
        # The YAML value is the long written form.
        matched = fact_value_appears_in_reply("12 de março de 1954", reply)
        if "doze" in reply:
            # Word-form ("doze") is out of scope; matcher may or may not
            # accept it depending on overlap. Not asserting either way.
            return
        assert matched, f"reply {reply!r} should have matched"

    def test_date_variants_match_numeric_yaml(self):
        # Some YAMLs write dates in numeric form — persona still says it
        # naturally.
        assert fact_value_appears_in_reply(
            "12/03/1954", "12 de março de 1954"
        ) is True

    def test_wrong_date_does_not_match(self):
        assert fact_value_appears_in_reply(
            "12 de março de 1954", "nasci em 15 de março de 1954"
        ) is False

    # --- Multi-word overlap (names, addresses) -----------------------------

    def test_partial_full_name_matches_when_enough_overlap(self):
        # "Maria das Graças Silva" — content words {maria, gracas, silva}.
        # Reply mentions maria + silva = 2/3 = 0.67 ≥ 0.6.
        assert fact_value_appears_in_reply(
            "Maria das Graças Silva", "o nome é Maria Silva."
        ) is True

    def test_barely_different_name_does_not_match(self):
        # Just "Silva" alone — 1/3 = 0.33 < 0.6.
        assert fact_value_appears_in_reply(
            "Maria das Graças Silva", "sobrenome Silva"
        ) is False

    def test_two_word_value_needs_literal_or_full_hit(self):
        # Multi-word threshold kicks in at >= 3 content words. A 2-word
        # value only wins on literal substring, not on overlap.
        assert fact_value_appears_in_reply(
            "João Pereira", "João"
        ) is False
        assert fact_value_appears_in_reply(
            "João Pereira", "o senhor João Pereira, sim"
        ) is True

    # --- revealed_patterns escape hatch ------------------------------------

    def test_revealed_patterns_win_over_default(self):
        # The default matcher would fail (nothing in common); the pattern
        # rescues it.
        assert fact_value_appears_in_reply(
            "codinome operacional XYZ",
            "vou responder com a alcunha combinada",
            revealed_patterns=["alcunha combinada"],
        ) is True

    def test_revealed_patterns_diacritic_insensitive(self):
        assert fact_value_appears_in_reply(
            "algo",
            "meu apelido é Zé",
            revealed_patterns=["apelido e ze"],
        ) is True

    # --- Regression against the pre-fix behaviour --------------------------

    def test_the_exact_bug_anderson_hit(self):
        """
        Anderson's session: YAML birth_date is "12 de março de 1954";
        DeepSeek replied "12/03/1954"; button stayed grey. This test
        would have failed on the old substring-only matcher.
        """
        assert fact_value_appears_in_reply(
            "12 de março de 1954", "sim, foi 12/03/1954."
        ) is True
