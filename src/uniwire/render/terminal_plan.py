"""Terminal plan drawn as sheets (view kind ``terminals``, format 1.1, UEP-0001 §3.5.2), in the usual layout of a
terminal diagram: one table per terminal strip, from left to right
the function, one column per external cable (its tag at the top, its type below, the core on the line of each
terminal it lands on), the external target and its terminal, the terminal number and the bridges, the internal
target and its terminal, one column per internal cable, and the wire mark. The strip's designation heads the middle
of the table; the rows fill the sheet like a form. A target connected on site is starred, with a note. Same data as
``uniwire terminals`` (:func:`uniwire.exports.terminal_rows`); a long strip goes on over the next sheets."""

from __future__ import annotations

from typing import Any

from ..exports import terminal_rows
from ..i18n import t as _t
from ..layout.engine import SheetLayout, SheetSpec, drawing_area
from ..model import Document, View
from ..resolve import build_index
from ..units import fmt
from .frame import compose_page
from .scene import NORMAL, THIN, Circle, Group, Line, Page, Rect, Style, Text, text_width

FUNCTION_W, CABLE_W, TARGET_W, PORT_W, PART_W, TERM_W, BRIDGE_W, MARK_W = 50.0, 10.0, 34.0, 14.0, 28.0, 14.0, 12.0, 18.0
MIN_CABLES = 4  # empty cable columns on each side, as on the printed form
STRIP_H, LABEL_H, LINE_H, PAD, NOTE_H = 20.0, 28.0, 3.8, 1.4, 7.0
SIZE, HEAD_SIZE = 2.5, 2.2  # text of the cells and of the column titles: read at arm's length on an A3 print
FRAME = Style(width=NORMAL)
RULE = Style(width=THIN)


def _fit(text: str, width: float, size: float = SIZE) -> str:
    while len(text) > 3 and text_width(text, size) > width - 1.6:
        text = text[:-2] + "…"
    return text


def _lines(row: dict[str, Any]) -> int:
    return max(1, len(row["_inside"]), len(row["_outside"]))


class _Cols:
    """The columns of one strip."""

    def __init__(self, rows: list[dict[str, Any]], name, kind, fill: float = 0.0):
        ext = list(dict.fromkeys(c for r in rows for _, c, _ in r["_outside"] if c))
        self.ext = ext + [""] * max(0, MIN_CABLES - len(ext))
        self.int: list[str] = [""] * MIN_CABLES  # cabinet-side cables: none in format 1.1 (wires only)
        self.name, self.kind = name, kind
        if fill <= 0:  # the natural width: what the fixed columns take
            fill = FUNCTION_W + 2 * TARGET_W
        grow = fill / (FUNCTION_W + 2 * TARGET_W)  # the free text columns share the width of the sheet
        self.function_w, self.target_w = FUNCTION_W * grow, TARGET_W * grow
        x = self.function_w
        self.x_ext = x
        x += CABLE_W * len(self.ext)
        self.x_target, self.x_port = x, x + self.target_w
        self.x_part = self.x_port + PORT_W
        self.x_term = self.x_part + PART_W
        self.x_bridge = self.x_term + TERM_W
        self.x_itarget = self.x_bridge + BRIDGE_W
        self.x_iport = self.x_itarget + self.target_w
        self.x_int = self.x_iport + PORT_W
        self.x_mark = self.x_int + CABLE_W * len(self.int)
        self.width = self.x_mark + MARK_W


class _Sheet:
    def __init__(self) -> None:
        self.g = Group(cls="terminal-plan")
        self.y = 0.0
        self.width = 0.0
        self.names: list[str] = []
        self.site = False
        self.cols: _Cols | None = None
        self.summary = ""


def terminal_plan_pages(doc: Document, view: View, lang: str) -> list[Page]:
    """The sheets of the terminal plan of every strip of ``doc`` (none without terminal strips)."""
    rows = terminal_rows(doc)
    if not rows:
        return []
    index = build_index(doc)

    def place(enclosure: str) -> str:  # the reference designation of the enclosure or board, else its id
        e = next((e for e in doc.enclosures if e.id == enclosure), None) or index.nodes.get(enclosure)
        return (getattr(e, "ref", None) or enclosure) if e is not None else enclosure

    def tree_cable(cid: str):
        n = index.nodes.get(cid.removesuffix(".cable")) if cid.endswith(".cable") else None
        return n.cable if n is not None else None

    def name(cid: str) -> str:  # a tree cable '<node id>.cable' by its tag ('W11')
        c = tree_cable(cid)
        return (c.ref or cid) if c is not None else cid

    def kind(cid: str) -> str:  # its type: designation, composition, length ('4G2.5 35 m')
        c = tree_cable(cid)
        if c is None:
            return ""
        comp = f"{c.cores or ''}{fmt(c.section_mm2) if c.section_mm2 else ''}"
        return " ".join(x for x in (c.designation, comp, f"{fmt(c.length_m)} m" if c.length_m else "") if x)

    _, _, aw, ah = drawing_area(view)
    by_strip: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_strip.setdefault(id(r["_strip"]), []).append(r)
    strips = []
    for rs in by_strip.values():
        natural = _Cols(rs, name, kind)
        free = FUNCTION_W + 2 * TARGET_W + max(0.0, aw - natural.width)  # the table takes the width of the sheet
        strips.append((rs, _Cols(rs, name, kind, free)))
    widest = max(c.width for _, c in strips)
    room = ah / min(1.0, aw / widest) - 2 * NOTE_H  # reduced to the width of the sheet; the two notes below
    row_h = 2 * PAD + LINE_H
    sheets: list[_Sheet] = []
    for strip_rows, cols in strips:  # each strip starts on a sheet of its own, as in CAD tools
        strip = strip_rows[0]["_strip"]
        title = strip.ref or strip.id
        about = " · ".join(x for x in (strip.label, strip.enclosure and place(strip.enclosure)) if x)
        sheet = _new(sheets, cols, title, about, lang)
        bridges: dict[str, list[float]] = {}
        for r in strip_rows:
            h = row_h + LINE_H * (_lines(r) - 1)
            if sheet.y + h > room:  # the strip goes on over the next sheet
                _close(sheet, bridges, room, row_h)
                bridges = {}
                sheet = _new(sheets, cols, title, f"{about} {_t('tplan.cont', lang)}".strip(), lang)
            _row(sheet, cols, r, h, bridges)
        _close(sheet, bridges, room, row_h)
        sheet.summary = _summary(strip_rows, lang)
    title = view.title or _t("tplan.title", lang)
    pages = []
    for i, s in enumerate(sheets, 1):
        if s.site:  # what the star means, under the table
            s.g.add(Text((0.0, s.y + 5.0), _t("tplan.site_note", lang), HEAD_SIZE))
            s.y += NOTE_H
        if s.summary:  # what to order: the terminals of the strip by kind and part, as on CAD terminal diagrams
            s.g.add(Text((0.0, s.y + 5.0), s.summary, HEAD_SIZE, bold=True))
            s.y += NOTE_H
        lay = SheetLayout(SheetSpec([]), s.g, s.width, s.y, [], [])
        pages.append(compose_page(doc, view, lay, i, len(sheets), f"{title} · {', '.join(s.names)}"))
    return pages


def _new(sheets: list[_Sheet], cols: _Cols, title: str, about: str, lang: str) -> _Sheet:
    """A new sheet, with the header of the strip: its designation over the middle columns, the column titles."""
    s = _Sheet()
    sheets.append(s)
    s.cols, s.width, s.names = cols, cols.width, [title]
    g, top = s.g, 0.0
    fill = Style(width=NORMAL, fill="#F2F2F2")
    head_h = STRIP_H + LABEL_H
    g.add(Rect(0.0, top, cols.width, head_h, FRAME))
    # the strip, over the targets, terminals and bridges
    x0, x1 = cols.x_target, cols.x_int
    g.add(Rect(x0, top, x1 - x0, STRIP_H, fill))
    g.add(Text(((x0 + x1) / 2, top + 4.5), _t("tplan.strip", lang), HEAD_SIZE, "middle", "middle"))
    g.add(Text(((x0 + x1) / 2, top + 10.5), title, 4.2, "middle", "middle", bold=True))
    if about:
        g.add(Text(((x0 + x1) / 2, top + 16.2), _fit(about, x1 - x0, HEAD_SIZE), HEAD_SIZE, "middle", "middle"))

    def vertical(x: float, w: float, y: float, h: float, text: str, bold: bool = False) -> None:
        g.add(Rect(x, y, w, h, fill))
        if text:
            g.add(Text((x + w / 2 + 0.8, y + h - 1.4), _fit(text, h, 2.0), 2.0, "start", "alphabetic", 90, bold=bold))

    for x0, cables in ((cols.x_ext, cols.ext), (cols.x_int, cols.int)):  # cable columns: name above, type below
        for k, cid in enumerate(cables):
            vertical(x0 + k * CABLE_W, CABLE_W, top, STRIP_H + LABEL_H / 2, cols.name(cid) if cid else "", True)
            vertical(x0 + k * CABLE_W, CABLE_W, top + STRIP_H + LABEL_H / 2, LABEL_H / 2, cols.kind(cid) if cid else "")
    y = top + STRIP_H
    for x, w, key, upright in ((0.0, cols.function_w, "label", False), (cols.x_target, cols.target_w, "outside", False),
                               (cols.x_port, PORT_W, "port", True), (cols.x_part, PART_W, "part", False),
                               (cols.x_term, TERM_W, "terminal", True),
                               (cols.x_bridge, BRIDGE_W, "bridge", True), (cols.x_itarget, cols.target_w, "inside",
                                                                              False),
                               (cols.x_iport, PORT_W, "port", True), (cols.x_mark, MARK_W, "mark", False)):
        if upright:
            vertical(x, w, y, LABEL_H, _t(f"tplan.{key}", lang))
        else:
            h = LABEL_H if key != "label" else LABEL_H + STRIP_H
            yy = y if key != "label" else top
            g.add(Rect(x, yy, w, h, fill))
            g.add(Text((x + w / 2, yy + h - 2.6), _fit(_t(f"tplan.{key}", lang), w, HEAD_SIZE), HEAD_SIZE, "middle",
                       bold=True))
    if cols.x_mark + MARK_W > 0:  # the mark column also spans the strip band
        g.add(Rect(cols.x_mark, top, MARK_W, STRIP_H, fill))
    s.y = head_h
    return s


def _row(sheet: _Sheet, cols: _Cols, r: dict[str, Any], h: float, bridges: dict[str, list[float]]) -> None:
    y = sheet.y
    row = Group(cls="terminal", attrs={"data-uw-terminal": f"{r['strip']}:{r['terminal']}"})

    def cell(x: float, w: float, lines: list[str], bold: bool = False, middle: bool = False) -> None:
        row.add(Rect(x, y, w, h, RULE))
        for k, text in enumerate(lines):
            if text:
                cy = y + PAD + LINE_H * k + LINE_H / 2
                at = (x + w / 2, cy) if middle else (x + 1.0, cy)
                row.add(Text(at, _fit(text, w), SIZE, "middle" if middle else "start", "middle", bold=bold))

    def split(display: str) -> tuple[str, str]:  # '-M1:U1' -> ('-M1', 'U1')
        dev, _, port = display.rpartition(":")
        return (dev, port) if dev else (display, "")

    site = [s or r["wiring"] == "site" for s in r["_site"]]
    sheet.site = sheet.site or any(site)
    outside = [split(d) for d, _, _ in r["_outside"]]
    inside = [split(d) for d, _ in r["_inside"]]
    cell(0.0, cols.function_w, [r["label"]])
    for k, cid in enumerate(cols.ext):
        cores = [core or "•" for _, c, core in r["_outside"] if cid and c == cid]
        cell(cols.x_ext + k * CABLE_W, CABLE_W, [", ".join(cores)], middle=True)
    cell(cols.x_target, cols.target_w, [d + (" *" if s else "") for (d, _), s in zip(outside, site)])
    cell(cols.x_port, PORT_W, [p for _, p in outside], middle=True)
    cell(cols.x_part, PART_W, [r["product"]])
    cell(cols.x_term, TERM_W, [r["terminal"]], bold=True, middle=True)
    cell(cols.x_bridge, BRIDGE_W, [])
    cell(cols.x_itarget, cols.target_w, [d for d, _ in inside])
    cell(cols.x_iport, PORT_W, [p for _, p in inside], middle=True)
    for k in range(len(cols.int)):
        cell(cols.x_int + k * CABLE_W, CABLE_W, [])
    cell(cols.x_mark, MARK_W, [r["mark"]])
    sheet.g.add(row)
    if r["bridge_group"]:
        bridges.setdefault(r["bridge_group"], []).append(y + PAD + LINE_H / 2)  # level with the terminal number
    sheet.y = y + h


def _close(sheet: _Sheet, bridges: dict[str, list[float]], room: float, row_h: float) -> None:
    """The bridges of the sheet, then empty ruled rows down to the bottom, as on the printed form."""
    cols = sheet.cols
    assert cols is not None
    lanes: list[float] = []  # lowest end of the last group in each lane: groups that overlap go side by side
    for ys in bridges.values():  # one vertical line per bridge group, a dot on each terminal
        lane = next((k for k, end in enumerate(lanes) if end < min(ys)), len(lanes))
        if lane == len(lanes):
            lanes.append(0.0)
        lanes[lane] = max(ys)
        x = cols.x_bridge + 3.0 + (lane % 3) * 3.0
        if len(ys) > 1:
            sheet.g.add(Line((x, min(ys)), (x, max(ys)), Style(width=NORMAL)))
        for y in ys:
            sheet.g.add(Circle((x, y), 0.7, Style(width=THIN, fill="#000000")))
    xs = sorted({0.0, cols.x_target, cols.x_port, cols.x_part, cols.x_term, cols.x_bridge, cols.x_itarget, cols.x_iport,
                 cols.x_mark, cols.width} | {cols.x_ext + k * CABLE_W for k in range(len(cols.ext))}
                | {cols.x_int + k * CABLE_W for k in range(len(cols.int))})
    blank = Group(cls="blank-rows")
    while sheet.y + row_h <= room:
        for a, b in zip(xs, xs[1:]):
            blank.add(Rect(a, sheet.y, b - a, row_h, RULE))
        sheet.y += row_h
    sheet.g.add(blank)
    sheet.g.add(Rect(0.0, 0.0, cols.width, sheet.y, FRAME))


def _summary(rows: list[dict[str, Any]], lang: str) -> str:
    """'8 terminals: 7 feed-through, 1 earth (UK 4-PE)': the count of the strip by kind and part number."""
    count: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r["kind"], r["product"])
        count[key] = count.get(key, 0) + 1
    detail = ", ".join(f"{n} {_t(f'tplan.kind.{k}', lang)}" + (f" ({p})" if p else "") for (k, p), n in count.items())
    return _t("tplan.summary", lang, count=len(rows), detail=detail)
