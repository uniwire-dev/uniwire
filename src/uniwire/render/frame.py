"""Sheet composition: border, scaled drawing area, title block."""

from __future__ import annotations

import math
from typing import Any, Optional

from ..i18n import normalize_lang
from ..i18n import t as _t
from ..layout.engine import (
    MARGIN,
    NOTES_BAND,
    PAPER,
    TITLE_BAND,
    TITLE_BLOCK_W,
    SheetLayout,
    drawing_area,
    notes_beside,
)
from ..model import Document, View
from ..resolve import iter_nodes
from ..units import fmt
from .colors import Legend
from .scene import (
    NORMAL,
    THICK,
    THIN,
    Group,
    Item,
    Line,
    Page,
    Rect,
    Style,
    Text,
    bbox,
    text_units,
    text_width,
    transform,
)


def _generator() -> str:
    from .. import __version__
    return f"uniwire {__version__}"


def _fit(text: str, size: float, width: float) -> float:
    tw = text_width(text, size)
    return size if tw <= width else max(1.2, size * width / tw)


def compose_page(doc: Document, view: View, lay: SheetLayout, folio: int, total: int, sheet_title: str,
                 legend: Optional[Legend] = None, scale: Optional[float] = None) -> Page:
    """One sheet: frame, title block, the drawing (``scale``: the enlargement shared by the sheets of the view;
    otherwise reduced to fit when needed, never enlarged)."""
    w, h = PAPER[view.paper]
    if view.orientation == "portrait":
        w, h = h, w
    page = Page(w, h, Group(cls="page"), title=sheet_title)
    root = page.root

    ax, ay, aw, ah = drawing_area(view)
    if view.title_block:
        root.add(Rect(MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN, Style(width=THICK)))
    else:
        ah += TITLE_BAND + 2.0

    lang = normalize_lang(doc.meta.lang)
    # drawing scaled to fit; enlarged only with the scale shared by all the sheets of the view (see render_pages)
    if scale is None:
        scale = min(1.0, aw / max(lay.width, 1e-6), ah / max(lay.height, 1e-6))
    dx = ax + max(0.0, (aw - lay.width * scale) / 2) if lay.width * scale < aw * 0.6 else ax
    drawing = transform(lay.group, dx, ay, scale=scale)
    root.add(drawing)  # type: ignore[arg-type]
    if scale < 0.995:
        root.add(Text((w - MARGIN - 2.0, MARGIN + 4.0), _t("render.scale", lang, scale=fmt(round(scale, 2))), 1.8, "end"))
    if legend is not None and legend.entries:
        lw, lh = _legend_size(legend)
        scale_box = [(w - MARGIN - 40.0, MARGIN, w - MARGIN, MARGIN + 6.0)] if scale < 0.995 else []
        x, y = _free_spot(drawing, (ax, ay, aw, ah), lw, lh, scale_box)
        root.add(_legend(legend, x, y, lw, lh))

    if not view.title_block:
        return page
    folio = view.first_folio + folio - 1
    total = view.total_folios or (total if view.first_folio == 1 else None)
    # title-block band
    band_y = h - MARGIN - TITLE_BAND
    root.add(Line((MARGIN, band_y), (w - MARGIN, band_y), Style(width=NORMAL)))
    tb_w = min(TITLE_BLOCK_W, w - 2 * MARGIN)
    first = lay.spec.roots[0] if lay.spec.roots else None
    here = first if first is not None and all(first is not s for s in doc.sources) else None  # a board on its sheet
    _title_block(root, doc, w - MARGIN - tb_w, band_y, tb_w, TITLE_BAND, folio, total, sheet_title, lang, here)
    if notes_beside(view):
        _notes(root, doc, MARGIN + 2.0, band_y, w - 2 * MARGIN - tb_w - 6.0, TITLE_BAND, lang)
    else:  # narrow sheet (A4 portrait): notes in a band above the title block
        root.add(Line((MARGIN, band_y - NOTES_BAND), (w - MARGIN, band_y - NOTES_BAND), Style(width=THIN)))
        _notes(root, doc, MARGIN + 2.0, band_y - NOTES_BAND, w - 2 * MARGIN - 4.0, NOTES_BAND, lang)
    return page


def _cell(g: Group, x: float, y: float, w: float, h: float, label: str, value: str, size: float = 2.2,
          bold: bool = False) -> None:
    g.add(Rect(x, y, w, h, Style(width=THIN)))
    g.add(Text((x + 1.0, y + 2.4), label, 1.5, color="#555555"))
    if value:
        lines, s = _fit_lines(value, size, (w - 4.0) * (0.9 if bold else 1.0), (h - 4.4) / 2.4)
        for i, line in enumerate(reversed(lines)):
            g.add(Text((x + 1.0, y + h - 1.6 - i * s * 1.2), line, s, bold=bold))


def _fit_lines(text: str, size: float, width: float, two_line_size: float) -> tuple[list[str], float]:
    """Lines and size of a title block value: one line, reduced down to a readable size, else two lines
    (at most ``two_line_size``), else one line cut with an ellipsis; never wider than the cell."""
    s = _fit(text, size, width)
    words = text_units(text)  # words, and each CJK character
    if s < min(size, 1.6) and len(words) > 1:
        pair = _halves(words)
        s2 = min(two_line_size, size, *(_fit(t, size, width) for t in pair))
        if s2 > s:
            return list(pair), s2
    if text_width(text, s) > width:
        text = _cut(text, s, width) + "…"
    return [text], s


def _halves(words: list[str]) -> tuple[str, str]:
    """``words`` on two lines, the wider as narrow as possible. The first line widens and the second narrows as
    the cut moves right: the best cut is where they cross, found by halving."""
    def pair(i: int) -> tuple[str, str]:
        return "".join(words[:i]).strip(), "".join(words[i:]).strip()

    def wider_first(i: int) -> bool:
        a, b = pair(i)
        return text_width(a, 1.0) >= text_width(b, 1.0)

    lo, hi = 1, len(words) - 1  # the first cut where the first line is the wider (hi when none)
    while lo < hi:
        mid = (lo + hi) // 2
        if wider_first(mid):
            hi = mid
        else:
            lo = mid + 1
    return min((pair(i) for i in (lo - 1, lo) if i >= 1),
               key=lambda p: max(text_width(p[0], 1.0), text_width(p[1], 1.0)))


def _cut(text: str, size: float, width: float) -> str:
    """The longest beginning of ``text`` that fits ``width`` with an ellipsis (trailing spaces dropped), found by
    halving; a single character when none fits."""
    if len(text) <= 1:
        return text

    def fits(k: int) -> bool:
        return text_width(text[:k].rstrip() + "…", size) <= width

    # one character at least: up to the second one that is not a space
    floor = min(next((i for i in range(1, len(text)) if not text[i].isspace()), len(text)), len(text) - 1)
    lo, hi = 0, len(text) - 1  # lo: no fitting length found yet
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(mid):
            lo = mid
        else:
            hi = mid - 1
    return text[:max(lo, floor)].rstrip()


_PROFILE_NAMES = {"iec60364": "IEC 60364", "nfc15100": "NF C 15-100", "enedis": "Enedis"}


def _title_block(g: Group, doc: Document, x: float, y: float, w: float, h: float, folio: int, total: Optional[int],
                 sheet_title: str, lang: str = "en", here: Any = None) -> None:
    """``here``: the node a sheet of its own is drawn from (a board behind a transformer has its own voltage and
    short-circuit current, shown instead of the installation's)."""
    L = lambda key: _t(key, lang)  # noqa: E731
    m, inst = doc.meta, doc.installation
    rev = m.revisions[-1] if m.revisions else None
    tb = Group(cls="title-block")
    rh = h / 4
    # left column: title + project
    c1 = w * 0.48
    _cell(tb, x, y, c1, rh * 2, L("tb.title"), m.title or "", 3.2, True)
    _cell(tb, x, y + rh * 2, c1, rh, L("tb.sheet_title"), sheet_title or L("tb.default_sheet_title"), 2.2)
    _cell(tb, x, y + rh * 3, c1 / 2, rh, L("tb.project"), " · ".join(v for v in (m.project, m.drawing_number) if v))
    _cell(tb, x + c1 / 2, y + rh * 3, c1 / 2, rh, L("tb.client"), m.client or "")
    # middle column: installation
    c2x, c2 = x + c1, w * 0.30
    half = c2 / 2
    un = getattr(here, "un_V", None) or inst.un_V
    ik = getattr(here, "ik_kA", None) or inst.ik3_kA
    sys = " ".join(v for v in (getattr(here, "system", None) or inst.system or "", fmt(un, " V") if un else "") if v)
    _cell(tb, c2x, y, half, rh, L("tb.earthing"), inst.earthing or "")
    _cell(tb, c2x + half, y, half, rh, L("tb.voltage"), sys)
    pw = inst.subscribed_kVA or inst.planned_kVA
    _cell(tb, c2x, y + rh, half, rh, L("tb.power"), fmt(pw, " kVA") if pw else "")
    _cell(tb, c2x + half, y + rh, half, rh, L("tb.ik_max"), fmt(ik, " kA") if ik else "")
    earth = inst.earth_resistance_ohm or next((getattr(n, "resistance_ohm", None) for n, _, _ in iter_nodes(doc)
                                                if n.type == "earth" and getattr(n, "resistance_ohm", None)), None)
    _cell(tb, c2x, y + rh * 2, half, rh, L("tb.earth_electrode"), fmt(earth, " Ω") if earth else "")
    _cell(tb, c2x + half, y + rh * 2, half, rh, L("tb.standard"),
          inst.standard or ", ".join(_PROFILE_NAMES.get(p, p) for p in doc.profiles))
    _cell(tb, c2x, y + rh * 3, half, rh, L("tb.drawn_by"), m.author or "")
    _cell(tb, c2x + half, y + rh * 3, half, rh, L("tb.checked_by"), m.checked_by or "")
    # right column
    c3x, c3 = c2x + c2, w - c1 - c2
    _cell(tb, c3x, y, c3, rh, L("tb.company"), m.company or "")
    _cell(tb, c3x, y + rh, c3 / 2, rh, L("tb.date"), (rev.date if rev and rev.date else m.date) or "")
    _cell(tb, c3x + c3 / 2, y + rh, c3 / 2, rh, L("tb.revision"), rev.index if rev else "")
    sheet = Group(cls="tb-sheet")  # the sheet number: renumbered when several views make one drawing set
    _cell(sheet, c3x, y + rh * 2, c3, rh, L("tb.sheet"), f"{folio} / {total}" if total else str(folio), 3.0, True)
    tb.add(sheet)
    _cell(tb, c3x, y + rh * 3, c3, rh, L("tb.generated_by"), _generator(), 1.8)
    g.add(tb)


def _notes(g: Group, doc: Document, x: float, y: float, w: float, h: float, lang: str = "en") -> None:
    lines: list[str] = []
    if doc.meta.site:
        lines.append(_t("notes.site", lang, site=doc.meta.site))
    inst = doc.installation
    if inst.supply:
        lines.append(_t("notes.supply", lang, supply=inst.supply))
    lines += doc.meta.notes
    if doc.meta.revisions:
        lines += [" ".join(_t("notes.revision", lang, index=r.index, date=r.date or "", description=r.description or "").split())
                  for r in doc.meta.revisions[-2:]]
    ng = Group(cls="notes")
    ng.add(Text((x, y + 4.0), _t("notes.title", lang), 2.0, bold=True))
    size = 1.7
    max_lines = int((h - 6.0) / (size * 1.35))
    wrapped: list[str] = []
    for t in lines:  # wrap to the available width, between words or CJK characters
        cur = ""
        for u in text_units(t):
            cand = (cur + u) if cur else u.strip()
            if text_width(cand, size) <= w or not cur:
                cur = cand
            else:
                wrapped.append(cur)
                cur = u.strip()
        wrapped.append(cur)
    if len(wrapped) > max_lines:
        wrapped = wrapped[: max_lines - 1] + [_t("notes.more", lang, count=len(wrapped) - max_lines + 1)]
    for i, t in enumerate(wrapped):
        ng.add(Text((x, y + 7.2 + i * size * 1.35), t, _fit(t, size, w), color="#222222"))
    g.add(ng)


# ---------------------------------------------------------------- colour legend
LEG_TITLE, LEG_TEXT, LEG_ROW, LEG_SAMPLE, LEG_PAD = 2.0, 1.8, 3.0, 7.0, 1.5


def _legend_size(legend: Legend) -> tuple[float, float]:
    rows = max((text_width(e.label, LEG_TEXT) for e in legend.entries), default=0.0) * 1.15 + LEG_SAMPLE + 1.5
    return max(text_width(legend.title, LEG_TITLE) * 1.15, rows) + 2 * LEG_PAD, 4.6 + len(legend.entries) * LEG_ROW + 0.6


def _legend(legend: Legend, x: float, y: float, w: float, h: float) -> Group:
    g = Group(cls="uw-legend")
    g.add(Rect(x, y, w, h, Style(width=THIN, fill="#ffffff")))
    g.add(Text((x + LEG_PAD, y + 3.4), legend.title, LEG_TITLE, bold=True))
    for i, e in enumerate(legend.entries):
        yy = y + 4.6 + (i + 0.5) * LEG_ROW
        a, b = (x + LEG_PAD, yy), (x + LEG_PAD + LEG_SAMPLE, yy)
        g.add(Line(a, b, Style(width=THICK, dash=e.dash, color=e.color)))
        if e.stripe:
            g.add(Line(a, b, Style(width=THICK, dash=(1.0, 1.0), color=e.stripe)))
        g.add(Text((b[0] + 1.5, yy), e.label, LEG_TEXT, "start", "middle"))
    return g


def _leaf_boxes(item: Item, out: list[tuple[float, float, float, float]]) -> None:
    if isinstance(item, Group):
        for it in item.items:
            _leaf_boxes(it, out)
        return
    b = bbox(item)
    if b is not None:
        out.append(b)


def _free_spot(drawing: Group, area: tuple[float, float, float, float], w: float, h: float,
               extra: list[tuple[float, float, float, float]]) -> tuple[float, float]:
    """Top-left corner of a ``w`` x ``h`` box in the drawing area clear of the drawing: a free corner (top
    right, top left, bottom right, bottom left), else the free spot nearest the bottom-right corner, else
    the least covered one."""
    ax, ay, aw, ah = area
    cell = 2.0
    nx, ny = max(1, int(aw / cell)), max(1, int(ah / cell))
    wc, hc = min(nx, math.ceil(w / cell) + 1), min(ny, math.ceil(h / cell) + 1)
    occ = [[0] * nx for _ in range(ny)]
    boxes: list[tuple[float, float, float, float]] = list(extra)
    _leaf_boxes(drawing, boxes)
    for x0, y0, x1, y1 in boxes:
        i0, i1 = max(0, int((x0 - ax - 1.0) / cell)), min(nx - 1, int((x1 - ax + 1.0) / cell))
        j0, j1 = max(0, int((y0 - ay - 1.0) / cell)), min(ny - 1, int((y1 - ay + 1.0) / cell))
        for j in range(j0, j1 + 1):
            row = occ[j]
            for i in range(i0, i1 + 1):
                row[i] = 1
    pre = [[0] * (nx + 1) for _ in range(ny + 1)]
    for j in range(ny):
        acc = 0
        for i in range(nx):
            acc += occ[j][i]
            pre[j + 1][i + 1] = pre[j][i + 1] + acc

    def covered(i: int, j: int) -> int:
        return pre[j + hc][i + wc] - pre[j][i + wc] - pre[j + hc][i] + pre[j][i]

    last_i, last_j = nx - wc, ny - hc
    spots = [(last_i, 0), (0, 0), (last_i, last_j), (0, last_j)]
    spots += sorted(((i, j) for j in range(last_j + 1) for i in range(last_i + 1)),
                    key=lambda p: (last_i - p[0]) ** 2 + (last_j - p[1]) ** 2)
    i, j = next((p for p in spots if covered(*p) == 0), None) or min(spots, key=lambda p: covered(*p))
    x = ax + i * cell + (cell if i > 0 else 0.0)
    y = ay + j * cell + (cell if j > 0 else 0.0)
    return min(x, ax + aw - w), min(y, ay + ah - h)
