"""PDF writer (reportlab, optional extra ``uniwire[pdf]``). One sheet per page.

Each sheet gets a bookmark (document outline entry); every cross-sheet reference of the drawing
(``uw-ref`` group: off-page arrow, continuation, cross-sheet link end, incoming feed) becomes an
internal link to the sheet it names."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..i18n import t as _t
from .scene import Circle, Ellipse, Group, Item, Line, Page, Polyline, Rect, Style, Text, bbox
from .semantics import HIT_COLOR, has_cls
from .svg import xml_safe

_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
]
_FALLBACK = {"Δ": "D", "→": "->", "←": "<-", "Ω": "ohm", "≤": "<=", "≥": ">=", "~": "~"}


def _fonts() -> tuple[str, str, bool]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdfmetrics.registerFont(TTFont("UW", regular))
                pdfmetrics.registerFont(TTFont("UW-Bold", bold))
                return "UW", "UW-Bold", True
            except Exception:  # pragma: no cover - unreadable font
                continue
    return "Helvetica", "Helvetica-Bold", False


def write_pdf(pages: Iterable[Page], path: str | Path, lang: str | None = None, title: str | None = None) -> None:
    """Write ``pages`` to ``path``; ``lang`` is the language of the bookmarks (document language), ``title`` the
    PDF title (document title; default: the title of the first sheet)."""
    try:
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(_t("render.pdf_missing")) from e

    regular, bold, unicode_ok = _fonts()
    pages = list(pages)
    c = canvas.Canvas(str(path))
    c.setTitle(xml_safe(title or (pages[0].title if pages else "") or "uniwire"))
    c.setCreator("uniwire")

    def style(s: Style) -> None:
        if s.color == HIT_COLOR:  # pragma: no cover - hit paths are skipped with their group
            return
        r, g, b = (int(s.color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        c.setStrokeColorRGB(r, g, b)
        c.setLineWidth(s.width)
        c.setDash([d for d in s.dash] if s.dash else [])
        if s.fill:
            fr, fg, fb = (int(s.fill[i:i + 2], 16) / 255 for i in (1, 3, 5))
            c.setFillColorRGB(fr, fg, fb)

    refs: list[tuple[int, tuple[float, float, float, float]]] = []  # (target sheet, box in mm) on the current page

    def draw(it: Item) -> None:
        if isinstance(it, Group):
            if has_cls(it, "uw-hit"):  # invisible hover path of the SVG output
                return
            if has_cls(it, "uw-ref"):
                target = it.attrs.get("data-uw-target-sheet", "")
                box = bbox(it)
                if target.isdigit() and 1 <= int(target) <= len(pages) and box is not None:
                    refs.append((int(target), box))
            for x in it.items:
                draw(x)
        elif isinstance(it, Line):
            style(it.style)
            c.line(it.a[0], it.a[1], it.b[0], it.b[1])
        elif isinstance(it, Polyline):
            style(it.style)
            p = c.beginPath()
            p.moveTo(*it.points[0])
            for pt in it.points[1:]:
                p.lineTo(*pt)
            if it.closed:
                p.close()
            c.drawPath(p, stroke=1, fill=1 if it.style.fill else 0)
        elif isinstance(it, Circle):
            style(it.style)
            c.circle(it.c[0], it.c[1], it.r, stroke=1, fill=1 if it.style.fill else 0)
        elif isinstance(it, Ellipse):
            style(it.style)
            c.ellipse(it.c[0] - it.rx, it.c[1] - it.ry, it.c[0] + it.rx, it.c[1] + it.ry, stroke=1,
                      fill=1 if it.style.fill else 0)
        elif isinstance(it, Rect):
            style(it.style)
            c.rect(it.x, it.y, it.w, it.h, stroke=1, fill=1 if it.style.fill else 0)
        elif isinstance(it, Text):
            text = xml_safe(it.text)  # control characters and lone surrogates cannot be encoded
            if not unicode_ok:
                for k, v in _FALLBACK.items():
                    text = text.replace(k, v)
            r, g, b = (int(it.color[i:i + 2], 16) / 255 for i in (1, 3, 5))
            c.saveState()
            c.setFillColorRGB(r, g, b)
            c.translate(it.p[0], it.p[1])
            c.scale(1, -1)  # local frame with y pointing up for text
            if it.rotate:
                c.rotate(it.rotate)
            dy = {"middle": -0.35 * it.size, "hanging": -0.8 * it.size}.get(it.baseline, 0.0)
            c.setFont(bold if it.bold else regular, it.size)
            if it.anchor == "middle":
                c.drawCentredString(0, dy, text)
            elif it.anchor == "end":
                c.drawRightString(0, dy, text)
            else:
                c.drawString(0, dy, text)
            c.restoreState()

    for n, page in enumerate(pages, 1):
        c.setPageSize((page.width * mm, page.height * mm))
        c.bookmarkPage(_dest(n), fit="Fit")
        c.addOutlineEntry(_t("render.sheet_bookmark", lang, number=n, title=xml_safe(page.title)) if page.title else
                          _t("render.sheet_bookmark_untitled", lang, number=n), _dest(n), level=0)
        c.saveState()
        c.translate(0, page.height * mm)
        c.scale(mm, -mm)  # mm, y pointing down like the scene
        c.setLineCap(1)
        c.setLineJoin(1)
        refs.clear()
        draw(page.root)
        c.restoreState()
        for target, (x0, y0, x1, y1) in refs:  # clickable area, in absolute PDF coordinates (pt, y up)
            pad = 0.8
            c.linkAbsolute("", _dest(target), ((x0 - pad) * mm, (page.height - y1 - pad) * mm,
                                               (x1 + pad) * mm, (page.height - y0 + pad) * mm), thickness=0)
        c.showPage()
    if pages:
        c.showOutline()
    c.save()


def _dest(sheet: int) -> str:
    return f"uw-sheet-{sheet}"
