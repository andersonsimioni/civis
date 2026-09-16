"""
Document renderers for scenario actions that emit paperwork.

Phase D+++ ships two templates: a 2nd-copy birth certificate and a
2nd-copy RG. Both produce a monospace ASCII-boxed block a Streamlit
`<pre>` renders as a plausible-looking counter document.

Adding a new template = one function + one entry in
DOCUMENT_RENDERERS. Keep the surface flat on purpose so a designer can
tweak wording without navigating an abstraction.
"""

from civis.documents.templates import (
    DOCUMENT_RENDERERS,
    RenderedDocument,
    build_fic_number,
    render_document,
)

__all__ = [
    "DOCUMENT_RENDERERS",
    "RenderedDocument",
    "build_fic_number",
    "render_document",
]
