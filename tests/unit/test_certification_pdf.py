"""
Certificate PDF renderer tests (Onda-1 F2.2).

We don't parse the PDF — reportlab is a well-tested library, and pulling
in pdfplumber just to read our own uncompressed content stream would add
a heavy dependency for one assertion.

Instead the module under test builds the canvas with pageCompression=0
so the raw bytes contain the literal strings we drew. That lets us
grep for the level label, the agent's name and the certificate number.
"""

from __future__ import annotations

from datetime import date

import pytest

from civis.certification.eligibility import (
    CertificationEligibility,
    CertificationLevel,
)
from civis.certification.pdf_generator import (
    CertificateContext,
    generate_certificate_number,
    render_certificate_pdf,
)


def _make_context(
    level: CertificationLevel,
    n_sessions: int,
    mean_score: float,
    agent_name: str = "Fulana de Tal",
) -> CertificateContext:
    eligibility = CertificationEligibility(
        level=level,
        n_sessions=n_sessions,
        mean_score=mean_score,
        per_criterion_mean={
            "fact_verification": mean_score,
            "data_protection": mean_score,
            "protocol_adherence": mean_score,
            "communication": mean_score,
        },
    )
    return CertificateContext(
        agent_name=agent_name,
        eligibility=eligibility,
        issued_on=date(2026, 9, 16),
        certificate_number="FIC-CERT-20260916-000042",
        inter_model_agreement=0.78,
    )


def _pdf_bytes(context: CertificateContext) -> bytes:
    return render_certificate_pdf(context)


# ---- one test per level ----------------------------------------------------

def test_render_bronze_certificate_contains_all_fields():
    """
    BRONZE certificate must carry the agent name, the BRONZE level label
    (Portuguese label), the session count, the certificate number and
    the emission date.
    """
    context = _make_context(
        level=CertificationLevel.BRONZE,
        n_sessions=5,
        mean_score=0.63,
        agent_name="Bianca Braga",
    )
    pdf = _pdf_bytes(context)

    # PDF sanity: starts with the %PDF- marker and ends with %%EOF.
    assert pdf.startswith(b"%PDF-")
    assert b"%%EOF" in pdf[-64:]

    # Fields we actually care about surface as literal ASCII (Helvetica
    # encodes the strings 1:1 for the character set we use).
    assert b"Bianca Braga" in pdf
    # "BRONZE" is our Portuguese label; matches the CertificationLevel enum.
    assert b"BRONZE" in pdf
    assert b"FIC-CERT-20260916-000042" in pdf
    assert b"16/09/2026" in pdf
    assert b"CIVIS" in pdf


def test_render_silver_certificate_uses_portuguese_label():
    """
    The Portuguese localisation shows SILVER as "PRATA" — the raw enum
    value must NOT leak into the PDF.
    """
    context = _make_context(
        level=CertificationLevel.SILVER,
        n_sessions=17,
        mean_score=0.74,
        agent_name="Silvio da Prata",
    )
    pdf = _pdf_bytes(context)

    assert b"PRATA" in pdf
    # The English enum value "silver" must not surface in the visible copy.
    # (Metadata pdf.setSubject uses the enum value; that is fine — it's
    # embedded lower-case in the /Subject key.)
    assert b" silver " not in pdf
    assert b"Silvio da Prata" in pdf


def test_render_gold_certificate_shows_mean_and_agreement():
    """GOLD render shows both the mean score and the inter-model kappa."""
    context = _make_context(
        level=CertificationLevel.GOLD,
        n_sessions=31,
        mean_score=0.87,
        agent_name="Guilherme Ouro",
    )
    pdf = _pdf_bytes(context)

    assert b"OURO" in pdf
    assert b"31" in pdf              # session count
    assert b"0.87" in pdf            # mean score formatted to two decimals
    assert b"0.78" in pdf            # inter-model agreement from _make_context
    assert b"Guilherme Ouro" in pdf


# ---- context assembly + defensive behaviour --------------------------------

def test_render_raises_when_level_is_none():
    """
    Rendering without an awarded level is a bug on the caller side; the
    generator raises so the CLI never accidentally emits a "nível None"
    certificate.
    """
    eligibility = CertificationEligibility(
        level=None,
        n_sessions=2,
        mean_score=0.3,
    )
    context = CertificateContext(
        agent_name="Alguém",
        eligibility=eligibility,
        issued_on=date(2026, 9, 16),
        certificate_number="FIC-CERT-20260916-000000",
    )
    with pytest.raises(ValueError, match="non-eligible"):
        render_certificate_pdf(context)


def test_certificate_number_format():
    """FIC-CERT-YYYYMMDD-XXXXXX with zero-padded 6-digit suffix."""
    number = generate_certificate_number(today=date(2026, 9, 16))
    assert number.startswith("FIC-CERT-20260916-")
    tail = number.rsplit("-", 1)[-1]
    assert len(tail) == 6
    assert tail.isdigit()


def test_certificate_number_varies_between_calls():
    """
    Two consecutive calls should produce different numbers with
    overwhelming probability (1 in 10**6 collision). Guards against a
    regression that pins the suffix to a constant.
    """
    seen = {generate_certificate_number(today=date(2026, 1, 1)) for _ in range(50)}
    # Even with a birthday-paradox-style collision, 50 draws over 10**6 is
    # ~0.12% chance of ANY collision — 49+ distinct is a very safe bar.
    assert len(seen) >= 49


def test_render_without_kappa_produces_placeholder_line():
    """
    When inter_model_agreement is None the certificate still renders and
    the kappa line falls back to a "não disponível" message.
    """
    eligibility = CertificationEligibility(
        level=CertificationLevel.BRONZE,
        n_sessions=5,
        mean_score=0.61,
    )
    context = CertificateContext(
        agent_name="Sem Kappa",
        eligibility=eligibility,
        issued_on=date(2026, 9, 16),
        certificate_number="FIC-CERT-20260916-000001",
        inter_model_agreement=None,
    )
    pdf = render_certificate_pdf(context)
    assert b"BRONZE" in pdf
    # 'não disponível' has non-ASCII chars that ReportLab escapes in the
    # content stream. The 'dispon' skeleton is stable regardless of encoding.
    assert b"dispon" in pdf
    # And the kappa label is drawn as-is: 'Concordancia'/'Concordância' both
    # start with 'Concord', which lives cleanly in the PDF text stream.
    assert b"Concord" in pdf
