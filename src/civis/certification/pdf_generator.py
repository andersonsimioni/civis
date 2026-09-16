"""
Certificate PDF generator (Onda-1 F2.2).

Renders a single-page A4 certificate using ReportLab's low-level `canvas`
API. We stay on `canvas` (not `platypus.SimpleDocTemplate`) because the
layout is fixed and centred — a flowing document engine would only add
indirection here.

Design decisions worth reading:

    1. `pageCompression=0` on the canvas. ReportLab defaults to zlib
       compression on content streams, which makes the raw PDF bytes
       opaque. Turning it off inflates the file by a few KB but lets our
       tests assert `b"Certificado" in pdf_bytes` without a PDF parser.
       At ~50 KB uncompressed, the cost is invisible next to any digital
       signature we might add later.

    2. Text drawn via `drawCentredString` for the title lines and
       `drawString` for the details block, using scaled coordinates
       (A4 width = 595 pt, height = 842 pt). Two lines of table code
       would let us change fonts globally; that is on the table when we
       add the coat-of-arms and the branded footer.

    3. Certificate number generator uses `secrets.randbelow` to keep it
       cryptographically random (predictable numbers on a public
       credential are a bad look). Format `FIC-CERT-YYYYMMDD-XXXXXX`
       matches the FIC-* pattern already used for scenario honeytokens.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from civis.certification.eligibility import (
    CertificationEligibility,
    CertificationLevel,
)

# A4 in points (1 pt = 1/72 inch). ReportLab convention: origin at bottom-left.
PAGE_WIDTH, PAGE_HEIGHT = A4

# Colour palette. Deep navy for the title (institutional feel), warm slate
# for the body, muted grey for the certificate number.
_TITLE_COLOR = Color(0.10, 0.16, 0.28)
_BODY_COLOR = Color(0.12, 0.14, 0.20)
_MUTED_COLOR = Color(0.42, 0.44, 0.50)

# Human-readable label per level. Rendered inside the paragraph body.
_LEVEL_LABEL: dict[CertificationLevel, str] = {
    CertificationLevel.BRONZE: "BRONZE",
    CertificationLevel.SILVER: "PRATA",
    CertificationLevel.GOLD: "OURO",
}


@dataclass(frozen=True)
class CertificateContext:
    """
    Bundles everything the renderer needs. Kept as a dataclass so the CLI
    can build it in one line and tests can mint fake certificates without
    touching the filesystem.
    """

    agent_name: str
    eligibility: CertificationEligibility
    issued_on: date
    certificate_number: str
    inter_model_agreement: float | None = None


def generate_certificate_number(today: date | None = None) -> str:
    """
    Return a FIC-CERT-YYYYMMDD-XXXXXX identifier.

    The six-digit suffix uses `secrets.randbelow(1_000_000)` so two
    certificates issued in the same day are extremely unlikely to
    collide (1 in 10**6) and impossible to predict. Zero-padded so the
    string width is stable across values.
    """
    day = today or date.today()
    suffix = secrets.randbelow(1_000_000)
    return f"FIC-CERT-{day.strftime('%Y%m%d')}-{suffix:06d}"


def render_certificate_pdf(context: CertificateContext) -> bytes:
    """
    Render the certificate to a bytes buffer and return it.

    Callers write it wherever they want (disk in the CLI, an HTTP
    response for a future web endpoint, an inline preview in Streamlit).
    We deliberately never touch the filesystem here.
    """
    if context.eligibility.level is None:
        # Defensive: the CLI is expected to short-circuit before calling
        # this function when the attendant is not eligible, but a clear
        # error is better than a confusing PDF titled "Certificado, nível None".
        raise ValueError(
            "Cannot render a certificate for a non-eligible attendant "
            "(eligibility.level is None)."
        )

    buffer = BytesIO()
    # pageCompression=0 keeps the content stream in plain text so tests
    # can grep the bytes; see module docstring for the rationale.
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    pdf.setTitle(f"Certificado CIVIS - {context.agent_name}")
    pdf.setAuthor("CIVIS")
    pdf.setSubject(
        f"Certificado de proficiencia nivel {context.eligibility.level.value}"
    )

    _draw_border(pdf)
    _draw_header(pdf)
    _draw_body(pdf, context)
    _draw_metrics(pdf, context)
    _draw_footer(pdf, context)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ---- individual drawing sections -------------------------------------------

def _draw_border(pdf: canvas.Canvas) -> None:
    """Thin decorative border 30 pt inside the page edge."""
    inset = 30
    pdf.setStrokeColor(_TITLE_COLOR)
    pdf.setLineWidth(2)
    pdf.rect(
        inset,
        inset,
        PAGE_WIDTH - 2 * inset,
        PAGE_HEIGHT - 2 * inset,
        stroke=1,
        fill=0,
    )


def _draw_header(pdf: canvas.Canvas) -> None:
    """CIVIS wordmark + main title, centred near the top of the page."""
    centre_x = PAGE_WIDTH / 2

    pdf.setFillColor(_TITLE_COLOR)
    pdf.setFont("Helvetica-Bold", 42)
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 110, "CIVIS")

    pdf.setFont("Helvetica", 12)
    pdf.setFillColor(_MUTED_COLOR)
    pdf.drawCentredString(
        centre_x,
        PAGE_HEIGHT - 130,
        "Cidadão Virtual Simulado — Simulador de atendimento público",
    )

    pdf.setFillColor(_TITLE_COLOR)
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawCentredString(
        centre_x, PAGE_HEIGHT - 190, "CERTIFICADO DE PROFICIÊNCIA"
    )


def _draw_body(pdf: canvas.Canvas, context: CertificateContext) -> None:
    """
    Award paragraph: "Certificamos que <name> concluiu ... nível <level>".
    Rendered as four lines so the level and name each get emphasis.
    """
    centre_x = PAGE_WIDTH / 2
    level_label = _LEVEL_LABEL[context.eligibility.level]

    pdf.setFillColor(_BODY_COLOR)
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 260, "Certificamos que")

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(centre_x, PAGE_HEIGHT - 300, context.agent_name)

    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(
        centre_x,
        PAGE_HEIGHT - 340,
        "concluiu com sucesso o programa de treinamento em atendimento",
    )
    pdf.drawCentredString(
        centre_x,
        PAGE_HEIGHT - 358,
        f"ao cidadão CIVIS, nível {level_label}.",
    )


def _draw_metrics(pdf: canvas.Canvas, context: CertificateContext) -> None:
    """Three-line metrics block: sessions, mean score, inter-model agreement."""
    left_x = 130
    eligibility = context.eligibility

    pdf.setFillColor(_BODY_COLOR)
    pdf.setFont("Helvetica", 13)

    pdf.drawString(
        left_x,
        PAGE_HEIGHT - 430,
        f"Sessões concluídas: {eligibility.n_sessions}",
    )
    pdf.drawString(
        left_x,
        PAGE_HEIGHT - 452,
        f"Nota média: {eligibility.mean_score:.2f}",
    )

    if context.inter_model_agreement is not None:
        agreement_line = (
            f"Concordância inter-modelo (kappa): {context.inter_model_agreement:.2f}"
        )
    else:
        agreement_line = (
            "Concordância inter-modelo (kappa): não disponível para esta amostra"
        )
    pdf.drawString(left_x, PAGE_HEIGHT - 474, agreement_line)


def _draw_footer(pdf: canvas.Canvas, context: CertificateContext) -> None:
    """
    Date, certificate number, and the signature-placeholder line at the
    bottom of the page. The signature line is intentionally a printed
    underscore — a real digital signature will replace it in a future
    iteration.
    """
    centre_x = PAGE_WIDTH / 2

    pdf.setFillColor(_BODY_COLOR)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(
        130,
        PAGE_HEIGHT - 520,
        f"Emitido em {context.issued_on.strftime('%d/%m/%Y')}",
    )
    pdf.setFillColor(_MUTED_COLOR)
    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(
        130,
        PAGE_HEIGHT - 538,
        f"Nº de Certificado: {context.certificate_number}",
    )

    # Signature placeholder: a horizontal line and a caption.
    signature_y = 140
    pdf.setStrokeColor(_BODY_COLOR)
    pdf.setLineWidth(1)
    pdf.line(centre_x - 120, signature_y, centre_x + 120, signature_y)
    pdf.setFillColor(_MUTED_COLOR)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(
        centre_x,
        signature_y - 14,
        "assinatura digital (placeholder)",
    )
