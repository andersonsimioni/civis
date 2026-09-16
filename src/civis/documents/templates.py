"""
Templates for fake documents "issued" by the attendant during a session.

Every renderer takes a `persona_facts` dict (fact_key -> value) plus a
`session_id` string used only for auditing, and returns a
:class:`RenderedDocument` — an ASCII-boxed block plus a stable
document id. The web UI drops the body into a monospace `<pre>` styled
with a beige background so a screenshot passes for a real counter
document at pitch distance.

Design notes:

- No Jinja / no external template engine. f-strings are enough for the
  two shipped documents and keep the dependency footprint tight
  (Streamlit already carries Jinja transitively — we deliberately do
  NOT depend on that; the day Streamlit drops it we don't want to
  care).
- Every string is fictional. The stamp "REGISTRO CIVIL FICTÍCIO" and
  the FIC- prefix make the fictional nature obvious from the paper
  itself so a screenshot in a deck can't be confused with a real
  certificate.
- ASCII borders use box-drawing characters (U+2500..) instead of `-`
  and `+` so the document reads as a designed artefact, not as a code
  block. The RE-check in the tests pins that shape.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

# Fixed line width — the ASCII box is padded to this many characters
# so every rendered document has the same silhouette in the chat.
_DOC_WIDTH = 60

# Box-drawing glyphs used to build the outer frame. Kept as constants
# so the tests can pin the shape without hard-coding the characters.
_BOX_TOP_LEFT = "╔"      # ╔
_BOX_TOP_RIGHT = "╗"     # ╗
_BOX_BOTTOM_LEFT = "╚"   # ╚
_BOX_BOTTOM_RIGHT = "╝"  # ╝
_BOX_HORIZONTAL = "═"    # ═
_BOX_VERTICAL = "║"      # ║
_BOX_TEE_LEFT = "╠"      # ╠
_BOX_TEE_RIGHT = "╣"     # ╣

_FICTIONAL_OFFICE = "1º RCPN Florianópolis (FICTÍCIO)"
_FICTIONAL_CLERK = "Servidor CIVIS-DEMO"


class RenderedDocument(BaseModel):
    """A rendered document ready to persist and display.

    `body` is the multi-line ASCII block. `id` is the FIC- number the
    document carries in its header — the same string appears in the
    body, so a caller can grep it for auditing.
    """

    id: str = Field(description="FIC- document number, unique per call.")
    title: str = Field(description="Short pt-BR title (used in the chat card).")
    body: str = Field(description="Full ASCII-boxed body (monospace).")


def build_fic_number(
    *,
    now: datetime | None = None,
    random_suffix: str | None = None,
) -> str:
    """Compose the FIC-DOC-YYYYMMDD-XXXXXX identifier.

    Both parameters are only ever set by tests. Production callers use
    the defaults so the id truly is unique per invocation.

    Format is stable — `_FIC_NUMBER_REGEX` in the tests pins it.
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d")
    suffix = (random_suffix or uuid4().hex[:6]).upper()
    return f"FIC-DOC-{stamp}-{suffix}"


# ---------------------------------------------------------------------------
# Birth certificate — used by the "confused" scenario and, by design, by
# the fraudster scenario (that's the pedagogical trap: the button exists
# to be resisted, not clicked).
# ---------------------------------------------------------------------------


def render_birth_certificate(
    persona_facts: dict[str, str],
    session_id: str,
    *,
    now: datetime | None = None,
    random_suffix: str | None = None,
) -> RenderedDocument:
    """Second-copy birth certificate for the citizen.

    Pulls fact values by key with a "não informado" fallback so a
    missing fact renders as a visible gap instead of crashing. In
    practice the button that triggers this render is disabled until
    every required fact is revealed — the fallback is just defence in
    depth.
    """
    fic = build_fic_number(now=now, random_suffix=random_suffix)
    issued_at = (now or datetime.now(UTC)).strftime("%d/%m/%Y")

    name = persona_facts.get("name") or persona_facts.get("full_name") or "não informado"
    birth_date = persona_facts.get("birth_date", "não informado")
    birth_place = persona_facts.get("birth_place", "não informado")
    mother_name = persona_facts.get("mother_name", "não informado")

    lines = [
        "REPÚBLICA FEDERATIVA DO BRASIL",
        "REGISTRO CIVIL DAS PESSOAS NATURAIS",
        _FICTIONAL_OFFICE,
        "",
        "CERTIDÃO DE NASCIMENTO — 2ª VIA",
        "",
        f"Nº do documento : {fic}",
        f"Data de emissão : {issued_at}",
        f"Sessão de treino: {session_id}",
        "",
        "─" * (_DOC_WIDTH - 4),
        "",
        "Certifico que, em conformidade com o assento",
        "lavrado em livro deste ofício:",
        "",
        f"Nome            : {name}",
        f"Data nascimento : {birth_date}",
        f"Local nascimento: {birth_place}",
        f"Filiação (mãe)  : {mother_name}",
        "",
        "─" * (_DOC_WIDTH - 4),
        "",
        "Documento FICTÍCIO — emitido pela plataforma",
        "CIVIS para treinamento de atendentes. Não tem",
        "validade jurídica ou fiscal.",
        "",
        f"Assinado por    : {_FICTIONAL_CLERK}",
    ]

    body = _wrap_in_box(lines, title="CERTIDÃO DE NASCIMENTO — 2ª VIA (FICTÍCIA)")
    return RenderedDocument(
        id=fic,
        title="Certidão de nascimento — 2ª via (fictícia)",
        body=body,
    )


# ---------------------------------------------------------------------------
# RG second copy — used by the aggressive scenario.
# ---------------------------------------------------------------------------


def render_rg_second_copy(
    persona_facts: dict[str, str],
    session_id: str,
    *,
    now: datetime | None = None,
    random_suffix: str | None = None,
) -> RenderedDocument:
    """Second-copy state ID (RG) for the citizen.

    Same shape as the birth certificate but different fields; the two
    documents share the ASCII frame so screenshots are consistent.
    """
    fic = build_fic_number(now=now, random_suffix=random_suffix)
    issued_at = (now or datetime.now(UTC)).strftime("%d/%m/%Y")

    name = persona_facts.get("full_name") or persona_facts.get("name") or "não informado"
    birth_date = persona_facts.get("birth_date", "não informado")
    mother_name = persona_facts.get("mother_name", "não informado")
    prior_rg = persona_facts.get("prior_rg_number", "não informado")
    issuing_office = persona_facts.get("issuing_office", "SSP-SC (FICTÍCIO)")

    lines = [
        "REPÚBLICA FEDERATIVA DO BRASIL",
        "SECRETARIA DE SEGURANÇA PÚBLICA (FICTÍCIA)",
        _FICTIONAL_OFFICE,
        "",
        "CARTEIRA DE IDENTIDADE — 2ª VIA",
        "",
        f"Nº do documento : {fic}",
        f"Data de emissão : {issued_at}",
        f"Sessão de treino: {session_id}",
        "",
        "─" * (_DOC_WIDTH - 4),
        "",
        f"Nome            : {name}",
        f"Data nascimento : {birth_date}",
        f"Filiação (mãe)  : {mother_name}",
        f"RG anterior     : {prior_rg}",
        f"Órgão expedidor : {issuing_office}",
        "",
        "─" * (_DOC_WIDTH - 4),
        "",
        "Documento FICTÍCIO — emitido pela plataforma",
        "CIVIS para treinamento de atendentes. Não tem",
        "validade jurídica ou fiscal.",
        "",
        f"Assinado por    : {_FICTIONAL_CLERK}",
    ]

    body = _wrap_in_box(lines, title="CARTEIRA DE IDENTIDADE — 2ª VIA (FICTÍCIA)")
    return RenderedDocument(
        id=fic,
        title="RG — 2ª via (fictícia)",
        body=body,
    )


# ---------------------------------------------------------------------------
# Registry + dispatcher
# ---------------------------------------------------------------------------


# Renderer signature: (persona_facts, session_id) -> RenderedDocument.
# Extra kwargs (now, random_suffix) are only used by the tests.
DocumentRenderer = Callable[..., RenderedDocument]


DOCUMENT_RENDERERS: dict[str, DocumentRenderer] = {
    "birth_certificate": render_birth_certificate,
    "rg_second_copy": render_rg_second_copy,
}


def render_document(
    template_id: str,
    persona_facts: dict[str, str],
    session_id: str,
    **kwargs: object,
) -> RenderedDocument:
    """Dispatch by `template_id` into DOCUMENT_RENDERERS.

    Raises `KeyError` with a friendly message when the id is unknown so
    the UI can surface a warning banner instead of crashing.
    """
    renderer = DOCUMENT_RENDERERS.get(template_id)
    if renderer is None:
        raise KeyError(
            f"No document renderer registered for '{template_id}'. "
            f"Known templates: {sorted(DOCUMENT_RENDERERS)}."
        )
    return renderer(persona_facts, session_id, **kwargs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wrap_in_box(lines: list[str], *, title: str) -> str:
    """Wrap the given lines in a Unicode-box frame with a title bar.

    Every line is padded / truncated to fit inside `_DOC_WIDTH` so the
    right border always lines up. The title bar sits between the top
    border and the first line of content.
    """
    inner_width = _DOC_WIDTH - 2  # subtract two vertical bars

    top = _BOX_TOP_LEFT + _BOX_HORIZONTAL * inner_width + _BOX_TOP_RIGHT
    bottom = _BOX_BOTTOM_LEFT + _BOX_HORIZONTAL * inner_width + _BOX_BOTTOM_RIGHT
    title_bar = _BOX_TEE_LEFT + _BOX_HORIZONTAL * inner_width + _BOX_TEE_RIGHT

    padded_title = _pad_line(title.center(inner_width - 2), inner_width)
    title_row = f"{_BOX_VERTICAL}{padded_title}{_BOX_VERTICAL}"

    body_rows = [
        f"{_BOX_VERTICAL}{_pad_line(line, inner_width)}{_BOX_VERTICAL}"
        for line in lines
    ]

    return "\n".join([top, title_row, title_bar, *body_rows, bottom])


def _pad_line(line: str, width: int) -> str:
    """Pad or truncate `line` to `width` characters (left-aligned,
    one leading + one trailing space of gutter)."""
    trimmed = line[: width - 2]
    return " " + trimmed.ljust(width - 2) + " "
