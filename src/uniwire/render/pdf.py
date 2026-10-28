"""PDF writer (reportlab, optional extra ``uniwire[pdf]``). One sheet per page.

Each sheet gets a bookmark (document outline entry); every cross-sheet reference of the drawing
(``uw-ref`` group: off-page arrow, continuation, cross-sheet link end, incoming feed) becomes an
internal link to the sheet it names."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..i18n import t as _t
from .scene import Circle, Ellipse, Group, Item, Line, Page, Polyline, Rect, Style, Text, bbox
from .scene import Path as Outline
from .semantics import HIT_COLOR, has_cls
from .svg import xml_safe

_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    # Liberation Sans has the widths of Arial, which the layout estimates; DejaVu Sans is about 13 % wider
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
]
_FALLBACK = {"Δ": "D", "→": "->", "←": "<-", "Ω": "ohm", "≤": "<=", "≥": ">=", "~": "~"}
# characters a Unicode font may lack: subscript and superscript digits as plain digits (CO₂ -> CO2), clocks
# (a time switch's symbol text) as a circle; anything else missing is left out rather than drawn as a box
_MISSING = {**{chr(0x2080 + i): str(i) for i in range(10)}, **{c: d for c, d in zip("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")},
            **{c: "○" for c in "⏱⏲⌚⌛⏰🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚🕛"}}


def _drawable(text: str, glyphs: frozenset[int]) -> str:
    """``text`` with the characters the font lacks (CJK aside, drawn with a CID font) replaced or left out."""
    out = []
    for ch in text:
        if ord(ch) in glyphs or _cjk(ch) or ch.isspace():
            out.append(ch)
        elif ch in _MISSING and all(ord(c) in glyphs for c in _MISSING[ch]):
            out.append(_MISSING[ch])
        elif ch in _FALLBACK:
            out.append(_FALLBACK[ch])
    return "".join(out)
# Chinese, Japanese and Korean text: the Adobe CID fonts known to every PDF reader, referenced and not embedded
# (no font file needed, on any system)
_CJK_FONTS = {"zh": "STSong-Light", "ja": "HeiseiKakuGo-W5", "ko": "HYGothic-Medium"}


def _fonts() -> tuple[str, str, bool, frozenset[int] | None]:
    """Regular and bold font names, whether they cover Unicode, and the code points they have (None: Helvetica,
    whose code points are those of cp1252)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            try:
                font = TTFont("UW", regular)
                pdfmetrics.registerFont(font)
                pdfmetrics.registerFont(TTFont("UW-Bold", bold))
                return "UW", "UW-Bold", True, frozenset(font.face.charToGlyph)
            except Exception:  # pragma: no cover - unreadable font
                continue
    return "Helvetica", "Helvetica-Bold", False, None


def _cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE4F
            or 0xFF00 <= o <= 0xFFEF or 0x20000 <= o <= 0x3FFFF)


def _cjk_font(text: str) -> str:
    """CID font for the CJK characters of ``text``: Japanese when it has kana, Korean when it has hangul."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    if any(0x3040 <= ord(ch) <= 0x30FF for ch in text):
        name = _CJK_FONTS["ja"]
    elif any(0xAC00 <= ord(ch) <= 0xD7AF or 0x1100 <= ord(ch) <= 0x11FF for ch in text):
        name = _CJK_FONTS["ko"]
    else:
        name = _CJK_FONTS["zh"]
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def _runs(text: str, font: str, glyphs: frozenset[int] | None) -> list[tuple[str, str]]:
    """``text`` cut into (font, part) runs: the CJK characters that ``font`` does not have go to a CID font."""
    def has(ch: str) -> bool:
        if glyphs is not None:
            return ord(ch) in glyphs
        try:
            ch.encode("cp1252")
            return True
        except UnicodeEncodeError:
            return False

    cjk = None
    runs: list[tuple[str, str]] = []
    for ch in text:
        f = font
        if _cjk(ch) and not has(ch):
            f = cjk = cjk or _cjk_font(text)
        if runs and runs[-1][0] == f:
            runs[-1] = (f, runs[-1][1] + ch)
        else:
            runs.append((f, ch))
    return runs


def write_pdf(pages: Iterable[Page], path: str | Path, lang: str | None = None, title: str | None = None) -> None:
    """Write ``pages`` to ``path``; ``lang`` is the language of the bookmarks (document language), ``title`` the
    PDF title (document title; default: the title of the first sheet)."""
    try:
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(_t("render.pdf_missing")) from e

    from reportlab.pdfbase.pdfmetrics import stringWidth

    regular, bold, unicode_ok, glyphs = _fonts()
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
    hrefs: list[tuple[str, tuple[float, float, float, float]]] = []  # (web address, box in mm) on the current page

    def draw(it: Item) -> None:
        if isinstance(it, Group):
            if has_cls(it, "uw-hit"):  # invisible hover path of the SVG output
                return
            if has_cls(it, "uw-href"):  # a web address (page "About this document")
                box = bbox(it)
                if box is not None and it.attrs.get("data-uw-href"):
                    hrefs.append((it.attrs["data-uw-href"], box))
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
        elif isinstance(it, Outline):
            r, g, b = (int(it.fill[i:i + 2], 16) / 255 for i in (1, 3, 5))
            c.setFillColorRGB(r, g, b)
            p = c.beginPath()
            x0 = y0 = 0.0
            for seg in it.segments:
                if seg[0] == "M":
                    p.moveTo(seg[1], seg[2])
                    x0, y0 = seg[1], seg[2]
                elif seg[0] == "L":
                    p.lineTo(seg[1], seg[2])
                    x0, y0 = seg[1], seg[2]
                elif seg[0] == "Q":  # quadratic -> cubic Bezier
                    qx, qy, x1, y1 = seg[1:]
                    p.curveTo(x0 + 2 / 3 * (qx - x0), y0 + 2 / 3 * (qy - y0), x1 + 2 / 3 * (qx - x1),
                              y1 + 2 / 3 * (qy - y1), x1, y1)
                    x0, y0 = x1, y1
                else:
                    p.close()
            c.drawPath(p, stroke=0, fill=1)
        elif isinstance(it, Rect):
            style(it.style)
            c.rect(it.x, it.y, it.w, it.h, stroke=1, fill=1 if it.style.fill else 0)
        elif isinstance(it, Text):
            text = xml_safe(it.text)  # control characters and lone surrogates cannot be encoded
            if not unicode_ok:
                for k, v in _FALLBACK.items():
                    text = text.replace(k, v)
            elif glyphs is not None:
                text = _drawable(text, glyphs)
            r, g, b = (int(it.color[i:i + 2], 16) / 255 for i in (1, 3, 5))
            c.saveState()
            c.setFillColorRGB(r, g, b)
            c.translate(it.p[0], it.p[1])
            c.scale(1, -1)  # local frame with y pointing up for text
            if it.rotate:
                c.rotate(it.rotate)
            dy = {"middle": -0.35 * it.size, "hanging": -0.8 * it.size}.get(it.baseline, 0.0)
            runs = _runs(text, bold if it.bold else regular, glyphs)
            widths = [stringWidth(part, font, it.size) for font, part in runs]
            x = {"middle": -sum(widths) / 2, "end": -sum(widths)}.get(it.anchor, 0.0)
            for (font, part), w in zip(runs, widths):
                c.setFont(font, it.size)
                c.drawString(x, dy, part)
                if it.bold and font in _CJK_FONTS.values():  # the CID fonts have no bold: drawn twice, a hair apart
                    c.drawString(x + it.size * 0.04, dy, part)
                x += w
            c.restoreState()

    for n, page in enumerate(pages, 1):
        c.setPageSize((page.width * mm, page.height * mm))
        c.bookmarkPage(_dest(n), fit="Fit")
        if page.attrs.get("data-uw-about"):  # page "About this document": no sheet number
            c.addOutlineEntry(xml_safe(page.title), _dest(n), level=0)
        else:
            c.addOutlineEntry(_t("render.sheet_bookmark", lang, number=n, title=xml_safe(page.title)) if page.title else
                              _t("render.sheet_bookmark_untitled", lang, number=n), _dest(n), level=0)
        c.saveState()
        c.translate(0, page.height * mm)
        c.scale(mm, -mm)  # mm, y pointing down like the scene
        c.setLineCap(1)
        c.setLineJoin(1)
        refs.clear()
        hrefs.clear()
        draw(page.root)
        c.restoreState()
        for target, (x0, y0, x1, y1) in refs:  # clickable area, in absolute PDF coordinates (pt, y up)
            pad = 0.8
            c.linkAbsolute("", _dest(target), ((x0 - pad) * mm, (page.height - y1 - pad) * mm,
                                               (x1 + pad) * mm, (page.height - y0 + pad) * mm), thickness=0)
        for url, (x0, y0, x1, y1) in hrefs:
            c.linkURL(url, (x0 * mm, (page.height - y1) * mm, x1 * mm, (page.height - y0) * mm), relative=0,
                      thickness=0)
        c.showPage()
    if pages:
        c.showOutline()
    c.save()


def _dest(sheet: int) -> str:
    return f"uw-sheet-{sheet}"
