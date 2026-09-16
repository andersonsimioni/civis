"""
Convert docs/ROADMAP_PITCH.md into a print-ready PDF via Chromium headless.

Pipeline: Markdown -> HTML (with embedded CSS tuned for print) -> PDF via
Edge/Chrome --headless=new --print-to-pdf. Keeps the intermediate HTML on
disk so the pitch-ready one-pager can also be viewed in a browser.

Usage:
    python scripts/build_roadmap_pdf.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SOURCE_MD = ROOT / "docs" / "ROADMAP_PITCH.md"
TARGET_HTML = ROOT / "docs" / "ROADMAP_PITCH.html"
TARGET_PDF = ROOT / "docs" / "ROADMAP_PITCH.pdf"

# Chromium-family binaries known to ship on Windows. First one that exists wins.
BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# CSS embedded in the HTML head. Tuned for A4 print with academic feel — meant
# to sit alongside Plano_de_Trabalho_CIVIS.pdf without looking out of place.
STYLESHEET = """
@page {
    size: A4;
    margin: 20mm 18mm 20mm 18mm;
}

:root {
    --ink: #1a1a1a;
    --muted: #555;
    --accent: #0b5394;
    --rule: #d0d7de;
    --code-bg: #f6f8fa;
    --code-ink: #24292f;
    --table-header: #f0f3f7;
    --callout-bg: #fff8e1;
    --callout-border: #f0c000;
}

* { box-sizing: border-box; }

html { font-size: 10.5pt; }

body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: var(--ink);
    line-height: 1.55;
    max-width: 100%;
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}

h1 {
    font-size: 22pt;
    margin: 0 0 6pt 0;
    color: var(--accent);
    border-bottom: 2px solid var(--accent);
    padding-bottom: 6pt;
    page-break-after: avoid;
}

h2 {
    font-size: 15pt;
    margin: 22pt 0 8pt 0;
    color: var(--accent);
    border-bottom: 1px solid var(--rule);
    padding-bottom: 3pt;
    page-break-after: avoid;
}

h3 {
    font-size: 12.5pt;
    margin: 16pt 0 6pt 0;
    color: var(--ink);
    page-break-after: avoid;
}

h4 {
    font-size: 11pt;
    margin: 12pt 0 4pt 0;
    color: var(--muted);
}

p, ul, ol { margin: 0 0 8pt 0; }

ul, ol { padding-left: 20pt; }

li { margin-bottom: 3pt; }

strong { color: var(--ink); }

em { color: var(--muted); font-style: italic; }

hr {
    border: none;
    border-top: 1px solid var(--rule);
    margin: 20pt 0;
}

/* Blockquote used as key-message callout. */
blockquote {
    margin: 10pt 0;
    padding: 10pt 14pt;
    background: var(--callout-bg);
    border-left: 3pt solid var(--callout-border);
    font-style: normal;
    color: var(--ink);
}

blockquote p { margin: 0; }

/* Tables — no zebra, subtle rules, header emphasized. */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10pt 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}

th {
    background: var(--table-header);
    color: var(--ink);
    text-align: left;
    padding: 6pt 8pt;
    border-bottom: 1.5pt solid var(--rule);
    font-weight: 600;
}

td {
    padding: 5pt 8pt;
    border-bottom: 1px solid var(--rule);
    vertical-align: top;
}

/* Code blocks — monospace, tinted background, no border for softness. */
pre {
    background: var(--code-bg);
    color: var(--code-ink);
    padding: 8pt 10pt;
    border-radius: 4pt;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8.5pt;
    line-height: 1.45;
    overflow-x: auto;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-break: break-word;
}

code {
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9pt;
    background: var(--code-bg);
    color: var(--code-ink);
    padding: 1pt 4pt;
    border-radius: 3pt;
}

pre code {
    background: transparent;
    padding: 0;
    font-size: 8.5pt;
}

/* Prevent page break inside major structural blocks. */
h1, h2, h3, h4 { break-after: avoid-page; }
table, pre, blockquote { break-inside: avoid; }
"""


def find_browser() -> str:
    """Return the first Chromium-family binary available, or exit with a hint."""
    for path in BROWSER_CANDIDATES:
        if Path(path).exists():
            return path
    print(
        "ERROR: no Chromium-family browser found. Install Chrome or Edge, or "
        "add the binary to BROWSER_CANDIDATES.",
        file=sys.stderr,
    )
    sys.exit(1)


def render_html(md_text: str) -> str:
    """Render Markdown to a standalone HTML document with the print stylesheet."""
    # Extensions: tables + fenced_code + toc anchors handle every construct used
    # in ROADMAP_PITCH.md. sane_lists prevents Markdown from merging paragraphs
    # into list items when we do not want that.
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <title>CIVIS — Roteiro até o pitch</title>
    <style>{STYLESHEET}</style>
</head>
<body>
{html_body}
</body>
</html>
"""


def html_to_pdf(browser: str, html_path: Path, pdf_path: Path) -> None:
    """Invoke the browser in headless print-to-pdf mode."""
    # --headless=new is the modern flag on Chrome 112+ and Edge equivalents.
    # file:/// URI ensures the browser reads the local HTML we just wrote.
    file_uri = html_path.resolve().as_uri()
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path.resolve()}",
        file_uri,
    ]
    print(f"Running: {browser} --headless=new --print-to-pdf ...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print("Browser stderr:", result.stderr, file=sys.stderr)
        print("Browser stdout:", result.stdout, file=sys.stderr)
        raise RuntimeError(f"Browser exited with code {result.returncode}")


def main() -> None:
    if not SOURCE_MD.exists():
        print(f"ERROR: {SOURCE_MD} not found.", file=sys.stderr)
        sys.exit(1)

    md_text = SOURCE_MD.read_text(encoding="utf-8")

    html = render_html(md_text)
    TARGET_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote HTML: {TARGET_HTML}")

    browser = find_browser()
    html_to_pdf(browser, TARGET_HTML, TARGET_PDF)

    if not TARGET_PDF.exists():
        raise RuntimeError(f"PDF was not written to {TARGET_PDF}")

    size_kb = TARGET_PDF.stat().st_size / 1024
    print(f"Wrote PDF:  {TARGET_PDF} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
