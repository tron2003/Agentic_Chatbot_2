"""
Research report as a PDF (the "Export PDF" button under a Deep research answer).

Markdown → HTML (python-markdown, with tables) → PDF (fpdf2's HTML renderer),
with a Unicode font from the system so names, ₹, € and dashes print correctly:
Segoe UI / Arial / Consolas on Windows, DejaVu on Linux (``fonts-dejavu-core``
in Docker). Without any of those it falls back to Helvetica and replaces
characters Helvetica can't show.
"""

from __future__ import annotations

import html
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

FONT_CANDIDATES: list[dict[str, str]] = [
    # Windows
    {"": "segoeui.ttf", "B": "segoeuib.ttf", "I": "segoeuii.ttf", "BI": "segoeuiz.ttf"},
    {"": "arial.ttf", "B": "arialbd.ttf", "I": "ariali.ttf", "BI": "arialbi.ttf"},
    # Linux (Debian/Ubuntu fonts-dejavu-core), macOS
    {"": "DejaVuSans.ttf", "B": "DejaVuSans-Bold.ttf", "I": "DejaVuSans-Oblique.ttf", "BI": "DejaVuSans-BoldOblique.ttf"},
    {"": "Arial.ttf", "B": "Arial Bold.ttf", "I": "Arial Italic.ttf", "BI": "Arial Bold Italic.ttf"},
]
MONO_CANDIDATES = ["consola.ttf", "DejaVuSansMono.ttf"]


def _font_dirs() -> list[Path]:
    dirs = []
    if sys.platform == "win32":
        dirs.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
        dirs.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts")
    dirs += [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"), Path("/usr/share/fonts/TTF"),
             Path("/Library/Fonts"), Path("/System/Library/Fonts/Supplemental")]
    return [d for d in dirs if d.is_dir()]


def _find(name: str) -> Path | None:
    for d in _font_dirs():
        p = d / name
        if p.is_file():
            return p
        hit = next((f for f in d.iterdir() if f.name.lower() == name.lower()), None)
        if hit:
            return hit
    return None


def _register_fonts(pdf) -> tuple[str, str | None]:
    """Register a Unicode body font (and a monospace one). Returns (body family, mono family)."""
    body = "helvetica"
    for cand in FONT_CANDIDATES:
        paths = {style: _find(name) for style, name in cand.items()}
        if paths[""] is None:
            continue
        for style, path in paths.items():
            pdf.add_font("Body", style, str(path or paths[""]))
        body = "Body"
        break
    mono = None
    for name in MONO_CANDIDATES:
        p = _find(name)
        if p:
            for style in ("", "B", "I", "BI"):
                pdf.add_font("Mono", style, str(p))
            mono = "Mono"
            break
    return body, mono


_LATIN1 = {"\u2011": "-", "\u2010": "-", "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
           "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2192": "->", "\u2022": "*", "\u00a0": " ", "\u20b9": "Rs "}


def _latin1(text: str) -> str:
    for a, b in _LATIN1.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


_DEMO = re.compile(r"^\*\*Demo mode\*\*.*?\n\n", re.S)


def markdown_to_html(text: str) -> str:
    import markdown

    text = _DEMO.sub("", text)
    out = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"], output_format="html")
    # fpdf2 draws table borders and widths from attributes, and doesn't know <thead>/<tbody>.
    out = re.sub(r"</?t(?:head|body)>", "", out)
    return out.replace("<table>", '<table border="1" width="100%">')


def safe_filename(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:60] or "report"
    return f"{slug}.pdf"


def render_report_pdf(title: str, content: str, sources: list[dict[str, Any]], *, question: str | None = None,
                      model: str | None = None, app_name: str = "Reittiä", created_at: str | None = None) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    class ReportPDF(FPDF):
        body_family = "helvetica"

        def clean(self, text: str) -> str:
            return text if self.body_family != "helvetica" else _latin1(text)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font(self.body_family, "", 8)
            self.set_text_color(130, 130, 140)
            self.cell(0, 6, self.clean(f"{app_name} · Deep research report · page {self.page_no()}/{{nb}}"), align="C")

    heading = re.match(r"\s*(?:\*\*Demo mode\*\*.*?\n\n)?#{1,2}\s+(.+?)\s*\n", content, re.S)
    if heading:  # the report's own heading becomes the PDF title instead of printing twice
        title = heading.group(1).strip()
        content = content[heading.end():]

    pdf = ReportPDF(format="A4")
    pdf.body_family, mono = _register_fonts(pdf)
    unicode_ok = pdf.body_family != "helvetica"
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.alias_nb_pages()
    pdf.set_title(title)
    pdf.set_author(app_name)
    pdf.add_page()

    # Title block
    pdf.set_font(pdf.body_family, "B", 19)
    pdf.set_text_color(20, 24, 33)
    pdf.multi_cell(0, 9, pdf.clean(title), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font(pdf.body_family, "", 9)
    pdf.set_text_color(110, 114, 126)
    when = created_at or datetime.now().strftime("%d %B %Y, %H:%M")
    meta = f"Generated by {app_name} Deep research · {when}" + (f" · model {model}" if model else "")
    pdf.multi_cell(0, 5, pdf.clean(meta), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if question:
        pdf.ln(1)
        pdf.set_font(pdf.body_family, "I", 10)
        pdf.set_text_color(60, 64, 76)
        pdf.multi_cell(0, 5.5, pdf.clean(f"Question: {question}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_draw_color(220, 222, 228)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    # Body
    pdf.set_text_color(25, 28, 36)
    pdf.set_font(pdf.body_family, "", 10.5)
    body = markdown_to_html(content)
    if not unicode_ok:
        body = _latin1(body)
    kwargs: dict[str, Any] = {"font_family": pdf.body_family, "li_prefix_color": (90, 96, 110)}
    try:
        from fpdf.fonts import FontFace, TextStyle

        styles: dict[str, Any] = {
            "h1": TextStyle(font_family=pdf.body_family, font_style="B", font_size_pt=16, color=(20, 24, 33), t_margin=3, b_margin=1),
            "h2": TextStyle(font_family=pdf.body_family, font_style="B", font_size_pt=14, color=(20, 24, 33), t_margin=4, b_margin=1),
            "h3": TextStyle(font_family=pdf.body_family, font_style="B", font_size_pt=12, color=(30, 34, 44), t_margin=3, b_margin=1),
            "h4": TextStyle(font_family=pdf.body_family, font_style="B", font_size_pt=11, color=(30, 34, 44), t_margin=2, b_margin=1),
            "a": FontFace(color=(29, 43, 216)),
        }
        if mono:
            styles["code"] = FontFace(family=mono, size_pt=9.5, color=(80, 40, 120))
            styles["pre"] = TextStyle(font_family=mono, font_size_pt=9, color=(40, 40, 50))
        kwargs["tag_styles"] = styles
    except Exception:  # older fpdf2 without tag styles: default heading styles
        pass
    try:
        pdf.write_html(body, **kwargs)
    except Exception:
        # A construct fpdf2 can't lay out (rare: very wide tables). Fall back to plain text, never fail the export.
        pdf.set_font(pdf.body_family, "", 10.5)
        plain = re.sub(r"<[^>]+>", "", html.unescape(body))
        pdf.multi_cell(0, 5.5, plain, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Sources
    if sources:
        pdf.ln(4)
        pdf.set_font(pdf.body_family, "B", 13)
        pdf.set_text_color(20, 24, 33)
        pdf.cell(0, 8, "Sources", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for i, s in enumerate(sources, 1):
            n = s.get("index") or i
            title_s = pdf.clean(str(s.get("title") or s.get("url") or "source"))
            pdf.set_font(pdf.body_family, "", 9.5)
            pdf.set_text_color(25, 28, 36)
            if s.get("url"):
                pdf.multi_cell(0, 5, f"[{n}] {title_s}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(29, 43, 216)
                pdf.set_font(pdf.body_family, "", 8.5)
                pdf.multi_cell(0, 4.5, pdf.clean(s["url"]), link=s["url"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                page = f", page {s['page']}" if s.get("page") else ""
                pdf.multi_cell(0, 5, f"[{n}] {title_s}{page} (your document)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

    return bytes(pdf.output())
