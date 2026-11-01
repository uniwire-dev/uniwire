from __future__ import annotations

import unicodedata
from collections import Counter
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
    cable_in_awg,
    cell,
    conductor_count,
    drawn_cable_text,
    feeder_mark,
    part_number,
    poles_mark,
    protection_short,
    ref_label,
    state_text,
    system_mark,
    without_ref,
)
from ..model import NODE_TYPES, Document, NodeBase, View
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
    cut_to_width,
    text_units,
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
from ..symbols import BUSWAY_H, DASH, PLC_SLOT_W, Symbol, controller, offpage, symbol_for
from ..symbols import motor as motor_symbol
from ..units import fmt
from .routing import (
    LANE,
    End,
    Obstacles,
    _hit,
    _seg_cost,
    boxes_union,
    place_box,
    place_label,
    route,
    route_grid,
    text_box,
)

GAP = 5.0  # vertical gap between two symbols in series
BUS_GAP = 3.75  # between a symbol and its busbar
CHILD_GAP = 3.75  # between the busbar and the outgoing feeders
BOARD_PAD = 2.5  # horizontal padding of a board frame
BOARD_TOP = 6.0  # room for the board name
LANDING = 2.5  # spacing of the links landing one above the other on an input conductor
SIGNAL_LANE = 1.0  # spacing of control, data and measure links in a channel (thin lines, often many)
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
    lead: float = 0.0  # extra length of the input conductor, for several links landing on it
    pad_bottom: float = 0.0  # room at the bottom of a board frame for the control links of its devices
    frame_reach: Optional[float] = None  # right side of a board frame enclosing the taps of feeds (_feed_taps)
    ann_off: tuple[float, float] = (0.0, 0.0)  # the view's label_offset for this node: where its text really is
    in_safety_board: bool = False  # inside a board that is itself a safety service: its feeders are not marked
    bus_y: Optional[float] = None
    bus_x0: float = 0.0
    bus_x1: float = 0.0
    bottom: bool = False  # load placed on the common baseline
    open_feeder: bool = False  # feeder with no described load: arrow down to the common baseline
    ann: list[str] = field(default_factory=list)
    ann_size: float = ANN_SIZE
    tagged: bool = False
    need: float = 0.0  # width the column needs for its annotation (or a board for its name), at full size
    dc_side: int = 0  # leading children on the DC side of an inverter/charger: fed from its DC terminal, not the bus
    left_room: float = 0.0  # room its links need on its left (the texts of a controller many links reach)

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
    def bus_children(self) -> list[LNode]:
        """The children on the output side (all of them, except the DC side of an inverter/charger)."""
        return self.children[self.dc_side:]

    @property
    def has_bus(self) -> bool:
        if self.kind == "bus_in":
            return True
        kids = self.bus_children
        return len(kids) >= 2 or self.bus_out or (self.type == "busbar" and len(kids) >= 1)

    def dc_terminal(self) -> tuple[float, float]:
        """Side terminal of the DC side (left of the symbol, at the height of its "=" mark)."""
        return (self.x - self.sym.left, self.y + self.sym.height * 0.3)

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
        ox, oy = self.ann_off
        x = self.x + self.sym.right + 1.0 + ox
        w = max(text_width(t, self.ann_size) for t in self.ann)
        return (x, self.y + 0.3 + oy, x + w, self.y + 0.3 + oy + len(self.ann) * ANN_LINE * self.ann_size / ANN_SIZE)

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
    moved: set[str] = field(default_factory=set)  # roots drawn on the sheet of a detached board (standby sources)


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
    if node.type == "spare" and getattr(node, "in_A", None):  # an equipped spare way: its breaker, then the free end
        dev = NODE_TYPES["breaker"].model_validate({"type": "breaker", "id": f"{node.id}.breaker", "ref": node.ref,
                                                    "in_A": node.in_A, "poles": getattr(node, "poles", None)})
        return LNode(dev, "node", symbol_for(dev), [LNode(node, "node", symbol_for(node), [])])
    sym = symbol_for(node)
    if node.type == "busbar" and children and getattr(node, "kind", None) != "busway":
        sym = Symbol("busbar", [], 0.0, sym.left, sym.right)  # its busbar is the one its feeders hang from
    ln = LNode(node, "node", sym, [_build(c, spec, False) for c in children], bus_out=bus_out)
    if node.type in DC_PORT_TYPES:  # an inverter/charger feeding both a DC side (batteries...) and an AC side
        dc = [c for c in ln.children if c.node is not None and _is_dc(c.node)]
        if dc and len(dc) < len(ln.children):
            ln.children = dc + [c for c in ln.children if c not in dc]
            ln.dc_side = len(dc)
    return ln


SPREAD_STEP = 1.5  # single-line: spacing of the link ends on the side of a controller many links reach
SPREAD_FROM = 3  # from this many links on a controller, one point each (fewer: one point per kind, as before)


def _signal_links(doc: Document, nid: Optional[str]) -> list[int]:
    """Control, data and measure links attached to the node ``nid`` by its side (not by a PLC channel)."""
    return [i for i, l in enumerate(doc.links) if l.kind not in SWITCHED_LINKS and l.kind != "earth"
            and ((l.from_ == nid and not l.from_port) or (l.to == nid and not l.to_port))]


SPREAD_OFF = 5.0  # ... for a link to another sheet: its stub carries two lines of text


LEFT_ROOM_MAX = 45.0


def _left_room(doc: Document, n: LNode, here: set[str], lang: str) -> float:
    """A controller many links reach (see ``_spread_symbol``): room on its left for the texts of its links (the
    labels, and the stubs of the links to other sheets), so that its column does not crowd the one before."""
    if n.sym.name != "controller" or n.node is None:
        return 0.0
    ids = _signal_links(doc, n.node.id)
    if len(ids) < SPREAD_FROM:
        return 0.0
    widths = [0.0]
    for i in ids:
        link = doc.links[i]
        other = link.to if link.from_ == n.node.id else link.from_
        if link.label:
            widths.append(text_width(link.label, 1.6))
        if other not in here:  # an off-page stub: its arrow and the name of the other end too
            widths.append(text_width(f"{other} → 00", 1.6) + 8.0)
    return min(LEFT_ROOM_MAX, max(widths) + n.sym.left + 4.0) if max(widths) else 0.0


def _spread_symbol(doc: Document, node: Optional[NodeBase], sym: Symbol, here: Optional[set[str]] = None) -> Symbol:
    """A controller many links reach: drawn taller, room for one link end each on its sides (``here``: the nodes
    drawn on the sheet; a link to another one ends on an off-page stub, which takes more room)."""
    if node is None or sym.name != "controller" or not node.id:
        return sym
    ids = _signal_links(doc, node.id)
    count = len(ids)
    others = [doc.links[i].to if doc.links[i].from_ == node.id else doc.links[i].from_ for i in ids]
    body = sum(SPREAD_OFF if here is not None and o not in here else SPREAD_STEP for o in others) + 1.5
    return controller(node, body) if count >= SPREAD_FROM and body > sym.height - 2 * 2.5 else sym


DC_PORT_TYPES = {"inverter", "ups"}
OVERCURRENT = {"breaker", "rcbo", "main_breaker", "fuse", "fuse_switch"}  # what protects a feeder
DC_ACCESSORIES = {"spd", "meter", "insulation_monitor"}  # beside a DC way, they do not make it an AC feeder


def _is_dc(node: NodeBase) -> bool:
    """A child on the DC side of an inverter/charger: batteries, PV, DC converters, DC boards, or a device
    (fuse, disconnector...) feeding one of them alone."""
    n = node
    while True:
        if n.type in ("battery", "pv_array", "dc_converter"):
            return True
        if n.type in ("board", "busbar"):
            return getattr(n, "kind", None) == "dc_box" or getattr(n, "system", None) == "DC"
        if len(n.children) != 1:
            # a string or battery way with its own surge protector / meter is still on the DC side
            kids = [c for c in n.children if c.type not in DC_ACCESSORIES]
            return len(kids) == 1 and len(n.children) > 1 and _is_dc(kids[0])
        n = n.children[0]


def _bus_name(node: NodeBase, index: Index) -> str:
    """Name of the busbar a node feeds: its board's (or busbar's), not the device at its head (a meter, a breaker)."""
    owner = next((a for a in [node] + index.ancestors(node.id or "")
                  if a.type in ("board", "busbar")), node)  # type: ignore[attr-defined]
    return owner.ref or owner.label or node.ref or node.label or node.id or ""


def _build_sheet_roots(spec: SheetSpec, index: Index) -> list[LNode]:
    if spec.continuation:
        nid, s, e = spec.continuation
        parent = index.nodes[nid]
        kids = parent.children[s:e]
        bus_sym = Symbol("bus_in", [], 0.0, 0.0, 0.0)
        root = LNode(None, "bus_in", bus_sym, [_build(c, spec, False) for c in kids],
                     label=_bus_name(parent, index), target=nid, bus_out=e < len(parent.children))
        return [root]
    return [_build(r, spec, True) for r in spec.roots if r.id not in spec.moved]


# ---------------------------------------------------------------- computation
def _measure(ln: LNode, pitch: float, left_room: float = 0.0) -> float:
    """``left_room``: room on the left asked by a device above in the same column (see ``LNode.left_room``)."""
    room = max(left_room, ln.left_room)
    for c in ln.children:
        _measure(c, pitch, room if len(ln.children) == 1 else 0.0)
    # intrinsic symbol width (modular PLC, transfer switch...): the column widens if needed
    own = pitch / 2 + ln.sym.right + 16.0 if ln.sym.right > pitch / 2 - 2 else pitch  # + room for the annotation
    if not ln.children:
        ln.left_room = room  # the column moves its axis right by that much
        ln.width = max(pitch, own, ln.need) + max(room - pitch / 2, 0.0)
    else:  # its text keeps the room it needs right of the axis, moved right by the room on the left
        shift = max(room - pitch / 2, 0.0) if len(ln.children) == 1 else 0.0
        ln.width = max(sum(c.width for c in ln.children), own + shift, ln.need + shift)
    if ln.is_board:
        ln.width += 2 * BOARD_PAD + pitch * 0.3  # right margin: annotations of the last column
        short = ln.need - ln.width
        if short > 0:  # the name of the board is wider than its columns: widen the last one
            ln.width += short
            c = ln.children[-1] if ln.children else None
            while c is not None:
                c.width += short
                c = c.children[-1] if c.children else None
    return ln.width


def _needs(ln: LNode, view: View, lang: str) -> None:
    """Widths the columns need so that no annotation is cut and the names of the boards keep their size."""
    for n in ln.walk():
        if n.is_board and n.node is not None:
            name = ref_label(n.node.ref, n.node.label)
            # the name starts above the first column, 1.5 right of its axis
            n.need = BOARD_PAD + view.pitch_mm / 2 + 1.5 + 1.1 * text_width(name, 2.4) + 1.5 if name else 0.0
        elif len(n.children) <= 1:  # a load, or a device feeding one load: its text has the column to itself
            lines = _ann_lines(n, view, lang)
            if lines:
                # room for the text reduced to ANN_MIN at most: a long text is reduced, never cut
                widest = max(text_width(t, ANN_MIN) for t in lines)
                n.need = view.pitch_mm / 2 + n.sym.right + 2.0 + widest


def _place_x(ln: LNode, x_left: float, pitch: float = 20.0) -> None:
    ln.x_left = x_left
    if not ln.children:
        ln.x = x_left + max(pitch / 2, ln.left_room) if ln.width > pitch else x_left + ln.width / 2
        return
    cx = x_left + (BOARD_PAD if ln.is_board else 0.0)
    for c in ln.children:
        _place_x(c, cx, pitch)
        cx += c.width
    out = ln.bus_children
    ln.x = out[0].x
    if ln.has_bus:
        ln.bus_x0 = min(ln.x, out[0].x) - (6.0 if ln.kind == "bus_in" else 0.0)
        ln.bus_x1 = out[-1].x + (6.0 if ln.bus_out else 0.0)


def _ann_lines(ln: LNode, view: View, lang: str) -> list[str]:
    """Annotation of a node: its tag, then its characteristics (5 lines at most)."""
    node = ln.node
    if ln.kind != "node" or not view.annotations or node is None or ln.bottom or ln.is_board:
        return []
    feeds_bus = any(len(d.children) >= 2 for d in ln.walk())
    lines = annotation(node, lang, show_label=feeds_bus)
    pn = part_number(node)
    tag = pn if view.tag_field == "part_number" and pn else node.ref
    if node.label and node.label in lines:  # the label: not repeating the tag above it, nor the lines below it
        label = without_ref(node.label, node.ref) if tag == node.ref else node.label
        lines = [label if t == node.label else t for t in lines]
        lines = [t for t in lines if t and (t == label or t.casefold() not in label.casefold())]  # 'Type 2' in 'type 2'
    if tag:
        lines.insert(0, tag)
    # the cable it feeds, when the circuit table does not show it (feeder of a sub-board, a transformer...), and
    # the incoming cable of the board it feeds
    in_table = _in_column(ln) and bool(view.cartouche) and "cable" in (view.cartouche or [])
    cables = [] if in_table else [getattr(node, "cable", None)]
    if len(ln.children) == 1 and ln.children[0].is_board and ln.children[0].node is not None:
        cables.append(getattr(ln.children[0].node, "cable", None))
    captions = [c for c in (_cable_caption(c) for c in cables if c is not None) if c]
    leaf = ln
    while len(leaf.children) == 1:
        leaf = leaf.children[0]
    if node.type in PROTECTIVE and not ln.in_safety_board and "safety" in (getattr(node, "priority", None),
                                                                    getattr(leaf.node, "priority", None) if leaf.bottom else None):
        captions.insert(0, _t("label.safety", lang))  # a safety service circuit (fire alarm, emergency lighting...)
    return lines[:5] + captions  # the cable and the safety mark come on top of the usual lines, never instead


OPEN_ROOM = 45.0  # width a label may take beside the last device of a row, nothing drawn to its right


def _annotate(ln: LNode, view: View, lang: str, avail_override: float | None = None,
              right_limit: float | None = None, room: float | None = None) -> None:
    if ln.kind != "node" or not view.annotations:
        ln.ann = []
        return
    node = ln.node
    assert node is not None
    if ln.bottom or ln.is_board:
        ln.ann = []
        return
    ln.ann = _ann_lines(ln, view, lang)
    ov = view.overrides.get(node.id) if node.id else None
    ln.ann_off = tuple(ov.label_offset) if ov is not None and ov.label_offset else (0.0, 0.0)  # type: ignore[assignment]
    pn = part_number(node)
    ln.tagged = bool(pn if view.tag_field == "part_number" and pn else node.ref)
    # space available to the right of the symbol
    avail = (ln.x_left + ln.width) - (ln.x + ln.sym.right + 1.0) + view.pitch_mm / 2 - 3.5
    if not ln.children:
        avail = max(view.pitch_mm - ln.sym.right - 4.0, (ln.x_left + ln.width) - (ln.x + ln.sym.right + 1.0) - 1.0)
    if right_limit is not None:
        avail = min(avail, right_limit - (ln.x + ln.sym.right + 1.0))
    if room is not None:
        avail = max(avail, room)
    if avail_override is not None:
        avail = avail_override
    size = ANN_SIZE
    widest = max((text_width(t, ANN_SIZE) for t in ln.ann), default=0)
    if widest > avail > 0 and (full := _wrap_full_size(ln, avail)) is not None:
        ln.ann, ln.ann_size = full, size  # on more lines at the usual size rather than smaller
        return
    if widest > avail > 0:
        size = max(ANN_MIN, ANN_SIZE * avail / widest)
    ln.ann_size = size
    if widest * size / ANN_SIZE > avail:
        out = []
        for i, t in enumerate(ln.ann):
            units = text_units(t)
            if (i or not ln.tagged) and text_width(t, size) > avail and len(units) > 1 and len(ln.ann) + len(out) - i < 5:
                two = _wrap_words(units, 2, lambda u: text_width(u, size))  # on two lines rather than cut
                if max(text_width(u, size) for u in two) <= avail:
                    out += two
                    continue
            out.append(cut_to_width(t, size, avail))
        ln.ann = out


def _wrap_full_size(ln: LNode, avail: float) -> list[str] | None:
    """The label lines of ``ln`` with each line too wide for ``avail`` on two lines, at the usual size; None when a
    line cannot be split so (one word, the tag) or the label would run to more than five lines."""
    out: list[str] = []
    for i, t in enumerate(ln.ann):
        if text_width(t, ANN_SIZE) <= avail:
            out.append(t)
            continue
        units = text_units(t)
        if (not i and ln.tagged) or len(units) < 2:
            return None
        two = _wrap_words(units, 2, lambda u: text_width(u, ANN_SIZE))
        if max(text_width(u, ANN_SIZE) for u in two) > avail:
            return None
        out += two
    return out if len(out) <= 5 else None


def _place_y(ln: LNode, y: float) -> None:
    y += ln.lead
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
        if ab and ln.children and (ln.children[0].ann or ln.children[0].is_board):  # a board's frame too
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
    return max(n.content_bottom() for n in _owned(board)) + board.pad_bottom


def _separate_boards(ln: LNode) -> None:
    for n in ln.walk():
        if n.is_board:
            subs = _sub_boards(n)
            if not subs:
                continue
            # below the frame, and side by side on one line (their frames, names and first devices aligned)
            top = max([_board_bottom(n) + 4.0] + [sb.frame_top for sb in subs])
            for sb in subs:
                if top > sb.frame_top:
                    _shift(sb, top - sb.frame_top)


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


def _beside_hosts(main: list[LNode], doc: Document) -> list[LNode]:
    """A tree that only adds a supply to another one (its ``infeed`` links all land below the head of that tree,
    on a node already fed there; no link lands in it, no other power link) is drawn just right of it, in the order
    of the document, so that its feed stays short. A tree feeding the head of another one is the supply of that
    tree, not an addition to it: it keeps its place."""
    tree = {n.node.id: i for i, r in enumerate(main) for n in r.walk() if n.node is not None}
    heads = {r.node.id for r in main if r.node is not None}
    targets: dict[int, set[int]] = {}
    fixed: set[int] = set()  # trees that receive a link or carry another power link: never moved
    for link in doc.links:
        a, b = tree.get(link.from_), tree.get(link.to)
        if a is None or b is None or a == b:
            continue
        if link.kind == "infeed" and link.to in heads:
            fixed |= {a, b}
        elif link.kind == "infeed":
            targets.setdefault(a, set()).add(b)
            fixed.add(b)
        elif link.kind in POWER_LINKS or link.kind in ("transfer", "tie"):
            fixed |= {a, b}
    host = {a: next(iter(t)) for a, t in targets.items() if len(t) == 1 and a not in fixed}
    if not host:
        return main
    order: list[int] = []
    for i in range(len(main)):
        if i not in host:
            order.append(i)
            order.extend(a for a in sorted(host) if host[a] == i)
    return [main[i] for i in order]


def _far_links(doc: Document, main: list[LNode]) -> set[int]:
    """Links between two trees with a third tree drawn between them (other than one feeding the same tree): drawn
    as an interrupted line, a short stub at each end naming the other end, instead of a run across the sheet."""
    tree = {n.node.id: i for i, r in enumerate(main) for n in r.walk() if n.node is not None}
    fed: dict[int, set[int]] = {}  # tree -> the trees it feeds
    for link in doc.links:
        a, b = tree.get(link.from_), tree.get(link.to)
        if link.kind == "infeed" and a is not None and b is not None and a != b:
            fed.setdefault(a, set()).add(b)
    far: set[int] = set()
    for i, link in enumerate(doc.links):
        a, b = tree.get(link.from_), tree.get(link.to)
        if a is None or b is None or abs(a - b) < 2 or link.kind in ("transfer", "tie"):
            continue
        lo, hi = sorted((a, b))
        if any(link.kind != "infeed" or fed.get(k) != {b} for k in range(lo + 1, hi)):
            far.add(i)
    return far


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

    here = sheet_node_ids(doc, spec, index)
    for r in roots:
        for n in r.walk():
            if n.type == "generator" and n.node is not None:
                n.sym = symbol_for(n.node, _system_of(n.node, doc))
            elif n.type == "motor" and n.node is not None and getattr(n.node, "phases", None) is None:
                # phases not stated: those of its feeder (a motor on a single-phase circuit is drawn 1~)
                live = conductor_count(_feeder_chain(n, index), _supply_system(n, index, doc))
                n.sym = motor_symbol(n.node, live)
            n.sym = _spread_symbol(doc, n.node, n.sym, here)
            n.left_room = _left_room(doc, n, here, lang)

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

    main = _beside_hosts([r for r in roots if id(r) not in anchored], doc)
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
        _needs(r, view, lang)
        _measure(r, pitch)
        _place_x(r, x, pitch)
        x += r.width + pitch * (ROOT_GAP_COLS + (1.0 if i in wide_gap else 0.0))
    for r in roots:  # the feeders of a safety board are safety circuits by themselves: not marked one by one
        for b in r.walk():
            if b.is_board and b.node is not None and getattr(b.node, "priority", None) == "safety":
                for n in list(b.walk())[1:]:
                    n.in_safety_board = True
    # several infeeds on one input conductor: room for one landing point each
    fed_ok = _fed_ok(roots)
    feeds = Counter(l.to for l in doc.links if l.kind == "infeed" and l.to in fed_ok)
    for r in roots:
        for n in r.walk():
            if n.node is not None and feeds[n.node.id] > 2:
                n.lead = LANDING * (feeds[n.node.id] - 2)
    # control, data, measure and power links of the devices of a board run inside its frame: room at its bottom
    for r in roots:
        for b in r.walk():
            if b.is_board:
                own = {n.node.id for n in _owned(b) if n.node is not None}
                k = sum(1 for l in doc.links if l.kind not in SWITCHED_LINKS and (l.from_ in own or l.to in own))
                p = sum(1 for l in doc.links if l.kind in POWER_LINKS and (l.from_ in own or l.to in own))
                b.pad_bottom = SIGNAL_LANE * min(k, 8) + LANE * 2 * min(p, 4) + 1.5 if k or p else 0.0
    xs = sorted({round(n.x - n.sym.left, 3) for r in main for n in r.walk()})
    for r in main:
        nxt = {id(a): b for n in r.walk() for a, b in zip(n.children, n.children[1:])}
        for n in r.walk():  # a label stops before the next symbol, as wide as it is (a converter)
            b = nxt.get(id(n))
            # the last device of a row with nothing drawn to its right (a controller at the end of a feeder):
            # its label runs on rather than shrinks, up to the next column of the sheet
            right = next((x for x in xs if x > n.x + n.sym.right + 1.0), None)
            room = None if b is not None or n.children else \
                min(OPEN_ROOM, (right - 1.0 if right is not None else 1e9) - (n.x + n.sym.right + 1.0))
            _annotate(n, view, lang, right_limit=b.x - b.sym.left - 1.0 if b is not None else None, room=room)
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

    # several feeds from other trees tapping one busbar (see _draw_links): their sources high enough above it for
    # one channel each
    far = _far_links(doc, main)
    tapping: dict[str, list[LNode]] = {}
    for i, link in enumerate(doc.links):
        a, b = _find(main, link.from_), _find(main, link.to)
        if (link.kind == "infeed" and i not in far and a is not None and b is not None and b.sym.height == 0
                and b.bus_y is not None and b.children and _root_of(main, a) is not _root_of(main, b)):
            tapping.setdefault(b.id, []).append(a)
    lift: dict[int, tuple[LNode, float]] = {}
    for bid, srcs in tapping.items():
        b = _find(main, bid)
        if len(srcs) < 2 or b is None or b.bus_y is None:
            continue
        need = 2.0 + 4.0 + 3.0 * (len(srcs) - 1) + 1.0  # see bus_lane in _draw_links
        xs = [a.x for a in srcs] + [b.bus_x0, b.bus_x1]
        if any(min(xs) - 1.0 < e.x < max(xs) + 1.0 for e in _down_stubs(doc, main)):
            need += STUB_DROP  # the channels below an off-sheet stub hanging down where they run (see _feed_taps)
        for a in srcs:
            r = _root_of(main, a)
            d = min(b.bus_y - _end(a, "infeed").y - need, lift.get(id(r), (r, 0.0))[1])
            lift[id(r)] = (r, d)
    for r, d in lift.values():
        if d < 0:
            _shift(r, d)

    # normally-open alternative supplies: a band of lanes under the busbars they leave
    band = _alt_band(doc, main, lang)

    # secondary sources on a transfer switch
    placed: list[LNode] = []  # several standby sources: each one beside the ones already placed
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
        boxes = [b for m in main + placed for b in _boxes(m)]
        boxes += [_frame_box(n) for m in main + placed for n in m.walk() if n.is_board]
        obstacles = [b for b in boxes if b[3] > top - 1 and b[1] < sy - 2 and b[2] > target.x - 3]
        right = max([b[2] for b in obstacles] + [sx])
        new_x = max(sx, right + 3.0 + r.sym.left)
        _translate(r, new_x - last.x, top)
        placed.append(r)

    everything = [n for r in roots for n in r.walk()]

    # common baseline of the loads
    non_bottom = [n for n in everything if not n.bottom]
    y_load = max([n.content_bottom() + 7.5 for n in non_bottom]
                 + [_board_bottom(n) + 2.0 + 5.5 for n in everything if n.is_board and n.pad_bottom], default=0.0)
    for n in everything:
        if n.bottom:
            n.y = y_load

    # feeds tapping a busbar: their taps known before the frames, so that the frame of the board encloses them
    feed_taps = _feed_taps(doc, roots, far, band)
    for r in main:
        for b in r.walk():
            if b.is_board:
                b.frame_reach = max([feed_taps.reach[n.id] for n in _owned(b) if n.id in feed_taps.reach],
                                    default=None)

    # what is already drawn: auxiliary devices and link routes must avoid it
    obs = _obstacles(everything, main, y_load)
    for i, e in feed_taps.land.items():  # the taps, their drop and the busbar extended to them
        b = _find(roots, doc.links[i].to)
        if b is not None and b.bus_y is not None:
            obs.add_vline(e.x, b.bus_y - 10.0, b.bus_y)
            obs.add_hline(b.bus_y, min(e.x, b.bus_x0), max(e.x, b.bus_x1), bus=True)

    NO_COLUMN = {"earth", "earth_bar", "earthing_switch", "voltage_indicator", "neutral_impedance",
                 "surge_limiter", "insulation_monitor", "protection_relay", "instrument_transformer"}
    on_bus = {id(c) for n in everything if n.has_bus for c in n.bus_children}
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

    # auxiliary devices: on the sheet of the tree node they are linked to, in free space near their partner (and off
    # the channels already given to the feeds tapping a busbar, which are routed later)
    lanes: list[tuple[str, tuple[float, float, float]]] = []
    for i, y in feed_taps.lane.items():
        a, e = _find(roots, doc.links[i].from_), feed_taps.land[i]
        if a is not None:
            s = _end(a, "infeed")
            lanes += [("h", (y, min(e.x, s.x), max(e.x, s.x))), ("v", (s.x, min(s.y, y), max(s.y, y)))]
    for kind, line in lanes:
        (obs.hlines if kind == "h" else obs.vwires).append(line)
    annex = _place_devices(doc, roots, everything, view, lang, obs, pitch)
    for kind, line in lanes:
        (obs.hlines if kind == "h" else obs.vwires).remove(line)
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
    _draw_links(doc, roots + annex, anchored, g, view, obs, y_load, lang, node_folio, band, far=far,
                feed_taps=feed_taps)

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
            txt = _t("render.continued_from", lang, label=n.label, folio=prev_f or '?')
            g.add(ref_group(prev_f, n.target, [
                Polyline([(n.bus_x0 + 1.6, n.bus_y - 1.2), (n.bus_x0, n.bus_y), (n.bus_x0 + 1.6, n.bus_y + 1.2)]),
                _bus_end_text(obs, txt, n.bus_x0, n.bus_y, "start")]))
        if n.bus_out and n.bus_y is not None:
            nxt = continuation_folios[1]
            txt = _t("render.continued_on", lang, folio=nxt or '?')
            g.add(ref_group(nxt, n.id, [
                Polyline([(n.bus_x1 - 1.6, n.bus_y - 1.2), (n.bus_x1, n.bus_y), (n.bus_x1 - 1.6, n.bus_y + 1.2)]),
                _bus_end_text(obs, txt, n.bus_x1, n.bus_y, "end")]))

    bottom_end = max([y_load + n.sym.height for n in everything if n.bottom] + [y_load + 2.0])
    if view.cartouche:  # the sheet a feeder continues on, under its arrow (the table repeats it with the name)
        for n in columns:
            if n.kind == "stub" and n.target_folio:
                t = n.label if text_width(n.label, 1.8) <= view.pitch_mm * 0.95 else \
                    _t("render.to_folio", lang, folio=n.target_folio).strip()
                y = y_load + n.sym.height + 2.4
                g.add(ref_group(n.target_folio, n.target, [Text((n.x, y), t, 1.8, "middle")]))
                bottom_end = max(bottom_end, y + 0.5)
            elif n.node is not None and n.node.type == "offpage" and getattr(n.node, "target", None):
                t = str(n.node.target)  # type: ignore[attr-defined]  # another drawing: on up to 3 lines
                words, room = text_units(t), view.pitch_mm * 0.95
                lines = next((ls for k in (1, 2, 3) if len(words) >= k
                              for ls in [_wrap_words(words, k, lambda u: text_width(u, 1.8))]
                              if max(text_width(u, 1.8) for u in ls) <= room), None) \
                    or _wrap_words(words, min(3, len(words)), lambda u: text_width(u, 1.8))
                y = y_load + n.sym.height + 2.4
                for k, line in enumerate(lines):
                    g.add(Text((n.x, y + k * 2.2), line, 1.8, "middle"))
                bottom_end = max(bottom_end, y + 2.2 * (len(lines) - 1) + 0.5)
    if view.cartouche and columns:
        # below everything drawn so far: auxiliary devices and link routes may go lower than the loads
        drawn_box = bbox(g)
        _draw_table(g, columns, index, view, lang, max(bottom_end, drawn_box[3] if drawn_box else 0.0) + 6.0)
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
    name = ref_label(node.ref, node.label)
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
            obs.add_hline(n.bus_y, n.bus_x0, max(n.bus_x1, n.bus_x0 + 4), bus=True)
            if n.kind != "bus_in":
                obs.add_vline(n.x, n.out_y, n.bus_y)
        for c in n.children:
            obs.add_vline(c.x, start, c.y)
            if c.x != n.x and n.bus_y is None:
                obs.add_hline(n.out_y + 1.5, n.x, c.x)
        if n.open_feeder:
            obs.add_vline(n.x, n.out_y, y_load + 4.0)
    for n in everything:  # boards of every tree, standby sources included
        if n.is_board:
            x0, y0, x1, y1 = _frame_box(n)
            obs.add_frame((x0, y0, x1, y1))
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


def _bus_end_text(obs: Obstacles, txt: str, x: float, y: float, anchor: str) -> Text:
    """The text at an end of a busbar continued on another sheet: above it, inward; where that is taken (a short
    busbar: the text of its other end, the name of its board), beyond its end, then below it."""
    w = text_width(txt, 2.0)
    out = 1.0 if anchor == "end" else -1.0  # beyond the end of the busbar
    beyond = "start" if anchor == "end" else "end"
    cands = [(x, y - 2.0, anchor), (x + 2.0 * out, y + 0.7, beyond), (x + 2.0 * out, y - 2.0, beyond),
             (x, y + 3.8, anchor)]
    pick = next((c for c in cands if obs.box_free(text_box(c[0], c[1], w, 2.0, c[2]), 0.3)), None)
    if pick is None:  # across a line (a frame, a conductor) rather than on a text
        pick = min(cands, key=lambda c: obs.overlap(text_box(c[0], c[1], w, 2.0, c[2]), 0.3))
    obs.add_box(text_box(pick[0], pick[1], w, 2.0, pick[2]))
    return Text((pick[0], pick[1]), txt, 2.0, pick[2])


def sheet_node_ids(doc: Document, spec: SheetSpec, index: Index) -> set[str]:
    """Ids of the nodes (tree nodes and auxiliary devices) drawn on the sheet ``spec``."""
    ids = {n.node.id for r in _build_sheet_roots(spec, index) for n in r.walk()
           if n.kind == "node" and n.node is not None and n.node.id}
    ids |= {d for d, h in _device_homes(doc).items() if h in ids}
    return ids


DEVICE_PAD_MM = 2.5  # free margin around an auxiliary device (symbol and text)
DEVICE_AXIS_MM = 30.0  # length of the reserved axis below a load


def _place_devices(doc: Document, roots: list[LNode], everything: list[LNode], view: View, lang: str,
                   obs: Obstacles, pitch: float, left_of: Callable[[LNode], bool] | None = None) -> list[LNode]:
    """Auxiliary devices whose home node is on this sheet, each in the free space nearest its partner
    (``left_of(partner)``: on its left, the side its links can reach)."""
    homes = _device_homes(doc)
    placed: dict[str, LNode] = {n.node.id: n for n in everything if n.kind == "node" and n.node is not None and n.node.id}
    todo = [d for d in doc.devices if d.id and homes.get(d.id) in placed]
    annex: list[LNode] = []
    reserved: list[tuple[float, float, float, float]] = []  # room kept for the link labels, freed at the end
    # the axis under each load stays free: a device there would read as wired in series with the load
    axes = [(n.x, n.y, n.y + n.sym.height + DEVICE_AXIS_MM) for n in everything if n.bottom]
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
            ln = LNode(dev, "node", _spread_symbol(doc, dev, symbol_for(dev)))
            ln.width = pitch
            _annotate(ln, view, lang, avail_override=60.0)
            ln.x, ln.y = 0.0, 0.0
            u = boxes_union([ln.sym_box()] + ([ln.ann_box()] if ln.ann else []))
            assert u is not None
            pab = partner.ann_box()
            pref_x = (pab[2] if pab else partner.x + partner.sym.right) + 4.0
            if left_of is not None and left_of(partner):
                pref_x = partner.x - partner.sym.left - 4.0 - (u[2] - u[0])
            # its link labels are written beside it, where its links leave (the left side, see _end): room for the
            # widest one, kept free of the next devices (the routes and labels drawn later may use it)
            lw = max((text_width(l.label, 1.6) for l in doc.links if l.label and dev.id in (l.from_, l.to)),
                     default=0.0)
            lane = lw + 2.0 if lw else 0.0
            free = Obstacles(obs.boxes, obs.vwires + axes, obs.hlines, obs.buses)
            for right_side in (False, True):  # the room on the side facing its partner: left, unless placed left of it
                v = (u[0], u[1], u[2] + lane, u[3]) if right_side else (u[0] - lane, u[1], u[2], u[3])
                x0, y0 = place_box(free, v[2] - v[0], v[3] - v[1], (pref_x, partner.y), pad=DEVICE_PAD_MM)
                ln.x, ln.y = x0 - v[0], y0 - v[1]
                if not lane or right_side or ln.x > partner.x:
                    break
            ln.x_left = ln.x - pitch / 2
            obs.add_box(ln.sym_box())
            obs.add_box(ln.ann_box())
            if lane:
                e = _end(ln, "control")
                if ln.x < partner.x:  # its links leave by the right (see _right_end)
                    x = ln.x + ln.sym.right + 0.8
                    reserved.append((x, e.y - 2.4, x + lane, e.y + 2.4))
                else:
                    reserved.append((e.x - lane, e.y - 2.4, e.x, e.y + 2.4))
                obs.add_box(reserved[-1])
            annex.append(ln)
            placed[dev.id] = ln  # type: ignore[index]
        if not progress:
            break
    for b in reserved:
        obs.boxes.remove(b)
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


def _dc_node(n: NodeBase) -> bool:
    """A node that starts a DC part: DC system, DC box, or a device declared ``dc``."""
    return (getattr(n, "system", None) == "DC" or (n.type == "board" and getattr(n, "kind", None) == "dc_box")  # type: ignore[attr-defined]
            or getattr(n, "dc", None) is True)


def _dc_line(node: NodeBase, index: Index) -> bool:
    """Whether ``node`` sits on a DC line: a DC node at or above it, before any inverter."""
    for n in [node] + (index.ancestors(node.id) if node.id else []):
        if _dc_node(n):
            return True
        if n.type == "inverter":  # type: ignore[attr-defined]
            return False
    return False


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

    def walk(n: NodeBase, up: Optional[Mark], dc: bool = False) -> None:
        dc = _dc_node(n) or (dc and n.type != "inverter")  # type: ignore[attr-defined]
        m_in[id(n)] = up
        out = up
        if n.type == "transformer":  # type: ignore[attr-defined]
            out = system_mark(_system_of(n, doc)) or up
        elif dc:  # a DC line has two poles and no neutral, whatever the devices cut
            out = (2, False)
        elif n.type in SWITCHING and getattr(n, "poles", None):  # type: ignore[attr-defined]
            out = poles_mark(n.poles, _needs_neutral(n)) or up  # type: ignore[attr-defined]
        m_out[id(n)] = out
        for c in n.children:
            walk(c, out, dc)

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


def _in_column(n: LNode) -> bool:
    """Whether the circuit table shows the cable of ``n``: its column runs down to a load, no board nor busbar
    in between (the path :func:`_column_info` follows)."""
    while n.children:
        if len(n.children) != 1 or n.is_board or n.children[0].is_board:
            return False
        n = n.children[0]
    return True


def _cable_caption(c: Any) -> str:
    """'W7 5x6 38 m': tag, composition and length of a cable written in the text of its device ('' without a
    composition: a bare length says nothing)."""
    comp = drawn_cable_text(c)
    return " ".join(x for x in (c.ref, comp, fmt(c.length_m, " m") if c.length_m else "") if x) if comp else ""


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
        mark = feeder_mark(chain, "DC" if _dc_line(chain[0], index) else _supply_system(ln, index, doc))
        phase = next((getattr(c, "phase", None) for c in chain if getattr(c, "phase", None)), None)
        if ln.open_feeder and ln.node is not None and ln.type in ("power_supply", "dc_converter"):
            mark, phase = (2, False), None  # what leaves a power supply: its two output poles (L+ L-), not its input
        if not mark:
            continue
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
        ab = ln.ann_box()  # the view's label_offset included
        assert ab is not None
        tg = Group(cls="annotation")
        for i, t in enumerate(ln.ann):
            tg.add(Text((ab[0], ab[1] + (i + 0.8) * ANN_LINE * ln.ann_size / ANN_SIZE), t,
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
        for c in ln.bus_children:
            eg = edge_group(c.id, me, [Line((c.x, ln.bus_y + trunk), (c.x, c.frame_top if c.is_board else c.y))])
            if c.is_board:
                eg.add(Line((c.x, c.frame_top), (c.x, c.y)))
            g.add(eg)
    else:
        for c in ln.bus_children:
            top = c.frame_top if c.is_board else c.y
            eg = edge_group(c.id, me)
            if ln.x == c.x:
                eg.add(Line((ln.x, ln.out_y), (c.x, top)))
            else:
                eg.add(Polyline([(ln.x, ln.out_y), (ln.x, ln.out_y + 1.5), (c.x, ln.out_y + 1.5), (c.x, top)]))
            if c.is_board:
                eg.add(Line((c.x, c.frame_top), (c.x, c.y)))
            g.add(eg)
    tx, ty = ln.dc_terminal()
    for c in ln.children[:ln.dc_side]:  # DC side: from the side terminal of the inverter/charger
        top = c.frame_top if c.is_board else c.y
        eg = edge_group(c.id, me, [Polyline([(tx, ty), (c.x, ty), (c.x, top)])])
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
    if b.frame_reach is not None:  # taps of feeds on its busbar, beyond its end (see _feed_taps)
        x1 = max(x1, b.frame_reach + 1.0)
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
    at the bottom of the frame; on one line, else on two or three lines and between the conductors crossing
    the frame, slightly smaller if need be; the frame and its label then become obstacles for the link routes."""
    x0, top, x1, y1 = box
    content_top = top + gap
    # nearest busbar or frame edge crossing the frame above the content: the frame must start below it
    limit = max([y for y, h0, h1 in obs.hlines if h0 < x1 and x0 < h1 and y < content_top - 0.2] + [-1e9])

    def frame_top(lh: float) -> float:
        y0 = max(top - lh, limit + 0.8) if limit > top - lh - 0.8 else top - lh
        return min(y0, content_top - 0.6)

    y0 = frame_top(size + 1.2 if label else 0.0)
    if label:
        placed = None
        for s, lines, widen in _frame_label_tries(label, size, x1 - x0 - 2.0):
            lead = s * 1.25
            lh = lead * (len(lines) - 1) + s + 1.2
            ws = [text_width(t, s) for t in lines]
            w = max(ws)
            # the frame side, else just right of a conductor crossing the frame; widened: the frame grows
            # over free room so that its label stays inside
            lefts = [x0 + 1.0] + sorted(x + 1.0 for x, a, b in obs.vwires if x0 < x < x1 and a < y1 and top - lh < b)
            xs = [(x, "start") for x in lefts if (x + w > x1 - 1.0) == widen]
            if widen or x0 + 1.0 + w <= x1 - 1.0:  # right-aligned: in the frame, or widening it to the left
                xs.insert(min(1, len(xs)), (x1 - 1.0, "end"))
            ty0 = frame_top(lh)
            slots = [(ty0 + s + 0.6, ty0)] if content_top - ty0 >= lh + 0.4 else []
            slots.append((y1 + s + 0.3, None))
            for base, fy0 in slots:
                fy0 = y0 if fy0 is None else fy0
                fy1 = y1 + (lh if base > y1 else 0.0)
                for lx, anchor in xs:
                    tbs = [text_box(lx, base + i * lead, wi, s, anchor) for i, wi in enumerate(ws)]
                    nx0, nx1 = (min(x0, lx - w - 1.0), x1) if anchor == "end" else (x0, max(x1, lx + w + 1.0))
                    grown = [r for r in ((nx0 - 0.4, fy0, x0, fy1), (x1, fy0, nx1 + 0.4, fy1)) if r[2] - r[0] > 0.41]
                    if all(obs.box_free(t, 0.2, 0.1) for t in tbs) and all(obs.box_free(r) for r in grown):
                        placed = (lines, s, lx, base, anchor, tbs, (nx0, fy0, nx1, fy1))
                        break
                if placed:
                    break
            if placed:
                break
        if placed is None:  # nothing free: one line above the content, as before
            base = y0 + size + 0.6 if content_top - y0 >= size + 1.6 else y1 + size + 0.3
            placed = ([label], size, x0 + 1.0, base, "start", [text_box(x0 + 1.0, base, text_width(label, size), size)],
                      (x0, y0, x1, y1 + (size + 1.2 if base > y1 else 0.0)))
        lines, s, lx, base, anchor, tbs, (x0, y0, x1, y1) = placed
        for i, t in enumerate(lines):
            g.add(Text((lx, base + i * s * 1.25), t, s, anchor, bold=True))
        for b in tbs:
            obs.add_box(b)
    g.add(Rect(x0, y0, x1 - x0, y1 - y0, style))
    obs.add_frame((x0, y0, x1, y1))


def _frame_label_tries(label: str, size: float, width: float) -> Iterator[tuple[float, list[str], bool]]:
    """Ways of writing a frame label, best first: (size, lines, the frame may widen). One line, then two
    lines fitting ``width``, in the frame; the same widening the frame; then three lines or a smaller size."""
    words = text_units(label)

    def wrapped(n: int, s: float) -> Optional[list[str]]:
        return _wrap_words(words, n, lambda t: text_width(t, s)) if len(words) >= n else None

    two, three = wrapped(2, size), wrapped(3, size)
    small = round(size * 0.85, 2)
    tries = [(size, [label]), (size, two)]
    for widen in (False, True):
        for s, lines in tries:
            if lines and (widen or max(text_width(t, s) for t in lines) <= width):
                yield s, lines, widen
    for s, lines in ((size, three), (small, wrapped(2, small)), (small, wrapped(3, small))):
        for widen in (False, True):
            if lines:
                yield s, lines, widen


NO_LINE_START = {"—", "–", "-", "/", ":", ";", "!", "?", "»", ")"}  # a separator ends a line, never starts one
WRAP_EXACT = 40  # beyond so many words (or ten times as many characters), lines of even width rather than every
#                 cut tried (that grows as words cubed)


def _wrap_words(words: list[str], n: int, width: Callable[[str], float]) -> list[str]:
    """``words`` (:func:`text_units`: words, CJK characters) on ``n`` lines, the widest line as narrow as possible."""
    if len(words) > WRAP_EXACT or sum(map(len, words)) > 10 * WRAP_EXACT:
        return _wrap_even(words, n, width)
    best: Optional[list[str]] = None
    for cuts in _cuts(len(words), n):
        if any(words[c].strip() in NO_LINE_START for c in cuts) and len(words) > n + 1:
            continue  # a dash or a slash ends the line before it, never starts the next one
        lines = ["".join(words[a:b]).strip() for a, b in zip((0,) + cuts, cuts + (len(words),))]
        if best is None or max(map(width, lines)) < max(map(width, best)):
            best = lines
    return best or ["".join(words).strip()]


def _wrap_even(words: list[str], n: int, width: Callable[[str], float]) -> list[str]:
    """``words`` on ``n`` lines of about the same width, in one pass (a text too long to try every cut)."""
    acc, total = [0.0], 0.0
    for u in words:
        total += width(u)
        acc.append(total)
    cuts: list[int] = []
    for k in range(1, n):
        lo = (cuts[-1] if cuts else 0) + 1
        c = next((i for i in range(lo, len(words) - (n - k) + 1) if acc[i] >= total * k / n), len(words) - (n - k))
        cuts.append(max(c, lo))
    bounds = [0, *cuts, len(words)]
    return ["".join(words[a:b]).strip() for a, b in zip(bounds, bounds[1:])]


def _cuts(m: int, n: int) -> Iterator[tuple[int, ...]]:
    if n == 1:
        yield ()
        return
    for i in range(1, m - n + 2):
        for rest in _cuts(m - i, n - 1):
            yield (i,) + tuple(i + r for r in rest)


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


def interlock_mark(x: float, y: float, horizontal: bool = True) -> Polyline:
    """Mechanical interlock (IEC 60617): a triangle pointing at the dashed link, at (x, y) on it (drawn, not a
    character: the PDF fonts have no triangle)."""
    if horizontal:
        return Polyline([(x - 0.6, y - 1.1), (x + 0.6, y - 1.1), (x, y)], Style(width=THIN), closed=True)
    return Polyline([(x + 1.1, y - 0.6), (x + 1.1, y + 0.6), (x, y)], Style(width=THIN), closed=True)


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


def _end(n: LNode, kind: str, fed: bool = False, toward: Optional[float] = None, taken: int = 0,
         near: Optional[float] = None) -> End:
    """Where a link attaches to a node: left side of the symbol, busbar end of a board (the end nearer
    ``near``, the x of the other end), output terminal of a feeder continued by a power link, input conductor
    of a node fed by an ``infeed`` link, or a tap on the busbar of a node feeding a power link toward ``toward``."""
    if toward is not None and kind in POWER_LINKS and n.bus_y is not None and n.children:
        return End(_bus_tap(n, toward, taken), n.bus_y, "down")
    if n.sym.height == 0 and n.bus_y is not None:
        if near is not None and near > n.bus_x1:
            return End(n.bus_x1, n.bus_y, "right")
        return End(n.bus_x0, n.bus_y)
    if fed:
        return End(n.x, n.y - 1.2)
    if kind in POWER_LINKS and not n.children and n.sym.has_output:
        return End(n.x, n.out_y + 0.7, "down")
    return End(n.x - n.sym.left - n.sym.extra.get("end_gap", 0.8), n.y + n.sym.extra.get("end_y", max(n.sym.height, 1) / 2))


def _right_end(n: LNode) -> Optional[End]:
    """The right side of a device, below its text (never through it), if the symbol is tall enough."""
    ab = n.ann_box()
    if "right_end" in n.sym.extra:  # a given point (multi-line: right end of the operating line of the poles)
        x, y = n.sym.extra["right_end"]
        return End(x, y, "right") if not ab or ab[3] + n.sym.extra.get("text_gap", 0.8) < y or ab[0] > x + 3.0 else None
    y = max(n.y + max(n.sym.height, 1) / 2, ab[3] + n.sym.extra.get("text_gap", 0.8) if ab else 0.0)
    return End(n.x + n.sym.right + n.sym.extra.get("end_gap", 0.8), y, "right") if y < n.y + n.sym.height - 0.4 else None


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
    """Nodes drawn below a parent (a conductor arrives on their input): an infeed lands on that conductor. A
    device feeding nothing (back-feed breaker of a PV inverter) is fed on its output terminal instead."""
    return {c.node.id for r in roots for n in r.walk() for c in n.children
            if c.kind == "node" and c.node is not None and n.kind in ("node", "bus_in")
            and (c.children or not c.sym.has_output)}


@dataclass
class AltBand:
    """Horizontal band under the busbars, one lane per normally-open alternative supply."""

    links: list[int]  # indexes in doc.links
    y0: float  # level of the (lowest) busbar the links leave
    top: float  # first lane, below y0
    pitch: float  # spacing of the lanes


@dataclass
class FeedTaps:
    """Taps on top of a busbar for the feeds landing on it (several of them: no input conductor of their own)."""

    land: dict[int, End]  # link index -> its tap
    lane: dict[int, float]  # link index -> the height of its channel (routed feeds)
    taken: dict[tuple[str, bool, bool], int]  # busbar side -> taps used there
    reach: dict[str, float]  # busbar id -> x of the outermost tap and its texts on the right (the frame encloses it)


STUB_DROP = 7.5 + 2.5  # an off-sheet stub leaving downwards: its arrow and the texts beside its tip


def _down_stubs(doc: Document, roots: list[LNode]) -> list[End]:
    """Where the off-sheet stubs leaving downwards start (see ``_draw_offpage_link``)."""
    out = []
    for link in doc.links:
        a, b = _find(roots, link.from_), _find(roots, link.to)
        if (a is None) != (b is None) and (e := _end(a or b, link.kind)).side == "down":  # type: ignore[arg-type]
            out.append(e)
    return out


def _feed_taps(doc: Document, roots: list[LNode], far: set[int], band: Optional[AltBand]) -> FeedTaps:
    """One tap each on top of the busbar, beyond its end on the side of their source: the interrupted lines
    (stubs, see ``_far_links``) innermost with room for their texts, then the routed feeds, the nearest innermost
    on the highest channel, so that no route crosses another."""
    nodes = {n.id: n for n, _, _ in iter_nodes(doc)}
    feeds: dict[str, list[int]] = {}
    for i, link in enumerate(doc.links):
        a, b = _find(roots, link.from_), _find(roots, link.to)
        if (link.kind == "infeed" and a is not None and b is not None and b.sym.height == 0 and b.bus_y is not None
                and b.children and not (band is not None and i in band.links)):
            feeds.setdefault(b.id, []).append(i)
    stubs = _down_stubs(doc, roots)
    ft = FeedTaps({}, {}, {}, {})
    for bid, ids in feeds.items():
        b = _find(roots, bid)
        if len(ids) < 2 or b is None or b.bus_y is None:
            continue
        src = {i: _find(roots, doc.links[i].from_) for i in ids}
        routed = [i for i in ids if i not in far]
        tops = [_end(n, doc.links[i].kind).y for i in routed if (n := src[i]) is not None]
        xs = [n.x for i in routed if (n := src[i]) is not None] + [b.bus_x0, b.bus_x1]
        for e in stubs:  # an off-sheet stub hanging down where the channels run: the channels below its texts
            if tops and min(xs) - 1.0 < e.x < max(xs) + 1.0 and e.y < b.bus_y:
                tops.append(e.y + STUB_DROP)
        y0, room = (max(tops) + 2.0, b.bus_y - 4.0 - (max(tops) + 2.0)) if tops else (0.0, -1.0)
        near = sorted(routed, key=lambda i: abs(src[i].x - b.x))  # type: ignore[union-attr]
        if len(near) == 1 and room >= 0:
            ft.lane[near[0]] = y0
        elif len(near) > 1 and room >= LANE * (len(near) - 1):
            for k, i in enumerate(near):
                ft.lane[i] = y0 + k * min(3.0, room / (len(near) - 1))
        room_out: dict[tuple[str, bool, bool], float] = {}
        for i in sorted(ids, key=lambda i: (i in routed, abs(src[i].x - b.x))):  # type: ignore[union-attr]
            toward = src[i].x  # type: ignore[union-attr]
            if b.bus_x0 < toward < b.bus_x1:  # a source above the busbar: the nearer end
                toward = b.bus_x1 if toward - b.bus_x0 > b.bus_x1 - toward else b.bus_x0
            side = (b.id, toward >= b.bus_x1, toward <= b.bus_x0)
            out = 1.0 if toward >= b.bus_x1 else -1.0 if toward <= b.bus_x0 else 0.0
            x = _bus_tap(b, toward, ft.taken.get(side, 0)) + out * room_out.get(side, 0.0)
            ft.taken[side] = ft.taken.get(side, 0) + 1
            ft.land[i] = End(x, b.bus_y, "up")
            texts = 0.0
            if i not in routed:  # the texts of the stub, written outward: the next tap beyond them
                link = doc.links[i]
                n = nodes.get(link.from_)
                on = (n.ref or n.label or link.from_) if n is not None else link.from_
                texts = max(text_width(t, 1.6) for t in [on] + ([link.label] if link.label else [])) + 1.0
                room_out[side] = room_out.get(side, 0.0) + texts
            if out > 0:
                ft.reach[b.id] = max(ft.reach.get(b.id, x), x + texts + 1.5)
    return ft


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
                band: Optional[AltBand] = None, only: Optional[set[int]] = None,
                sides: Optional[dict[int, tuple[str, str]]] = None,
                far: Optional[set[int]] = None, feed_taps: Optional[FeedTaps] = None) -> dict[int, tuple[str, str]]:
    """``only``: indexes of the links to draw (the multi-line view draws its power links itself). ``far``: links
    drawn as an interrupted line (a stub at each end naming the other end, see ``_far_links``). ``feed_taps``: the
    taps of the feeds landing on a busbar (see ``_feed_taps``).

    Multi-line (grid routing): returns the side by which each link leaves its two ends; given back as
    ``sides`` for a second drawing, the links sharing a side of a device get their points in the order of
    the devices they go to (no crossing at the device)."""
    chosen: dict[int, tuple[str, str]] = {}
    slots: dict[tuple[str, str], list[int]] = {}  # (node, side) -> links, in the order of their other ends
    if sides:
        pos = {n.id: (n.x, n.y + n.sym.height / 2) for r in roots for n in r.walk()}
        for i, (sa, sb) in sides.items():
            link = doc.links[i]
            for nid, side in ((link.from_, sa), (link.to, sb)):
                slots.setdefault((nid, side), []).append(i)
        for (nid, side), ids in slots.items():
            nx_, ny_ = pos.get(nid, (0.0, 0.0))

            def key(j: int, nid: str = nid, side: str = side, nx_: float = nx_, ny_: float = ny_) -> tuple:
                """No crossing at the device: the exit nearest the turn takes the inner lane (below a device:
                the targets on the left first, farthest outermost; beside it: the targets above first)."""
                other = doc.links[j].to if doc.links[j].from_ == nid else doc.links[j].from_
                x, y = pos.get(other, (0.0, 0.0))
                if side == "down":
                    return (0, x) if x < nx_ else (1, -x)
                d = abs(x - nx_)  # targets above: nearest on top; below: nearest at the bottom
                return (0, -round(y), d) if y < ny_ - 0.5 else (1, -round(y), -d)
            ids.sort(key=key)
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
    order = sorted((i for i in range(len(doc.links)) if only is None or i in only),
                   key=lambda i: (i in first, first.get(i, 0.0)))
    if obs.grid:  # the straight drop under every PLC port is kept for its own link
        for i in order:
            link = doc.links[i]
            for nid, port in ((link.from_, link.from_port), (link.to, link.to_port)):
                n = _find(roots, nid)
                slot = _port_slot(n, port) if n is not None else None
                if slot is not None:
                    j, count = lane_of.get(i, (0, 1))
                    room = (7.0 if slot == 0 else PLC_SLOT_W) - 1.2
                    gap = min(max(1.0, 0.9 * obs.min_lane), room / max(count - 1, 1))
                    px = n.x + n.sym.extra["ports"][slot] + (j - (count - 1) / 2) * gap
                    py = n.y + n.sym.extra.get("port_y", n.sym.height)
                    obs.add_vline(px, py, py + 3.0)
                    break
    nodes = {n.id: n for n, _, _ in iter_nodes(doc)}
    fed_ok = _fed_ok(roots)
    y_max = y_load - 1.5
    # power links leaving a busbar: one tap each, the busbar extended to the taps beyond its ends (drawn and
    # recorded before any route, so that no other link runs along the extension)
    # busbar side -> power links already tapped there
    taps: dict[tuple[str, bool, bool], int] = dict(feed_taps.taken) if feed_taps is not None else {}
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
            obs.add_hline(e.y, x0, x1, bus=True)
    # several feeds tapping one busbar (see _feed_taps, recorded in the obstacles already): the busbar extended
    bus_land, bus_lane = (feed_taps.land, feed_taps.lane) if feed_taps is not None else ({}, {})
    for i, e in bus_land.items():
        b = _find(roots, doc.links[i].to)
        if b is not None and b.bus_y is not None and not b.bus_x0 <= e.x <= b.bus_x1:
            x0, x1 = min(e.x, b.bus_x0), max(e.x, b.bus_x1)
            g.add(busbar_group(b.id, [Line((x0, b.bus_y), (x1, b.bus_y), Style(width=BUS))]))
    groups: dict[int, Group] = {}

    def group_of(i: int) -> Group:
        if i not in groups:
            groups[i] = link_group(doc, i)
        return groups[i]

    done = _draw_band(doc, band, roots, tap_end, group_of, obs, lang) if band is not None else set()
    labels: list[tuple[int, list[tuple[float, float]], str, float, str]] = []
    side_ends: dict[tuple[str, float, float], list[str]] = {}
    right_used: dict[str, int] = {}  # multi-line: links already leaving each node by its right side
    bottom_used: dict[str, int] = {}  # ... and by the bottom of a final device
    turns: dict[tuple[float, float], float] = {}  # ends turning down out of an operating line -> x of that line
    offpage: dict[str, float] = {}  # offset taken by the off-sheet stubs of each node
    landings: dict[str, list[int]] = {}  # infeeds landing on the input conductor of each node, in drawing order
    for i in order:
        if doc.links[i].kind == "infeed" and doc.links[i].to in fed_ok:
            landings.setdefault(doc.links[i].to, []).append(i)
    parent_of = {id(c): n for r in roots for n in r.walk() for c in n.children}
    spread = {} if obs.min_lane > 0 else _spread_ends(doc, roots, order)

    def landing(i: int, b: LNode, e: End) -> End:
        """Several feeds on one input conductor: one point each, up the conductor (``e``: the lowest)."""
        seq = landings.get(b.node.id if b.node is not None else "", [])
        if len(seq) < 2 or i not in seq:
            return e
        up = parent_of.get(id(b))
        top = (up.out_y if up.sym.has_output else up.y + up.sym.height) + 1.0 if up is not None else e.y - 12.0
        step = min(LANDING, max(e.y - top, 0.0) / (len(seq) - 1))
        return End(e.x, e.y - step * seq.index(i), e.side)
    # standby sources reaching side by side the side inputs of their transfer switches: one channel each, the
    # leftmost switch highest, so that the routes cross nothing (they all ran on one horizontal)
    side_runs: dict[int, tuple[float, float, float]] = {}  # link -> (y of the side input, x0, x1)
    for i, link in enumerate(doc.links):
        a, b = _find(roots, link.from_), _find(roots, link.to)
        if link.kind == "transfer" and a is not None and b is not None and b.sym.side_input is not None:
            sx = b.x + b.sym.side_input[0]
            side_runs[i] = (b.y + b.sym.side_input[1], min(a.x, sx), max(a.x, sx))
    side_level = {i: sum(1 for j, (y2, u0, u1) in side_runs.items() if j != i and abs(y2 - y) < 1.0
                         and u0 > x0 and u0 < x1 + 1e-6 and u1 > x0)
                  for i, (y, x0, x1) in side_runs.items()}
    # off-sheet stubs first: their arrows and sheet references are fixed, the routed links go round them
    first = [i for i in order if (_find(roots, doc.links[i].from_) is None) != (_find(roots, doc.links[i].to) is None)]
    # feeds tapping a busbar last, the outermost tap first: the inner ones then pass above it (no crossing)
    rest = sorted((i for i in order if i not in first), key=lambda i: (i in bus_land, not (far and i in far), -abs(
        bus_land[i].x - (_find(roots, doc.links[i].to) or roots[0]).x) if i in bus_land else 0.0))
    for i in first + rest:
        link = doc.links[i]
        a, b = _find(roots, link.from_), _find(roots, link.to)
        if (a is None and b is None) or i in done:
            continue
        lg = group_of(i)
        if a is None or b is None:
            n = a or b
            if link.kind == "tie" and n.bus_y is not None:  # a bus tie to another sheet: out of the busbar end
                other = link.to if b is None else link.from_
                at = End(n.bus_x1, n.bus_y, "right") if b is None else End(n.bus_x0, n.bus_y, "left")
                _draw_offpage_link(link, n, other, nodes.get(other), obs, lg, lang, node_folio, offpage, at)
            elif link.kind not in ("transfer", "tie"):
                other = link.to if b is None else link.from_
                at = spread.get((i, 0 if b is None else 1))  # a controller many links reach: its own point
                if b is not None and link.kind == "infeed" and link.to in fed_ok:  # on its input conductor
                    at = landing(i, b, _end(b, link.kind, fed=True))
                _draw_offpage_link(link, a or b, other, nodes.get(other), obs, lg, lang, node_folio, offpage, at)
            continue
        if far and i in far:
            at = bus_land.get(i) or (landing(i, b, _end(b, link.kind, fed=True))
                                     if link.kind == "infeed" and link.to in fed_ok else None)
            _draw_offpage_link(link, a, link.to, nodes.get(link.to), obs, lg, lang, None, offpage, same_sheet=True)
            _draw_offpage_link(link, b, link.from_, nodes.get(link.from_), obs, lg, lang, None, offpage, at,
                               same_sheet=True)
            continue
        style = _link_style(link.kind, link.normally_open)
        if link.kind == "transfer" and b.sym.side_input is not None:
            sx = b.x + b.sym.side_input[0]
            sy = b.y + b.sym.side_input[1]
            ay = a.out_y if a.sym.has_output else a.y + a.sym.height
            cy = sy - 2.5 - 1.5 * side_level.get(i, 0)
            lg.add(Polyline([(a.x, ay), (a.x, cy), (sx, cy), (sx, sy)], style))
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
        # an inverter/charger at the head of the tree takes its AC input on top: its side is the DC terminal
        fed = link.kind == "infeed" and (link.to in fed_ok or (b in roots and b.dc_side > 0))
        start = tap_end.get(i) or _end(a, link.kind)
        ends = [start, _end(b, link.kind, fed=fed, near=start.x)]
        if (link.kind == "measure" and obs.min_lane == 0 and b.sym.height == 0 and b.bus_y is not None
                and b.bus_x0 + 1.0 < start.x < b.bus_x1 - 1.0 and start.y < b.bus_y - 4.0):
            ends[1] = End(start.x, b.bus_y, "up")  # an instrument above a busbar: straight down onto it
        for k, (n, e) in enumerate(zip((a, b), ends)):  # links of different kinds on the side of a node:
            if e.side == "left":                         # one point per kind (a power feed, a data bus...)
                kinds = side_ends.setdefault((n.id, round(e.x, 2), round(e.y, 2)), [])
                if obs.min_lane > 0:  # multi-line: one point per link, spread over the side (see below)
                    if str(i) not in kinds:
                        kinds.append(str(i))
                    count = sum(1 for j in order if (doc.links[j].from_ == n.id and not doc.links[j].from_port)
                                or (doc.links[j].to == n.id and not doc.links[j].to_port))
                    step = min(max(1.5, obs.min_lane), max(n.sym.height - 1.0, 0.0) / max(count - 1, 1))
                    ends[k] = End(e.x, e.y + step * (kinds.index(str(i)) - (count - 1) / 2))
                    continue
                if link.kind not in kinds:
                    kinds.append(link.kind)
                shift = kinds.index(link.kind)
                if shift:
                    ends[k] = End(e.x, e.y + 1.5 * shift)
        if i in bus_land:
            ends[1] = bus_land[i]
        elif fed and link.to in fed_ok:
            ends[1] = landing(i, b, ends[1])
        port_label: Optional[tuple[int, str]] = None
        for k, (n, _nid, port) in enumerate(((a, link.from_, link.from_port), (b, link.to, link.to_port))):
            slot = _port_slot(n, port)
            if slot is None:
                continue
            j, count = lane_of.get(i, (0, 1))
            room = (7.0 if slot == 0 else PLC_SLOT_W) - 1.2
            gap = min(max(1.0, 0.9 * obs.min_lane), room / max(count - 1, 1))  # multi-line: drawn reduced
            px = n.x + n.sym.extra["ports"][slot] + (j - (count - 1) / 2) * gap
            ends[k] = End(px, n.y + n.sym.extra.get("port_y", n.sym.height), "down")
            port_label = (k, str(port))
            break
        lo = min(e.y for e in ends) - 30.0
        hi = max(max(e.y for e in ends) + 30.0, max(e.y for e in ends) + 2.0)
        if max(e.y for e in ends) < y_max:
            hi = min(hi, y_max)
        on_conductor = ends[1].y < b.y and link.to in fed_ok
        if on_conductor:  # infeed landing on an input conductor: never come back up from below the feeder
            hi = min(hi, max(e.y for e in ends) + 0.5)
        if i in bus_lane:
            lo, hi = bus_lane[i], bus_lane[i] + 0.01
        carries = link.device is not None and link.kind in SWITCHED_LINKS
        opts = {"record": not carries,
                "lane": max(3.5 if carries else LANE if link.kind in POWER_LINKS else SIGNAL_LANE, obs.min_lane),
                "solid": link.kind in POWER_LINKS and not style.dash}
        pts: list[tuple[float, float]] = []
        ml = obs.min_lane > 0  # multi-line: also beside a PLC port and for earth links, right ends spread
        if link.kind not in SWITCHED_LINKS and i not in tap_end and (
                ml or (link.kind != "earth" and port_label is None)):
            # a control, data or measure link leaves each device by the side that gives the clearest route
            alts = []
            for k, (n, e) in enumerate(zip((a, b), ends)):
                if (i, k) in spread:  # a controller many links reach: its own point, on the side facing the other end
                    alts.append([spread[(i, k)]])
                    continue
                if ml and link.kind == "earth" and "pe_end" in n.sym.extra:  # on the PE conductor of the feeder
                    alts.append([End(*n.sym.extra["pe_end"], "right")])
                    continue
                if ml and n.sym.name in ("earth", "earth_bar"):  # an earth electrode / bar: on its terminal, the
                    alts.append([End(n.x, n.y, s) for s in ("up", "left", "right")])  # conductor turning down
                    continue
                r = _right_end(n) if e.side == "left" and (port_label is None or port_label[0] != k) else None
                if r is not None and ml:  # the links already leaving by this side: one point each, below
                    count = sum(1 for j in order if n.id in (doc.links[j].from_, doc.links[j].to))
                    step = min(obs.min_lane, max(n.y + n.sym.height - 0.4 - r.y, 0.0) / count)
                    shift = step * right_used.get(n.id, 0)
                    if n.sym.extra.get("turn") and r is not None:  # out of the operating line, then straight
                        tx = r.x + 2.0 + right_used.get(n.id, 0) * obs.min_lane  # down: never its continuation
                        turns[(round(tx, 6), round(r.y, 6))] = r.x
                        r = End(tx, r.y, "down")
                    else:
                        r = End(r.x, r.y + shift, "right") if step >= 0.6 else None
                bottom = []
                if ml and n.sym.extra.get("free_below") and (port_label is None or port_label[0] != k):
                    count = sum(1 for j in order if n.id in (doc.links[j].from_, doc.links[j].to))
                    w = n.sym.left + n.sym.right
                    bottom = [End(n.x - n.sym.left + w * (bottom_used.get(n.id, 0) + 1) / (count + 1),
                                  n.y + n.sym.extra.get("bottom_y", n.sym.height) + 0.5, "down")]
                alts.append([e] + ([r] if r is not None else []) + bottom)
            if obs.grid and sides and i in sides:  # second drawing: each end on its side, in its slot
                for k, (n, side) in enumerate(zip((a, b), sides[i])):
                    pick = next((e for e in alts[k] if e.side == side), alts[k][0])
                    if n.sym.name in ("earth", "earth_bar"):  # one point, whatever the side
                        alts[k] = [pick]
                        continue
                    ids = slots.get((n.id, side), [i])
                    idx, count = ids.index(i) if i in ids else 0, len(ids)
                    h = max(n.sym.height, 1.0)
                    if side == "left" and count > 1 and (port_label is None or port_label[0] != k):
                        base = _end(n, link.kind)  # middle of the side (before any spreading)
                        top = n.y + n.sym.extra.get("body_top", 0.5)
                        step = min(obs.min_lane, (n.y + h - 0.5 - top) / (count - 1))
                        y = min(max(base.y + step * (idx - (count - 1) / 2), top), n.y + h - 0.5)
                        pick = End(base.x, y, "left")
                    elif side == "right":
                        top = _right_end(n)
                        if top is not None:
                            step = min(obs.min_lane, max(n.y + h - 0.4 - top.y, 0.0) / count)
                            pick = End(top.x, top.y + step * idx, "right")
                    elif side == "down" and pick in alts[k] and n.sym.extra.get("free_below"):
                        w = n.sym.left + n.sym.right
                        pick = End(n.x - n.sym.left + w * (idx + 1) / (count + 1), pick.y, "down")
                    alts[k] = [pick]
            if obs.grid:  # multi-line: the route and the ends it uses chosen together, any number of corners
                xs_ = [e.x for e in alts[0] + alts[1]]
                ys_ = [e.y for e in alts[0] + alts[1]]
                window = (min(xs_) - 25.0, min(ys_) - 25.0, max(xs_) + 25.0, max(ys_) + 25.0)
                pts, ka, kb = route_grid(obs, alts[0], alts[1], window, opts["lane"], record=not carries)
                ends = [alts[0][ka], alts[1][kb]]
                chosen[i] = (ends[0].side, ends[1].side)
                for k, e in enumerate(ends):  # an end turning out of an operating line: its first stretch
                    ox = turns.get((round(e.x, 6), round(e.y, 6)))
                    if ox is not None and pts:
                        pts = [(ox, e.y)] + pts if k == 0 else pts + [(ox, e.y)]
                for n, e in zip((a, b), ends):
                    if e.side == "right" or (round(e.x, 6), round(e.y, 6)) in turns:
                        right_used[n.id] = right_used.get(n.id, 0) + 1
                    elif e.side == "down":
                        bottom_used[n.id] = bottom_used.get(n.id, 0) + 1
            elif len(alts[0]) > 1 or len(alts[1]) > 1:
                scored = []
                for ea in alts[0]:
                    for eb in alts[1]:
                        c: list[float] = []
                        top = max(ea.y, eb.y)
                        route(obs, ea, eb, min(ea.y, eb.y) - 30.0, min(top + 30.0, y_max) if top < y_max else top + 30.0,
                              step=1.0, record=False, lane=opts["lane"], cost_out=c)  # coarse: only to compare
                        scored.append((c[0], [ea, eb]))
                ends = min(scored, key=lambda t: t[0])[1]
                for n, e in zip((a, b), ends):
                    if e.side == "right":
                        right_used[n.id] = right_used.get(n.id, 0) + 1
                    elif e.side == "down" and ml:
                        bottom_used[n.id] = bottom_used.get(n.id, 0) + 1
                lo = min(e.y for e in ends) - 30.0
                hi = max(e.y for e in ends) + 30.0
                if max(e.y for e in ends) < y_max:
                    hi = min(hi, y_max)
            else:  # one end each (a controller's own point)
                ends = [alts[0][0], alts[1][0]]
        if (not ml and a.bottom and b.bottom and link.label and port_label is None
                and abs(ends[0].x - ends[1].x) < text_width(link.label, 1.6) + 2.0):
            # two loads too close for the label between them: under the loads, where the label has room
            lo = max(lo, max(a.y + a.sym.height, b.y + b.sym.height) + 1.5)
            hi = max(hi, lo + 0.01)
        if not obs.grid or not pts:
            pts = route(obs, ends[0], ends[1], lo, hi, **opts)
        if not pts and on_conductor:  # e.g. a feeder leaving downwards: the channel must go below it after all
            pts = route(obs, ends[0], ends[1], lo, max(e.y for e in ends) + 30.0, **opts)
        if not pts:  # no free channel: leave this link out rather than fail the whole drawing
            continue
        if carries:
            _draw_link_device(link, link.device, pts, style, lg, obs, lang)
        else:
            lg.add(Polyline(pts, style))
            if ml and link.kind == "interlock":  # a mechanical interlock (IEC 60617): a triangle on its link,
                segs = sorted(zip(pts, pts[1:]), key=lambda s: (abs(s[0][1] - s[1][1]) > 1e-6,  # not a linkage
                                                                -abs(s[0][0] - s[1][0]) - abs(s[0][1] - s[1][1])))
                (p, q) = segs[0]
                mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
                lg.add(interlock_mark(mx, my, abs(p[1] - q[1]) < 1e-6))
        if on_conductor:  # infeed landing on the input conductor: junction dot
            lg.add(Circle(pts[-1], 0.45, Style(width=THIN, fill="#000000")))
        seq = pts if port_label is None or port_label[0] == 0 else pts[::-1]  # oriented PLC -> other end
        if i in bus_land and len(pts) > 2:  # on its channel, not on the short drop crowded with the other taps
            seq = pts[:-1]
        if port_label is not None:
            labels.append((i, seq, port_label[1], 1.3, "#1565c0"))
        text = link.label  # a data link without a label: its protocol, unless a device text already gives it
        if not text and link.kind == "data" and link.protocol \
                and not any(link.protocol in t for t in (a.ann or []) + (b.ann or [])):
            text = link.protocol
        if text and link.device is None:  # a carried device is annotated: the label would repeat it
            labels.append((i, seq, text, 1.6, "#000000"))
    # labels once every route is known, near the far end of their link (port labels: near the controlled device),
    # unless more links meet there than at the near end: near the near end then (a controller many links reach)
    degree = Counter(e for l in doc.links for e in (l.from_, l.to))
    for i, seq, txt, size, color in labels:
        units = text_units(txt)
        far_end = color != "#000000" or degree[doc.links[i].to] <= degree[doc.links[i].from_]
        if color == "#000000":
            # a clear place on one line near the preferred end, else near the other end, else on two lines (a short
            # link), near either end
            two = _wrap_words(units, 2, lambda u, sz=size: text_width(u, sz)) if len(units) > 1 else []
            tries = [(fe, lines) for lines in ([txt], two) if lines for fe in (far_end, not far_end)]
            placed = False
            for fe, lines in tries:
                w = max(text_width(u, size) for u in lines)
                h = size if len(lines) == 1 else 2.2 * size
                at = place_label(obs, seq, w, h, from_end=fe, optional=True)
                if at is None:
                    continue
                if len(lines) == 1:
                    group_of(i).add(Text((at[0], at[1]), txt, size, at[2], color=color))
                else:  # the box of the two lines: baselines 1.2 size apart
                    for k, u in enumerate(lines):
                        group_of(i).add(Text((at[0], at[1] - 0.96 * size + 1.2 * size * k), u, size, at[2],
                                             color=color))
                placed = True
                break
            if placed:
                continue
            if not obs.label_channel:  # single-line: in the nearest free space, a leader to its link
                if _leader_label(obs, seq, txt, size, group_of(i)):
                    continue
        # multi-line: a link label with no free place along its route is left out (the single-line has it)
        at = place_label(obs, seq, text_width(txt, size), size, from_end=far_end,
                         optional=obs.label_channel and color == "#000000")
        if at is not None:
            group_of(i).add(Text((at[0], at[1]), txt, size, at[2], color=color))
    for i in sorted(groups):
        if groups[i].items:
            g.add(finish_link_group(groups[i]))
    return chosen


LEADER_REACH = 25.0  # how far from its link a label may go, joined to it by a leader


def _leader_label(obs: Obstacles, pts: list[tuple[float, float]], txt: str, size: float, g: Group) -> bool:
    """A link label with no clear place along its route (a short link between neighbours): in the nearest free
    space, a thin leader from the middle of the link's longest stretch to the label. False if none is near."""
    p, q = max(zip(pts, pts[1:]), key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    w, h = text_width(txt, size), size * 1.1
    x, y = place_box(obs, w, h, (mx - w / 2, my + 2.0), step=0.5, reach=LEADER_REACH, pad=0.6)
    if abs(x + w / 2 - mx) > LEADER_REACH + w / 2 or abs(y - my) > LEADER_REACH:
        return False
    box = (x, y, x + w, y + h)
    tx, ty = min(max(mx, box[0]), box[2]), min(max(my, box[1]), box[3])  # the point of the label nearest the link
    g.add(Line((mx, my), (tx, ty), Style(width=THIN)))
    g.add(Text((x, y + 0.85 * size), txt, size))
    obs.add_box(box)
    return True


def _spread_ends(doc: Document, roots: list[LNode], order: list[int]) -> dict[tuple[int, int], End]:
    """Single-line: the links reaching a controller from many sides, one end each on its sides (see
    ``_spread_symbol``): on the right for the other ends to its right, if there is room under its text, else on the
    left; on each side in the order of the other ends from top to bottom (no crossing at the controller)."""
    out: dict[tuple[int, int], End] = {}
    for r in roots:
        for n in r.walk():
            ids = [i for i in _signal_links(doc, n.node.id if n.node is not None else None) if i in order]
            if n.sym.name != "controller" or len(ids) < SPREAD_FROM:
                continue
            top, bottom = n.y + 2.5 + 0.75, n.y + n.sym.height - 2.5 - 0.75  # the box, 1 M below and above its leads
            ab = n.ann_box()
            right_top = max(top, ab[3] + 0.8) if ab else top
            sides: dict[str, list[tuple[float, int, int]]] = {"left": [], "right": []}
            off: list[tuple[int, int]] = []
            for i in ids:
                link = doc.links[i]
                k = 0 if link.from_ == n.node.id else 1  # type: ignore[union-attr]
                o = _find(roots, link.to if k == 0 else link.from_)
                if o is None:  # to another sheet: an off-page stub on the left, below the others
                    off.append((i, k))
                    continue
                oy = o.y + o.sym.height / 2
                sides["right" if o.x > n.x + n.sym.right else "left"].append((oy, i, k))
            if off:  # the stubs take the bottom of the left side
                bottom_left = bottom - SPREAD_OFF * (len(off) - 1) - 1.0
                x = n.x - n.sym.left - 0.8
                for j, (i, k) in enumerate(off):
                    out[(i, k)] = End(x, bottom_left + 0.5 + SPREAD_OFF * j, "left")
            room = int((bottom - right_top) / SPREAD_STEP) + 1
            if len(sides["right"]) > room:  # no room under the text: the farthest down go round by the left
                sides["right"].sort()
                sides["left"] += sides["right"][:len(sides["right"]) - room]
                sides["right"] = sides["right"][len(sides["right"]) - room:]
            for side, items in sides.items():
                items.sort()
                y0 = right_top if side == "right" else top
                y1 = bottom if side == "right" or not off else bottom_left - SPREAD_STEP
                step = min(SPREAD_STEP, max(y1 - y0, 0.0) / max(len(items) - 1, 1))
                x = n.x + n.sym.right + 0.8 if side == "right" else n.x - n.sym.left - 0.8
                for j, (_oy, i, k) in enumerate(items):
                    out[(i, k)] = End(x, y0 + step * j, side)
    return out


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
                       lang: str, node_folio: Callable[[str], Optional[int]] | None,
                       taken: Optional[dict[str, float]] = None, at: Optional[End] = None,
                       same_sheet: bool = False) -> None:
    """Link whose other end is drawn on another sheet: short stub ending on an off-page arrow + sheet reference.
    ``taken``: offset already used by the stubs drawn on each node; the next one is drawn beside them.
    ``at``: where the stub starts when the caller has chosen it (a feed landing on an input conductor).
    ``same_sheet``: interrupted line on this sheet, the stub names the other end only (and stays in ``g``, the
    group of the link, so that both ends are one link for the editor)."""
    f = node_folio(other) if node_folio is not None and not same_sheet else None
    if f is None and not same_sheet:
        return
    on = target_node.ref or target_node.label or other if target_node is not None else other
    txts = ([link.label] if link.label else []) + [on + (_t("render.to_folio", lang, folio=f) if f else "")]
    e = at or _end(n, link.kind)
    key = n.id or ""
    if at is None and e.side == "left":  # no room on the left for its texts (a neighbour there): by the right side
        need = max(text_width(t, 1.6) for t in txts) + 9.0
        r = _right_end(n)
        d = taken.get(key, 0.0) if taken is not None else 0.0
        if r is not None and not obs.box_free((e.x - need, e.y + d - 2.0, e.x, e.y + d + 2.0), 0.3) \
                and obs.box_free((r.x, r.y - 2.0, r.x + need, r.y + 2.0), 0.3):
            e, key = r, key + ">"
    if taken is not None and at is None:  # its labels on both sides of a horizontal stub, beside a vertical one
        d = taken.get(key, 0.0)
        taken[key] = d + (max(text_width(t, 1.6) for t in txts) + 1.5 if e.side == "down" else 5.0)
        e = End(e.x + d, e.y, e.side) if e.side == "down" else End(e.x, e.y + d, e.side)
    if e.side == "down":
        pts = [(e.x, e.y), (e.x, e.y + 6.0)]
        tip = (e.x, e.y + 7.5)
        head = [(e.x - 0.8, e.y + 6.0), tip, (e.x + 0.8, e.y + 6.0)]
    elif e.side == "up":  # a tap on top of a busbar
        pts = [(e.x, e.y), (e.x, e.y - 6.0)]
        tip = (e.x, e.y - 7.5)
        head = [(e.x - 0.8, e.y - 6.0), tip, (e.x + 0.8, e.y - 6.0)]
    elif e.side == "right":  # out of the right end of a busbar
        pts = [(e.x, e.y), (e.x + 6.0, e.y)]
        tip = (e.x + 7.5, e.y)
        head = [(e.x + 6.0, e.y - 0.8), tip, (e.x + 6.0, e.y + 0.8)]
    else:
        pts = [(e.x, e.y), (e.x - 6.0, e.y)]
        tip = (e.x - 7.5, e.y)
        head = [(e.x - 6.0, e.y - 0.8), tip, (e.x - 6.0, e.y + 0.8)]
    g.add(Polyline(pts, _link_style(link.kind, link.normally_open)))
    rg = Group([Polyline(head, Style(width=THIN, fill="#ffffff"), closed=True)]) if same_sheet else \
        ref_group(f, other, [Polyline(head, Style(width=THIN, fill="#ffffff"), closed=True)])
    if e.side in ("down", "up"):
        obs.add_vline(e.x, min(e.y, tip[1]), max(e.y, tip[1]))
    else:
        obs.add_hline(pts[1][1], pts[0][0], pts[1][0])
    for txt in txts:
        w = text_width(txt, 1.6)
        x, y, anchor = place_label(obs, [pts[0], tip], w, 1.6, from_end=True, record=False)
        b = text_box(x, y, w, 1.6, anchor)
        if e.side == "left" and anchor == "end" and x > tip[0] - 0.6 and b[1] < e.y + 0.8 and e.y - 0.8 < b[3]:
            moved = text_box(tip[0] - 0.6, y, w, 1.6, anchor)  # running onto the point of its arrow: ends before it
            if obs.box_free(moved, 0.1, wire_pad=0.0):
                x, b = tip[0] - 0.6, moved
        obs.add_box(b)
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
    # walk up to the first busbar node (excluded); a board with a single outgoing (a panel fed through, an
    # enclosure around one load) is crossed: the feeder's protection and cable are above it
    path = []
    for n in chain:
        if n is not leaf and (len(n.children) >= 2 or n.type == "busbar"):  # type: ignore[attr-defined]
            break
        path.append(n)
    prots = [n for n in path if n.type in PROTECTIVE]  # type: ignore[attr-defined]
    rated = [n for n in prots if n.type != "motor_starter" and protection_short(n)]  # type: ignore[attr-defined]
    # the overcurrent protection of the feeder (breaker, fuse) rather than an RCD or switch below it
    rated.sort(key=lambda n: n.type not in OVERCURRENT)  # type: ignore[attr-defined]
    info["prot"] = (rated or prots or [None])[0]
    if leaf.type == "spare" and (info["prot"] is None or leaf.ref or protection_short(leaf)  # type: ignore[attr-defined]
                                 or getattr(leaf, "poles", None)):
        info["prot"] = leaf  # pre-equipped spare way: its own rating and poles, else the device feeding it
    elif info["prot"] is None and len(path) < len(chain) and leaf.type not in ("spd", "insulation_monitor"):  # type: ignore[attr-defined]
        up = chain[len(path)]
        info["own_ref"] = next((n.ref for n in path if n.ref), None)  # the column keeps its own tag
        if up.type in OVERCURRENT and protection_short(up):  # type: ignore[attr-defined]
            info["prot"] = up  # way of a small sub-busbar: protected by the breaker or fuse feeding it
        elif getattr(up, "kind", None) == "busway":
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
            board = next((b for b in chain[1:] if b.type == "board"), None)  # type: ignore[attr-defined]  # not the leaf
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
    for i in infos:
        i["rcd_type_column"] = "rcd_type" in (view.cartouche or [])
    # the same tag in two boards of one table: prefixed with the board's ("=PDU-A-Q1", "TD2 -Q1")
    def board_of(i: dict[str, Any]) -> Optional[NodeBase]:
        leaf = i.get("leaf")
        return next((a for a in index.ancestors(leaf.id) if a.type == "board"), None) \
            if leaf is not None and leaf.id else None  # type: ignore[attr-defined]
    refs = [cell("ref", i, lang) for i in infos]
    boards = [board_of(i) for i in infos]
    for i, r, board in zip(infos, refs, boards):
        others = {id(b) for b, r2 in zip(boards, refs) if r2 == r}
        if r and len(others) > 1 and board is not None and (board.ref or board.label):
            b = board.ref or board.label or ""
            i["own_ref"] = f"{b}{r}" if b[0] in "=+" else f"{b} {r}"
    # column boundaries: a column widened by a long board name keeps the extra room on its right, as in the drawing
    xs = [c.x for c in columns]
    bounds = [xs[0] - pitch / 2]
    for a, b in zip(xs, xs[1:]):
        bounds.append(max((a + b) / 2, b - pitch / 2))
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
        if field_ == "cable" and any(cable_in_awg(i["cable"]) for i in infos):
            title = titles["cable_awg"]  # North-American sizes: no "(mm²)" unit in the header
        tg.add(Rect(x_start, y, header_w, h, small))
        tg.add(Text((x_start + 1.2, y + h / 2), title, 1.9, "start", "middle", bold=True))
        for i, v in enumerate(values):
            cx0, cx1 = bounds[i], bounds[i + 1]
            cg = Group([Rect(cx0, y, cx1 - cx0, h, small)], attrs={"data-uw-field": field_})
            # the text stays under its feeder: centred on the column, as wide as the cell allows on both sides
            half = min(xs[i] - cx0, cx1 - xs[i])
            cx0, cx1 = xs[i] - half, xs[i] + half
            if field_ == "label" and columns[i].kind == "stub":  # "-> sheet n": reference to the board's sheet
                cg = ref_group(columns[i].target_folio, columns[i].target, cg.items)
                cg.attrs["data-uw-field"] = field_
            cols[i].add(cg)
            if not v:
                continue
            wide = sum(1 for ch in v if unicodedata.east_asian_width(ch) in "WF")
            if field_ == "label" and wide * 2 >= len(v.replace(" ", "")):  # CJK: upright, one character under another
                chars = [ch for ch in v if not ch.isspace()]
                size = max(1.2, min(2.0, (h - 2.0) / (len(chars) * 1.05)))
                fit = int((h - 2.0) / (size * 1.05))
                if len(chars) > fit:
                    chars = chars[:max(1, fit - 1)] + ["…"]
                for k, ch in enumerate(chars):
                    cg.add(Text(((cx0 + cx1) / 2, y + 1.0 + (k + 0.85) * size * 1.05), ch, size, "middle"))
            elif field_ == "label":
                size, room = 2.0, h - 2
                lines = [v]
                if text_width(v, size) > room:  # too long for the cell: on 2 or 3 lines side by side, then smaller
                    words = text_units(v)
                    across = int((cx1 - cx0 - 1.0) // (size * 1.2))
                    for k in range(2, min(3, across, len(words)) + 1):
                        lines = _wrap_words(words, k, lambda u, sz=size: text_width(u, sz))
                        if max(text_width(u, size) for u in lines) <= room:
                            break
                widest = max(text_width(u, size) for u in lines)
                if widest > room:
                    size = max(1.3, size * room / widest)
                step = size * 1.2
                for i, line in enumerate(lines):
                    line = cut_to_width(line, size, room, keep=4)
                    x = (cx0 + cx1) / 2 + 0.7 + (i - (len(lines) - 1) / 2) * step
                    cg.add(Text((x, y + h - 1.0), line, size, "start", "alphabetic", 90))
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
        return ref_label(n.ref, n.label) or (n.id or "")

    def process(spec: SheetSpec, allow_bus_split: bool = True) -> list[SheetSpec]:
        root_ids = {r.id for r in spec.roots}
        spec.detached |= {f for f in forced if f not in root_ids and _in_spec(spec, f, index)}
        conts: list[SheetSpec] = []
        groups: list[list[NodeBase]] = []
        for _ in range(50):
            spec.moved = {s.id for nid in spec.detached for s in standby(nid) if s.id and s in spec.roots}
            lay = layout_sheet(doc, view, spec, index)
            if view.folio_split == "none" or fit_scale(lay, view) >= view.min_scale:
                break
            if allow_bus_split and not groups and spec.continuation is None:
                # several installations side by side: each whole on a sheet, before taking boards out of them
                groups = _split_trees(doc, spec, lay, view, index)
                if groups:
                    spec.roots = groups.pop(0)
                    root_ids = {r.id for r in spec.roots}
                    continue
            boards = [n for n in lay.lnodes if n.is_board and n.node is not None and n.node.id not in root_ids
                      and n.node.id not in spec.detached and n.width >= 3 * view.pitch_mm]
            drawn = {n.node.id for n in lay.lnodes if n.is_board and n.node is not None}
            nested = {n.node.id for n in boards if any(a.id in drawn for a in index.ancestors(n.node.id))}  # type: ignore[union-attr]
            board = _board_to_detach(boards, lay, view, keep_whole=allow_bus_split, nested=nested)
            if board is not None:
                spec.detached.add(board.node.id)  # type: ignore[union-attr]
                continue
            if allow_bus_split:
                conts = _split_bus(spec, lay, view, index, normalize_lang(doc.meta.lang))
            break
        out = [spec]
        for c in conts:
            out += process(c, allow_bus_split=False)
        for nid in _ordered(spec, index):
            out += process(SheetSpec([index.nodes[nid]] + standby(nid), name=name_of(index.nodes[nid])))
        for roots in groups:
            board = next((n for r in roots for n in _walk_nodes(r) if n.type == "board"), roots[0])  # type: ignore[attr-defined]
            out += process(SheetSpec(roots, name=name_of(board)))
        return out

    def standby(nid: str) -> list[NodeBase]:
        """Sources linked by a 'transfer' to a switch inside board ``nid``: drawn on that board's sheet."""
        inside = {l.from_ for l in doc.links if l.kind == "transfer" and l.to in index.nodes
                  and (l.to == nid or any(a.id == nid for a in index.ancestors(l.to)))}
        return [s for s in doc.sources if s.id not in (None, nid) and any(
            f == s.id or any(a.id == s.id for a in index.ancestors(f)) for f in inside if f in index.nodes)]

    first = SheetSpec(_sheet_roots(doc, view, index), name="")
    return process(first)


def _board_to_detach(boards: list[LNode], lay: SheetLayout, view: View, keep_whole: bool = False,
                     nested: frozenset[str] | set[str] = frozenset()) -> Optional[LNode]:
    """The board to draw on its own sheet: among those that are not nearly the whole sheet, the narrowest whose
    departure makes the sheet fit, otherwise the widest (the rest of the tree keeps its upstream boards: not a sheet
    holding only an incomer). A board that is nearly the whole sheet (the main board) stays with its supply when
    ``keep_whole``: its busbar is continued on the next sheets instead; ``None`` then. A board below another one on
    the sheet (``nested``: their ids) is not kept so: however wide, it goes, and the board feeding it keeps its ways
    together rather than being cut way by way."""
    _, _, aw, _ = drawing_area(view)
    excess = lay.width - aw / view.min_scale
    part = [n for n in boards if n.width < 0.85 * lay.width]
    enough = [n for n in part if n.width - view.pitch_mm >= excess]
    if enough:
        return min(enough, key=lambda n: n.width)
    if part:
        return max(part, key=lambda n: n.width)
    below = [n for n in boards if n.node is not None and n.node.id in nested]
    if below:
        return max(below, key=lambda n: n.width)
    return None if keep_whole or not boards else max(boards, key=lambda n: n.width)


def _walk_nodes(n: NodeBase) -> Iterator[NodeBase]:
    yield n
    for c in n.children:
        yield from _walk_nodes(c)


def _split_trees(doc: Document, spec: SheetSpec, lay: SheetLayout, view: View, index: Index) -> list[list[NodeBase]]:
    """Trees of a sheet too wide for it, in their drawing order, cut into groups that each fit (a tree wider than a
    sheet alone on its own): the fewest sheets, then the fewest links between them (a link cut is drawn as an
    off-page reference at both ends). Empty: nothing to cut."""
    by_id = {id(r.node): r for r in lay.lnodes if r.node is not None and any(r.node is s for s in spec.roots)}
    trees = sorted((r for r in by_id.values()), key=lambda r: r.x_left)
    if len(trees) < 2:
        return []
    _, _, aw, _ = drawing_area(view)
    cap = aw / view.min_scale - 30.0
    pos = {n.id: k for k, r in enumerate(trees) for n in _walk_nodes(r.node) if n.id}  # type: ignore[arg-type]
    spans = [(pos[l.from_], pos[l.to], 100 if l.kind in ("tie", "transfer") else 1) for l in doc.links
             if l.from_ in pos and l.to in pos and pos[l.from_] != pos[l.to]]

    def cut(k: int) -> int:  # links between trees [0, k) and [k, n), a bus tie or a transfer weighing most
        return sum(w for a, b, w in spans if min(a, b) < k <= max(a, b))

    n = len(trees)
    # (sheets, links cut, widest sheet, previous cut)
    best: list[tuple[int, int, float, int]] = [(0, 0, 0.0, -1)] + [(10 ** 9, 0, 0.0, -1)] * n
    for j in range(1, n + 1):
        for i in range(j):
            width = trees[j - 1].x_left + trees[j - 1].width - trees[i].x_left
            if width > cap and j - i > 1:
                continue
            s, c, w, _ = best[i]
            cand = (s + 1, c + (cut(i) if i else 0), max(w, width), i)
            if cand[:3] < best[j][:3]:
                best[j] = cand
    if best[n][0] < 2:
        return []
    cuts, j = [], n
    while j > 0:
        cuts.append(j)
        j = best[j][3]
    bounds = [0] + sorted(cuts)
    return [[trees[k].node for k in range(a, b)] for a, b in zip(bounds, bounds[1:])]  # type: ignore[misc]


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
                      name=_t("render.continuation_name", lang, name=_bus_name(node, index)), prev=prev)
        prev.next = c
        out.append(c)
        prev = c
    return out
