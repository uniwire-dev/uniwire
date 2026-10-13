from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Optional

from .. import registry
from ..i18n import normalize_lang
from ..i18n import t as _t
from ..labels import (
    CARTOUCHE_TITLES,
    PROTECTIVE,
    SWITCHING,
    Mark,
    annotation,
    cell,
    feeder_mark,
    part_number,
    poles_mark,
    protection_short,
    state_text,
    system_mark,
)
from ..model import Document, NodeBase, View
from ..render.scene import (
    BUS,
    NORMAL,
    THICK,
    THIN,
    Circle,
    Ellipse,
    Group,
    Line,
    Polyline,
    Rect,
    Style,
    Text,
    bbox,
    text_width,
    transform,
)
from ..render.semantics import (
    add_cls,
    busbar_group,
    edge_group,
    finish_link_group,
    link_group,
    node_group,
    ref_group,
)
from ..resolve import Index, build_index, iter_nodes
from ..symbols import BUSWAY_H, DASH, PLC_SLOT_W, Symbol, offpage, symbol_for
from .routing import LANE, End, Obstacles, _hit, _seg_cost, boxes_union, place_box, place_label, route, text_box

GAP = 5.0  # vertical gap between two symbols in series
BUS_GAP = 3.75  # between a symbol and its busbar
CHILD_GAP = 3.75  # between the busbar and the outgoing feeders
BOARD_PAD = 2.5  # horizontal padding of a board frame
BOARD_TOP = 6.0  # room for the board name
ANN_SIZE = 2.0
ANN_LINE = 2.45
ANN_MIN = 1.5
ROOT_GAP_COLS = 0.5

BOTTOM_TYPES = {"pv_array", "battery", "offpage"}
SIDE_TYPES = {"spd", "earth", "earthing_switch", "voltage_indicator", "neutral_impedance", "earth_bar",
              "surge_limiter", "insulation_monitor", "protection_relay"}


# --------------------------------------------------------------------- tree
@dataclass
class LNode:
    node: Optional[NodeBase]
    kind: str  # 'node' | 'stub' | 'bus_in'
    sym: Symbol
    children: list[LNode] = field(default_factory=list)
    label: str = ""
    target: Optional[str] = None  # id of the root of the target sheet (off-page reference)
    bus_out: bool = False  # busbar continued on the next sheet
    target_folio: Optional[int] = None  # sheet of the target of an off-page reference
    # computed
    width: float = 0.0
    x_left: float = 0.0
    x: float = 0.0
    y: float = 0.0
    frame_top: float = 0.0
    bus_y: Optional[float] = None
    bus_x0: float = 0.0
    bus_x1: float = 0.0
    bottom: bool = False  # load placed on the common baseline
    open_feeder: bool = False  # feeder with no described load: arrow down to the common baseline
    ann: list[str] = field(default_factory=list)
    ann_size: float = ANN_SIZE
    tagged: bool = False

    @property
    def id(self) -> str:
        return self.node.id if self.node is not None and self.node.id else f"_{self.kind}_{id(self)}"

    @property
    def type(self) -> str:
        return self.node.type if self.node is not None else self.kind  # type: ignore[attr-defined]

    @property
    def is_board(self) -> bool:
        return self.kind == "node" and self.type == "board"

    @property
    def has_bus(self) -> bool:
        if self.kind == "bus_in":
            return True
        return len(self.children) >= 2 or self.bus_out or (self.type == "busbar" and len(self.children) >= 1)

    @property
    def out_y(self) -> float:
        return self.y + self.sym.height

    def walk(self) -> Iterator[LNode]:
        yield self
        for c in self.children:
            yield from c.walk()

    def ann_box(self) -> Optional[tuple[float, float, float, float]]:
        if not self.ann:
            return None
        x = self.x + self.sym.right + 1.0
        w = max(text_width(t, self.ann_size) for t in self.ann)
        return (x, self.y + 0.3, x + w, self.y + 0.3 + len(self.ann) * ANN_LINE * self.ann_size / ANN_SIZE)

    def sym_box_group(self) -> Rect:
        b = self.sym_box()
        return Rect(b[0], b[1], b[2] - b[0], b[3] - b[1])

    def sym_box(self) -> tuple[float, float, float, float]:
        return (self.x - self.sym.left, self.y, self.x + self.sym.right, self.y + max(self.sym.height, 0.1))

    def content_bottom(self) -> float:
        b = self.y + self.sym.height
        ab = self.ann_box()
        if ab:
            b = max(b, ab[3])
        if self.bus_y is not None:
            b = max(b, self.bus_y)
        return b


@dataclass
class SheetSpec:
    """Content of a sheet, before numbering."""

    roots: list[NodeBase]
    detached: set[str] = field(default_factory=set)
    bus_slice: Optional[tuple[str, int, int]] = None  # (id of the busbar node, start, end)
    continuation: Optional[tuple[str, int, int]] = None  # continuation sheet: children [start:end] of this node
    name: str = ""
    prev: Optional[SheetSpec] = field(default=None, repr=False)  # previous sheet of a continuation
    next: Optional[SheetSpec] = field(default=None, repr=False)  # next sheet of a continuation


@dataclass
class SheetLayout:
    spec: SheetSpec
    group: Group
    width: float
    height: float
    lnodes: list[LNode]
    columns: list[LNode]
    annex: list[LNode] = field(default_factory=list)  # auxiliary devices drawn beside the tree


# ------------------------------------------------------------- construction
def _is_bottom(ln: LNode) -> bool:
    if ln.kind == "stub":
        return True
    if ln.children or ln.kind != "node":
        return False
    return registry.is_load(ln.type) or ln.type in BOTTOM_TYPES


def _build(node: NodeBase, spec: SheetSpec, is_root: bool) -> LNode:
    if not is_root and node.id in spec.detached:
        label = node.ref or node.label or node.id or ""
        return LNode(node, "stub", offpage(label), [], label=label, target=node.id)
    children = list(node.children)
    bus_out = False
    if spec.bus_slice and spec.bus_slice[0] == node.id:
        _, s, e = spec.bus_slice
        bus_out = e < len(children)
        children = children[s:e]
    ln = LNode(node, "node", symbol_for(node), [_build(c, spec, False) for c in children], bus_out=bus_out)
    return ln


def _build_sheet_roots(spec: SheetSpec, index: Index) -> list[LNode]:
    if spec.continuation:
        nid, s, e = spec.continuation
        parent = index.nodes[nid]
        kids = parent.children[s:e]
        bus_sym = Symbol("bus_in", [], 0.0, 0.0, 0.0)
        root = LNode(None, "bus_in", bus_sym, [_build(c, spec, False) for c in kids],
                     label=parent.ref or parent.label or nid, target=nid, bus_out=e < len(parent.children))
        return [root]
    return [_build(r, spec, True) for r in spec.roots]


# ---------------------------------------------------------------- computation
def _measure(ln: LNode, pitch: float) -> float:
    for c in ln.children:
        _measure(c, pitch)
    # intrinsic symbol width (modular PLC, transfer switch...): the column widens if needed
    own = pitch / 2 + ln.sym.right + 16.0 if ln.sym.right > pitch / 2 - 2 else pitch  # + room for the annotation
    if not ln.children:
        ln.width = max(pitch, own)
    else:
        ln.width = max(sum(c.width for c in ln.children), own)
    if ln.is_board:
        ln.width += 2 * BOARD_PAD + pitch * 0.3  # right margin: annotations of the last column
    return ln.width


def _place_x(ln: LNode, x_left: float, pitch: float = 20.0) -> None:
    ln.x_left = x_left
    if not ln.children:
        ln.x = x_left + pitch / 2 if ln.width > pitch else x_left + ln.width / 2
        return
    cx = x_left + (BOARD_PAD if ln.is_board else 0.0)
    for c in ln.children:
        _place_x(c, cx, pitch)
        cx += c.width
    ln.x = ln.children[0].x
    if ln.has_bus:
        ln.bus_x0 = min(ln.x, ln.children[0].x) - (6.0 if ln.kind == "bus_in" else 0.0)
        ln.bus_x1 = ln.children[-1].x + (6.0 if ln.bus_out else 0.0)


def _annotate(ln: LNode, view: View, lang: str, avail_override: float | None = None) -> None:
    if ln.kind != "node" or not view.annotations:
        ln.ann = []
        return
    node = ln.node
    assert node is not None
    if ln.bottom or ln.is_board:
        ln.ann = []
        return
    feeds_bus = any(len(d.children) >= 2 for d in ln.walk())
    lines = annotation(node, lang, show_label=feeds_bus)
    pn = part_number(node)
    tag = pn if view.tag_field == "part_number" and pn else node.ref
    if tag:
        lines.insert(0, tag)
    ln.tagged = bool(tag)
    ln.ann = lines[:5]
    # space available to the right of the symbol
    avail = (ln.x_left + ln.width) - (ln.x + ln.sym.right + 1.0) + view.pitch_mm / 2 - 3.5
    if not ln.children:
        avail = max(view.pitch_mm - ln.sym.right - 4.0, (ln.x_left + ln.width) - (ln.x + ln.sym.right + 1.0) - 1.0)
    if avail_override is not None:
        avail = avail_override
    size = ANN_SIZE
    widest = max((text_width(t, ANN_SIZE) for t in ln.ann), default=0)
    if widest > avail > 0:
        size = max(ANN_MIN, ANN_SIZE * avail / widest)
    ln.ann_size = size
    if widest * size / ANN_SIZE > avail:
        out = []
        for t in ln.ann:
            while len(t) > 3 and text_width(t, size) > avail:
                t = t[:-2] + "…"
            out.append(t)
        ln.ann = out


def _place_y(ln: LNode, y: float) -> None:
    if ln.is_board:
        ln.frame_top = y
        y += BOARD_TOP
    ln.y = y
    if ln.kind == "bus_in":
        ln.bus_y = y
        child_y = y + CHILD_GAP + 1.0
    elif ln.has_bus:
        ln.bus_y = y + ln.sym.height + (BUS_GAP if ln.sym.height > 0 else 1.0)
        ab = ln.ann_box()
        if ab and ab[3] + 1.0 > ln.bus_y and ab[2] > ln.children[0].x + 3:
            ln.bus_y = ab[3] + 1.5
        child_y = ln.bus_y + CHILD_GAP
    else:
        child_y = y + ln.sym.height + (GAP if ln.sym.height > 0 else 0.0)
        ab = ln.ann_box()
        if ab and ln.children and ln.children[0].ann:
            child_y = max(child_y, ab[3] + 1.5)
    for c in ln.children:
        _place_y(c, child_y)


def _shift(ln: LNode, dy: float) -> None:
    for n in ln.walk():
        n.y += dy
        n.frame_top += dy
        if n.bus_y is not None:
            n.bus_y += dy


def _owned(board: LNode) -> Iterator[LNode]:
    """Nodes belonging to the board (excluding sub-boards and loads)."""
    stack = list(board.children)
    yield board
    while stack:
        n = stack.pop()
        if n.is_board or n.bottom:
            continue
        yield n
        stack.extend(n.children)


def _sub_boards(board: LNode) -> list[LNode]:
    out, stack = [], list(board.children)
    while stack:
        n = stack.pop()
        if n.is_board:
            out.append(n)
            continue
        stack.extend(n.children)
    return out


def _board_bottom(board: LNode) -> float:
    return max(n.content_bottom() for n in _owned(board))


def _separate_boards(ln: LNode) -> None:
    for n in ln.walk():
        if n.is_board:
            for sb in _sub_boards(n):
                delta = _board_bottom(n) + 4.0 - sb.frame_top
                if delta > 0:
                    _shift(sb, delta)


def _translate(ln: LNode, dx: float, dy: float) -> None:
    for n in ln.walk():
        n.x += dx
        n.x_left += dx
        n.bus_x0 += dx
        n.bus_x1 += dx
    _shift(ln, dy)


# ------------------------------------------------------------- links / roots
def _find(roots: list[LNode], nid: str) -> Optional[LNode]:
    for r in roots:
        for n in r.walk():
            if n.kind == "node" and n.node is not None and n.node.id == nid:
                return n
    return None


def _root_of(roots: list[LNode], ln: LNode) -> LNode:
    for r in roots:
        if any(n is ln for n in r.walk()):
            return r
    raise KeyError


def _is_chain(r: LNode) -> bool:
    return all(len(n.children) <= 1 for n in r.walk())


def _boxes(ln: LNode) -> list[tuple[float, float, float, float]]:
    out = []
    for n in ln.walk():
        out.append(n.sym_box())
        ab = n.ann_box()
        if ab:
            out.append(ab)
    return out


def _system_of(node: NodeBase, doc: Document) -> Optional[str]:
    """Supply system downstream of a source: first explicit ``system`` below it, else the installation's."""
    stack = list(node.children)
    while stack:
        n = stack.pop(0)
        if getattr(n, "system", None):
            return n.system  # type: ignore[attr-defined]
        stack.extend(n.children)
    return doc.installation.system


# -------------------------------------------------------------- sheet layout
def layout_sheet(doc: Document, view: View, spec: SheetSpec, index: Index | None = None,
                 folio_of: Callable[[str], Optional[int]] | None = None,
                 continuation_folios: tuple[Optional[int], Optional[int]] = (None, None),
                 incoming: Optional[str] = None,
                 node_folio: Callable[[str], Optional[int]] | None = None,
                 incoming_ref: tuple[Optional[int], Optional[str]] = (None, None)) -> SheetLayout:
    """Lay out one sheet. ``node_folio`` (node id -> sheet number) lets links to nodes drawn on other
    sheets end on an off-page reference; ``incoming_ref`` (sheet, node id) is where the incoming feed
    of a detached board comes from."""
    index = index or build_index(doc)
    lang = normalize_lang(doc.meta.lang)
    pitch = view.pitch_mm
    roots = _build_sheet_roots(spec, index)
    for r in roots:
        for n in r.walk():
            n.bottom = _is_bottom(n)
            n.open_feeder = (not n.children and not n.bottom and n.kind == "node" and n.sym.has_output
                             and n.type not in SIDE_TYPES and n.type not in ("controller", "plc")
                             and registry.category(n.type) != "source")

    for r in roots:
        for n in r.walk():
            if n.type == "generator" and n.node is not None:
                n.sym = symbol_for(n.node, _system_of(n.node, doc))

    # feeders continued by a power link (transfer source, parallel / bypass / infeed connection): no open arrow
    connected = {l.from_ for l in doc.links if l.kind == "transfer"}
    connected |= {e for l in doc.links if l.kind in ("parallel", "bypass", "infeed") for e in (l.from_, l.to)}
    for r in roots:
        for n in r.walk():
            if n.node is not None and n.node.id in connected:
                n.open_feeder = False

    # 'transfer' links: roots anchored on a transfer switch of another root
    anchored: dict[int, tuple[LNode, Any]] = {}
    for link in doc.links:
        if link.kind != "transfer":
            continue
        a, b = _find(roots, link.from_), _find(roots, link.to)
        if a is None or b is None:
            continue
        ra, rb = _root_of(roots, a), _root_of(roots, b)
        if ra is not rb and _is_chain(ra) and b.sym.side_input is not None:
            anchored[id(ra)] = (b, link)

    main = [r for r in roots if id(r) not in anchored]
    # power links carrying a device between two trees: one more column between them for the device
    wide_gap: set[int] = set()
    for link in doc.links:
        if link.device is None or link.kind not in POWER_LINKS:
            continue
        a, b = _find(main, link.from_), _find(main, link.to)
        if a is not None and b is not None:
            ia, ib = sorted((main.index(_root_of(main, a)), main.index(_root_of(main, b))))
            wide_gap |= set(range(ia, ib))
    x = 0.0
    for i, r in enumerate(main):
        _measure(r, pitch)
        _place_x(r, x, pitch)
        x += r.width + pitch * (ROOT_GAP_COLS + (1.0 if i in wide_gap else 0.0))
    for r in main:
        for n in r.walk():
            _annotate(n, view, lang)
        _place_y(r, 0.0)
        _separate_boards(r)

    # ties (bus couplers): align the connected busbars
    for link in doc.links:
        if link.kind != "tie":
            continue
        a, b = _find(main, link.from_), _find(main, link.to)
        if a is None or b is None or a.bus_y is None or b.bus_y is None:
            continue
        ra, rb = _root_of(main, a), _root_of(main, b)
        if ra is rb:
            continue
        d = a.bus_y - b.bus_y
        if d > 0:
            _shift(rb, d)
        elif d < 0:
            _shift(ra, -d)

    # normally-open alternative supplies: a band of lanes under the busbars they leave
    band = _alt_band(doc, main, lang)

    # secondary sources on a transfer switch
    for r in roots:
        if id(r) not in anchored:
            continue
        target, _ = anchored[id(r)]
        _measure(r, pitch)
        _place_x(r, 0.0, pitch)
        for n in r.walk():
            _annotate(n, view, lang, avail_override=40.0)
        _place_y(r, 0.0)
        last = list(r.walk())[-1]
        height = max(n.content_bottom() for n in r.walk())
        sx = target.x + target.sym.side_input[0]
        sy = target.y + target.sym.side_input[1]
        top = sy - 3.5 - height
        boxes = [b for m in main for b in _boxes(m)]
        boxes += [_frame_box(n) for m in main for n in m.walk() if n.is_board]
        obstacles = [b for b in boxes if b[3] > top - 1 and b[1] < sy - 2 and b[2] > target.x - 3]
        right = max([b[2] for b in obstacles] + [sx])
        new_x = max(sx, right + 3.0 + r.sym.left)
        _translate(r, new_x - last.x, top)

    everything = [n for r in roots for n in r.walk()]

    # common baseline of the loads
    non_bottom = [n for n in everything if not n.bottom]
    y_load = max((n.content_bottom() for n in non_bottom), default=0.0) + 7.5
    for n in everything:
        if n.bottom:
            n.y = y_load

    # what is already drawn: auxiliary devices and link routes must avoid it
    obs = _obstacles(everything, main, y_load)

    NO_COLUMN = {"earth", "earth_bar", "earthing_switch", "voltage_indicator", "neutral_impedance",
                 "surge_limiter", "insulation_monitor", "protection_relay", "instrument_transformer"}
    on_bus = {id(c) for n in everything if n.has_bus for c in n.children}
    columns = [n for n in everything if not n.children and n.kind != "bus_in" and not
               (n.type in NO_COLUMN and not (n.type == "insulation_monitor" and id(n) in on_bus)) and not
               (n.node is not None and any(n.node.id == l.from_ for l in doc.links if l.kind == "transfer"))]
    columns.sort(key=lambda n: n.x)

    # conductor-count strokes / phase on the outgoing feeders, PEN split marker (TN-C-S)
    marks = Group(cls="conductors")
    _draw_pen_splits(main, doc, marks, obs)
    if view.conductor_marks:
        drawn = _draw_line_marks(main, everything, doc, marks, obs, incoming)
        parent = {id(c): n for n in everything for c in n.children}
        _draw_conductor_marks(columns, index, doc, marks, obs, y_load, drawn, parent)

    # auxiliary devices: on the sheet of the tree node they are linked to, in free space near their partner
    annex = _place_devices(doc, roots, everything, view, lang, obs, pitch)
    homes = _device_homes(doc)
    unlinked: list[NodeBase] = [d for d in doc.devices if homes.get(d.id or "") is None]

    # ------------------------------------------------------------- drawing
    g = Group(cls="diagram")
    for r in roots:
        _draw_tree(r, g, y_load, view, folio_of)
    for r in main:
        for n in r.walk():
            if n.is_board:
                _draw_board_frame(n, g)
    g.add(marks)
    # devices with no link to this sheet: "Auxiliary devices" row at the top right (once only, sheet 1)
    if unlinked and not spec.continuation and (not spec.roots or spec.roots == list(doc.sources) or view.root):
        box = boxes_union(obs.boxes)
        ax0 = (box[2] if box else 0) + 12.0
        g.add(Text((ax0 - 2.0, -3.0), _t("render.auxiliary_devices", lang), 2.0, bold=True))
        for i, dev in enumerate(unlinked):
            ln = LNode(dev, "node", symbol_for(dev))
            ln.x, ln.y, ln.width, ln.x_left = ax0 + ln.sym.left, 1.0 + i * 16.0, pitch, ax0 - 2
            _annotate(ln, view, lang, avail_override=60.0)
            annex.append(ln)
            obs.add_box(ln.sym_box())
            obs.add_box(ln.ann_box())
    for ln in annex:
        g.add(node_group(ln.sym.group(ln.x, ln.y, ln.id)))
        if ln.ann:
            ab = ln.ann_box()
            for i, t in enumerate(ln.ann):
                g.add(Text((ab[0], ln.y + 0.3 + (i + 0.8) * ANN_LINE * ln.ann_size / ANN_SIZE), t, ln.ann_size,
                           bold=(i == 0 and ln.tagged)))
    _draw_view_frames(view, everything + annex, g, obs)
    _draw_enclosures(doc, everything + annex, g, obs)
    _draw_links(doc, roots + annex, anchored, g, view, obs, y_load, lang, node_folio, band)

    # incoming feed from another sheet (detached board)
    if incoming and main and main[0].kind == "node":
        r = main[0]
        top = r.frame_top if r.is_board else r.y
        g.add(ref_group(*incoming_ref, [
            Line((r.x, top - 9.0), (r.x, top)),
            Polyline([(r.x - 1.0, top - 2.0), (r.x, top - 0.2), (r.x + 1.0, top - 2.0)], Style(fill="#000000"), closed=True),
            Text((r.x + 1.5, top - 6.0), incoming, 2.0)]))

    # off-page references / continuations
    for n in everything:
        if n.kind == "stub":
            f = folio_of(n.target) if folio_of and n.target else None
            n.target_folio = f
            n.label = f"{n.sym.extra.get('label', '')}" + (_t("render.to_folio", lang, folio=f) if f else "")
        if n.kind == "bus_in":
            prev_f = continuation_folios[0]
            g.add(ref_group(prev_f, n.target, [
                Polyline([(n.bus_x0 + 1.6, n.bus_y - 1.2), (n.bus_x0, n.bus_y), (n.bus_x0 + 1.6, n.bus_y + 1.2)]),
                Text((n.bus_x0, n.bus_y - 2.0), _t("render.continued_from", lang, label=n.label, folio=prev_f or '?'), 2.0)]))
        if n.bus_out and n.bus_y is not None:
            nxt = continuation_folios[1]
            g.add(ref_group(nxt, n.id, [
                Polyline([(n.bus_x1 - 1.6, n.bus_y - 1.2), (n.bus_x1, n.bus_y), (n.bus_x1 - 1.6, n.bus_y + 1.2)]),
                Text((n.bus_x1, n.bus_y - 2.0), _t("render.continued_on", lang, folio=nxt or '?'), 2.0, "end")]))

    bottom_end = max([y_load + n.sym.height for n in everything if n.bottom] + [y_load + 2.0])
    if view.cartouche and columns:
        _draw_table(g, columns, index, view, lang, bottom_end + 6.0)
    elif columns:
        for n in columns:
            if n.label or (n.node is not None and n.node.label):
                txt = Text((n.x + 0.8, bottom_end + 3.0), n.label or n.node.label or "", 2.0, "end", "middle", 90)
                g.add(ref_group(n.target_folio, n.target, [txt]) if n.kind == "stub" else txt)

    if view.direction == "up":
        b0 = bbox(g) or (0, 0, 1, 1)
        g = _mirror_up(g, b0[1] + b0[3])  # type: ignore[assignment]
    box = bbox(g) or (0, 0, 1, 1)
    g = transform(g, -box[0], -box[1])  # type: ignore[assignment]
    return SheetLayout(spec, g, box[2] - box[0], box[3] - box[1], everything, columns, annex)


# ------------------------------------------------- obstacles / auxiliary devices
def _board_texts(b: LNode) -> list[tuple[tuple[float, float], str, float, str]]:
    """Name and characteristics printed on the top edge of a board frame: (position, text, size, anchor)."""
    x0, y0, x1, _ = _frame_box(b)
    node = b.node
    assert node is not None
    out = []
    name = " ".join(x for x in (node.ref, node.label) if x)
    if name:
        out.append(((b.x + 1.5 if b.x - x0 < 30 else x0 + 1.0, y0 + 3.6), name, 2.4, "start"))
    extra = [t for t in annotation(node) if t != node.label]
    if extra:
        out.append(((x1 - 1.0, y0 + 3.0), "  ".join(extra), 1.8, "end"))
    return out


def _obstacles(everything: list[LNode], main: list[LNode], y_load: float) -> Obstacles:
    obs = Obstacles()
    for n in everything:
        if n.kind != "bus_in" and not (n.is_board and n.sym.height == 0):
            obs.add_box(n.sym_box())
        obs.add_box(n.ann_box())
        start = n.bus_y if n.bus_y is not None else n.out_y
        if n.bus_y is not None:
            obs.add_hline(n.bus_y, n.bus_x0, max(n.bus_x1, n.bus_x0 + 4))
            if n.kind != "bus_in":
                obs.add_vline(n.x, n.out_y, n.bus_y)
        for c in n.children:
            obs.add_vline(c.x, start, c.y)
            if c.x != n.x and n.bus_y is None:
                obs.add_hline(n.out_y + 1.5, n.x, c.x)
        if n.open_feeder:
            obs.add_vline(n.x, n.out_y, y_load + 4.0)
    for r in main:
        for n in r.walk():
            if n.is_board:
                x0, y0, x1, y1 = _frame_box(n)
                obs.add_hline(y0, x0, x1)
                obs.add_hline(y1, x0, x1)
                obs.add_vline(x0, y0, y1)
                obs.add_vline(x1, y0, y1)
                for (tx, ty), t, size, anchor in _board_texts(n):
                    obs.add_box(text_box(tx, ty, text_width(t, size), size, anchor))
    return obs


def _tree_ids(doc: Document) -> set[str]:
    out: set[str] = set()
    stack = list(doc.sources)
    while stack:
        n = stack.pop()
        if n.id:
            out.add(n.id)
        stack.extend(n.children)
    return out


def _device_homes(doc: Document) -> dict[str, Optional[str]]:
    """Tree node each auxiliary device belongs to: its first linked tree node, possibly through other devices.

    A device is drawn on the sheet of its home node (``None``: no link to the tree, "Auxiliary devices" row)."""
    tree = _tree_ids(doc)
    partners: dict[str, list[str]] = {d.id: [] for d in doc.devices if d.id}
    for l in doc.links:
        for x, y in ((l.from_, l.to), (l.to, l.from_)):
            if x in partners:
                partners[x].append(y)

    def home(did: str, seen: set[str]) -> Optional[str]:
        for o in partners.get(did, []):
            if o in tree:
                return o
        for o in partners.get(did, []):
            if o in partners and o not in seen:
                h = home(o, seen | {o})
                if h is not None:
                    return h
        return None

    return {d: home(d, {d}) for d in partners}


def sheet_node_ids(doc: Document, spec: SheetSpec, index: Index) -> set[str]:
    """Ids of the nodes (tree nodes and auxiliary devices) drawn on the sheet ``spec``."""
    ids = {n.node.id for r in _build_sheet_roots(spec, index) for n in r.walk()
           if n.kind == "node" and n.node is not None and n.node.id}
    ids |= {d for d, h in _device_homes(doc).items() if h in ids}
    return ids


def _place_devices(doc: Document, roots: list[LNode], everything: list[LNode], view: View, lang: str,
                   obs: Obstacles, pitch: float) -> list[LNode]:
    """Auxiliary devices whose home node is on this sheet, each in the free space nearest its partner."""
    homes = _device_homes(doc)
    placed: dict[str, LNode] = {n.node.id: n for n in everything if n.kind == "node" and n.node is not None and n.node.id}
    todo = [d for d in doc.devices if d.id and homes.get(d.id) in placed]
    annex: list[LNode] = []
    while todo:
        progress = False
        for dev in list(todo):
            partner = None
            for l in doc.links:
                other = l.to if l.from_ == dev.id else l.from_ if l.to == dev.id else None
                if other in placed:
                    partner = placed[other]
                    break
            if partner is None:
                continue
            todo.remove(dev)
            progress = True
            ln = LNode(dev, "node", symbol_for(dev))
            ln.width = pitch
            _annotate(ln, view, lang, avail_override=60.0)
            ln.x, ln.y = 0.0, 0.0
            u = boxes_union([ln.sym_box()] + ([ln.ann_box()] if ln.ann else []))
            assert u is not None
            pab = partner.ann_box()
            pref_x = (pab[2] if pab else partner.x + partner.sym.right) + 4.0
            x0, y0 = place_box(obs, u[2] - u[0], u[3] - u[1], (pref_x, partner.y))
            ln.x, ln.y = x0 - u[0], y0 - u[1]
            ln.x_left = ln.x - pitch / 2
            obs.add_box(ln.sym_box())
            obs.add_box(ln.ann_box())
            annex.append(ln)
            placed[dev.id] = ln  # type: ignore[index]
        if not progress:
            break
    return annex


def _feeder_chain(ln: LNode, index: Index) -> list[NodeBase]:
    """Final node of a column then its ancestors up to (excluding) the feeding busbar."""
    leaf = ln.node
    if leaf is None or not leaf.id:
        return []
    chain = []
    for n in [leaf] + index.ancestors(leaf.id):
        if n is not leaf and (len(n.children) >= 2 or n.type in ("busbar", "board")):  # type: ignore[attr-defined]
            break
        chain.append(n)
    return chain


def _supply_system(ln: LNode, index: Index, doc: Document) -> Optional[str]:
    if ln.node is None or not ln.node.id:
        return doc.installation.system
    for n in [ln.node] + index.ancestors(ln.node.id):
        if getattr(n, "system", None):
            return n.system  # type: ignore[attr-defined]
    return doc.installation.system


def _needs_neutral(node: NodeBase) -> bool:
    """Whether a circuit below ``node`` (up to a transformer) uses the neutral."""
    stack = list(node.children)
    while stack:
        n = stack.pop()
        if n.type == "transformer":  # type: ignore[attr-defined]
            continue
        cores = (n.cable.cores or "") if n.cable is not None else ""
        if (getattr(n, "poles", None) in ("1P", "1P+N", "3P+N", "4P") or getattr(n, "phase", None) in ("L1", "L2", "L3")
                or getattr(n, "system", None) in ("1P+N", "3P+N", "split-phase")
                or (len(cores) == 2 and cores[0] in "35" and cores[1] in "Gg")):
            return True
        stack.extend(n.children)
    return False


def _source_mark(src: NodeBase, doc: Document) -> Optional[Mark]:
    """Line leaving a source: its own system, else the first one declared below (not beyond a transformer);
    the high-voltage side of a transformer is a three-conductor line."""
    if getattr(src, "system", None):
        return system_mark(src.system)  # type: ignore[attr-defined]
    hv = (src.un_V or 0) > 1000
    stack = list(src.children)
    while stack:
        n = stack.pop(0)
        if n.type == "transformer":  # type: ignore[attr-defined]
            u1 = getattr(n, "u1_V", None) or src.un_V
            hv = hv or (u1 or 0) > 1000
            if u1 is None:
                return None
            continue
        if getattr(n, "system", None) and not hv:
            return system_mark(n.system)  # type: ignore[attr-defined]
        stack.extend(n.children)
    return system_mark("3P") if hv else system_mark(doc.installation.system)


def _line_marks(doc: Document) -> tuple[dict[int, Optional[Mark]], dict[int, Optional[Mark]]]:
    """Conductor mark of the line entering and leaving every node (keyed by ``id(node)``)."""
    m_in: dict[int, Optional[Mark]] = {}
    m_out: dict[int, Optional[Mark]] = {}

    def walk(n: NodeBase, up: Optional[Mark]) -> None:
        m_in[id(n)] = up
        out = up
        if n.type == "transformer":  # type: ignore[attr-defined]
            out = system_mark(_system_of(n, doc)) or up
        elif n.type in SWITCHING and getattr(n, "poles", None):  # type: ignore[attr-defined]
            out = poles_mark(n.poles, _needs_neutral(n)) or up  # type: ignore[attr-defined]
        m_out[id(n)] = out
        for c in n.children:
            walk(c, out)

    for src in doc.sources:
        walk(src, None)
        m_out[id(src)] = _source_mark(src, doc)
        for c in src.children:
            walk(c, m_out[id(src)])
    return m_in, m_out


def _mark_text(mark: Mark, phase: Optional[str] = None) -> str:
    n, neutral = mark
    parts = [str(n)] if n > 3 else []
    ph = phase if phase and phase != "L1L2L3" else ""
    if neutral:
        parts.append(f"{ph}+N")
    elif ph:
        parts.append(ph)
    return " ".join(parts)


def _put_mark(g: Group, obs: Obstacles, x: float, y0: float, y1: float, pref: float, mark: Mark, nid: str,
              phase: Optional[str] = None) -> None:
    """IEC 60617 conductor-count mark on the vertical conductor x, y0..y1: one oblique stroke per conductor
    (up to 3), otherwise one stroke and the number; '+N' for a neutral that the device does not cut, then the
    phase of a single-phase circuit. Placed near ``pref``, clear of texts, symbols and other lines."""
    n = mark[0]
    strokes = n if n <= 3 else 1
    h = (strokes - 1) * 0.9 + 1.2
    txt = _mark_text(mark, phase)
    tw = text_width(txt, 1.6) if txt else 0.0
    lo, hi = y0 + h / 2 + 0.2, y1 - h / 2 - 0.2
    if hi < lo:
        lo = hi = (y0 + y1) / 2
    cands = sorted({min(hi, max(lo, pref + k * 0.25 * s)) for k in range(0, 41) for s in (1, -1)},
                   key=lambda y: abs(y - pref))

    def free(b: tuple[float, float, float, float], wires: bool) -> bool:
        if wires:
            return obs.box_free(b, 0.2, wire_pad=0.0)
        return not any(_hit(b, o, 0.2) for o in obs.boxes) and not any(
            b[1] - 0.7 < y < b[3] + 0.7 and x0 < b[2] and b[0] < x1 for y, x0, x1 in obs.hlines)

    best: tuple[float, float, float, str] = (1e18, pref, x + 1.3, "start")  # (cost, y, text x, anchor)
    for i, y in enumerate(cands):
        sb = (x - 1.0, y - h / 2, x + 1.0, y + h / 2)
        for tx, anchor in ((x + 1.3, "start"), (x - 1.3, "end")):
            tb = text_box(tx, y + 0.6, tw, 1.6, anchor)
            cost = (0.0 if free(sb, False) else 10.0) + (0.0 if not txt or free(tb, True) else 1.0 + obs.overlap(tb, 0.2))
            cost += i * 1e-3 + (0.0005 if anchor == "end" else 0.0)
            if cost < best[0]:
                best = (cost, y, tx, anchor)
        if best[0] < 1.0:
            break
    _, y, tx, anchor = best
    mg = Group(id=nid, cls=f"conductor-mark cm-{n}{'N' if mark[1] else ''}")
    for k in range(strokes):
        dy = (k - (strokes - 1) / 2) * 0.9
        mg.add(Line((x - 0.9, y + dy + 0.6), (x + 0.9, y + dy - 0.6), Style(width=THIN)))
    obs.add_box((x - 1.0, y - h / 2, x + 1.0, y + h / 2))
    if txt:
        mg.add(Text((tx, y + 0.6), txt, 1.6, anchor))
        obs.add_box(text_box(tx, y + 0.6, tw, 1.6, anchor))
    g.add(mg)


def _draw_line_marks(roots: list[LNode], everything: list[LNode], doc: Document, g: Group, obs: Obstacles,
                     incoming: Optional[str]) -> dict[int, Mark]:
    """Marks on the line leaving each source / transformer and each switching device whose conductors differ
    from the line above it (outgoing cables are marked by :func:`_draw_conductor_marks`). Returns the marks
    drawn, keyed by ``id(node)``."""
    m_in, m_out = _line_marks(doc)
    drawn: dict[int, Mark] = {}
    sources = {id(n) for n in doc.sources}
    for ln in everything:
        node = ln.node
        if ln.kind != "node" or node is None:
            continue
        if incoming and ln is roots[0] and m_in.get(id(node)):  # feed coming from another sheet
            top = ln.frame_top if ln.is_board else ln.y
            obs.add_box(text_box(ln.x + 1.5, top - 6.0, text_width(incoming, 2.0), 2.0))
            _put_mark(g, obs, ln.x, top - 9.0, top - 2.0, top - 5.5, m_in[id(node)], ln.id)  # type: ignore[arg-type]
        mark = m_out.get(id(node))
        if mark is None:
            continue
        top_source = id(node) in sources
        if not (top_source or (ln.type in SWITCHING | {"transformer"} and mark != m_in.get(id(node)))):
            continue
        # the output conductor, down to the busbar or to the next node (not an outgoing cable)
        y0, pref = ln.out_y, None
        if ln.bus_y is not None:
            y1 = ln.bus_y
        elif len(ln.children) == 1 and (ln.children[0].kind == "stub" or not ln.children[0].bottom) \
                and not (ln.children[0].type in SIDE_TYPES and not ln.children[0].children):
            c = ln.children[0]
            # into a board: the conductor goes on through the frame down to the board's first node
            y1 = c.y if c.x == ln.x else ln.out_y + 1.5
            if c.is_board and c.x == ln.x and c.sym.height == 0 and c.children and c.bus_y is None:
                y1 = c.children[0].y if c.children[0].x == c.x else c.out_y + 1.5
            if c.is_board and c.x == ln.x:  # rather above the frame when there is room, else inside it
                h = ((mark[0] if mark[0] <= 3 else 1) - 1) * 0.9 + 1.2
                pref = (y0 + c.frame_top) / 2 if c.frame_top - y0 >= h + 1.8 else (c.frame_top + y1) / 2
        else:
            continue
        if y1 - y0 < 1.5:
            continue
        _put_mark(g, obs, ln.x, y0, y1, (y0 + y1) / 2 if pref is None else pref, mark, ln.id)
        drawn[id(node)] = mark
    return drawn


def _draw_conductor_marks(columns: list[LNode], index: Index, doc: Document, g: Group, obs: Obstacles,
                          y_load: float, drawn: dict[int, Mark] | None = None,
                          parent: dict[int, LNode] | None = None) -> None:
    """Conductor-count mark on each outgoing cable (see :func:`_put_mark`), unless the same mark was already
    drawn higher up in the column."""
    drawn = drawn or {}
    parent = parent or {}
    for ln in columns:
        if not (ln.bottom or ln.open_feeder):
            continue  # nothing leaves the column below the node (surge arrester, controller...)
        chain = _feeder_chain(ln, index)
        if not chain:
            continue
        mark = feeder_mark(chain, _supply_system(ln, index, doc))
        if not mark:
            continue
        phase = next((getattr(c, "phase", None) for c in chain if getattr(c, "phase", None)), None)
        above = next((drawn[id(c)] for c in chain if id(c) in drawn), None)
        if above == mark and not (phase and phase != "L1L2L3"):
            continue
        p = parent.get(id(ln))
        y0 = ln.out_y if ln.open_feeder else (p.bus_y if p.bus_y is not None else p.out_y) if p else y_load - 9.0
        _put_mark(g, obs, ln.x, y0, y_load - 0.3, y_load - 2.8, mark, ln.id, phase)


def _draw_pen_splits(main: list[LNode], doc: Document, g: Group, obs: Obstacles) -> None:
    """TN-C-S: PEN -> PE + N split at the board flagged ``pen_split`` (default: the first board of the drawing)."""
    boards = [n for r in main for n in r.walk() if n.is_board and n.node is not None]
    if any(getattr(n, "pen_split", None) is not None for n, _, _ in iter_nodes(doc)):
        flagged = [b for b in boards if getattr(b.node, "pen_split", None)]
    elif doc.installation.earthing == "TN-C-S":
        first = _first_boards(doc)[:1]
        flagged = [b for b in boards if first and b.node is first[0]]
    else:
        flagged = []
    parent = {id(c): n for r in main for n in r.walk() for c in n.children}
    for b in flagged:
        p = parent.get(id(b))
        above = (p.bus_y if p.bus_y is not None else p.out_y) if p is not None else b.frame_top - 9.0
        # on the incoming conductor just above the frame, or inside the frame when the feeder is too short
        y = b.frame_top - 2.8 if b.frame_top - above >= 4.5 else b.frame_top + 2.2
        x = b.x
        g.add(Circle((x, y), 0.45, Style(width=THIN, fill="#000000")))
        g.add(Polyline([(x, y), (x - 4.0, y), (x - 4.0, y + 1.0)], Style(width=THIN)))
        for k, w in enumerate((1.8, 1.2, 0.6)):  # protective-earth terminal
            g.add(Line((x - 4.0 - w / 2, y + 1.0 + k * 0.45), (x - 4.0 + w / 2, y + 1.0 + k * 0.45), Style(width=THIN)))
        g.add(Text((x - 0.7, y - 0.7), "PEN", 1.5, "end"))
        g.add(Text((x - 5.2, y + 1.9), "PE", 1.5, "end"))
        obs.add_box((x - 5.2 - text_width("PE", 1.5), y - 2.0, x, y + 2.2))


def _first_boards(doc: Document) -> list[NodeBase]:
    """First board met below each source (where a PEN conductor is usually split)."""
    out: list[NodeBase] = []
    for src in doc.sources:
        stack = [src]
        while stack:
            n = stack.pop(0)
            if n.type == "board":  # type: ignore[attr-defined]
                out.append(n)
                break
            stack.extend(n.children)
    return out


# ---------------------------------------------------------------- strokes
def _draw_tree(ln: LNode, g: Group, y_load: float, view: View, folio_of: Callable[[str], Optional[int]] | None = None,
               parent_id: Optional[str] = None) -> None:
    trunk = BUSWAY_H / 2 if ln.bus_y is not None and ln.sym.name == "busway" else 0.0
    if ln.kind == "node" or ln.kind == "stub":
        if not (ln.is_board and ln.sym.height == 0) and not trunk:  # busway with tap-offs: drawn as its trunk
            sg = ln.sym.group(ln.x, ln.y, ln.id)
            if ln.node is not None and getattr(ln.node, "external", False):
                sg = _restyle(sg, Style(width=THIN, dash=(1.2, 0.8), color="#555555"))
                sg.cls = (sg.cls or "") + " external"
            if ln.kind == "stub":  # board drawn on its own sheet: reference to that sheet
                sg.id = None
                f = folio_of(ln.target) if folio_of and ln.target else None
                add_cls(sg, "uw-ref").attrs.update(ref_group(f, ln.target).attrs)
            else:
                node_group(sg)
            g.add(sg)
    if ln.ann:
        ab = ln.ann_box()
        assert ab is not None
        ox, oy = 0.0, 0.0
        ov = view.overrides.get(ln.node.id) if ln.node is not None and ln.node.id else None
        if ov is not None and ov.label_offset:
            ox, oy = ov.label_offset
        tg = Group(cls="annotation")
        for i, t in enumerate(ln.ann):
            tg.add(Text((ab[0] + ox, ln.y + 0.3 + oy + (i + 0.8) * ANN_LINE * ln.ann_size / ANN_SIZE), t,
                        ln.ann_size, bold=(i == 0 and ln.tagged)))
        g.add(tg)
    if ln.open_feeder:
        y0, y1 = ln.out_y, y_load + 4.0
        g.add(Line((ln.x, y0), (ln.x, y1)))
        g.add(Polyline([(ln.x - 1.0, y1 - 1.8), (ln.x, y1), (ln.x + 1.0, y1 - 1.8)], Style(fill="#000000"), closed=True))
    me = ln.target if ln.kind == "bus_in" else ln.id
    if ln.bus_y is not None:
        bg = busbar_group(me or ln.id)
        if ln.kind != "bus_in" and ln.bus_y > ln.out_y:
            bg.add(Line((ln.x, ln.y if trunk else ln.out_y), (ln.x, ln.bus_y - trunk)))
        x1 = max(ln.bus_x1, ln.bus_x0 + 4)
        if trunk:  # busbar trunking: casing along the bars, tap-off units below it
            bg.add(Rect(ln.bus_x0 - 2.0, ln.bus_y - trunk, x1 - ln.bus_x0 + 4.0, 2 * trunk, Style(fill="#ffffff")))
            bg.add(Line((ln.bus_x0 - 1.2, ln.bus_y), (x1 + 1.2, ln.bus_y), Style(width=THICK)))
        else:
            bg.add(Line((ln.bus_x0, ln.bus_y), (x1, ln.bus_y), Style(width=BUS)))
        g.add(bg)
        for c in ln.children:
            eg = edge_group(c.id, me, [Line((c.x, ln.bus_y + trunk), (c.x, c.frame_top if c.is_board else c.y))])
            if c.is_board:
                eg.add(Line((c.x, c.frame_top), (c.x, c.y)))
            g.add(eg)
    else:
        for c in ln.children:
            top = c.frame_top if c.is_board else c.y
            eg = edge_group(c.id, me)
            if ln.x == c.x:
                eg.add(Line((ln.x, ln.out_y), (c.x, top)))
            else:
                eg.add(Polyline([(ln.x, ln.out_y), (ln.x, ln.out_y + 1.5), (c.x, ln.out_y + 1.5), (c.x, top)]))
            if c.is_board:
                eg.add(Line((c.x, c.frame_top), (c.x, c.y)))
            g.add(eg)
    for c in ln.children:
        _draw_tree(c, g, y_load, view, folio_of, me)


def _frame_box(b: LNode) -> tuple[float, float, float, float]:
    x0 = b.x_left + 0.8
    x1 = b.x_left + b.width - 0.8
    for n in _owned(b):
        ab = n.ann_box()
        if ab:
            x1 = max(x1, ab[2] + 1.0)
    return (x0, b.frame_top, x1, _board_bottom(b) + 2.0)


def _restyle(item: Any, style: Style) -> Any:
    """Copy of a group with its stroke style replaced (external equipment)."""
    if isinstance(item, Group):
        return Group([_restyle(i, style) for i in item.items], item.id, item.cls, dict(item.attrs))
    if hasattr(item, "style"):
        import copy
        it = copy.copy(item)
        it.style = Style(style.width, style.dash, style.color, item.style.fill)
        return it
    return item


def _framed(g: Group, obs: Obstacles, box: tuple[float, float, float, float], label: Optional[str], size: float,
            style: Style, gap: float = 2.0) -> None:
    """Frame ``box`` (content + padding) with its label, kept clear of busbars and of the frames already drawn.

    The label goes above the content when there is room below the nearest busbar / frame edge, otherwise
    at the bottom of the frame; the frame and its label then become obstacles for the link routes."""
    x0, top, x1, y1 = box
    content_top = top + gap
    lh = size + 1.2 if label else 0.0
    # nearest busbar or frame edge crossing the frame above the content: the frame must start below it
    limit = max([y for y, h0, h1 in obs.hlines if h0 < x1 and x0 < h1 and y < content_top - 0.2] + [-1e9])
    y0 = max(top - lh, limit + 0.8) if limit > top - lh - 0.8 else top - lh
    y0 = min(y0, content_top - 0.6)
    if label:
        w = text_width(label, size)
        cands = []  # (x, baseline, anchor, frame grows at the bottom)
        if content_top - y0 >= lh + 0.4:
            cands += [(x0 + 1.0, y0 + size + 0.6, "start", False), (x1 - 1.0, y0 + size + 0.6, "end", False)]
        cands += [(x0 + 1.0, y1 + lh - 0.9, "start", True), (x1 - 1.0, y1 + lh - 0.9, "end", True)]
        lx, ly, anchor, grow = next((c for c in cands if obs.box_free(text_box(c[0], c[1], w, size, c[2]), 0.2, 0.1)),
                                    cands[0])
        if grow:
            y1 += lh
        g.add(Text((lx, ly), label, size, anchor, bold=True))
        obs.add_box(text_box(lx, ly, w, size, anchor))
    g.add(Rect(x0, y0, x1 - x0, y1 - y0, style))
    obs.add_hline(y0, x0, x1)
    obs.add_hline(y1, x0, x1)
    obs.add_vline(x0, y0, y1)
    obs.add_vline(x1, y0, y1)


def _draw_view_frames(view: View, everything: list[LNode], g: Group, obs: Obstacles) -> None:
    by_id = {n.node.id: n for n in everything if n.node is not None and n.kind == "node"}
    for fr in view.frames:
        boxes = []
        for nid in fr.nodes:
            n = by_id.get(nid)
            if n is None:
                continue
            boxes.append(n.sym_box())
            if n.ann_box():
                boxes.append(n.ann_box())
        if not boxes:
            continue
        u = boxes_union(boxes)
        assert u is not None
        _framed(g, obs, (u[0] - 2.5, u[1] - 2.0, u[2] + 2.0, u[3] + 2.0), fr.label, 2.2,
                Style(width=THIN, dash=(2.0, 1.0), color="#444444"))


def _mirror_up(item: Any, c: float) -> Any:
    """Bottom-up drawing (RGIE, rising columns / colonnes montantes): vertical mirroring of the geometry; texts,
    annotations and tables are moved as blocks so they stay readable."""
    import copy

    def block(it: Any) -> Any:
        b = bbox(it)
        if b is None:
            return it
        return transform(it, 0.0, (c - b[3]) - b[1])

    if isinstance(item, Group):
        if item.cls and any(k in item.cls for k in ("annotation", "cartouche")):
            return block(item)
        return Group([_mirror_up(i, c) for i in item.items], item.id, item.cls, dict(item.attrs))
    if isinstance(item, Text):
        return block(item)
    it = copy.copy(item)
    if isinstance(item, Line):
        it.a, it.b = (item.a[0], c - item.a[1]), (item.b[0], c - item.b[1])
    elif isinstance(item, Polyline):
        it.points = [(x, c - y) for x, y in item.points]
    elif isinstance(item, (Circle, Ellipse)):
        it.c = (item.c[0], c - item.c[1])
    elif isinstance(item, Rect):
        it.y = c - item.y - item.h
    return it


def _draw_enclosures(doc: Document, nodes: list[LNode], g: Group, obs: Obstacles) -> None:
    """Addressable enclosures (enveloppes, 1.2): frame around the listed nodes present on the sheet."""
    by_id = {n.node.id: n for n in nodes if n.node is not None and n.kind == "node"}
    style = {"cell": Style(width=THIN, color="#444444"), "zone": Style(width=THIN, dash=(4.0, 1.5), color="#777777"),
             "boundary": Style(width=NORMAL, dash=(6.0, 1.5, 1.0, 1.5), color="#555555")}
    sets = {e.id: set(e.nodes) for e in doc.enclosures}
    parent_of = {e.id: e.parent for e in doc.enclosures}

    def inner_count(eid: str) -> int:  # number of contained enclosures (via 'parent' or by node inclusion)
        n = 0
        for o in doc.enclosures:
            if o.id == eid:
                continue
            p, contained = parent_of.get(o.id), False
            while p is not None:
                if p == eid:
                    contained = True
                    break
                p = parent_of.get(p)
            if contained or (sets[o.id] and sets[o.id] < sets[eid]):
                n += 1
        return n

    for enc in sorted(doc.enclosures, key=lambda e: -inner_count(e.id)):
        pad = 2.0 + 2.2 * min(inner_count(enc.id), 4)
        boxes = []
        nids = set(enc.nodes)
        for child in doc.enclosures:  # an enclosure also encloses the nodes of its child enclosures
            p = child.parent
            while p is not None and p != enc.id:
                p = parent_of.get(p)
            if p == enc.id:
                nids |= sets[child.id]
        for nid in nids:
            n = by_id.get(nid)
            if n is None:
                continue
            boxes.append(n.sym_box())
            if n.ann_box():
                boxes.append(n.ann_box())
        if not boxes:
            continue
        label = " ".join(x for x in (enc.ref, enc.label or enc.cell_type) if x)
        u = boxes_union(boxes)
        assert u is not None
        _framed(g, obs, (u[0] - pad, u[1] - pad, u[2] + pad, u[3] + pad), label or None, 2.0,
                style.get(enc.kind, Style(width=THIN, dash=(2.0, 1.0), color="#444444")), gap=pad)


def _draw_board_frame(b: LNode, g: Group) -> None:
    x0, y0, x1, y1 = _frame_box(b)
    fg = Group(id=b.id, cls="board uw-node")
    fg.add(Rect(x0, y0, x1 - x0, y1 - y0, Style(width=THIN, dash=(2.0, 1.0), color="#444444")))
    for pos, t, size, anchor in _board_texts(b):
        fg.add(Text(pos, t, size, anchor, bold=(size > 2.0)))
    g.add(fg)


POWER_LINKS = ("bypass", "parallel", "infeed")
SWITCHED_LINKS = ("transfer", "tie", "bypass", "parallel", "infeed")  # power links that may be normally open
OPEN_POWER = Style(dash=(3.0, 1.2))  # normally-open power link: long dash (control links: short dash)


def _link_style(kind: str, normally_open: Optional[bool] = None) -> Style:
    # control / other links: dashed; earth: dash-dot; data: fine dotted; normally-open power link: long dash
    if normally_open and kind in SWITCHED_LINKS:
        return OPEN_POWER
    if kind == "earth":
        return Style(width=THIN, dash=(3.0, 0.8, 0.6, 0.8), color="#2e7d32")
    if kind == "data":
        return Style(width=THIN, dash=(0.5, 0.8), color="#1565c0")
    if kind in ("control", "interlock", "trip", "measure", "key"):
        return DASH
    return Style()


def _bus_tap(n: LNode, toward: float, taken: int = 0) -> float:
    """x where a power link taps a busbar: just beyond the end facing the other node, or midway between the
    two outgoing feeders around it; ``taken`` earlier taps on the same side push it outward (own lane)."""
    off = 5.0 + 3.0 * taken
    if toward >= n.bus_x1:  # beyond the annotations of the last outgoing column
        right = max([b[2] for c in n.walk() if c is not n and (b := c.ann_box()) is not None
                     and c.x <= n.bus_x1 + 0.01 and c.x >= n.children[-1].x - 0.01] + [n.bus_x1 + 3.0])
        return right + 2.0 + 3.0 * taken
    if toward <= n.bus_x0:
        return n.bus_x0 - off
    xs = [c.x for c in n.children]
    gaps = [(a + b) / 2 + 1.5 * taken for a, b in zip(xs, xs[1:])] or [n.bus_x0 - off]
    return min(gaps, key=lambda x: abs(x - toward))


def _end(n: LNode, kind: str, fed: bool = False, toward: Optional[float] = None, taken: int = 0) -> End:
    """Where a link attaches to a node: left side of the symbol, busbar end of a board, output terminal
    of a feeder continued by a power link, input conductor of a node fed by an ``infeed`` link, or a tap
    on the busbar of a node feeding a power link toward ``toward``."""
    if toward is not None and kind in POWER_LINKS and n.bus_y is not None and n.children:
        return End(_bus_tap(n, toward, taken), n.bus_y, "down")
    if n.sym.height == 0 and n.bus_y is not None:
        return End(n.bus_x0, n.bus_y)
    if fed:
        return End(n.x, n.y - 1.2)
    if kind in POWER_LINKS and not n.children and n.sym.has_output:
        return End(n.x, n.out_y + 0.7, "down")
    return End(n.x - n.sym.left - 0.8, n.y + max(n.sym.height, 1) / 2)


def _port_slot(n: LNode, port: Optional[str]) -> Optional[int]:
    ports = n.sym.extra.get("ports") if port else None
    if not ports:
        return None
    try:
        slot = int(str(port).split(".")[0])
    except ValueError:
        return None
    return slot if slot in ports else None


# ------------------------------------------------- alternative supplies band
ALT_SIZE, ALT_LINE = 1.9, 2.35  # annotation of a device carried by a link


def _is_alternative(link: Any) -> bool:
    """Normally-open alternative supply landing on a feeder input (``infeed`` link open in normal operation,
    or carrying a device whose normal state is open)."""
    dev = link.device
    return link.kind == "infeed" and bool(link.normally_open or (dev is not None and dev.normal_state == "open"))


def _fed_ok(roots: list[LNode]) -> set[str]:
    """Nodes drawn below a parent (a conductor arrives on their input): an infeed lands on that conductor."""
    return {c.node.id for r in roots for n in r.walk() for c in n.children
            if c.kind == "node" and c.node is not None and n.kind in ("node", "bus_in")}


@dataclass
class AltBand:
    """Horizontal band under the busbars, one lane per normally-open alternative supply."""

    links: list[int]  # indexes in doc.links
    y0: float  # level of the (lowest) busbar the links leave
    top: float  # first lane, below y0
    pitch: float  # spacing of the lanes


def _alt_extent(link: Any, lang: str) -> tuple[float, float]:
    """Room needed above / below a lane by the device of the link and its annotation (stacked above it)."""
    if link.device is None:
        return 1.0, 0.5
    sym = symbol_for(link.device)
    th = max(len(_device_text(link, link.device, lang, c)[:4]) for c in (True, False)) * ALT_LINE
    return sym.right + 0.8 + th, sym.left  # turned like a bus coupler: the blade below the lane


def _alt_band(doc: Document, main: list[LNode], lang: str) -> Optional[AltBand]:
    """Reserve, under the busbars, one lane per alternative supply (``_is_alternative``) and push everything
    below the busbars down so that the lanes, their devices and annotations collide with no feeder."""
    fed = _fed_ok(main)
    idx: list[int] = []
    sources: list[LNode] = []
    for i, link in enumerate(doc.links):
        if not _is_alternative(link):
            continue
        a, b = _find(main, link.from_), _find(main, link.to)
        if a is None or b is None or a.bus_y is None or not a.children or link.to not in fed or b.y <= a.bus_y:
            continue
        idx.append(i)
        sources.append(a)
    if not idx:
        return None
    y0 = max(a.bus_y for a in sources)  # type: ignore[type-var]
    ext = [_alt_extent(doc.links[i], lang) for i in idx]
    above, below = max(e[0] for e in ext), max(e[1] for e in ext)
    pitch = above + below + 1.2
    top = 2.0 + above
    height = top + (len(idx) - 1) * pitch + below + 1.5
    under = [n for r in main for n in r.walk() if n.y > y0 + 1e-6]
    if under:
        dy = y0 + height + CHILD_GAP - min(n.y for n in under)
        if dy > 0:
            for n in under:
                n.y += dy
                n.frame_top += dy
                if n.bus_y is not None:
                    n.bus_y += dy
    return AltBand(idx, y0, top, pitch)


def _lane_order(geo: list[tuple[float, float, float, float]]) -> list[int]:
    """Order of the lanes (top to bottom) crossing the fewest conductors. ``geo``: (tap x, drop x, tap y,
    landing y) per link; a tap goes down from its busbar to its lane, a drop from its lane to its landing."""
    import itertools

    def crossings(order: tuple[int, ...]) -> float:
        lane = {k: j for j, k in enumerate(order)}
        n = 0.0
        for i, (ti, di, _, _) in enumerate(geo):
            for j, (tj, dj, _, _) in enumerate(geo):
                if i == j:
                    continue
                lo, hi = min(tj, dj), max(tj, dj)
                if lane[j] < lane[i] and lo < ti < hi:  # tap of i crosses the lane of j, above it
                    n += 1
                if lane[j] > lane[i] and lo < di < hi:  # drop of i crosses the lane of j, below it
                    n += 1
        return n + 1e-3 * sum(abs(j - k) for j, k in enumerate(order))  # stable on ties

    ks = tuple(range(len(geo)))
    if len(geo) <= 7:
        return list(min(itertools.permutations(ks), key=crossings))
    return sorted(ks, key=lambda k: abs(geo[k][1] - geo[k][0]))  # many links: shortest spans on top


def _draw_band(doc: Document, band: AltBand, roots: list[LNode], tap_end: dict[int, End],
               group_of: Callable[[int], Group], obs: Obstacles, lang: str) -> set[int]:
    """Draw the alternative supplies of ``band``: tap on the busbar, own lane in the band, drop beside the
    target, junction dot on its input conductor; the device sits on the lane, its annotation just above it.
    Returns the links drawn."""
    items: list[tuple[int, Any, LNode, float, float, float]] = []  # (link, link, target, tap x, drop x, landing y)
    for i in band.links:
        link = doc.links[i]
        b = _find(roots, link.to)
        if i not in tap_end or b is None:
            continue
        tx = tap_end[i].x
        yj = b.y - 1.2
        bottom = band.y0 + band.top + (len(band.links) - 1) * band.pitch
        best: tuple[float, float] = (1e18, 3.5)
        for k in range(15):  # drop beside the target column, clear of the neighbouring texts and blades
            s = 3.0 + 0.25 * k
            for xd in (b.x - s, b.x + s) if tx > b.x else (b.x - s,):
                c = _seg_cost(obs, (xd, bottom), (xd, yj)) + _seg_cost(obs, (xd, yj), (b.x, yj)) + 0.1 * abs(s - 3.5)
                c += 0.5 if xd > b.x else 0.0
                if c < best[0]:
                    best = (c, xd)
        items.append((i, link, b, tx, best[1], yj))
    if not items:
        return set()
    order = _lane_order([(tx, xd, tap_end[i].y, yj) for i, _, _, tx, xd, yj in items])
    style = OPEN_POWER
    routes: list[tuple[int, Any, LNode, list[tuple[float, float]]]] = []
    for j, k in enumerate(order):
        i, link, b, tx, xd, yj = items[k]
        y = band.y0 + band.top + j * band.pitch
        pts = [(tx, tap_end[i].y), (tx, y), (xd, y), (xd, yj), (b.x, yj)]
        _record(obs, pts)
        routes.append((i, link, b, pts))
    for i, link, _b, pts in routes:
        g = group_of(i)
        dev = link.device
        if dev is None:
            g.add(Polyline(pts, style))
        elif not _band_device(link, dev, pts, style, g, obs, lang):
            _draw_link_device(link, dev, pts, style, g, obs, lang)
        g.add(Circle(pts[-1], 0.45, Style(width=THIN, fill="#000000")))
        if dev is None and link.label:
            x, y, anchor = place_label(obs, pts, text_width(link.label, 1.6), 1.6, from_end=True)
            g.add(Text((x, y), link.label, 1.6, anchor))
    return {items[k][0] for k in order}


def _band_device(link: Any, dev: NodeBase, pts: list[tuple[float, float]], style: Style, g: Group,
                 obs: Obstacles, lang: str) -> bool:
    """Device of an alternative supply on its lane (``pts[1] -> pts[2]``), turned like a bus coupler, its tag
    and annotation stacked just above it. False when the lane is too short for the symbol."""
    sym = symbol_for(dev)
    h = sym.height
    (x0, y), (x1, _) = pts[1], pts[2]
    lo, hi = min(x0, x1), max(x0, x1)
    if hi - lo < h + 2.0:
        return False
    best: Optional[tuple[float, float, float, list[str], float, float]] = None  # cost, symbol x, text x, lines
    for variant in (True, False):  # compact text, else characteristics on separate (narrower) lines
        lines = _device_text(link, dev, lang, variant)[:4]
        w = 1.1 * max((text_width(t, ALT_SIZE) for t in lines), default=0.0)  # estimate: keep a margin
        ht = len(lines) * ALT_LINE
        n = int((hi - lo - h - 2.0) / 0.5)
        for k in range(n + 1):
            s0 = lo + 1.0 + 0.5 * k
            sbox = (s0, y - sym.right, s0 + h, y + sym.left)
            cs = 3.0 * obs.overlap(sbox, 0.3, 1.0) + 0.004 * abs(s0 + h / 2 - x1) + (0.0 if variant else 0.3)
            for tx in (s0 + h / 2 - w / 2, s0, s0 + h - w):
                ty = y - sym.right - 0.8 - ht
                cost = cs + obs.overlap((tx, ty, tx + w, ty + ht), 0.5, 2.0) + 0.02 * abs(tx - (s0 + h / 2 - w / 2))
                if best is None or cost < best[0]:
                    best = (cost, s0, tx, lines, w, ht)
    assert best is not None
    _, s0, tx, txt, tw, th = best
    ty = y - sym.right - 0.8 - th
    first, second = ((s0, y), (s0 + h, y)) if x1 > x0 else ((s0 + h, y), (s0, y))
    for part in (pts[:2] + [first], [second] + pts[2:]):
        g.add(Polyline(part, style))
    g.add(Group([transform(it, s0, y, rot=270) for it in sym.items], dev.id, f"sym sym-{sym.name}"))
    obs.add_box((s0, y - sym.right, s0 + h, y + sym.left))
    obs.add_box((tx, ty, tx + tw, ty + th))
    for k, t in enumerate(txt):
        g.add(Text((tx, ty + (k + 0.8) * ALT_LINE), t, ALT_SIZE, bold=(k == 0 and bool(dev.ref))))
    return True


def _draw_links(doc: Document, roots: list[LNode], anchored: dict, g: Group, view: View, obs: Obstacles,
                y_load: float, lang: str = "en", node_folio: Callable[[str], Optional[int]] | None = None,
                band: Optional[AltBand] = None) -> None:
    # links leaving a PLC channel ('slot.channel') fan out under their module, one lane per channel
    # (farthest target on the outer lane, nearest target routed first on the upper channel: no crossings)
    lanes: dict[tuple[str, int], list[tuple[float, int]]] = {}
    for i, link in enumerate(doc.links):
        for nid, port, other in ((link.from_, link.from_port, link.to), (link.to, link.to_port, link.from_)):
            n, o = _find(roots, nid), _find(roots, other)
            slot = _port_slot(n, port) if n is not None else None
            if slot is not None and o is not None:
                lanes.setdefault((nid, slot), []).append((o.x - n.x - n.sym.extra["ports"][slot], i))
                break
    lane_of: dict[int, tuple[int, int]] = {}
    first: dict[int, float] = {}
    for group in lanes.values():
        right = sorted(group, key=lambda t: -t[0])  # targets to the right: farthest gets the leftmost lane
        for j, (dist, i) in enumerate(right):
            lane_of[i] = (j, len(group))
            first[i] = abs(dist)
    order = sorted(range(len(doc.links)), key=lambda i: (i in first, first.get(i, 0.0)))
    nodes = {n.id: n for n, _, _ in iter_nodes(doc)}
    fed_ok = _fed_ok(roots)
    y_max = y_load - 1.5
    # power links leaving a busbar: one tap each, the busbar extended to the taps beyond its ends (drawn and
    # recorded before any route, so that no other link runs along the extension)
    taps: dict[tuple[str, bool, bool], int] = {}  # busbar side -> power links already tapped there
    tap_end: dict[int, End] = {}
    for i in order:
        link = doc.links[i]
        a, b = _find(roots, link.from_), _find(roots, link.to)
        if a is None or b is None or link.kind not in POWER_LINKS:
            continue
        side = (a.id, b.x > a.bus_x1, b.x < a.bus_x0)
        e = _end(a, link.kind, toward=b.x, taken=taps.get(side, 0))
        if e.side != "down" or a.bus_y is None or abs(e.y - a.bus_y) > 1e-9:
            continue
        taps[side] = taps.get(side, 0) + 1
        tap_end[i] = e
        obs.add_vline(e.x, e.y, e.y + 10.0)  # its first leg goes down from there: keep texts off it
        if not a.bus_x0 <= e.x <= a.bus_x1:
            x0, x1 = min(e.x, a.bus_x0), max(e.x, a.bus_x1)
            g.add(busbar_group(a.id, [Line((x0, e.y), (x1, e.y), Style(width=BUS))]))
            obs.add_hline(e.y, x0, x1)
    groups: dict[int, Group] = {}

    def group_of(i: int) -> Group:
        if i not in groups:
            groups[i] = link_group(doc, i)
        return groups[i]

    done = _draw_band(doc, band, roots, tap_end, group_of, obs, lang) if band is not None else set()
    labels: list[tuple[int, list[tuple[float, float]], str, float, str]] = []
    for i in order:
        link = doc.links[i]
        a, b = _find(roots, link.from_), _find(roots, link.to)
        if (a is None and b is None) or i in done:
            continue
        lg = group_of(i)
        if a is None or b is None:
            if link.kind not in ("transfer", "tie"):
                other = link.to if b is None else link.from_
                _draw_offpage_link(link, a or b, other, nodes.get(other), obs, lg, lang, node_folio)
            continue
        style = _link_style(link.kind, link.normally_open)
        if link.kind == "transfer" and b.sym.side_input is not None:
            sx = b.x + b.sym.side_input[0]
            sy = b.y + b.sym.side_input[1]
            ay = a.out_y if a.sym.has_output else a.y + a.sym.height
            lg.add(Polyline([(a.x, ay), (a.x, sy - 2.5), (sx, sy - 2.5), (sx, sy)], style))
            continue
        if link.kind == "tie" and a.bus_y is not None and b.bus_y is not None:
            left, right = (a, b) if a.x < b.x else (b, a)
            x0, x1, y = left.bus_x1, right.bus_x0, left.bus_y
            if abs(left.bus_y - right.bus_y) > 0.01 or x1 - x0 < 8:
                lg.add(Polyline([(x0, left.bus_y), (x0 + 2, left.bus_y), (x0 + 2, right.bus_y), (x1, right.bus_y)],
                               style if link.normally_open else Style(width=NORMAL)))
                continue
            g.add(busbar_group(left.id, [Line((left.bus_x0, y), (x0 + 2.0, y), Style(width=BUS))]))
            dev = link.device
            if dev is not None:
                sym = symbol_for(dev)
                mid = (x0 + x1) / 2
                sx0 = mid - sym.height / 2
                lg.add(Line((x0, y), (sx0, y), style))
                lg.add(Group([transform(it, sx0, y, rot=270) for it in sym.items], dev.id, f"sym sym-{sym.name}"))
                lg.add(Line((sx0 + sym.height, y), (x1, y), style))
                txt = _device_text(link, dev, lang)
                for k, t in enumerate(txt[:3]):
                    lg.add(Text((mid, y - 4.0 - (len(txt[:3]) - 1 - k) * 2.4), t, 1.9, "middle", bold=(k == 0 and bool(dev.ref))))
            else:
                lg.add(Line((x0, y), (x1, y), style if link.normally_open else Style(width=BUS)))
            continue
        ends = [tap_end.get(i) or _end(a, link.kind),
                _end(b, link.kind, fed=link.kind == "infeed" and link.to in fed_ok)]
        port_label: Optional[tuple[int, str]] = None
        for k, (n, _nid, port) in enumerate(((a, link.from_, link.from_port), (b, link.to, link.to_port))):
            slot = _port_slot(n, port)
            if slot is None:
                continue
            j, count = lane_of.get(i, (0, 1))
            room = (7.0 if slot == 0 else PLC_SLOT_W) - 1.2
            gap = min(1.0, room / max(count - 1, 1))
            px = n.x + n.sym.extra["ports"][slot] + (j - (count - 1) / 2) * gap
            ends[k] = End(px, n.y + n.sym.extra.get("port_y", n.sym.height), "down")
            port_label = (k, str(port))
            break
        lo = min(e.y for e in ends) - 30.0
        hi = max(max(e.y for e in ends) + 30.0, max(e.y for e in ends) + 2.0)
        if max(e.y for e in ends) < y_max:
            hi = min(hi, y_max)
        if ends[1].y < b.y:  # infeed landing on an input conductor: never come back up from below the feeder
            hi = min(hi, max(e.y for e in ends) + 0.5)
        carries = link.device is not None and link.kind in SWITCHED_LINKS
        pts = route(obs, ends[0], ends[1], lo, hi, record=not carries, lane=3.5 if carries else LANE)
        if carries:
            _draw_link_device(link, link.device, pts, style, lg, obs, lang)
        else:
            lg.add(Polyline(pts, style))
        if ends[1].y < b.y:  # infeed landing on the input conductor: junction dot
            lg.add(Circle(pts[-1], 0.45, Style(width=THIN, fill="#000000")))
        seq = pts if port_label is None or port_label[0] == 0 else pts[::-1]  # oriented PLC -> other end
        if port_label is not None:
            labels.append((i, seq, port_label[1], 1.3, "#1565c0"))
        if link.label and link.device is None:  # a carried device is annotated: the label would repeat it
            labels.append((i, seq, link.label, 1.6, "#000000"))
    # labels once every route is known, near the far end of their link (port labels: near the controlled device)
    for i, seq, txt, size, color in labels:
        x, y, anchor = place_label(obs, seq, text_width(txt, size), size, from_end=True)
        group_of(i).add(Text((x, y), txt, size, anchor, color=color))
    for i in sorted(groups):
        if groups[i].items:
            g.add(finish_link_group(groups[i]))


def _device_text(link: Any, dev: NodeBase, lang: str, compact: bool = True) -> list[str]:
    """Tag + annotation of the device carried by a link; its state line includes the link's own
    ``normally_open`` and ``locks``. ``compact``: short characteristics joined on one line."""
    lines = [x for x in annotation(dev, lang) if x and x != state_text(dev, lang)]
    joined = " ".join(lines)
    lines = [joined] if len(joined) <= 24 and compact else lines[:2]  # the link already carries the route
    lines.append(state_text(dev, lang, bool(link.normally_open), link.locks))
    return [t for t in [dev.ref] + lines if t]


def _draw_link_device(link: Any, dev: NodeBase, pts: list[tuple[float, float]], style: Style, g: Group,
                      obs: Obstacles, lang: str) -> None:
    """Draw a routed power link with its device (switch, removable link, fuse...) inserted on the route:
    on the free stretch of a vertical segment if possible (symbol upright), else of a horizontal one
    (symbol turned like a bus coupler). The tag and annotation go in the nearest free box."""
    sym = symbol_for(dev)
    h = sym.height
    txt = _device_text(link, dev, lang)[:4]
    size, line = 1.9, 2.35
    tw = max((text_width(t, size) for t in txt), default=0.0)
    th = len(txt) * line

    def text_spots(box: tuple[float, float, float, float], vertical: bool) -> list[tuple[float, float]]:
        """Preferred annotation corners around a symbol box: beside it (upright) or above / below it."""
        if vertical:
            return [(box[2] + 1.0, box[1]), (box[0] - 1.0 - tw, box[1])]
        shifts = sorted({0.0, box[2] - box[0] - tw} | {float(k) for k in range(-int(tw), int(box[2] - box[0]) + 1)},
                        key=abs)  # slid along the symbol, closest first
        return [(box[0] + dx, y) for dx in shifts for y in (box[3] + 0.8, box[1] - 0.8 - th)]

    best: Optional[tuple[float, int, float, bool]] = None  # (cost, segment, start along the axis, vertical)
    for k, (p, q) in enumerate(zip(pts, pts[1:])):
        vertical = abs(p[0] - q[0]) < 1e-9
        a0, a1 = (min(p[1], q[1]), max(p[1], q[1])) if vertical else (min(p[0], q[0]), max(p[0], q[0]))
        if a1 - a0 < h + 1.0:
            continue
        mid = (a0 + a1) / 2
        n = int((a1 - a0 - h - 1.0) / 0.5)
        for i in range(n + 1):
            s0 = a0 + 0.5 + i * 0.5
            if vertical:
                box = (p[0] - sym.left, s0, p[0] + sym.right, s0 + h)
            else:
                box = (s0, p[1] - sym.right, s0 + h, p[1] + sym.left)
            cost = obs.overlap(box, 0.3, 1.5) + 0.01 * abs(s0 + h / 2 - mid) + (0.5 if vertical else 0.0)
            if txt and cost < (best[0] if best else 1e9):  # room for the tag next to the symbol
                if not any(obs.box_free((x, y, x + tw, y + th), 0.6) for x, y in text_spots(box, vertical)):
                    cost += 2.0
            if best is None or cost < best[0]:
                best = (cost, k, s0, vertical)
    if best is None:  # no stretch long enough: plain route, tag beside it
        g.add(Polyline(pts, style))
        _record(obs, pts)
        if dev.ref:
            x, y, anchor = place_label(obs, pts, text_width(dev.ref, 1.9), 1.9, from_end=False)
            g.add(Text((x, y), dev.ref, 1.9, anchor, bold=True))
        return
    _, k, s0, vertical = best
    p, q = pts[k], pts[k + 1]
    if vertical:
        e0, e1 = (p[0], s0), (p[0], s0 + h)
        forward = q[1] > p[1]
        items = [transform(i, p[0], s0) for i in sym.items]
        sbox = (p[0] - sym.left, s0, p[0] + sym.right, s0 + h)
    else:
        e0, e1 = (s0, p[1]), (s0 + h, p[1])
        forward = q[0] > p[0]
        items = [transform(i, s0, p[1], rot=270) for i in sym.items]
        sbox = (s0, p[1] - sym.right, s0 + h, p[1] + sym.left)
    first, second = (e0, e1) if forward else (e1, e0)
    part1, part2 = pts[:k + 1] + [first], [second] + pts[k + 1:]
    for part in (part1, part2):
        g.add(Polyline(part, style))
        _record(obs, part)
    g.add(Group(items, dev.id, f"sym sym-{sym.name}"))
    obs.add_box(sbox)
    if not txt:
        return
    w, hh = tw, th
    free = [p for p in text_spots(sbox, vertical) if obs.box_free((p[0], p[1], p[0] + w, p[1] + hh), 0.6)]
    x, y = free[0] if free else place_box(obs, w, hh, text_spots(sbox, vertical)[0], step=0.5, reach=40.0, pad=1.0)
    obs.add_box((x, y, x + w, y + hh))
    for i, t in enumerate(txt):
        g.add(Text((x, y + (i + 0.8) * line), t, size, bold=(i == 0 and bool(dev.ref))))


def _record(obs: Obstacles, pts: list[tuple[float, float]]) -> None:
    for p, q in zip(pts, pts[1:]):
        if abs(p[1] - q[1]) < 1e-9:
            obs.add_hline(p[1], p[0], q[0])
        elif abs(p[0] - q[0]) < 1e-9:
            obs.add_vline(p[0], p[1], q[1])


def _draw_offpage_link(link: Any, n: LNode, other: str, target_node: Optional[NodeBase], obs: Obstacles, g: Group,
                       lang: str, node_folio: Callable[[str], Optional[int]] | None) -> None:
    """Link whose other end is drawn on another sheet: short stub ending on an off-page arrow + sheet reference."""
    f = node_folio(other) if node_folio is not None else None
    if f is None:
        return
    e = _end(n, link.kind)
    if e.side == "down":
        pts = [(e.x, e.y), (e.x, e.y + 6.0)]
        tip = (e.x, e.y + 7.5)
        head = [(e.x - 0.8, e.y + 6.0), tip, (e.x + 0.8, e.y + 6.0)]
    else:
        pts = [(e.x, e.y), (e.x - 6.0, e.y)]
        tip = (e.x - 7.5, e.y)
        head = [(e.x - 6.0, e.y - 0.8), tip, (e.x - 6.0, e.y + 0.8)]
    g.add(Polyline(pts, _link_style(link.kind, link.normally_open)))
    rg = ref_group(f, other, [Polyline(head, Style(width=THIN, fill="#ffffff"), closed=True)])
    obs.add_hline(pts[1][1], pts[0][0], pts[1][0]) if e.side != "down" else obs.add_vline(e.x, e.y, e.y + 7.5)
    on = target_node.ref or target_node.label or other if target_node is not None else other
    for txt in ([link.label] if link.label else []) + [on + _t("render.to_folio", lang, folio=f)]:
        x, y, anchor = place_label(obs, [pts[0], tip], text_width(txt, 1.6), 1.6, from_end=True)
        rg.add(Text((x, y), txt, 1.6, anchor))
    g.add(rg)


# ----------------------------------------------------------------- table
def _column_info(ln: LNode, index: Index, lang: str) -> dict[str, Any]:
    """Protection, cable and upstream RCD of a feeder column."""
    leaf = ln.node
    info: dict[str, Any] = {"leaf": leaf, "prot": None, "cable": None, "rcd": None, "label": ""}
    if leaf is None:
        return info
    chain = [leaf] + index.ancestors(leaf.id or "")
    # walk up to the first busbar node (excluded)
    path = []
    for n in chain:
        if n is not leaf and (len(n.children) >= 2 or n.type in ("busbar", "board")):  # type: ignore[attr-defined]
            break
        path.append(n)
    prots = [n for n in path if n.type in PROTECTIVE]  # type: ignore[attr-defined]
    rated = [n for n in prots if n.type != "motor_starter" and protection_short(n)]  # type: ignore[attr-defined]
    info["prot"] = (rated or prots or [None])[0]
    if leaf.type == "spare":  # type: ignore[attr-defined]
        info["prot"] = leaf  # pre-equipped spare way: its own rating and poles
    elif info["prot"] is None and len(path) < len(chain) and getattr(chain[len(path)], "kind", None) == "busway":
        # tap-off of a busbar trunking: protected by the device feeding the trunking
        for n in chain[len(path) + 1:]:
            if len(n.children) >= 2 or n.type == "board":  # type: ignore[attr-defined]
                break
            if n.type in PROTECTIVE and protection_short(n):  # type: ignore[attr-defined]
                info["prot"] = n
                break
    for n in path:
        if info["cable"] is None and n.cable is not None:
            info["cable"] = n.cable
    for n in chain:
        if n.type in ("rcd", "rcbo", "main_breaker") and getattr(n, "idn_mA", None):  # type: ignore[attr-defined]
            info["rcd"] = n
            # marked "(upstream)" only when it is not a group RCD of the feeder's own board:
            # outside that board, or the incomer directly fed by a source
            board = next((b for b in chain if b.type == "board"), None)  # type: ignore[attr-defined]
            outside = board is not None and chain.index(n) > chain.index(board)
            parents = index.ancestors(n.id or "")
            incomer = bool(parents) and registry.category(parents[0].type) == "source"  # type: ignore[attr-defined]
            info["rcd_upstream"] = not any(n is p for p in path) and (outside or incomer)
            break
    label = leaf.label
    if not label:
        for n in path:
            if n.label:
                label = n.label
                break
    if not label and ln.kind != "stub":
        label = registry.label(leaf.type, lang)  # type: ignore[attr-defined]
    if ln.kind == "stub":
        label = ln.label or label
    if leaf.type == "spare" and not leaf.label:  # type: ignore[attr-defined]
        label = registry.label("spare", lang)
    info["label"] = label
    return info


def _draw_table(g: Group, columns: list[LNode], index: Index, view: View, lang: str, y0: float) -> None:
    pitch = view.pitch_mm
    titles = CARTOUCHE_TITLES.get(lang, CARTOUCHE_TITLES["en"])
    infos = [_column_info(c, index, lang) for c in columns]
    # column boundaries
    xs = [c.x for c in columns]
    bounds = [xs[0] - pitch / 2]
    for a, b in zip(xs, xs[1:]):
        bounds.append((a + b) / 2)
    bounds.append(xs[-1] + pitch / 2)
    header_w = 24.0
    x_start = bounds[0] - header_w
    tg = Group(cls="cartouche")
    cols = [Group(id=c.node.id if c.node is not None else None, cls="uw-cell") for c in columns]
    y = y0
    small = Style(width=THIN)
    for field_ in view.cartouche:
        values = [cell(field_, inf, lang) for inf in infos]
        if field_ == "cable" and "cable_ref" not in view.cartouche:  # cable tag next to the cable text
            values = [" · ".join(x for x in (inf["cable"].ref, v) if x) if inf["cable"] is not None else v
                      for v, inf in zip(values, infos)]
        if field_ == "label":
            longest = max((text_width(v, 2.0) for v in values), default=0)
            h = min(max(longest + 3.0, 14.0), 42.0)
        else:
            h = 5.5
        title = titles.get(field_, field_)
        if field_ == "cable" and any(i["cable"] is not None and i["cable"].section_mm2 is None and i["cable"].size_awg
                                     for i in infos):
            title = titles["cable_awg"]  # North-American sizes: no "(mm²)" unit in the header
        tg.add(Rect(x_start, y, header_w, h, small))
        tg.add(Text((x_start + 1.2, y + h / 2), title, 1.9, "start", "middle", bold=True))
        for i, v in enumerate(values):
            cx0, cx1 = bounds[i], bounds[i + 1]
            cg = Group([Rect(cx0, y, cx1 - cx0, h, small)], attrs={"data-uw-field": field_})
            if field_ == "label" and columns[i].kind == "stub":  # "-> sheet n": reference to the board's sheet
                cg = ref_group(columns[i].target_folio, columns[i].target, cg.items)
                cg.attrs["data-uw-field"] = field_
            cols[i].add(cg)
            if not v:
                continue
            if field_ == "label":
                size = 2.0
                tw = text_width(v, size)
                if tw > h - 2:
                    size = max(1.3, size * (h - 2) / tw)
                while len(v) > 4 and text_width(v, size) > h - 2:
                    v = v[:-2] + "…"
                cg.add(Text(((cx0 + cx1) / 2 + 0.7, y + h - 1.0), v, size, "start", "alphabetic", 90))
            else:
                size = 1.8
                avail = cx1 - cx0 - 1.0
                tw = text_width(v, size)
                if tw > avail:
                    size = max(1.2, size * avail / tw)
                cg.add(Text(((cx0 + cx1) / 2, y + h / 2), v, size, "middle", "middle"))
        y += h
    tg.add(*cols)
    g.add(tg)


# ------------------------------------------------------------ sheet splitting
PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}
MARGIN = 10.0
TITLE_BAND = 32.0


TITLE_BLOCK_W = 200.0
NOTES_BAND = 20.0  # notes band above the title block, on sheets too narrow to put them beside it


def notes_beside(view: View) -> bool:
    """True when the notes fit to the left of the title block; otherwise they get a band above it."""
    w, h = PAPER[view.paper]
    if view.orientation == "portrait":
        w, h = h, w
    return w - 2 * MARGIN - min(TITLE_BLOCK_W, w - 2 * MARGIN) - 6.0 > 40


def drawing_area(view: View) -> tuple[float, float, float, float]:
    """(x, y, width, height) of the sheet's drawing area."""
    w, h = PAPER[view.paper]
    if view.orientation == "portrait":
        w, h = h, w
    x0, y0 = MARGIN + 5.0, MARGIN + 5.0
    notes = 0.0 if notes_beside(view) or not view.title_block else NOTES_BAND
    return x0, y0, w - 2 * MARGIN - 10.0, h - 2 * MARGIN - TITLE_BAND - 12.0 - notes


def fit_scale(lay: SheetLayout, view: View) -> float:
    _, _, aw, ah = drawing_area(view)
    return min(1.0, aw / max(lay.width, 1e-6), ah / max(lay.height, 1e-6))


def _sheet_roots(doc: Document, view: View, index: Index) -> list[NodeBase]:
    if view.root:
        return [index.nodes[view.root]]
    return list(doc.sources)


def plan_sheets(doc: Document, view: View, index: Index | None = None) -> list[SheetSpec]:
    index = index or build_index(doc)
    forced = {n.id for n in index.nodes.values() if n.type == "board" and getattr(n, "own_sheet", False)}  # type: ignore[attr-defined]

    def name_of(n: NodeBase) -> str:
        return " ".join(x for x in (n.ref, n.label) if x) or (n.id or "")

    def process(spec: SheetSpec, allow_bus_split: bool = True) -> list[SheetSpec]:
        root_ids = {r.id for r in spec.roots}
        spec.detached |= {f for f in forced if f not in root_ids and _in_spec(spec, f, index)}
        conts: list[SheetSpec] = []
        for _ in range(50):
            lay = layout_sheet(doc, view, spec, index)
            if view.folio_split == "none" or fit_scale(lay, view) >= view.min_scale:
                break
            boards = [n for n in lay.lnodes if n.is_board and n.node is not None and n.node.id not in root_ids
                      and n.node.id not in spec.detached and n.width >= 3 * view.pitch_mm]
            if boards:
                boards.sort(key=lambda n: -n.width)
                spec.detached.add(boards[0].node.id)  # type: ignore[union-attr]
                continue
            if allow_bus_split:
                conts = _split_bus(spec, lay, view, index, normalize_lang(doc.meta.lang))
            break
        out = [spec]
        for c in conts:
            out += process(c, allow_bus_split=False)
        for nid in _ordered(spec, index):
            out += process(SheetSpec([index.nodes[nid]], name=name_of(index.nodes[nid])))
        return out

    first = SheetSpec(_sheet_roots(doc, view, index), name="")
    return process(first)


def _in_spec(spec: SheetSpec, nid: str, index: Index) -> bool:
    anc = {a.id for a in index.ancestors(nid)}
    return any(r.id in anc for r in spec.roots)


def _ordered(spec: SheetSpec, index: Index) -> list[str]:
    """Boards detached from this sheet, in tree order."""
    order = []
    def walk(n: NodeBase, top: bool):
        if not top and n.id in spec.detached:
            order.append(n.id)
            return
        kids = n.children
        if spec.bus_slice and spec.bus_slice[0] == n.id:
            kids = kids[spec.bus_slice[1]:spec.bus_slice[2]]
        for c in kids:
            walk(c, False)
    if spec.continuation:
        nid, s, e = spec.continuation
        for c in index.nodes[nid].children[s:e]:
            walk(c, False)
    else:
        for r in spec.roots:
            walk(r, True)
    return order


def _split_bus(spec: SheetSpec, lay: SheetLayout, view: View, index: Index, lang: str = "en") -> list[SheetSpec]:
    """Split the most crowded busbar into several continuation sheets."""
    cands = [n for n in lay.lnodes if n.kind == "node" and n.has_bus and n.node is not None and len(n.children) >= 4]
    if not cands:
        return []
    bus = max(cands, key=lambda n: n.width)
    node = bus.node
    assert node is not None
    _, _, aw, _ = drawing_area(view)
    cap = aw / view.min_scale - 30.0 - (bus.x - (lay.lnodes[0].x_left if lay.lnodes else 0))
    widths = [c.width for c in bus.children]
    chunks: list[tuple[int, int]] = []
    start, acc = 0, 0.0
    for i, w in enumerate(widths):
        limit = cap if not chunks else aw / view.min_scale - 30.0
        if acc + w > limit and i > start:
            chunks.append((start, i))
            start, acc = i, 0.0
        acc += w
    chunks.append((start, len(widths)))
    if len(chunks) == 1:
        return []
    spec.bus_slice = (node.id, *chunks[0])  # type: ignore[assignment]
    out = []
    prev = spec
    for s, e in chunks[1:]:
        c = SheetSpec([], detached=set(spec.detached), continuation=(node.id, s, e),  # type: ignore[arg-type]
                      name=_t("render.continuation_name", lang, name=node.ref or node.label or node.id), prev=prev)
        prev.next = c
        out.append(c)
        prev = c
    return out
