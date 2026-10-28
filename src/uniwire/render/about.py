"""Page "About this document", added after the sheets of a PDF (``render_pdf(..., about=...)``).

It is not a sheet of the diagram: no folio number, and it can be left out. It says what was checked (profiles,
findings, the scope of automatic checks), where the online copy of the document is and how to delete it, and how to
write to the uniwire team. Every web address on it is a link (``uw-href`` groups, clickable in the PDF).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from ..i18n import normalize_lang
from ..i18n import t as _t
from ..layout.engine import MARGIN, TITLE_BAND, TITLE_BLOCK_W
from ..model import Document
from . import brand
from .frame import _title_block
from .scene import NORMAL, THICK, THIN, Group, Line, Page, Path, Rect, Style, Text, parse_path, text_units, text_width

INK, GREY, LIGHT, RUST, WARM = "#15181C", "#5B6168", "#C9CDD2", "#8F3F12", "#FBF3EC"


@dataclass
class About:
    """What the page links to. ``doc_id``: id of the stored copy of the document (short links of the hosted
    server); without it, the page says nothing of an online copy and the contact link has no document."""
    doc_id: Optional[str] = None
    site: str = "https://uniwire.sh"


def _bare(url: str) -> str:
    return url.split("://", 1)[-1]


@functools.lru_cache(maxsize=1)
def _metrics() -> Optional[Callable[[str, float, bool], float]]:
    """Width of a text in the fonts of the PDF (mm), or None without reportlab (estimate of the scene)."""
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth

        from .pdf import _fonts
        regular, bold, _, _ = _fonts()
    except Exception:  # noqa: BLE001  # pragma: no cover
        return None
    return lambda s, size, b: stringWidth(s, bold if b else regular, size)


def _width(s: str, size: float, bold: bool = False) -> float:
    m = _metrics()
    return m(s, size, bold) if m is not None and not any(ord(ch) > 0x2E7F for ch in s) else text_width(s, size)


# no line break before these marks, nor inside French quotes: the space before them becomes a no-break space
_NO_BREAK = re.compile(r" (?=[:;!?»])|(?<=«) ")
_NBSP_MARK = "\ue000"  # stands for a no-break space while the text is cut into words
_CLOSING = set("，。、；：！？）」』》”’.,;:!?)»")  # never at the start of a line (Chinese and Latin)


class _Writer:
    """Wrapped text with bold runs and links, at a fixed size, in a column."""

    def __init__(self, g: Group, k: float) -> None:
        self.g, self.k = g, k

    def para(self, x: float, y: float, width: float, text: str, size: float, color: str = INK, bold: bool = False,
             links: Optional[dict[str, str]] = None, lead: float = 1.38) -> float:
        """Draw ``text`` (``{name}`` placeholders replaced by the shown text of ``links[name] = (text, url)``)
        wrapped to ``width`` from baseline ``y``; returns the baseline after the last line."""
        size *= self.k
        tokens: list[tuple[str, Optional[str]]] = []  # (unit with its leading space, url)
        rest = _NO_BREAK.sub("\u00a0", text).replace("\u00a0", _NBSP_MARK)
        links = links or {}
        while rest:
            i = rest.find("{")
            j = rest.find("}", i) if i >= 0 else -1
            if i < 0 or j < 0:
                tokens += [(u, None) for u in text_units(rest)]
                break
            if i:
                tokens += [(u, None) for u in text_units(rest[:i])]
            name = rest[i + 1:j]
            shown, url = links.get(name, (rest[i:j + 1], None))
            shown = shown.replace(" ", _NBSP_MARK) if url else shown
            lead_space = " " if i and rest[i - 1] == " " else ""
            for n, u in enumerate(text_units(shown)):
                tokens.append(((lead_space if n == 0 else "") + u.lstrip() if n == 0 else u, url))
            rest = rest[j + 1:]
        lines: list[list[tuple[str, Optional[str]]]] = [[]]
        for unit, url in tokens:
            line = lines[-1]
            cand = "".join(u for u, _ in line) + unit
            if line and _width(cand.strip().replace(_NBSP_MARK, " "), size, bold) > width \
                    and unit.strip()[:1] not in _CLOSING:
                lines.append([(unit.lstrip(), url)])
            else:
                line.append((unit if line else unit.lstrip(), url))
        for line in lines:
            cx = x
            run: list[tuple[str, Optional[str]]] = []
            for unit, url in line + [("", "\0")]:  # sentinel flushes the last run
                if run and url != run[-1][1]:
                    cx = self._run(cx, y, "".join(u for u, _ in run), run[-1][1], size, color, bold)
                    run = []
                if unit:
                    run.append((unit, url))
            y += size * lead
        return y

    def _run(self, x: float, y: float, s: str, url: Optional[str], size: float, color: str, bold: bool) -> float:
        lead = len(s) - len(s.lstrip())
        x += _width(" " * lead, size, bold)
        s = s.lstrip().replace(_NBSP_MARK, "\u00a0")
        w = _width(s, size, bold)
        item = Text((x, y), s, size, bold=bold, color=color)
        if url:
            self.g.add(Group([item, Line((x, y + size * 0.18), (x + w, y + size * 0.18), Style(THIN * 0.8, color=color))],
                             cls="uw-href", attrs={"data-uw-href": url}))
        else:
            self.g.add(item)
        return x + w


def _logo(g: Group, x: float, y: float, height: float) -> float:
    """The logo with its top left corner at (x, y); returns its width."""
    bx, by, bw, bh = brand.BOX
    s = height / bh
    for a, b, width, color in brand.MARK:
        g.add(Line((x + (a[0] - bx) * s, y + (a[1] - by) * s), (x + (b[0] - bx) * s, y + (b[1] - by) * s),
                   Style(width * s, color=color)))
    g.add(Path(parse_path(brand.WORDMARK, x - bx * s, y - by * s, s), brand.INK))
    return bw * s


def _qr(g: Group, text: str, x: float, y: float, size: float, url: str) -> bool:
    """QR code of ``text`` (reportlab's encoder); False when reportlab is missing."""
    try:
        from reportlab.graphics.barcode import qrencoder
    except ImportError:  # pragma: no cover
        return False
    qr = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    qr.addData(text)
    qr.make()
    n = qr.getModuleCount()
    m = size / n
    cells = Group()
    for r in range(n):
        c = 0
        while c < n:  # one rectangle per run of dark modules on a row
            if qr.isDark(r, c):
                c0 = c
                while c < n and qr.isDark(r, c):
                    c += 1
                cells.add(Rect(x + c0 * m, y + r * m, (c - c0) * m, m * 1.02, Style(0.0, color=INK, fill=INK)))
            else:
                c += 1
    g.add(Group([cells], cls="uw-href", attrs={"data-uw-href": url}))
    return True


def about_page(doc: Document, width: float, height: float, sheets: list[str], about: About) -> Page:
    """The page, ``width`` x ``height`` mm (the size of the first sheet); ``sheets``: the titles of the sheets."""
    from ..rules import check

    lang = normalize_lang(doc.meta.lang)
    L = lambda key, **kw: _t(f"about.{key}", lang, **kw)  # noqa: E731
    page = Page(width, height, Group(cls="page about"), title=L("title"), attrs={"data-uw-about": "1"})
    g = page.root
    k = min(1.4, max(1.0, width / 297.0))  # A4 sizes, a little larger on large sheets
    w = _Writer(g, k)
    g.add(Rect(MARGIN, MARGIN, width - 2 * MARGIN, height - 2 * MARGIN, Style(width=THICK)))

    # title block: same grid as the sheets, folio outside the numbering
    band_y = height - MARGIN - TITLE_BAND
    g.add(Line((MARGIN, band_y), (width - MARGIN, band_y), Style(width=NORMAL)))
    tb_w = min(TITLE_BLOCK_W, width - 2 * MARGIN)
    _title_block(g, doc, width - MARGIN - tb_w, band_y, tb_w, TITLE_BAND, "–", None, L("title"), lang)  # type: ignore[arg-type]
    notes_w = width - 2 * MARGIN - tb_w - 6.0
    g.add(Text((MARGIN + 2.0, band_y + 4.0), _t("notes.title", lang), 2.0, bold=True))
    _Writer(g, 1.0).para(MARGIN + 2.0, band_y + 7.2, notes_w, L("notes"), 1.7, GREY, lead=1.35)

    # header
    x0, top = MARGIN + 12.0 * k, MARGIN + 12.0 * k
    _logo(g, x0, top, 9.0 * k)
    g.add(Text((x0, top + 17.0 * k), L("title"), 5.3 * k, bold=True, color=INK))

    gap = 12.0 * k
    colw = (width - 2 * MARGIN - 24.0 * k - 2 * gap) / 3
    xs = [x0 + i * (colw + gap) for i in range(3)]
    y_top = top + 34.0 * k

    def heading(x: float, y: float, text: str) -> float:
        g.add(Rect(x, y - 3.2 * k, 1.1 * k, 4.4 * k, Style(0.0, color=RUST, fill=RUST)))
        g.add(Text((x + 3.5 * k, y), text, 3.7 * k, bold=True, color=INK))
        return y + 9.0 * k

    def row(x: float, y: float, label: str, value: str, links: Optional[dict] = None) -> float:
        g.add(Text((x, y), label, 2.6 * k, color=GREY))
        return w.para(x + 26.0 * k, y, colw - 26.0 * k, value, 3.0, links=links) + 0.6 * k

    # 1. checks
    findings = check(doc)
    count = {lvl: sum(1 for f in findings if f.level == lvl) for lvl in ("error", "warning", "info")}
    y = heading(xs[0], y_top, L("checks"))
    names = {"nfc15100": "NF C 15-100", "iec60364": "IEC 60364", "enedis": "Enedis", "vde0100": "DIN VDE 0100"}
    profiles = ", ".join(names.get(p, p) for p in doc.profiles) or L("no_profile")
    y = row(xs[0], y, L("profiles"), profiles)
    result = L("result_none") if not any(count.values()) else L("result_counts", errors=count["error"],
                                                                  warnings=count["warning"], infos=count["info"])
    y = row(xs[0], y, L("result"), result)
    from .frame import _generator
    y = row(xs[0], y, L("by"), _generator())
    y += 2.0 * k
    box_top = y - 1.0 * k
    yb = w.para(xs[0] + 3.0 * k, y + 3.0 * k, colw - 6.0 * k, L("scope"), 2.6)
    g.add(Rect(xs[0], box_top, colw, yb - box_top - 0.5 * k, Style(THIN, color=LIGHT)))

    # 2. this document
    y = heading(xs[1], y_top, L("document"))
    y = row(xs[1], y, L("doc_title"), doc.meta.title or "")
    y = row(xs[1], y, L("sheets"), L("sheet_count", count=len(sheets)) if len(sheets) > 1
            else (sheets[0] if sheets else ""))
    if about.doc_id:
        viewer = f"{about.site}/viewer/#d={about.doc_id}"
        y = row(xs[1], y, L("doc_id"), about.doc_id)
        y = row(xs[1], y, L("online"), "{v}", {"v": (_bare(viewer), viewer)})
        r_url = f"{about.site}/r/{about.doc_id}"
        y += 3.0 * k
        g.add(Text((xs[1], y), L("copy"), 3.0 * k, bold=True, color=INK))
        y = w.para(xs[1], y + 4.6 * k, colw, L("copy_text", site=_bare(about.site)), 3.0) + 0.6 * k
        y = w.para(xs[1], y, colw, L("copy_delete"), 3.0, links={"link": (_bare(r_url), r_url)}) + 3.0 * k
        g.add(Text((xs[1], y), L("without"), 3.0 * k, bold=True, color=INK))
        pdf_url = f"{about.site}/pdf/{about.doc_id}?about=0"
        w.para(xs[1], y + 4.6 * k, colw, L("without_text"), 3.0, links={"link": (L("without_link"), pdf_url)})
        contact = r_url
    else:
        contact = f"{about.site}/contact"

    # 3. a word for the team: warm, on a light warm background
    pad = 4.5 * k
    panel = Group()
    g.add(panel)
    y = heading(xs[2], y_top, L("warm_title"))
    y = w.para(xs[2], y, colw, L("warm_1"), 3.0) + 0.6 * k
    y = w.para(xs[2], y, colw, L("warm_2"), 3.0) + 0.6 * k
    y = w.para(xs[2], y, colw, L("warm_3"), 3.0, bold=True) + 2.5 * k
    qs = 28.0 * k
    if _qr(g, contact, xs[2], y, qs, contact):
        qx = xs[2] + qs + 4.0 * k
        w.para(qx, y + 10.0 * k, colw - qs - 4.0 * k, "{c}", 3.4, bold=True, links={"c": (_bare(contact), contact)})
        if about.doc_id:
            w.para(qx, y + 16.0 * k, colw - qs - 4.0 * k, L("qr_note"), 2.4, GREY)
        y += qs + 6.0 * k
    else:  # pragma: no cover
        y = w.para(xs[2], y, colw, "{c}", 3.4, bold=True, links={"c": (_bare(contact), contact)}) + 3.0 * k
    y = w.para(xs[2], y, colw, L("email"), 2.6, GREY,
               links={"email": ("contact@uniwire.sh", "mailto:contact@uniwire.sh")}) + 0.6 * k
    repo = "https://github.com/uniwire-dev/uniwire"
    y = w.para(xs[2], y, colw, L("open_source"), 2.6, GREY, links={"repo": (_bare(repo), repo)}) + 2.0 * k
    g.add(Text((xs[2], y), L("thanks"), 3.2 * k, bold=True, color=RUST))
    panel.add(Rect(xs[2] - pad, y_top - 9.0 * k, colw + 2 * pad, y - y_top + 15.0 * k, Style(0.0, color=WARM, fill=WARM)))
    return page
