"""
Tests for the Phase D+++ document renderers.

Five concerns:

    - Every persona fact the template promises to display actually
      shows up in the rendered body.
    - The FIC- identifier follows a stable format so a screenshot in
      the deck can point at it.
    - FIC numbers are effectively unique per call (uuid4-backed).
    - The body is ASCII-boxed monospace (all rows have the same visual
      width so the frame doesn't collapse on the right).
"""

from __future__ import annotations

import re

from civis.documents.templates import (
    build_fic_number,
    render_birth_certificate,
    render_document,
    render_rg_second_copy,
)

# Pinned format: FIC-DOC-<8-digit stamp>-<6-char alnum> in upper case.
_FIC_NUMBER_REGEX = re.compile(r"^FIC-DOC-\d{8}-[A-Z0-9]{6}$")


# ---------------------------------------------------------------------------
# D+++.2.1 — birth certificate renders every fact
# ---------------------------------------------------------------------------


def test_birth_certificate_renders_all_persona_facts() -> None:
    """Every fact_key the template promises to display must land in the body."""
    facts = {
        "name": "Iracema da Silva",
        "birth_date": "12 de março de 1954",
        "birth_place": "Florianópolis, SC",
        "mother_name": "Maria das Graças Silva",
    }
    doc = render_birth_certificate(facts, session_id="test-session")

    for value in facts.values():
        assert value in doc.body, f"missing fact value in body: {value!r}"
    # Header + session id are visible on the paper for auditing.
    assert doc.id in doc.body
    assert "test-session" in doc.body


# ---------------------------------------------------------------------------
# D+++.2.2 — RG second copy renders every fact
# ---------------------------------------------------------------------------


def test_rg_second_copy_renders_all_persona_facts() -> None:
    """Same contract as the birth certificate, for the RG template."""
    facts = {
        "full_name": "Roberto Almeida Souza",
        "birth_date": "05 de outubro de 1985",
        "mother_name": "Antônia de Souza Almeida",
        "prior_rg_number": "FIC-RG-SC-6.847.291",
        "issuing_office": "SSP-SC, unidade Florianópolis Centro",
    }
    doc = render_rg_second_copy(facts, session_id="test-session")

    for value in facts.values():
        assert value in doc.body, f"missing fact value in body: {value!r}"
    assert "SSP-SC" in doc.body  # legend / header, not just the fact echo


# ---------------------------------------------------------------------------
# D+++.2.3 — FIC number format is stable
# ---------------------------------------------------------------------------


def test_fic_number_format_is_stable() -> None:
    """FIC-DOC-YYYYMMDD-XXXXXX, upper-case. Pinned by the tests so a
    designer accidentally changing the width is caught."""
    number = build_fic_number()
    assert _FIC_NUMBER_REGEX.match(number), f"unexpected FIC shape: {number!r}"


# ---------------------------------------------------------------------------
# D+++.2.4 — FIC numbers are effectively unique per call
# ---------------------------------------------------------------------------


def test_fic_number_is_unique_per_call() -> None:
    """
    20 calls produce 20 distinct FIC numbers. Backed by uuid4, so
    collisions are astronomically unlikely — this test just guards
    against someone swapping in a lazy time-only suffix.
    """
    numbers = {build_fic_number() for _ in range(20)}
    assert len(numbers) == 20


# ---------------------------------------------------------------------------
# D+++.2.5 — body is ASCII-boxed monospace with uniform width
# ---------------------------------------------------------------------------


def test_document_is_ascii_boxed_monospace() -> None:
    """
    Every row of the box must share the same visual width so the frame
    doesn't tear on the right in the chat card. The top and bottom rows
    must be built from Unicode box-drawing glyphs, not `-`/`+`.
    """
    doc = render_document(
        "birth_certificate",
        {
            "name": "Iracema",
            "birth_date": "12 de março de 1954",
            "birth_place": "Florianópolis, SC",
            "mother_name": "Maria",
        },
        session_id="s",
    )
    rows = doc.body.splitlines()
    assert rows, "body is empty"

    # All rows share the same width (measured in code points — every
    # box glyph and space is one code point, which matches the visual
    # width in a monospace font).
    widths = {len(row) for row in rows}
    assert len(widths) == 1, f"non-uniform row widths: {sorted(widths)}"

    # Top and bottom rows are pure box-drawing.
    assert rows[0].startswith("╔") and rows[0].endswith("╗")
    assert rows[-1].startswith("╚") and rows[-1].endswith("╝")
    # No ASCII fallback glyphs snuck in for the frame.
    assert "+" not in rows[0] and "-" not in rows[0]
