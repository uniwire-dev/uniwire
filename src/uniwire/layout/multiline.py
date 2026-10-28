"""Multi-line power diagram (one line per conductor), generated from the single-line tree.

The document needs no extra data: the conductors of every node are derived from what the single-line
description already says, in this order of precedence:

1. the ``phase`` of a single-phase circuit (``L2`` taps phase L2; without ``phase``, L1 is used);
2. the ``poles`` of a switching / protective device (``1P``, ``1P+N``, ``2P``, ``3P``, ``3P+N``, ``4P``)
   and of a socket;
3. the cable composition (``3G`` = L + N + PE, ``4G`` = 3 L + PE, ``5G`` = 3 L + N + PE; ``x`` compositions
   count the protective conductor too when the count is odd, ``pen`` marks a PEN conductor);
4. the number of phases of a motor, the ``system`` of a board or busbar, the usual connection of a load type
   (sockets, lighting, appliances are single-phase);
5. otherwise the conductors arriving from upstream.

The supply conductors come from ``installation.system`` / ``grid.system`` and the earthing system: TN-C and
TN-C-S carry a PEN conductor (split into PE + N at the board flagged ``pen_split``, by default the first board
in TN-C-S), TN-S carries a PE from the source, TT and IT get their PE at the first board (main earthing
terminal). Transformers start a new low-voltage system (neutral from the vector group, ``Dyn11`` -> N),
inverters, DC/DC converters and power supplies feed a DC pair (``L+``, ``L-``).

Layout: the tree is laid out like the single-line diagram (power flowing down, one column per outgoing
feeder, loads aligned on a common baseline), each column being a bundle of parallel conductors spaced
:data:`S` apart. A node with several children (or an explicit busbar) gets one horizontal rail per
conductor. Large documents are split into sheets like the single-line diagram (sub-boards on their own sheet,
then busbars cut into continuation sheets).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from .. import registry
from ..i18n import normalize_lang, render_lang
from ..i18n import t as _t
from ..labels import annotation, cable_text, part_number
from ..marks import marked_wires, marks_shown
from ..model import Document, NodeBase, View
from ..render.scene import (
    NORMAL,
    THICK,
    THIN,
    Circle,
    Ellipse,
    Group,
    Item,
    Line,
    Polyline,
    Rect,
    Style,
    Text,
    arc_points,
    bbox,
    text_width,
    transform,
)
from ..render.semantics import (
    add_cls,
    busbar_group,
    cond_group,
    edge_group,
    finish_link_group,
    link_group,
    node_group,
    ref_group,
)
from ..resolve import Index, build_index, iter_nodes
from ..symbols import ABBREVIATIONS, M, Symbol, symbol_for
from ..symbols import grid as grid_symbol
from ..units import fmt
from .engine import DC_PORT_TYPES, LNode, SheetLayout, SheetSpec, _is_dc, drawing_area, interlock_mark, sheet_node_ids
from .routing import FRAME_CROSS, Box, Obstacles, boxes_union

S = 3.0  # spacing of the conductors of a bundle (mm)
PAD = 3.0  # first conductor of a column, from the column's left edge
GAP = 4.0  # vertical gap between two devices in series
RAIL_GAP = 3.5  # between a device and the first rail below it
CHILD_GAP = 4.5  # between the last rail and the outgoing feeders
RAIL_IN = 6.0  # horizontal room between the incoming conductors and the first outgoing feeder
COL_GAP = 2.5
BOARD_TOP = 7.0  # room for the board name
FRAME_ROOM = 2.5  # right of a board's content: its frame, then a gap before the next frame
SPLIT_H = 6.0  # room for a PEN split / a conductor starting in a board
DC_JOG = 4.5  # under an inverter/charger: room for its DC pair turning toward the DC side
CABLE_BAND = 9.0  # room above the loads for the feeder cable
DEV_H = 12.5  # height of a contact (5 modules)
ANN_SIZE = 1.8
ANN_LINE = 2.2
ANN_MAX_W = 34.0
LOAD_TEXT = 1.8

PHASES = ("L1", "L2", "L3")
DC = ("L+", "L-")
ORDER = {c: i for i, c in enumerate(("L1", "L2", "L3", "L+", "L-", "N", "PEN", "PE"))}
LIVE = set(PHASES) | set(DC) | {"N"}

DASH = Style(width=THIN, dash=(1.0, 0.7))
DOT_R = 0.45

CONTACT_TYPES = {"breaker", "disconnector", "switch_disconnector", "contactor", "impulse_relay", "rcd", "rcbo",
                 "main_breaker", "fuse", "fuse_switch", "transfer_switch", "spare", "thermal_relay"}
SOURCE_TYPES = {"grid", "generator", "transformer", "offpage", "ups", "pv_array", "battery", "inverter"}
CONVERTERS = {"inverter", "dc_converter", "power_supply"}
SINGLE_PHASE_LOADS = {"socket", "lighting", "shutter", "appliance", "ventilation"}
BOTTOM_TYPES = {"pv_array", "battery", "offpage"}
POLES = {"1P": (1, None), "1P+N": (1, True), "2P": (1, True), "3P": (3, None), "3P+N": (3, True), "4P": (3, True)}
SOCKET_POLES = {"2P": (1, True), "2P+T": (1, True), "3P": (3, False), "3P+T": (3, False), "3P+N": (3, True),
                "3P+N+T": (3, True)}
SYSTEMS = {"1P+N": (1, True), "2P": (2, False), "3P": (3, False), "3P+N": (3, True), "split-phase": (2, True)}
_CORES = re.compile(r"^\s*(\d+)\s*([GgXx×])\s*$")
_VECTOR = re.compile(r"^(YN|ZN|Y|D|Z)(yn|zn|y|d|z)")


def _sorted(conds: list[str]) -> list[str]:
    return sorted(dict.fromkeys(conds), key=lambda c: ORDER.get(c, 99))


def _dc_side(node: Any) -> list[Any]:
    """Children on the DC side of an inverter/charger or UPS that also feeds an AC side (none otherwise)."""
    if node.type not in DC_PORT_TYPES:
        return []
    dc = [c for c in node.children if _is_dc(c)]
    return dc if len(dc) < len(node.children) else []


# ------------------------------------------------------------- conductors
@dataclass
class Conductors:
    """Conductors of a node: at its input, at its output, and where each input conductor comes from in the
    parent's output (``None``: the conductor starts here, e.g. a PE at the main earthing terminal)."""

    inp: list[str]
    out: list[str]
    src: dict[str, Optional[str]]


class _Assigner:
    def __init__(self, doc: Document, show_pe: bool = True):
        self.doc = doc
        self.show_pe = show_pe
        self.info: dict[int, Conductors] = {}
        self._needs: dict[int, bool] = {}
        nodes = [n for n, _, _ in iter_nodes(doc)]
        flagged = [n for n in nodes if getattr(n, "pen_split", None)]
        if flagged:
            self.split = {id(n) for n in flagged}
        elif doc.installation.earthing == "TN-C-S":
            self.split = {id(b) for b in _first_boards(doc)}
        else:
            self.split = set()
        # North American split-phase (120/240 V): a "2P" breaker switches L1 and L2, a 3-wire cable is L1 L2 G
        self.split_phase = doc.installation.system == "split-phase" or any(
            getattr(n, "system", None) == "split-phase" for n in nodes)
        for src in doc.sources:
            self._walk(src, None, False)

    # -- explicit description of a node: (phase names, number of phases, neutral)
    def spec(self, node: Any, type_default: bool = True) -> tuple[Optional[list[str]], Optional[int], Optional[bool]]:
        """``type_default``: fall back on the usual connection of the load type (single-phase sockets...)."""
        t = node.type
        names = None
        ks: list[Optional[int]] = []
        ns: list[Optional[bool]] = []
        ph = getattr(node, "phase", None)
        if ph:
            names = re.findall(r"L[123]", ph)
            ns.append(True if len(names) == 1 else False if len(names) == 2 else None)
        poles = getattr(node, "poles", None)
        if t == "socket" and poles in SOCKET_POLES:
            k, n = SOCKET_POLES[poles]
            ks.append(k)
            ns.append(n)
        elif poles == "2P" and self.split_phase:
            ks.append(2)
            ns.append(None)
        elif poles in POLES:
            k, n = POLES[poles]
            ks.append(k)
            ns.append(n)
        cable = getattr(node, "cable", None)
        if cable is not None and cable.cores and t not in ("board", "busbar", "transformer"):
            m = _CORES.match(cable.cores)
            if m:
                total = int(m[1])
                live = total - 1 if (m[2] in "Gg" or (total % 2 == 1 and not cable.pen)) else total
                k, n = ({2: (2, False), 3: (2, True)} if self.split_phase else
                        {2: (1, True), 3: (3, False), 4: (3, True)}).get(live, (None, None))
                ks.append(k)
                ns.append(n)
        if t == "motor":
            phases = getattr(node, "phases", None)
            if phases == 1 and self.split_phase:  # 240 V on L1 L2 (no neutral), or 120 V on a phase and N
                ks.append(None)
                ns.append(False)
            else:
                ks.append(1 if phases == 1 else 3)
                ns.append(True if phases == 1 else False)
        system = getattr(node, "system", None)
        if t in ("board", "busbar") and system in SYSTEMS:
            k, n = SYSTEMS[system]
            ks.append(k)
            ns.append(n)
        if t in SINGLE_PHASE_LOADS and type_default:
            ks.append(1)
            ns.append(True)
        k = next((x for x in ks if x is not None), None)
        neutral = next((x for x in ns if x is not None), None)
        return names, k, neutral

    def needs_n(self, node: Any) -> bool:
        key = id(node)
        if key not in self._needs:
            names, k, neutral = self.spec(node)
            if neutral is not None:
                r = neutral
            elif (names and len(names) == 1) or k == 1:
                r = True
            elif not node.children:
                r = True
            else:
                r = any(self.needs_n(c) for c in node.children)
            self._needs[key] = r
        return self._needs[key]

    def _preferred_phase(self, node: Any) -> Optional[str]:
        n = node
        while n is not None:
            ph = getattr(n, "phase", None)
            if ph:
                return re.findall(r"L[123]", ph)[0] if re.findall(r"L[123]", ph) else None
            n = n.children[0] if len(n.children) == 1 else None
        return None

    def select(self, node: Any, parent: list[str], parent_node: Any = None) -> list[str]:
        t = node.type
        if t == "earth_bar" and getattr(node, "kind", None) == "neutral_bar":
            return [c for c in parent if c in ("N", "PEN")][-1:] or parent[-1:]
        if t in ("earth", "earth_bar"):  # an earth electrode or bar is on the protective conductor only
            pe = [c for c in parent if c in ("PE", "PEN")]
            return pe[-1:] or parent[-1:]
        if any(c in DC for c in parent):
            return [c for c in parent if c in DC or c == "PE"]
        avail = [c for c in parent if c in PHASES]
        nname = "N" if "N" in parent else "PEN" if "PEN" in parent else None
        # a load alone behind its own (three-phase) device takes what the device delivers
        alone = parent_node is not None and len(parent_node.children) == 1 and parent_node.type not in ("board", "busbar")
        names, k, neutral = self.spec(node, type_default=not alone)
        if names:
            phases: list[str] = []
            for nm in names:
                if nm in avail and nm not in phases:
                    phases.append(nm)
                else:
                    alt = next((a for a in avail if a not in phases), None)
                    if alt:
                        phases.append(alt)
            phases = phases or avail[:1]
        elif k is not None and k < len(avail):
            if k == 1:
                pref = self._preferred_phase(node)
                phases = [pref if pref in avail else avail[0]]
            else:
                phases = avail[:k]
        else:
            phases = list(avail)
        if len(phases) == 1:
            if nname is None:  # no neutral: phase-to-phase single-phase circuit
                phases = avail[:2] if len(avail) >= 2 else phases
                neutral = False
            else:
                neutral = True
        if neutral is None:
            neutral = self.needs_n(node)
        out = list(phases)
        if nname == "N" and neutral:
            out.append("N")
        if nname == "PEN" and (neutral or self.show_pe):
            out.append("PEN")
        if "PE" in parent:
            out.append("PE")
        return _sorted(out) or parent[:1]

    def lv(self, system: Optional[str], earthing: Optional[str]) -> tuple[list[str], bool]:
        """Conductors of a low-voltage supply, and whether the PE is still to be added (TT, IT)."""
        system = system or "3P+N"
        if system == "DC":
            return list(DC), False
        k, n = SYSTEMS.get(system, (3, True))
        conds = list(PHASES[:k]) + (["N"] if n else [])
        pending = False
        if earthing in ("TN-C", "TN-C-S"):
            conds = [c for c in conds if c != "N"] + ["PEN"]
        elif earthing in ("TT", "IT"):
            pending = self.show_pe
        elif self.show_pe:
            conds.append("PE")
        return conds, pending

    def _downstream_earthing(self, node: Any) -> Optional[str]:
        stack = list(node.children)
        while stack:
            n = stack.pop(0)
            if getattr(n, "earthing", None):
                return n.earthing
            if n.type == "transformer":
                continue
            stack.extend(n.children)
        return self.doc.installation.earthing

    def _transformer_out(self, node: Any, inp: Optional[list[str]] = None) -> tuple[list[str], bool]:
        u2 = getattr(node, "u2_V", None)
        if u2 is not None and u2 > 1000:
            return list(PHASES), False
        if inp is not None and len([c for c in inp if c in PHASES]) == 1:  # single-phase transformer
            if u2 is not None and u2 <= 50:  # safety extra-low voltage: two conductors, never earthed
                return ["L1", "N"], False
            return self.lv("1P+N", self._downstream_earthing(node))
        m = _VECTOR.match(getattr(node, "coupling", None) or "")
        neutral = m is None or m[2].endswith("n")
        system = next((getattr(n, "system", None) for n in node.children if getattr(n, "system", None)), None)
        if system is None:
            system = "3P+N" if neutral else "3P"
        return self.lv(system, self._downstream_earthing(node))

    def _is_mv(self, node: Any) -> bool:
        if (getattr(node, "un_V", None) or 0) > 1000:
            return True
        stack = list(node.children)
        while stack:
            n = stack.pop(0)
            if n.type == "transformer":
                return True
            if n.type in ("board", "busbar"):
                return False
            stack.extend(n.children)
        return False

    def _source(self, node: Any) -> tuple[list[str], list[str], bool]:
        t = node.type
        inst = self.doc.installation
        if t in ("pv_array", "battery"):
            return list(DC), list(DC), False
        if t == "transformer":
            out, pending = self._transformer_out(node)
            return list(PHASES), out, pending
        if t == "grid" and self._is_mv(node):
            return list(PHASES), list(PHASES), False
        earthing = inst.earthing
        if t == "generator" and earthing == "TN-C-S":  # the PEN is the utility's: a genset has its N and PE
            earthing = "TN-S"
        conds, pending = self.lv(getattr(node, "system", None) or inst.system, earthing)
        return conds, conds, pending

    def _walk(self, node: Any, parent: Optional[list[str]], pending: bool, parent_node: Any = None) -> None:
        t = node.type
        if parent is None:
            inp, out, pending = self._source(node)
            src: dict[str, Optional[str]] = {c: None for c in inp}
        else:
            inp = self.select(node, parent, parent_node)
            src = {c: (c if c in parent else "PEN" if c in ("N", "PE") and "PEN" in parent else None) for c in inp}
            out = list(inp)
            if t == "transformer":
                out, pending = self._transformer_out(node, inp)
            elif t in CONVERTERS and not any(c in DC for c in inp) and not _dc_side(node):
                out = list(DC)
            elif _vfd_to_three_phase(node, inp):  # a drive fed in single phase makes the motor's three phases
                out = list(PHASES) + (["PE"] if "PE" in inp else [])
        # the PEN splits into N and PE where asked, or at the entry of a board declared TN-S / TN-C-S
        if "PEN" in inp and (id(node) in self.split or (t in ("board", "busbar") and
                                                         getattr(node, "earthing", None) in ("TN-S", "TN-C-S"))):
            inp = _sorted([c for c in inp if c != "PEN"] + ["N"] + (["PE"] if self.show_pe else []))
            src = {c: src.get(c, "PEN") if c not in ("N", "PE") else "PEN" for c in inp}
            out = list(inp)
        pe_cable = node.cable is not None and node.cable.pe_section_mm2  # cable with its own protective conductor
        # TT, IT: the PE starts at the main earthing terminal, in the first board (never upstream of it, even in a
        # cable that carries a protective conductor); without a board downstream, at the device or load
        here = t in ("board", "busbar") or (not _board_below(node) and (len(node.children) != 1 or pe_cable))
        if pending and parent is not None and here and "PE" not in inp and not any(c in DC for c in inp):
            inp = _sorted(inp + ["PE"])
            src["PE"] = None
            out = _sorted(out + ["PE"]) if t not in CONVERTERS | {"transformer"} else out
            pending = False
        dc_side = _dc_side(node) if not any(c in DC for c in inp) else []
        if dc_side:  # AC side on the outputs, plus a DC pair for the batteries, PV...
            out = list(inp)
            self.info[id(node)] = Conductors(inp, _sorted(out + list(DC)), src)
        else:
            self.info[id(node)] = Conductors(inp, out, src)
        for c in node.children:
            if any(c is d for d in dc_side):
                self._walk(c, list(DC), False, node)
            else:
                self._walk(c, out, pending, node)


def _vfd_to_three_phase(node: Any, inp: list[str]) -> bool:
    return (node.type == "motor_starter" and getattr(node, "method", None) == "vfd"
            and len([c for c in inp if c in PHASES]) < 3
            and any(c.type == "motor" and getattr(c, "phases", None) == 3 for c in node.children))


def _board_below(node: Any) -> bool:
    """A board downstream: the main earthing terminal of a TT / IT installation is in a board."""
    stack = list(node.children)
    while stack:
        n = stack.pop()
        if n.type == "board":
            return True
        stack.extend(n.children)
    return False


def _first_boards(doc: Document) -> list[NodeBase]:
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


def conductors(doc: Document, show_pe: bool = True) -> dict[str, Conductors]:
    """Conductors of every node of the power tree, by node id (see the module docstring)."""
    a = _Assigner(doc, show_pe)
    return {n.id: a.info[id(n)] for n, _, _ in iter_nodes(doc) if n.id and id(n) in a.info}


def switched(node: Any, conds: list[str]) -> tuple[list[str], list[str]]:
    """Poles of a switching device: (protected / switched conductors, unprotected neutral pole).

    ``1P`` / ``3P``: the phases only (the neutral, if any, goes straight through); ``1P+N`` / ``3P+N``: the
    phases plus a neutral pole without protection; ``2P`` / ``4P``: identical poles on every live conductor
    (a ``2P`` on two phases, split-phase 240 V: those two, the neutral straight through).
    A PEN conductor is never switched."""
    phases = [c for c in conds if c in PHASES or c in DC]
    has_n = "N" in conds
    poles = getattr(node, "poles", None)
    t = node.type
    if poles == "2P" and len([c for c in phases if c in PHASES]) == 2 and t != "rcd":
        return phases, []  # split-phase 2P: L1 and L2 (240 V), the neutral goes straight through
    if t in ("rcd",) or poles in ("2P", "4P") or (poles is None and t != "fuse"):
        return phases + (["N"] if has_n else []), []
    if poles in ("1P+N", "3P+N") and has_n:
        return phases, ["N"]
    return phases, []


# ---------------------------------------------------------------- layout tree
@dataclass
class MLNode:
    node: Optional[NodeBase]
    kind: str  # 'node' | 'stub' (detached board) | 'bus_in' (continuation of a busbar)
    inp: list[str]
    out: list[str]
    src: dict[str, Optional[str]]
    children: list[MLNode] = field(default_factory=list)
    label: str = ""
    target: Optional[str] = None
    bus_out: bool = False
    root: bool = False
    # computed
    off_in: dict[str, float] = field(default_factory=dict)
    off_out: dict[str, float] = field(default_factory=dict)
    h: float = 0.0
    ann: list[str] = field(default_factory=list)
    ann_size: float = ANN_SIZE
    tagged: bool = False
    load_lines: list[str] = field(default_factory=list)
    cable_lines: list[str] = field(default_factory=list)
    width: float = 0.0
    x_left: float = 0.0
    y: float = 0.0
    frame_top: float = 0.0
    rail_y0: Optional[float] = None
    # power links outside the tree (see _plan_links)
    lead: float = 0.0  # room left of the column for the conductors of a link landing on it
    head: float = 0.0  # room between the incoming conductors and the first feeder, for link taps
    tail: float = 0.0  # room after the last feeder, for link taps
    extra_taps: dict[str, list[float]] = field(default_factory=dict)  # link taps on the rails, per conductor
    dc_side: int = 0  # last children: the DC side of an inverter/charger, fed from its DC pair, not the AC outputs
    dc_at: float = 0.0  # where the columns of the DC side start, from the column's left edge
    pad_bottom: float = 0.0  # room at the bottom of a board frame for the signal links of its devices
    link_gap: float = 0.0  # room between the poles and the text, for the control links of the operating line
    below: float = 0.0  # room under a final device for the landings of a power link (inside its board frame)

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
    def bus_children(self) -> list[MLNode]:
        """The children fed by the outputs (all of them, except the DC side of an inverter/charger)."""
        return self.children[:len(self.children) - self.dc_side]

    @property
    def dc_children(self) -> list[MLNode]:
        return self.children[len(self.children) - self.dc_side:]

    def on_dc_side(self, child: MLNode) -> bool:
        return any(child is c for c in self.dc_children)

    @property
    def rails(self) -> bool:
        return self.kind == "bus_in" or len(self.bus_children) >= 2 or self.bus_out or \
            (self.type == "busbar" and bool(self.children))

    @property
    def bottom(self) -> bool:
        """Drawn on the common baseline of the loads."""
        if self.kind == "stub":
            return True
        equipped = self.type == "spare" and (getattr(self.node, "in_A", None) or getattr(self.node, "poles", None))
        return self.kind == "node" and not self.children and not self.root and not equipped and \
            (registry.is_load(self.type) or self.type in BOTTOM_TYPES)  # an equipped spare way: its (grey) device

    def xi(self, c: str) -> float:
        return self.x_left + self.off_in[c]

    def xo(self, c: str) -> float:
        return self.x_left + self.off_out[c]

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def lanes_max(self) -> float:
        return max(list(self.off_in.values()) + list(self.off_out.values()) + [PAD])

    def lanes_min(self) -> float:
        return min(list(self.off_in.values()) + list(self.off_out.values()) + [PAD])

    def right(self) -> float:
        """Right edge of the symbol, relative to the column's left edge."""
        r = self.lanes_max()
        live = [o for c, o in self.off_in.items() if c != "PE"] or [PAD]
        if self.type in ("transformer", "generator") or (self.type == "motor" and self.bottom):
            cx, rad = _circle(self)
            r = max(r, cx + rad)
            if self.type == "transformer" and "PE" in self.off_in:  # the PE beside it, or its earth symbol
                r = max(r, cx + rad + (1.0 if "PE" in self.out else 3.5))
        elif self.type in CONTACT_TYPES and self.type in ("rcd", "rcbo", "main_breaker"):
            r = max(r, max(live) + 2.2)
        elif self.type == "plc":  # the single-line PLC symbol: head on the supply, then its modules
            r = max(r, _plc_axis(self) + symbol_for(self.node).right)
        elif self.type not in CONTACT_TYPES:  # boxes drawn across the conductors
            r += 1.5
        sets = _starter_sets(self.node) if self.type == "motor_starter" else 0
        if sets:  # the other contactors of a reversing or star-delta starter, right of all its conductors
            phases = [o for c, o in self.off_in.items() if c in PHASES] or [PAD]
            r = max(r, self.lanes_max() + sets * ((len(phases) - 1) * S + STARTER_GAP))
        return r + 0.8 + self.link_gap

    def block_h(self) -> float:
        return max(self.h, len(self.ann) * ANN_LINE * self.ann_size / ANN_SIZE + 0.6 if self.ann else 0.0)

    def rails_bottom(self) -> float:
        assert self.rail_y0 is not None
        return self.rail_y0 + (len(self.out) - 1) * S

    def content_bottom(self) -> float:
        b = max(self.y + self.block_h(), self.y + self.h + self.below)
        if self.rail_y0 is not None:
            b = max(b, self.rails_bottom())
        return b


def _circle(ln: MLNode) -> tuple[float, float]:
    """Centre (relative x) and radius of a machine / transformer drawn across its conductors."""
    if ln.type == "transformer":
        offs = [o for c, o in ln.off_out.items() if c != "PE"] + [o for c, o in ln.off_in.items() if c != "PE"]
    else:
        offs = [o for c, o in ln.off_in.items() if c != "PE"]
    offs = offs or [PAD]
    lo, hi = min(offs), max(offs)
    return (lo + hi) / 2, max((hi - lo) / 2 + 2.2, 4.5)


# ------------------------------------------------------------ construction
def _plc_axis(ln: MLNode) -> float:
    """x of the head of a PLC (relative to the column's left edge): the middle of its supply conductors."""
    xs = [o for c, o in ln.off_in.items() if c != "PE"] or [PAD]
    return (min(xs) + max(xs)) / 2


PLC_TOP = 1.5  # supply conductors above the body of a PLC


def _plc_origin(ln: MLNode) -> tuple[float, float]:
    """Origin of the single-line PLC symbol drawn on ``ln``: its head on the supply conductors, its body
    ``PLC_TOP`` below the top of the node (the symbol's own lead, 0.8 M long, is replaced by the conductors)."""
    return ln.x_left + _plc_axis(ln), ln.y + PLC_TOP - 0.8 * M


def _build(node: NodeBase, spec: SheetSpec, info: dict[int, Conductors], is_root: bool) -> MLNode:
    c = info[id(node)]
    if not is_root and node.id in spec.detached:
        label = node.ref or node.label or node.id or ""
        fed = [x for x in c.inp if c.src.get(x) is not None]  # a PE starting in the board is drawn on its sheet
        return MLNode(node, "stub", fed, fed, {x: c.src[x] for x in fed}, label=label, target=node.id)
    children = list(node.children)
    bus_out = False
    if spec.bus_slice and spec.bus_slice[0] == node.id:
        _, s, e = spec.bus_slice
        bus_out = e < len(children)
        children = children[s:e]
    dc = [ch for ch in children if any(ch is d for d in _dc_side(node))]
    children = [ch for ch in children if not any(ch is d for d in dc)] + dc
    return MLNode(node, "node", list(c.inp), list(c.out), dict(c.src),
                  [_build(ch, spec, info, False) for ch in children], bus_out=bus_out, root=is_root, dc_side=len(dc))


def _build_roots(spec: SheetSpec, index: Index, info: dict[int, Conductors]) -> list[MLNode]:
    if spec.continuation:
        nid, s, e = spec.continuation
        parent = index.nodes[nid]
        out = list(info[id(parent)].out)
        root = MLNode(None, "bus_in", out, out, {c: None for c in out},
                      [_build(ch, spec, info, False) for ch in parent.children[s:e]],
                      label=parent.ref or parent.label or nid, target=nid, bus_out=e < len(parent.children), root=True)
        return [root]
    roots = [_build(r, spec, info, True) for r in spec.roots]
    for r in roots:
        r.root = True
    return roots


def _height(ln: MLNode) -> float:
    t = ln.type
    if _is_busway(ln) and not ln.children:
        return 9.0  # trunk box of a busbar trunking ending the feeder
    if ln.kind == "bus_in" or t in ("board", "busbar"):
        return 0.0
    if ln.kind == "stub":
        return 6.0
    if ln.bottom:
        if t == "motor":
            _, r = _circle(ln)
            return 3.0 + 2 * r
        return 4.0 + 9.0
    if t in ("rcd", "rcbo") or (t == "main_breaker" and getattr(ln.node, "idn_mA", None)):
        return 17.5
    if t == "fuse_switch":
        return 20.0
    if t in CONTACT_TYPES or (t == "motor_starter" and _starter_contacts(ln.node)):
        return DEV_H
    if t == "transformer":
        _, r = _circle(ln)
        return 4.0 + 3.5 * r
    if t == "generator":
        _, r = _circle(ln)
        return 4.0 + 2 * r
    if t == "grid":
        return 17.0
    if t == "spd":
        return 11.0
    if t == "earth":
        return 6.0
    if t == "earth_bar":
        return symbol_for(ln.node).height
    if ln.root and t in SOURCE_TYPES:
        return 11.0
    return 11.0


def _is_busway(ln: MLNode) -> bool:
    return ln.type == "busbar" and getattr(ln.node, "kind", None) == "busway"


def _starter_contacts(node: Any) -> bool:
    return (getattr(node, "method", None) or "dol") not in ("vfd", "soft_starter")


STARTER_GAP = 4.0  # between two contactors of a starter


def _starter_sets(node: Any) -> int:
    """Contactors of a starter beside its line contactor: 1 for reversing, 2 for star-delta (delta and star)."""
    return {"reversing": 1, "star_delta": 2}.get(getattr(node, "method", None) or "", 0)


def _starter_extra(node: Any, xs: list[float], y: float, h: float, last: float = 0.0) -> list[Item]:
    """The other contactors of a reversing or star-delta starter, right of the line contactor whose poles are at
    ``xs``: a reverse contactor fed from the lines and returning with L1 and L3 swapped, mechanically interlocked;
    or a delta contactor (lines to the motor's W2 U2 V2) and a star contactor shorting W2 U2 V2."""
    method = getattr(node, "method", None)
    xs = sorted(xs)
    n = len(xs)
    items: list[Item] = []
    dot = lambda x, yy: Circle((x, yy), 0.35, Style(width=THIN, fill="#000000"))  # noqa: E731
    yt, ht = y + 1.8, h - 3.4  # the extra poles: shorter, room above for the taps, below for the returns
    x0 = max(xs[-1], last) + STARTER_GAP  # right of every conductor of the column (the PE too)
    first = [x0 + i * S for i in range(n)]
    for i, (xl, xr) in enumerate(zip(xs, first)):  # taps on the lines, above the contacts
        ty = y + 0.4 + i * 0.55
        items += [Line((xl, ty), (xr, ty)), Line((xr, ty), (xr, yt)), dot(xl, ty)]
        items += _contact(xr, yt, "arc", ht)
    items += _link(first, yt)
    bottom = yt + ht
    if method == "reversing":
        for i, xr in enumerate(first):  # back onto the lines, phases reversed (L1 <-> L3)
            by = bottom + 0.4 + i * 0.4
            xl = xs[n - 1 - i]
            items += [Line((xr, bottom), (xr, by)), Line((xr, by), (xl, by)), dot(xl, by)]
        lm = _blade_mid(xs[-1], y)
        rm = _blade_mid(first[0], yt)
        # level with the line contactor's linkage, down between the last conductor (PE) and the reverse contactor
        mx = (x0 - STARTER_GAP + first[0]) / 2
        items += [Polyline([(lm[0] + 0.4, lm[1]), (mx, lm[1]), (mx, rm[1]), (rm[0] - 0.4, rm[1])], DASH),
                  interlock_mark((lm[0] + x0 - STARTER_GAP) / 2, lm[1])]
        return items
    # star-delta: delta contactor outputs to W2 U2 V2, star contactor shorting them
    x1 = first[-1] + STARTER_GAP
    star = [x1 + i * S for i in range(n)]
    names = ["W2", "U2", "V2"][:n]
    for i, (xd, xy) in enumerate(zip(first, star)):  # W2 U2 V2 under the delta contactor, to the star contactor
        jy = bottom + 0.6 + i * 0.5
        items += [Line((xd, bottom), (xd, y + h + 1.5)), Text((xd, y + h + 3.4), names[i], 1.3, "middle"),
                  Line((xd, jy), (xy, jy)), dot(xd, jy), Line((xy, bottom), (xy, jy))]
        items += _contact(xy, yt, "arc", ht)
    items += _link(star, yt)
    items += [Line((star[0], yt), (star[-1], yt))]  # the star point, joining the tops of the star contactor
    # the delta and star contactors never close together: mechanically interlocked (the triangle between them)
    dm, sm = _blade_mid(first[-1], yt), _blade_mid(star[0], yt)
    items += [Line((dm[0] + 0.4, dm[1]), (sm[0] - 1.0, sm[1]), DASH), interlock_mark((dm[0] + sm[0] - 0.6) / 2, dm[1])]
    return items


def _abbr(key: str) -> str:
    table = ABBREVIATIONS.get(render_lang(), ABBREVIATIONS["en"])
    return table.get(key) or ABBREVIATIONS["en"].get(key, "")


def _fit_lines(lines: list[str], size: float, avail: float) -> tuple[list[str], float]:
    widest = max((text_width(t, size) for t in lines), default=0.0)
    if widest > avail:
        size = max(1.4, size * avail / widest)
    out = []
    for t in lines:
        while len(t) > 3 and text_width(t, size) > avail:
            t = t[:-2] + "…"
        out.append(t)
    return out, size


def _feeder_cable(ln: MLNode, parent: dict[int, MLNode]) -> Optional[MLNode]:
    """Node carrying the cable of the feeder ending on load ``ln`` (the load or the devices just above it)."""
    n: Optional[MLNode] = ln
    while n is not None and n.kind == "node":
        if n.node is not None and n.node.cable is not None and cable_text(n.node.cable):
            return n
        p = parent.get(id(n))
        if p is None or p.rails or p.is_board or p.type == "busbar":
            return None
        if {c for c in p.inp if c in LIVE} != {c for c in p.out if c in LIVE}:  # a drive or converter between
            return None
        n = p
    return None


def _annotate(roots: list[MLNode], view: View, lang: str) -> None:
    parent = {id(c): n for r in roots for n in r.walk() for c in n.children}
    shown_cable: set[int] = set()
    for r in roots:
        for ln in r.walk():
            if not ln.bottom or ln.node is None:
                continue
            node = ln.node
            if ln.kind == "stub":
                continue
            name = node.label or registry.label(ln.type, lang)
            if ln.type == "offpage":
                name = " ".join(x for x in (node.ref, node.label) if x) or name
                ln.load_lines = [name] + ([f"→ {node.target}"] if getattr(node, "target", None) else [])
                continue
            power = fmt(node.p_kW, " kW") if node.p_kW else ""
            if power and power in name:
                power = ""
            details = [x for x in (node.ref, power,
                                   _t("cell.points", lang, count=node.points) if getattr(node, "points", None) else "")
                       if x]
            ln.load_lines = [name] + ([" ".join(details)] if details else [])
            holder = _feeder_cable(ln, parent)
            if holder is not None and holder.node is not None and holder.node.cable is not None:
                cab = holder.node.cable
                ln.cable_lines = [x for x in (" ".join(x for x in (cab.ref, cab.designation) if x), cable_text(cab)) if x]
                if cab.length_m:
                    ln.cable_lines[-1] += f" {fmt(cab.length_m)} m"
                shown_cable.add(id(holder))
    for r in roots:
        for ln in r.walk():
            ln.ann = []
            if ln.kind != "node" or ln.node is None or ln.bottom or ln.is_board or not view.annotations:
                continue
            node = ln.node
            feeds_bus = any(len(d.children) >= 2 for d in ln.walk())
            lines = [x for x in annotation(node, lang, show_label=feeds_bus) if x]
            if ln.type == "spare":  # a spare way: what it is kept for, its rating
                in_a = getattr(node, "in_A", None)
                lines = [x for x in (node.label or registry.label("spare", lang), fmt(in_a, " A") if in_a else "",
                                     getattr(node, "poles", None) or "") if x]
            pn = part_number(node)
            tag = pn if view.tag_field == "part_number" and pn else node.ref
            if tag:
                lines.insert(0, tag)
            ln.tagged = bool(tag)
            lines = lines[:5]
            if node.cable is not None and id(ln) not in shown_cable and cable_text(node.cable):
                lines.append(" ".join(x for x in (node.cable.ref, node.cable.designation, cable_text(node.cable)) if x))
            ln.ann, ln.ann_size = _fit_lines(lines, ANN_SIZE, ANN_MAX_W)


def _assign_offsets(ln: MLNode, parent: Optional[MLNode]) -> None:
    if parent is None or parent.rails or parent.on_dc_side(ln):
        ln.off_in = {c: PAD + i * S for i, c in enumerate(ln.inp)}
    else:
        ln.off_in = {}
        used: set[str] = set()
        top = parent.lanes_max()
        for c in ln.inp:
            s = ln.src.get(c)
            if s is not None and s in parent.off_out and s not in used:
                ln.off_in[c] = parent.off_out[s]
                used.add(s)
        for c in ln.inp:
            if c not in ln.off_in:
                top = max([top] + list(ln.off_in.values())) + S
                ln.off_in[c] = top
    if not set(ln.out) & set(ln.off_in):
        ln.off_out = {c: PAD + i * S for i, c in enumerate(ln.out)}
    elif ln.type == "transformer":  # new windings: the outputs in their own order, the PE last
        ln.off_out = {c: PAD + i * S for i, c in enumerate(ln.out)}
    elif ln.node is not None and _vfd_to_three_phase(ln.node, ln.inp):  # U V W from under the drive, the PE beside
        a = min(o for c, o in ln.off_in.items() if c != "PE")
        ln.off_out = {c: a + i * S for i, c in enumerate(ln.out)}
    else:
        ln.off_out = {}
        top = max(ln.off_in.values()) if ln.off_in else PAD - S
        for c in ln.out:
            if c in ln.off_in:
                ln.off_out[c] = ln.off_in[c]
            else:
                top += S
                ln.off_out[c] = top
    for ch in ln.children:
        _assign_offsets(ch, ln)


def _measure(ln: MLNode) -> float:
    for c in ln.children:
        _measure(c)
    own = ln.right() + COL_GAP
    if ln.ann:
        own = ln.right() + 1.0 + max(text_width(t, ln.ann_size) for t in ln.ann) + COL_GAP
    if ln.bottom:
        own = max(own, ln.lanes_max() + 2.5 + len(ln.load_lines) * 2.4 + COL_GAP)
        if ln.cable_lines:
            own = max(own, ln.lanes_max() + 1.5 + max(text_width(t, 1.6) for t in ln.cable_lines) + COL_GAP)
    if ln.is_board and ln.node is not None:
        own = max(own, ln.lanes_max() + 1.1 * text_width(_board_name(ln.node), 2.4) + 6.0)
    if ln.kind == "bus_in":
        own = max(own, text_width(_t("render.continued_from", label=ln.label, folio=99), 1.8) + 4.0)
    if ln.rails:
        start = ln.lanes_max() + RAIL_IN + ln.head
        extra = 0.0
        if ln.tail and ln.bus_children:  # link taps right of the last feeder's conductors, in its annotation room
            last = ln.bus_children[-1]
            extra = max(0.0, ln.tail - (last.width - last.lanes_max() - 3.0))
        ln.width = max(own, start + sum(c.width for c in ln.bus_children) + 4.0 + extra)
    elif ln.children:
        ln.width = max(own, ln.children[0].width)
    else:
        ln.width = max(own, 14.0)
    if ln.dc_side:  # the DC side in columns of its own, right of the AC side
        ln.dc_at = ln.width
        ln.width += sum(c.width for c in ln.dc_children)
    if ln.is_board:  # room for the frame between the symbols and the next column
        ln.width += FRAME_ROOM
    ln.width += ln.lead
    return ln.width


def _board_name(node: Any) -> str:
    return " ".join(x for x in (node.ref, node.label) if x) or (node.id or "")


def _place_x(ln: MLNode, x_left: float) -> None:
    ln.x_left = x_left
    if ln.rails:
        cx = x_left + ln.lanes_max() + RAIL_IN + ln.head
        for c in ln.bus_children:
            _place_x(c, cx + c.lead)
            cx += c.width
    else:
        for c in ln.bus_children:
            _place_x(c, x_left)
    cx = x_left + ln.dc_at
    for c in ln.dc_children:
        _place_x(c, cx + c.lead)
        cx += c.width


def _needs_split_room(ln: MLNode, parent: Optional[MLNode]) -> bool:
    if parent is not None and parent.on_dc_side(ln):
        return False
    if parent is None or parent.rails:
        return any(s is None for s in ln.src.values()) and not (ln.root and ln.type in SOURCE_TYPES)
    for c in ln.inp:
        s = ln.src.get(c)
        if s is None or s not in parent.off_out or parent.off_out[s] != ln.off_in[c]:
            return True
    return False


def _place_y(ln: MLNode, y: float, parent: Optional[MLNode]) -> None:
    if ln.is_board:
        ln.frame_top = y
        y += BOARD_TOP
    if _needs_split_room(ln, parent):
        y += SPLIT_H
    ln.y = y
    if ln.rails:
        ln.rail_y0 = y + (ln.block_h() + RAIL_GAP if (ln.h > 0 or ln.ann) else 2.0) + (DC_JOG if ln.dc_side else 0.0)
        child_y = ln.rails_bottom() + CHILD_GAP
    else:
        child_y = y + ln.block_h() + (GAP if ln.block_h() > 0 else 0.0) + (DC_JOG if ln.dc_side else 0.0)
    for c in ln.children:
        _place_y(c, child_y, ln)


def _shift(ln: MLNode, dy: float) -> None:
    for n in ln.walk():
        n.y += dy
        n.frame_top += dy
        if n.rail_y0 is not None:
            n.rail_y0 += dy


def _owned(board: MLNode):
    """Nodes inside a board frame: its subtree, without sub-boards and loads."""
    stack = list(board.children)
    while stack:
        n = stack.pop()
        if n.is_board or n.bottom:
            continue
        yield n
        stack.extend(n.children)


def _sub_boards(board: MLNode) -> list[MLNode]:
    out, stack = [], list(board.children)
    while stack:
        n = stack.pop()
        if n.is_board:
            out.append(n)
            continue
        stack.extend(n.children)
    return out


def _frame_bottom(board: MLNode) -> float:
    return max([board.frame_top + BOARD_TOP] + [n.content_bottom() for n in _owned(board)]
               + ([board.rails_bottom()] if board.rail_y0 is not None else [])) + 3.0 + board.pad_bottom


def _separate_boards(ln: MLNode) -> None:
    if ln.is_board:
        subs = _sub_boards(ln)
        # below the frame, and side by side on one line (their frames, names and first devices aligned)
        top = max([_frame_bottom(ln) + 3.0] + [sb.frame_top for sb in subs])
        for sb in subs:
            if sb.frame_top < top:
                _shift(sb, top - sb.frame_top)
    for c in ln.children:
        _separate_boards(c)


# ---------------------------------------------------------------- drawing
def _dot(x: float, y: float) -> Circle:
    return Circle((x, y), DOT_R, Style(width=THIN, fill="#000000"))


def _earth(x: float, y: float) -> list[Item]:
    """Earth symbol hanging from (x, y)."""
    return [Line((x, y), (x, y + 1.2)), Line((x - 1.5, y + 1.2), (x + 1.5, y + 1.2)),
            Line((x - 1.0, y + 1.9), (x + 1.0, y + 1.9)), Line((x - 0.5, y + 2.6), (x + 0.5, y + 2.6))]


def _lane_label(x: float, y: float, text: str, size: float = 1.4) -> Text:
    """Conductor name written upwards just right of a conductor, its bottom at ``y``."""
    return Text((x + 0.35 + size * 0.75, y), text, size, "start", rotate=90, color="#333333")


BLADE_A = math.radians(20)
TOP, PIVOT = 3.75, 8.75
BLADE_L = (PIVOT - TOP) * 1.08


def _tip(x: float, y: float) -> tuple[float, float]:
    return (x - BLADE_L * math.sin(BLADE_A), y + PIVOT - BLADE_L * math.cos(BLADE_A))


def _blade_mid(x: float, y: float) -> tuple[float, float]:
    tx, ty = _tip(x, y)
    return ((x + tx) / 2, (y + PIVOT + ty) / 2)


def _contact(x: float, y: float, mark: str, h: float = DEV_H) -> list[Item]:
    """One pole: fixed contact at the top, inclined blade from the bottom pivot, function mark on the fixed
    contact ('cross' breaker, 'bar' disconnector, 'switch' switch-disconnector, 'arc' contactor)."""
    items: list[Item] = [Line((x, y), (x, y + TOP)), Line((x, y + PIVOT), _tip(x, y)), Line((x, y + PIVOT), (x, y + h))]
    c = (x, y + TOP)
    if mark == "cross":
        s = 0.7
        items += [Line((c[0] - s, c[1] - s), (c[0] + s, c[1] + s)), Line((c[0] - s, c[1] + s), (c[0] + s, c[1] - s))]
    elif mark in ("bar", "switch"):
        items.append(Line((c[0] - 0.8, c[1]), (c[0] + 0.8, c[1])))
        if mark == "switch":
            items.append(Circle((c[0], c[1] + 0.5), 0.5))
    elif mark == "arc":
        items.append(Polyline(arc_points((c[0], c[1] + 0.9), 0.9, 180, 360, 10)))
    return items


def _link(xs: list[float], y: float) -> list[Item]:
    """Dashed mechanical link joining the blades of several poles."""
    if len(xs) < 2:
        return []
    mids = [_blade_mid(x, y) for x in xs]
    return [Line((min(m[0] for m in mids) - 0.6, mids[0][1]), (max(m[0] for m in mids), mids[0][1]), DASH)]


def _toroid(live: list[float], y: float, ytor: float) -> list[Item]:
    """Residual-current toroid around all live conductors, linked to the blades."""
    lo, hi = min(live), max(live)
    cx, rx = (lo + hi) / 2, (hi - lo) / 2 + 1.4
    bm = _blade_mid(hi, y)
    xr = cx + rx + 0.6
    return [Ellipse((cx, ytor), rx, 0.9),
            Polyline([(cx + rx, ytor), (xr, ytor), (xr, bm[1]), (bm[0], bm[1])], DASH)]


def _box(x0: float, y0: float, x1: float, y1: float, text: str = "", size: float = 1.6) -> list[Item]:
    items: list[Item] = [Rect(x0, y0, x1 - x0, y1 - y0, Style(fill="#ffffff"))]
    if text:
        size = min(size, max(1.0, (x1 - x0 - 0.8) / max(text_width(text, 1.0), 0.1)))
        items.append(Text(((x0 + x1) / 2, (y0 + y1) / 2), text, size, "middle", "middle"))
    return items


def _icon(node: Any, x0: float, y0: float, x1: float, y1: float) -> Optional[Item]:
    """Single-line symbol of a load, without its lead, fitted inside a box."""
    try:
        sym = symbol_for(node)
    except Exception:  # pragma: no cover - defensive: a symbol that needs more context
        return None
    items = [i for i in sym.items if not (isinstance(i, Line) and i.a == (0, 0) and i.a[0] == i.b[0])]
    items = [i for i in items if not (isinstance(i, Line) and i.a[0] == 0 and i.b[0] == 0 and i.a[1] < 0.5)]
    if not items:
        return None
    g = Group(items)
    b = bbox(g)
    if b is None:
        return None
    w, h = max(b[2] - b[0], 0.1), max(b[3] - b[1], 0.1)
    sc = min(1.0, (x1 - x0 - 1.2) / w, (y1 - y0 - 1.2) / h)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return transform(g, cx - (b[0] + w / 2) * sc, cy - (b[1] + h / 2) * sc, scale=sc)


def _draw_device(ln: MLNode, lang: str) -> Group:
    node = ln.node
    t = ln.type
    y, h = ln.y, ln.h
    g = Group(id=ln.id if ln.node is not None else None, cls=f"ml-sym ml-{t}")
    lanes = [(c, ln.xi(c)) for c in ln.inp]
    lanes.sort(key=lambda p: p[1])
    xs = {c: x for c, x in lanes}
    drawn: set[str] = set()
    live = [c for c in ln.inp if c in LIVE or c == "PEN"]

    def through(cs=None):
        for c in (cs if cs is not None else ln.inp):
            if c not in drawn:
                g.add(cond_group(c, Line((xs[c], y), (xs[c], y + h))))
                drawn.add(c)

    if t in CONTACT_TYPES or (t == "motor_starter" and _starter_contacts(node)):
        prot, unprot = switched(node, ln.inp)
        prot = [c for c in prot if c in xs]
        unprot = [c for c in unprot if c in xs]
        if t == "fuse":
            for c in prot:
                x = xs[c]
                g.add(Group([Line((x, y), (x, y + DEV_H)), Rect(x - 0.8, y + 3.1, 1.6, 6.3)], cls="pole",
                            attrs={"data-uw-cond": c}))
                drawn.add(c)
        elif t == "thermal_relay":
            for c in prot:
                x = xs[c]
                g.add(Group([Line((x, y), (x, y + 3.1)), Rect(x - 1.0, y + 3.1, 2.0, 6.3),
                             Polyline([(x, y + 3.1), (x, y + 4.6), (x + 0.6, y + 4.6), (x + 0.6, y + 7.8), (x, y + 7.8),
                                       (x, y + 9.4)]), Line((x, y + 9.4), (x, y + DEV_H))], cls="pole",
                            attrs={"data-uw-cond": c}))
                drawn.add(c)
            if len(prot) > 1:
                g.add(Line((xs[prot[0]] + 1.0, y + 6.2), (xs[prot[-1]] - 1.0, y + 6.2), DASH))
        else:
            mark = {"breaker": "cross", "rcbo": "cross", "main_breaker": "cross", "motor_starter": "arc",
                    "disconnector": "bar", "switch_disconnector": "switch", "fuse_switch": "switch",
                    "transfer_switch": "switch", "contactor": "arc", "impulse_relay": "arc", "spare": "cross"}.get(t, "")
            for c in prot:
                pole = Group(_contact(xs[c], y, mark, h), cls="pole", attrs={"data-uw-cond": c})
                if t == "fuse_switch":  # fuse link in series below the switching contact
                    pole.add(Rect(xs[c] - 0.8, y + DEV_H + 1.0, 1.6, 5.5))
                g.add(pole)
                drawn.add(c)
            for c in unprot:  # neutral pole: same contact, without the protection mark
                g.add(Group(_contact(xs[c], y, "" if mark == "cross" else mark, h), cls="pole pole-n",
                            attrs={"data-uw-cond": c}))
                drawn.add(c)
            g.add(*_link([xs[c] for c in prot + unprot], y))
            if t == "motor_starter" and _starter_sets(node):
                g.add(Group(_starter_extra(node, [xs[c] for c in prot if c in PHASES], y, h, max(xs.values())),
                            cls="starter-contactors"))
            if t in ("rcd", "rcbo") or (t == "main_breaker" and getattr(node, "idn_mA", None)):
                rl = [xs[c] for c in prot + unprot] or [xs[c] for c in live]
                if rl:
                    g.add(*_toroid(rl, y, y + DEV_H + 2.3))
        through()
        if t == "spare":
            g = Group([_restyle(i, Style(width=THIN, dash=(1.0, 0.7), color="#777777")) for i in g.items], g.id, g.cls, dict(g.attrs))
        return g

    if t == "transformer":
        cxr, r = _circle(ln)
        cx = ln.x_left + cxr
        c1 = (cx, y + 2.0 + r)
        c2 = (cx, c1[1] + 1.5 * r)
        g.add(Circle(c1, r), Circle(c2, r))
        m = _VECTOR.match(getattr(node, "coupling", None) or "")
        sym = {"D": "Δ", "Y": "Y", "Z": "Z", "YN": "Y", "ZN": "Z"}
        if m:
            g.add(Text((cx, c1[1] - 0.3 * r), sym[m[1]], 2.2, "middle", "middle"),
                  Text((cx, c2[1] + 0.3 * r), sym[m[2].upper().rstrip("N")], 2.2, "middle", "middle"))
        for c, x in lanes:
            if c == "PE":  # the protective conductor passes beside the windings to the earthed secondary side
                # (no PE out, SELV or IT: it ends on the earthed enclosure)
                xp = max(ln.xo("PE") if "PE" in ln.out else x, cx + r + (1.0 if "PE" in ln.out else 2.0))
                yb = y + h - 2.0 if "PE" in ln.out else c2[1]
                pts = [(x, y), (x, y + 1.0), (xp, y + 1.0), (xp, yb)]
                if "PE" in ln.out and ln.xo("PE") != xp:
                    pts.append((ln.xo("PE"), yb))
                g.add(cond_group(c, Polyline(pts)))
                g.add(_dot(ln.xo("PE"), yb) if "PE" in ln.out else Group(_earth(xp, yb)))
                continue
            dx = min(abs(x - cx), r * 0.95)
            g.add(cond_group(c, Line((x, y), (x, c1[1] - math.sqrt(r * r - dx * dx)))))
        _draw_out_from_circle(g, ln, c2, r, y + h)
        return g

    if t == "generator" or (ln.root and t in SOURCE_TYPES):
        if t == "generator":
            cxr, r = _circle(ln)
            c = (ln.x_left + cxr, y + 1.0 + r)
            g.add(Circle(c, r), Text((c[0], c[1] - 0.6), "G", 2.6, "middle", "middle", bold=True),
                  Text((c[0], c[1] + 2.0), "3~" if len([x for x in ln.out if x in PHASES]) == 3 else "1~", 1.5,
                       "middle", "middle"))
            _draw_out_from_circle(g, ln, c, r, y + h)
            return g
        x0, x1 = ln.x_left + ln.lanes_min() - 1.5, ln.x_left + ln.lanes_max() + 1.5
        if t == "offpage":  # supply coming from another drawing: incoming arrows on every conductor
            for c in ln.out:
                x = ln.xo(c)
                g.add(cond_group(c, Polyline([(x - 0.7, y + 1.6), (x, y + 3.0), (x + 0.7, y + 1.6)], Style(fill="#000000"),
                                             closed=True), Line((x, y), (x, y + h))))
            return g
        if t == "grid":
            gs = grid_symbol(node)
            g.add(Group([transform(i, (x0 + x1) / 2, y) for i in gs.items]))
            g.add(Rect(x0, y + 10.0, x1 - x0, 2.0, Style(fill="#ffffff")))
            top = y + 12.0
        else:
            label = {"ups": "~/~", "inverter": "~/=", "pv_array": "PV",
                     "battery": "+ −"}.get(t, _box_text(ln))
            g.add(*_box(x0, y, x1, y + 7.0, label))
            top = y + 7.0
        for c, x in [(c, ln.xo(c)) for c in ln.out]:
            g.add(cond_group(c, Line((x, top), (x, y + h))))
        return g

    if t in CONVERTERS or t == "ups":
        x0 = ln.x_left + ln.lanes_min() - 1.5
        x1 = ln.x_left + ln.lanes_max() + 1.5
        x1 = max(x1, x0 + 7.0)
        g.add(*_box(x0, y + 2.0, x1, y + 9.0))
        g.add(Line((x0, y + 9.0), (x1, y + 2.0), Style(width=THIN)))
        a, b = ("~", "~") if t == "ups" else ("=", "=") if t == "dc_converter" else ("~", "=")
        g.add(Text((x0 + 1.6, y + 4.0), a, 1.8, "middle", "middle"), Text((x1 - 1.6, y + 7.2), b, 1.8, "middle", "middle"))
        for c, x in lanes:
            g.add(cond_group(c, Line((x, y), (x, y + 2.0))))
        for c in ln.out:
            g.add(cond_group(c, Line((ln.xo(c), y + 9.0), (ln.xo(c), y + h))))
        return g

    if t == "spd":
        surge = [c for c in ln.inp if c in LIVE]
        pe = next((c for c in ln.inp if c in ("PE", "PEN")), None)
        yj = y + 9.0
        for c in surge:
            x = xs[c]
            g.add(Line((x, y), (x, y + 2.5)), Rect(x - 0.8, y + 2.5, 1.6, 4.5), Line((x, y + 4.0), (x, y + 6.0)),
                  Line((x, y + 7.0), (x, yj)))
        if surge:
            xe = xs[pe] if pe else max(xs[c] for c in surge) + S
            g.add(Line((min(xs[c] for c in surge), yj), (xe, yj)))
            if pe:
                g.add(Line((xe, y), (xe, yj)))
            if not pe or pe == "PEN":
                g.add(*_earth(xe, yj))
            for c in surge[1:]:
                g.add(_dot(xs[c], yj))
        return g

    if t == "earth_bar":  # the single-line symbol, on its conductor
        sym = symbol_for(node)
        for c, x in lanes:
            g.add(cond_group(c, *[transform(i, x, y) for i in sym.items]))
        return g

    if t == "earth":
        for _c, x in lanes:
            g.add(Line((x, y), (x, y + 2.0)), *_earth(x, y + 2.0)[1:])
        return g

    if _is_busway(ln):  # busbar trunking: casing spanning every conductor (PE included), one bar per conductor
        x0, x1 = min(xs.values()) - 1.8, max(xs.values()) + 1.8
        g.add(Rect(x0, y + 1.5, x1 - x0, h - 1.5, Style(fill="#ffffff")))
        for c, x in lanes:
            g.add(Line((x, y), (x, y + 2.6)), Line((x, y + 2.6), (x, y + 4.4), Style(width=THICK)),
                  _lane_label(x - 0.2, y + h - 0.5, c, 1.0))
        return g

    if t == "plc":  # the single-line symbol (head and modules): its links leave from the module they use
        sym = symbol_for(node)
        ox, oy = _plc_origin(ln)
        g.add(*[transform(i, ox, oy) for i in sym.items[1:]])
        for c in ln.inp:
            if c != "PE":
                g.add(cond_group(c, Line((xs[c], y), (xs[c], y + PLC_TOP))))
        if ln.children:
            for c in ln.out:
                g.add(cond_group(c, Line((ln.xo(c), oy + sym.extra["port_y"]), (ln.xo(c), y + h))))
        head = ox - sym.left + 0.2  # the PE ends on the head (never between its modules)
        for c in ln.inp:
            if c == "PE":
                x, ym = xs[c], y + PLC_TOP + 1.5
                g.add(cond_group(c, Polyline([(x, y), (x, ym), (head if x < head else ox + sym.left - 0.2, ym)])))
        return g

    if t == "instrument_transformer" and getattr(node, "kind", None) in (None, "ct"):  # a ring on each live conductor
        through()
        for c in [c for c in live if c.startswith("L")] or live:  # the phases (never the PEN)
            g.add(Circle((xs[c], y + h / 2), 1.0))
        return g

    if t == "connector":  # socket and plug on each conductor, as in the single-line symbol
        ym = y + h / 2
        for c, x in lanes:
            g.add(cond_group(c, Line((x, y), (x, ym - 0.6)), Line((x, ym + 0.6), (x, y + h))),
                  Polyline([(x - 0.7, ym - 1.3), (x, ym - 0.6), (x + 0.7, ym - 1.3)]),
                  Polyline([(x - 0.7, ym - 0.1), (x, ym + 0.6), (x + 0.7, ym - 0.1)]))
        return g

    # meter and any other device: a box across the live conductors, the PE passing beside it
    boxed = [c for c in ln.inp if c not in ("PE",)] or list(ln.inp)
    x0 = min(xs[c] for c in boxed) - 1.5
    x1 = max(xs[c] for c in boxed) + 1.5
    if node is not None and _vfd_to_three_phase(node, ln.inp):  # wide enough for U V W, the PE jogging past
        x1 = max(ln.xo(c) for c in ln.out if c != "PE") + 1.5
        if "PE" in xs and "PE" in ln.out:
            x, xo = xs["PE"], ln.xo("PE")
            g.add(cond_group("PE", Polyline([(x, y), (x, y + 0.75), (xo, y + 0.75), (xo, y + h)])))
            drawn.add("PE")
    if t == "meter":
        g.add(*_box(x0, y + 1.5, x1, y + 9.5))
        g.add(Line((x0, y + 3.5), (x1, y + 3.5), Style(width=THIN)),
              Text(((x0 + x1) / 2, y + 6.5), "kWh", min(1.6, (x1 - x0 - 0.6) / 2.0), "middle", "middle"))
    else:
        g.add(*_box(x0, y + 1.5, x1, y + 9.5, _box_text(ln)))
    for c in boxed:
        g.add(cond_group(c, Line((xs[c], y), (xs[c], y + 1.5))))
    if ln.children:
        for c in ln.out:
            if c in boxed or c not in xs:
                g.add(cond_group(c, Line((ln.xo(c), y + 9.5), (ln.xo(c), y + h))))
        through([c for c in ln.inp if c not in boxed])
    else:  # a final device: its PE ends on its enclosure
        for c in ln.inp:
            if c not in boxed:
                x = xs[c]
                g.add(cond_group(c, Polyline([(x, y), (x, y + 3.0), (x1 if x > x1 else x0, y + 3.0)])))  # high: links below
    return g


def _box_text(ln: MLNode) -> str:
    node = ln.node
    t = ln.type
    if node is None:
        return ""
    txt = getattr(node, "symbol_text", None)
    if txt:
        return txt
    if t == "motor_starter":
        return _abbr(f"starter.{getattr(node, 'method', None) or ''}") or _abbr("starter.")
    if t == "offpage":
        return node.ref or node.label or ""
    if t == "power_supply":
        return "~/="
    return _abbr(t)  # never the tag: it is written beside the device


def _draw_out_from_circle(g: Group, ln: MLNode, c: tuple[float, float], r: float, y_end: float) -> None:
    """Output conductors of a machine / transformer: from the bottom of the circle; the PE starts beside it,
    bonded to the neutral (TN) or to an earth electrode."""
    for cond in ln.out:
        x = ln.xo(cond)
        if cond == "PE":
            yb = y_end - 2.0
            g.add(cond_group("PE", Line((x, yb), (x, y_end))))
            n = next((k for k in ("N", "PEN") if k in ln.out), None)
            if n is not None:
                g.add(Line((ln.xo(n), yb), (x, yb)), _dot(ln.xo(n), yb))
            g.add(Line((x, yb), (x + 2.0, yb)), *_earth(x + 2.0, yb))
            continue
        dx = min(abs(x - c[0]), r * 0.95)
        g.add(cond_group(cond, Line((x, c[1] + math.sqrt(r * r - dx * dx)), (x, y_end))))


def _draw_load(ln: MLNode, lang: str) -> Group:
    node = ln.node
    t = ln.type
    y = ln.y
    g = Group(id=ln.id if node is not None else None, cls=f"ml-sym ml-load ml-{t}")
    lanes = [(c, ln.xi(c)) for c in ln.inp]
    lanes.sort(key=lambda p: p[1])
    if ln.kind == "stub" or t == "offpage":
        for c, x in lanes:
            g.add(cond_group(c, Line((x, y), (x, y + 3.6)),
                             Polyline([(x - 0.7, y + 3.0), (x, y + 4.4), (x + 0.7, y + 3.0)], Style(fill="#000000"),
                                      closed=True)))
        return g
    if t == "motor":
        cxr, r = _circle(ln)
        c = (ln.x_left + cxr, y + 3.0 + r)
        dc = any(cd in DC for cd in ln.inp)
        kind = "=" if dc else "1~" if getattr(node, "phases", None) == 1 else "3~"
        g.add(Circle(c, r), Text((c[0], c[1] - 0.7), "M", 2.6, "middle", "middle", bold=True),
              Text((c[0], c[1] + 2.0), kind, 1.5, "middle", "middle"))
        terms = iter(("U", "V", "W"))
        for cond, x in lanes:
            if cond == "PE":
                g.add(cond_group("PE", Polyline([(x, y), (x, c[1]), (c[0] + r, c[1])])))
                g.add(_lane_label(x, y + 2.6, "PE", 1.3))
                continue
            dx = min(abs(x - c[0]), r * 0.95)
            g.add(cond_group(cond, Line((x, y), (x, c[1] - math.sqrt(r * r - dx * dx)))))
            name = next(terms, "") if cond in PHASES else cond
            if getattr(node, "phases", None) == 1 or dc:
                name = cond
            g.add(_lane_label(x, y + 2.6, name, 1.3))
        return g
    x0 = min(x for _, x in lanes) - 1.5
    x1 = max(x for _, x in lanes) + 1.5
    if x1 - x0 < 7.0:
        x1 = x0 + 7.0
    yb = y + 4.0
    for c, x in lanes:
        g.add(cond_group(c, Line((x, y), (x, yb))), Circle((x, yb), 0.35, Style(width=THIN, fill="#ffffff")),
              _lane_label(x, yb - 0.6, c, 1.3))
    g.add(Rect(x0, yb, x1 - x0, 9.0, Style(fill="#ffffff")))
    icon = _icon(node, x0, yb, x1, yb + 9.0) if node is not None else None
    if icon is not None:
        g.add(icon)
    return g


def _restyle(item: Any, style: Style) -> Any:
    if isinstance(item, Group):
        return Group([_restyle(i, style) for i in item.items], item.id, item.cls, dict(item.attrs))
    if isinstance(item, (Line, Polyline, Circle, Ellipse, Rect)):
        s = Style(style.width, style.dash, style.color, getattr(item.style, "fill", None))
        item = type(item)(**{**item.__dict__, "style": s})
    return item


def _draw_transition(ln: MLNode, ch: MLNode, g: Group) -> None:
    """Conductors from ``ln`` (no rails) down to its single child, with PEN splits and new conductors."""
    eg = edge_group(ch.id, ln.target if ln.kind == "bus_in" else ln.id)
    g.add(eg)
    g = eg
    y0 = ln.y + ln.h
    y1 = ch.y
    yj = y1 - SPLIT_H / 2 - 0.5
    from_x: dict[float, int] = {}
    labels: list[Item] = []
    for c in ch.inp:
        s = ch.src.get(c)
        xc = ch.xi(c)
        if s is None or s not in ln.off_out:
            ys = y1 - SPLIT_H + 1.0
            g.add(cond_group(c, Line((xc, ys), (xc, y1)), Line((xc, ys), (xc + 2.0, ys)), *_earth(xc + 2.0, ys)))
            labels.append(Text((xc - 0.5, ys + 2.6), c, 1.4, "end", color="#333333"))
            continue
        xs = ln.xo(s)
        if abs(xs - xc) < 1e-6:
            g.add(cond_group(c, Line((xs, y0), (xs, y1))))
        else:
            g.add(cond_group(c, Polyline([(xs, y0), (xs, yj), (xc, yj), (xc, y1)])))
        from_x[round(xs, 3)] = from_x.get(round(xs, 3), 0) + 1
        if s != c:
            labels.append(Text((xc + 0.5, y1 - 0.6), c, 1.4, color="#333333"))
            if s == "PEN" and from_x[round(xs, 3)] == 1:
                labels.append(Text((xs - 0.5, yj - 1.2), "PEN", 1.4, "end", color="#333333"))
    for xs, n in from_x.items():
        if n > 1:
            g.add(_dot(xs, yj))
    g.add(*labels)


def _draw_dc_side(ln: MLNode, g: Group) -> None:
    """DC pair of an inverter/charger down from its "=" corner, then right to the columns of the DC side; the
    leftmost conductor turns lowest so that the pair never crosses itself."""
    pair = sorted((c for c in ln.out if c in DC), key=ln.xo)
    y0 = ln.y + ln.h
    base = ln.y + ln.block_h() + 1.5
    branches: dict[str, list[tuple[float, float]]] = {}
    for ch in ln.dc_children:
        eg = edge_group(ch.id, ln.id)
        g.add(eg)
        for c in ch.inp:
            s = ch.src.get(c)
            if s not in pair:
                continue
            xs, xc = ln.xo(s), ch.xi(c)
            yj = base + (len(pair) - 1 - pair.index(s)) * S
            eg.add(cond_group(c, Polyline([(xs, y0), (xs, yj), (xc, yj), (xc, ch.y)])))
            branches.setdefault(s, []).append((xc, yj))
    for pts in branches.values():  # several columns on the DC side: a dot where each one leaves the pair
        for p in sorted(pts)[:-1]:
            g.add(_dot(*p))


def _draw_rails(ln: MLNode, g: Group, sheet_left: float, folio_of: Callable[[str], Optional[int]],
                continuation: tuple[Optional[int], Optional[int]], lang: str) -> None:
    assert ln.rail_y0 is not None
    bars = [c for c in ln.out if not (ln.dc_side and c in DC)]
    ry = {c: ln.rail_y0 + i * S for i, c in enumerate(bars)}
    taps: dict[str, list[float]] = {c: [] for c in bars}
    news: list[tuple[MLNode, str]] = []
    me = ln.target if ln.kind == "bus_in" else ln.id
    edges: dict[int, Group] = {}
    for ch in ln.bus_children:
        top = ch.frame_top if ch.is_board else ch.y
        eg = edges[id(ch)] = edge_group(ch.id, me)
        g.add(eg)
        for c in ch.inp:
            s = ch.src.get(c)
            x = ch.xi(c)
            if s is None or s not in ry:
                news.append((ch, c))
                continue
            taps[s].append(x)
            eg.add(cond_group(c, Line((x, ry[s]), (x, top if not ch.is_board else ch.y))))
    for c, xs_ in ln.extra_taps.items():  # power links outside the tree tapped on the rails
        if c in taps:
            taps[c] += xs_
    x_end = max([x for v in taps.values() for x in v] + [ln.xo(c) for c in bars]) + 2.0
    if ln.bus_out:
        x_end += 4.0
    style = Style(width=THICK if (ln.type in ("board", "busbar") or ln.kind == "bus_in" or len(ln.bus_children) > 2)
                  else NORMAL)
    for c in ln.out:
        if c not in ry:
            continue
        y = ry[c]
        bg = busbar_group(me or ln.id, cond=c)
        if ln.kind == "bus_in":
            x0 = sheet_left
        else:
            x0 = ln.xo(c)
            bg.add(Line((x0, ln.y + ln.h), (x0, y)))
        bg.add(Line((x0, y), (x_end, y), style))
        for x in taps[c]:
            if x0 + 1e-6 < x < x_end - 1e-6:
                bg.add(_dot(x, y))
        bg.add(Text((x_end + 0.8, y), c, 1.5, "start", "middle", color="#333333"))
        g.add(bg)
    if _is_busway(ln):  # busbar trunking: casing around the bars
        x0 = min(ln.xo(c) for c in ln.out) - 1.5 if ln.kind != "bus_in" else sheet_left
        g.add(Rect(x0, ln.rail_y0 - 1.6, x_end - x0 + 1.4 + text_width("PEN", 1.5), (len(ln.out) - 1) * S + 3.2,
                   Style(width=THIN, color="#333333")))
    if ln.bus_out:
        nxt = continuation[1]
        txt = _t("render.continued_on", lang, folio=nxt) if nxt else "…"
        g.add(ref_group(nxt, ln.id, [Text((x_end + 4.0, ln.rail_y0 - 1.5), txt, 1.8, "start")]))
    if ln.kind == "bus_in":
        prev = continuation[0]
        txt = _t("render.continued_from", lang, label=ln.label, folio=prev) if prev else ln.label
        g.add(ref_group(prev, ln.target, [Text((sheet_left, ln.rail_y0 - 1.8), txt, 1.8, "start")]))
    for ch, c in news:
        x = ch.xi(c)
        top = ch.y
        ys = top - SPLIT_H + 1.0
        edges[id(ch)].add(cond_group(c, Line((x, ys), (x, top)), Line((x, ys), (x + 2.0, ys)), *_earth(x + 2.0, ys)))


def _draw(ln: MLNode, g: Group, lang: str, view: View, sheet_left: float, folio_of: Callable[[str], Optional[int]],
          continuation: tuple[Optional[int], Optional[int]], incoming: Optional[str],
          incoming_ref: tuple[Optional[int], Optional[str]] = (None, None)) -> None:
    if ln.kind == "stub" or ln.bottom:
        sg = _draw_load(ln, lang)
    elif ln.kind == "node" and ln.h > 0:
        sg = _draw_device(ln, lang)
    else:
        sg = None
    if sg is not None:
        if ln.node is not None and getattr(ln.node, "external", False):
            sg = _restyle(sg, Style(width=THIN, dash=(1.2, 0.8), color="#555555"))
            sg.cls = (sg.cls or "") + " external"
        if ln.kind == "stub":  # board drawn on its own sheet: reference to that sheet
            sg.id = None
            add_cls(sg, "uw-ref").attrs.update(ref_group(folio_of(ln.target or ""), ln.target).attrs)
        elif sg.id:
            node_group(sg)
        g.add(sg)
    # sheet root fed from elsewhere: incoming conductors
    if ln.root and ln.kind == "node" and ln.type not in SOURCE_TYPES:
        top = ln.frame_top - 6.0 if ln.is_board else ln.y - 6.0
        rg = ref_group(*incoming_ref)
        for c in ln.inp:
            x = ln.xi(c)
            if ln.src.get(c) is None:  # starts here (PE at the main earthing terminal of the board)
                ys = ln.y - SPLIT_H + 1.0
                g.add(cond_group(c, Line((x, ys), (x, ln.y)), Line((x, ys), (x + 2.0, ys)), *_earth(x + 2.0, ys)),
                      Text((x - 0.5, ys + 2.6), c, 1.4, "end", color="#333333"))
                continue
            rg.add(cond_group(c, Line((x, top), (x, ln.y))), _lane_label(x, top + 3.0, c))
        if incoming:
            rg.add(Text((ln.x_left + ln.lanes_max() + 2.5, top + 1.5), incoming, 1.8))
        g.add(rg)
    if ln.root and ln.kind == "node" and ln.type in SOURCE_TYPES:
        y = ln.y + ln.h
        for c in ln.out:
            g.add(_lane_label(ln.xo(c), y - 0.6, c))
    if ln.ann:
        x = ln.x_left + ln.right() + 1.0
        tg = Group(cls="annotation")
        for i, txt in enumerate(ln.ann):
            tg.add(Text((x, ln.y + 0.3 + (i + 0.8) * ANN_LINE * ln.ann_size / ANN_SIZE), txt, ln.ann_size,
                        bold=(i == 0 and ln.tagged)))
        g.add(tg)
    if ln.bottom:
        _draw_load_texts(ln, g, folio_of, lang)
    if ln.rails:
        _draw_rails(ln, g, sheet_left, folio_of, continuation, lang)
    elif ln.bus_children:
        _draw_transition(ln, ln.bus_children[0], g)
    if ln.dc_side:
        _draw_dc_side(ln, g)
    for c in ln.children:
        _draw(c, g, lang, view, sheet_left, folio_of, continuation, None)


def _load_box_bottom(ln: MLNode) -> float:
    if ln.kind == "stub" or ln.type == "offpage":
        return ln.y + 5.0
    if ln.type == "motor":
        _, r = _circle(ln)
        return ln.y + 3.0 + 2 * r
    return ln.y + 13.0


def _draw_load_texts(ln: MLNode, g: Group, folio_of: Callable[[str], Optional[int]], lang: str) -> None:
    lines = list(ln.load_lines)
    if ln.kind == "stub":
        f = folio_of(ln.target or "")
        lines = [ln.label + (_t("render.to_folio", lang, folio=f) if f else "")]
    xs = [ln.xi(c) for c in ln.inp]
    cx = (min(xs) + max(xs)) / 2
    yb = _load_box_bottom(ln) + 1.5
    n = len(lines)
    tg = Group(cls="load-label")
    if ln.kind == "stub":
        tg = add_cls(ref_group(folio_of(ln.target or ""), ln.target), "load-label")
    for i, txt in enumerate(lines):
        x = cx + (i - (n - 1) / 2) * 2.5 + LOAD_TEXT * 0.35
        tg.add(Text((x, yb), txt, LOAD_TEXT, "end", rotate=90, bold=(i == 0 and ln.kind == "stub")))
    g.add(tg)
    if ln.cable_lines:
        x = ln.x_left + ln.lanes_max() + 1.5
        y = ln.y - CABLE_BAND + 2.8
        cg = Group(cls="cable")
        for i, txt in enumerate(ln.cable_lines):
            cg.add(Text((x, y + i * 2.0), txt, 1.6, color="#333333"))
        g.add(cg)


def _draw_frames(roots: list[MLNode], g: Group) -> None:
    drawn = {it.id: it for it in g.items if isinstance(it, Group) and it.id and it.cls.startswith("ml-sym")}
    for r in roots:
        for b in r.walk():
            if not b.is_board or b.node is None:
                continue
            x0, x1 = b.x_left + 0.8, b.x_left + b.width - FRAME_ROOM
            # clear of the symbols (blades and their mechanical link reach left of the first conductor), and
            # of the frame of the column on the left
            lefts = [box[0] for n in _owned(b) if n.id in drawn and (box := bbox(drawn[n.id])) is not None]
            x0 = max(b.x_left - 0.5, min([x0] + [x - 2.0 for x in lefts]))
            y0, y1 = b.frame_top, _frame_bottom(b)
            fg = Group(id=b.id, cls="board uw-node")
            fg.add(Rect(x0, y0, x1 - x0, y1 - y0, Style(width=THIN, dash=(2.0, 1.0), color="#555555")))
            name = _board_name(b.node)
            tx = b.x_left + b.lanes_max() + 2.5  # right of the incoming conductors
            fg.add(Text((tx, y0 + 4.0), name, 2.4, bold=True))
            extra = [txt for txt in annotation(b.node) if txt and txt != b.node.label]
            if extra:
                fg.add(Text((tx + 2.0 + 1.1 * text_width(name, 2.4), y0 + 4.0), "  ".join(extra), 1.8))
            g.add(fg)


# ------------------------------------------------------------ power links
ML_LINKS = ("infeed", "tie", "bypass", "parallel", "transfer")
LAND = 2.0  # vertical spacing of the landings of a link's conductors
TAP = 2.5  # between two blocks of link taps on the same rails
OPEN = Style(dash=(3.0, 1.2))  # normally-open power conductor: long dash (as in the single-line diagram)


@dataclass
class _Link:
    """Power link outside the tree, drawn conductor by conductor.

    ``src``: 'rails' (taps on the busbar rails of ``a``) or 'out' (from the output conductors of ``a``);
    ``dst``: 'inp' (junctions on the input conductors of ``b``), 'out' (on its output conductors), 'rails'
    (taps on its rails) or 'side' (second input of a transfer switch, arrows on its side)."""

    link: Any
    a: MLNode
    b: MLNode
    conds: list[str]  # in the order of the target conductors (left to right)
    src: str
    dst: str
    left: bool  # target to the left of the source
    a_head: bool = False  # taps on the source rails before its first feeder (else after the last one)
    b_head: bool = False  # same on the target rails
    text: list[str] = field(default_factory=list)
    alias: dict[str, str] = field(default_factory=dict)  # target conductor -> source conductor (N from a PEN)
    from_right: bool = False  # landing under a final device from its right (nothing beside it there)
    # routed
    sx: dict[str, float] = field(default_factory=dict)  # x of the source tap / output conductor
    sy: dict[str, float] = field(default_factory=dict)
    lane: dict[str, float] = field(default_factory=dict)
    dx: dict[str, float] = field(default_factory=dict)  # x of the vertical toward the target
    land: dict[str, tuple[float, float]] = field(default_factory=dict)  # landing point
    top: float = 0.0  # y of the block (annotation top)
    walls: list[tuple[float, float, float]] = field(default_factory=list)  # vertical conductors (x, y0, y1)

    @property
    def n(self) -> int:
        return len(self.conds)

    def block_h(self) -> float:
        return len(self.text) * 2.2 + 3.0 + (self.n - 1) * S + 3.5


def _order(roots: list[MLNode]) -> dict[int, int]:
    return {id(n): i for i, n in enumerate(n for r in roots for n in r.walk())}


def _plan_links(doc: Document, roots: list[MLNode], lang: str) -> list[_Link]:
    """Power links whose both ends are on the sheet; reserves the horizontal room they need (taps, landings)."""
    from .engine import _device_text

    nodes = {n.node.id: n for r in roots for n in r.walk() if n.kind == "node" and n.node is not None and n.node.id}
    parent = {id(c): n for r in roots for n in r.walk() for c in n.children}
    order = _order(roots)
    out: list[_Link] = []
    for link in doc.links:
        if link.kind not in ML_LINKS:
            continue
        a, b = nodes.get(link.from_), nodes.get(link.to)
        if a is None or b is None or a is b:
            continue
        src = "rails" if a.rails else "out"
        if link.kind == "transfer" and b.type == "transfer_switch":
            dst = "side"
        elif link.kind in ("infeed", "transfer") and id(b) in parent and (link.kind == "transfer" or b.children):
            dst = "inp"  # a device feeding nothing (back-feed breaker of a PV inverter) is fed on its outputs
        elif link.kind == "infeed" and b.root and b.type in CONVERTERS | {"ups"}:
            dst = "top"  # an inverter / UPS at the head of the tree: its AC input on top, never on its outputs
        elif b.rails:
            dst = "rails"
        else:
            dst = "out"
        have = a.out
        want = b.inp if dst in ("inp", "side", "top") else b.out
        # a source with a PEN (TN-C) feeds the neutral of a target that has N and PE (the PEN is split there)
        alias = {"N": "PEN"} if "PEN" in have and "N" in want and "N" not in have else {}
        conds = [c for c in sorted(want, key=lambda c: (b.off_in if dst in ("inp", "side", "top") else b.off_out).get(c, 0))
                 if alias.get(c, c) in have and (c != "PE" or dst != "side")]  # the PE goes with the cable
        if not conds:
            continue
        last = max([order[id(d)] for d in a.walk()])
        left = order[id(b)] < order[id(a)] or (order[id(b)] <= last and a.rails and
                                               _column_index(a, b, parent) < len(a.children) / 2)
        lk = _Link(link, a, b, conds, src, dst, left, alias=alias)
        p = parent.get(id(b))
        lk.from_right = dst == "out" and not b.children and left and p is not None and p.children[-1] is b
        if link.device is not None:
            lk.text = _device_text(link, link.device, lang)[:4]
        elif link.label:  # written above the bundle, where its conductors run side by side
            lk.text = [link.label]
        need = lk.n * S + TAP
        lk.a_head = left
        # on target rails coming from above (from a final device), the taps go after the last feeder: clear of
        # the annotations of the devices feeding those rails
        lk.b_head = not left and src == "rails"
        if src == "rails":
            if lk.a_head:
                a.head += need
            else:
                a.tail += need
        if dst == "rails":
            if lk.b_head:
                b.head += need
            else:
                b.tail += need
        elif not lk.from_right:  # the conductors come down beside the target column
            col = b
            while id(col) in parent and not parent[id(col)].rails:
                col = parent[id(col)]
            col.lead = max(col.lead, (col.lead + need) if col.lead else need + 1.0)
        out.append(lk)
    return out


def _column_index(a: MLNode, b: MLNode, parent: dict[int, MLNode]) -> int:
    n = b
    while id(n) in parent and parent[id(n)] is not a:
        n = parent[id(n)]
    return next((i for i, c in enumerate(a.children) if c is n), 0)


def _make_room(links: list[_Link], roots: list[MLNode]) -> None:
    """Vertical room: landings above (below) the target conductors, then a band of lanes under the source
    rails / outputs, one block per link (its device and annotation included)."""
    if not links:
        return
    for lk in links:
        room = lk.n * LAND + 2.5
        if lk.dst in ("inp", "top"):
            _shift(lk.b, room)
        elif lk.dst == "out":
            for c in lk.b.children:
                _shift(c, room)
            if not lk.b.children:
                lk.b.below = max(lk.b.below, room)
    y0 = max(lk.a.rails_bottom() if lk.src == "rails" else lk.a.y + lk.a.h for lk in links)
    height = 2.0 + sum(lk.block_h() for lk in links)
    under = [n for r in roots for n in r.walk() if n.y > y0 + 1e-6]
    # rails hanging below the band from a device above it (a sub-busbar beside the source): moved down too,
    # or the lanes would run between its bars
    rails = [n for r in roots for n in r.walk() if n.y <= y0 + 1e-6 and n.rail_y0 is not None and n.rail_y0 > y0 - 1e-6]
    if under or rails:
        tops = [n.frame_top if n.is_board else n.y for n in under] + [n.rail_y0 for n in rails]
        dy = y0 + height + CHILD_GAP - min(tops)
        if dy > 0:
            for n in under:
                n.y += dy
                n.frame_top += dy
                if n.rail_y0 is not None:
                    n.rail_y0 += dy
            for n in rails:
                n.rail_y0 += dy
    for lk in links:
        lk.top = y0 + 2.0  # provisional: set per lane in _route_links
    links[0].top = y0 + 2.0


def _route_links(links: list[_Link], roots: list[MLNode]) -> None:
    """Conductor by conductor routes: taps, lanes in the band (blocks ordered to cross the fewest
    conductors), verticals beside the target, landings."""
    if not links:
        return
    import itertools

    y0 = links[0].top
    head_used: dict[int, float] = {}
    tail_used: dict[int, float] = {}

    def taps(n: MLNode, lk: _Link, on_left: bool) -> dict[str, float]:
        """x of the taps of ``lk`` on the rails of ``n``: in the room before the first feeder or after the last."""
        if on_left:
            x0 = n.x_left + n.lanes_max() + 3.0 + head_used.get(id(n), 0.0)
            head_used[id(n)] = head_used.get(id(n), 0.0) + lk.n * S + TAP
        else:
            last = n.children[-1] if n.children else n
            base = max(last.x_left + last.lanes_max(), max([x for v in n.extra_taps.values() for x in v], default=0))
            x0 = base + 3.0 + tail_used.get(id(n), 0.0) if id(n) not in tail_used else base + TAP
            tail_used[id(n)] = 1.0
        # conductor k of the link (target order) taps at x0 + (n-1-k) S: no crossing inside the bundle
        return {c: x0 + (lk.n - 1 - k) * S for k, c in enumerate(lk.conds)}

    for lk in links:
        a, b = lk.a, lk.b
        if lk.src == "rails":
            ry = {c: a.rail_y0 + i * S for i, c in enumerate(a.out)}  # type: ignore[operator]
            lk.sx = taps(a, lk, lk.a_head)
            lk.sy = {c: ry[lk.alias.get(c, c)] for c in lk.conds}
            for c, x in lk.sx.items():
                a.extra_taps.setdefault(lk.alias.get(c, c), []).append(x)
        else:
            lk.sx = {c: a.xo(lk.alias.get(c, c)) for c in lk.conds}
            lk.sy = {c: a.y + a.h for c in lk.conds}
        if lk.dst == "rails":
            ry = {c: b.rail_y0 + i * S for i, c in enumerate(b.out)}  # type: ignore[operator]
            xs = taps(b, lk, lk.b_head)
            lk.dx = xs
            lk.land = {c: (xs[c], ry[c]) for c in lk.conds}
            for c, x in xs.items():
                b.extra_taps.setdefault(c, []).append(x)
        else:
            offs = b.off_in if lk.dst in ("inp", "side", "top") else b.off_out
            right = b.x_left + min(offs[c] for c in lk.conds) - 2.5
            lk.dx = {c: right - k * S for k, c in enumerate(lk.conds)}
            if lk.from_right:  # down beyond the device's text, then under the device: never across its inputs
                base = b.x_left + b.right() + 1.0 + max([text_width(t, b.ann_size) for t in b.ann], default=0.0) + 2.5
                lk.dx = {c: base + (lk.n - 1 - k) * S for k, c in enumerate(lk.conds)}
            for k, c in enumerate(lk.conds):
                if lk.dst == "inp":
                    y = b.y - 1.5 - (lk.n - 1 - k) * LAND
                elif lk.dst == "top":  # the first conductor nearest to the top: no crossing on the way down
                    y = b.y - 1.5 - k * LAND
                elif lk.dst == "out":  # (from the right: the first conductor lowest, no crossing)
                    y = b.y + b.h + 1.5 + ((lk.n - 1 - k) if lk.from_right else k) * LAND
                else:  # side input of a transfer switch: arrows toward its blades
                    y = b.y + 3.0 + k * LAND
                lk.land[c] = (b.x_left + offs[c], y)

    def span(lk: _Link) -> tuple[float, float]:
        xs = list(lk.sx.values()) + list(lk.dx.values())
        return min(xs), max(xs)

    def crossings(order: tuple[int, ...]) -> float:
        pos = {k: j for j, k in enumerate(order)}
        n = 0.0
        for i, li in enumerate(links):
            for j, lj in enumerate(links):
                if i == j:
                    continue
                lo, hi = span(lj)
                up = pos[j] < pos[i]
                n += sum(1 for x in li.sx.values() if lo < x < hi) if up else 0  # taps go down through upper lanes
                down_end = li.dst != "rails" or min(y for _, y in li.land.values()) > y0
                if (down_end and not up) or (not down_end and up):
                    n += sum(1 for x in li.dx.values() if lo < x < hi)
        return n + 1e-3 * sum(abs(j - k) for j, k in enumerate(order))

    # vertical conductors of the tree: the devices and their annotations avoid them
    walls: list[tuple[float, float, float]] = []
    for r in roots:
        for n in r.walk():
            for ch in n.children:
                y_from = n.rails_bottom() if n.rails else n.y + n.h
                walls += [(ch.xi(c), y_from - (len(n.out) * S if n.rails else 0.0), ch.y + ch.h) for c in ch.inp]
    for lk in links:
        lk.walls = walls

    ks = tuple(range(len(links)))
    best = min(itertools.permutations(ks), key=crossings) if len(ks) <= 6 else ks
    y = y0
    for k in best:
        lk = links[k]
        lk.top = y
        first = y + len(lk.text) * 2.2 + 3.0
        goes_left = sum(lk.dx.values()) < sum(lk.sx.values())
        for j, c in enumerate(lk.conds):
            idx = lk.n - 1 - j if goes_left else j
            lk.lane[c] = first + idx * S
        y += lk.block_h()


def _h_pole(x0: float, y: float, mark: str) -> list[Item]:
    """One pole of a switching device drawn on a horizontal conductor, from ``x0`` toward +x."""
    return [transform(i, x0, y, rot=270) for i in _contact(0.0, 0.0, mark, DEV_H)]


def _draw_links(doc: Document, links: list[_Link], g: Group, lang: str) -> None:
    for lk in links:
        link, dev = lk.link, lk.link.device
        style = OPEN if (link.normally_open or (dev is not None and dev.normal_state == "open")) else Style()
        index = next(i for i, other in enumerate(doc.links) if other is link)
        lg = add_cls(link_group(doc, index), f"ml-link ml-link-{link.kind}")
        # device: on the lanes, where all of them run horizontally
        s0 = None
        if dev is not None:
            lo = max(min(lk.sx[c], lk.dx[c]) for c in lk.conds) + 1.5
            hi = min(max(lk.sx[c], lk.dx[c]) for c in lk.conds) - 1.5
            tw = max((text_width(t, ANN_SIZE) for t in lk.text), default=0.0)
            if hi - lo >= DEV_H:
                y_top = min(lk.lane.values()) - 3.0 - len(lk.text) * 2.2
                y_bot = max(lk.lane.values()) + 2.5
                walls = [x for x, w0, w1 in lk.walls if w0 < y_bot and y_top < w1]
                walls += [x for o in links for x in list(o.sx.values()) + list(o.dx.values())]
                near_target = sum(lk.dx.values()) / lk.n
                cands = [lo + 0.5 * i for i in range(int((hi - lo - DEV_H) / 0.5) + 1)]
                s0 = min(cands, key=lambda s: sum(1 for x in walls if s - 1.5 < x < max(s + DEV_H, s + tw) + 1.5) * 10
                         + 0.01 * abs(s + DEV_H / 2 - near_target))
        if s0 is not None:  # the open contacts of the device show the normal state: the conductors stay solid
            style = Style()
        for c in lk.conds:
            sx, sy, ly, dx = lk.sx[c], lk.sy[c], lk.lane[c], lk.dx[c]
            lx, lyy = lk.land[c]
            pts = [(sx, sy), (sx, ly), (dx, ly), (dx, lyy)]
            if lk.dst != "rails":
                end = min(x for x, _ in lk.land.values()) - 2.4 if lk.dst == "side" else lx  # beside the blades
                pts.append((min(end, lx) if dx < lx else max(end, lx), lyy))
            cg = cond_group(c)
            cs = Style() if c == "PE" else style  # the PE is never switched: never drawn as open
            if s0 is not None:
                fwd = dx > sx
                a, b = ((s0, ly), (s0 + DEV_H, ly)) if fwd else ((s0 + DEV_H, ly), (s0, ly))
                cg.add(Polyline(pts[:2] + [a], cs), Polyline([b] + pts[2:], cs))
            else:
                cg.add(Polyline(pts, cs))
            if lk.dst == "side":
                tip = pts[-1]
                cg.add(Polyline([(tip[0] - 1.4, tip[1] - 0.7), tip, (tip[0] - 1.4, tip[1] + 0.7)],
                                Style(fill="#000000"), closed=True))
            elif lk.dst == "top":  # turning down into the top of the inverter / UPS
                cg.add(Line((lx, lyy), (lx, lk.b.y), cs))
            else:
                cg.add(_dot(lx, lyy))
            if lk.src == "rails":
                cg.add(_dot(sx, sy))
            lg.add(cg)
        if dev is None and lk.text:  # the link's label above its top lane, in the middle of the longest run
            c0 = min(lk.conds, key=lambda c: lk.lane[c])
            x0, x1 = sorted((lk.sx[c0], lk.dx[c0]))
            lg.add(Text(((x0 + x1) / 2, lk.lane[c0] - 0.8), lk.text[0], ANN_SIZE, "middle"))
        if lk.dst == "out" and not lk.b.children:  # output conductors of a final device: extended to the landings
            for c in lk.conds:
                x = lk.b.xo(c)
                lg.add(cond_group(c, Line((x, lk.b.y + lk.b.h), (x, lk.land[c][1]))))
        if s0 is not None and dev is not None:
            dg = Group(id=dev.id, cls=f"ml-sym ml-{dev.type} ml-link-device")
            prot, unprot = switched(dev, lk.conds)
            mark = {"breaker": "cross", "disconnector": "bar", "switch_disconnector": "switch", "fuse_switch": "switch",
                    "contactor": "arc", "transfer_switch": "switch"}.get(dev.type, "")
            mids = []
            for c in lk.conds:
                ly = lk.lane[c]
                if dev.type == "fuse":
                    dg.add(Group([Line((s0, ly), (s0 + DEV_H, ly)), Rect(s0 + 3.1, ly - 0.8, 6.3, 1.6, Style(fill="#ffffff"))],
                                 cls="pole", attrs={"data-uw-cond": c}))
                    continue
                if c not in prot and c not in unprot:  # conductor not switched: straight through
                    dg.add(cond_group(c, Line((s0, ly), (s0 + DEV_H, ly))))
                    continue
                dg.add(Group(_h_pole(s0, ly, mark if c in prot or mark != "cross" else ""),
                             cls="pole" if c in prot else "pole pole-n", attrs={"data-uw-cond": c}))
                mx, my = _blade_mid(0.0, 0.0)
                mids.append((s0 + my, ly - mx))
            if len(mids) >= 2:
                xm = mids[0][0]
                dg.add(Line((xm, min(m[1] for m in mids) - 0.5), (xm, max(m[1] for m in mids)), DASH))
            lg.add(dg)
            top = min(lk.lane.values())
            tg = Group(cls="annotation")
            for i, t in enumerate(lk.text):
                tg.add(Text((s0, top - 2.6 - (len(lk.text) - 1 - i) * 2.2), t, ANN_SIZE, bold=(i == 0 and bool(dev.ref))))
            lg.add(tg)
        g.add(finish_link_group(lg))


# ------------------------------------------- auxiliary devices, signal links
def _scene_obstacles(g: Group) -> tuple[Obstacles, dict[str, Box]]:
    """What the sheet already shows, for placing the auxiliary devices and routing the links: texts and
    symbols (boxes), conductors and rails (lines), board frames. Also returns the box of every drawn node
    (its symbol, or the frame of a board), by id."""
    obs = Obstacles()
    boxes: dict[str, Box] = {}

    def walk(item: Item) -> None:
        if isinstance(item, Group):
            cls = (item.cls or "").split()
            if "uw-hit" in cls:  # invisible copy of a link's strokes
                return
            if item.id and "ml-sym" in cls:
                # the protective conductor passing beside a device is not part of it: a link leaving beyond
                # it would read as the PE carried on
                pe = [i for i in item.items if isinstance(i, Group) and i.attrs.get("data-uw-cond") in ("PE", "PEN")
                      and "pole" not in (i.cls or "")]
                for i in pe:
                    walk(i)
                shape = [b for i in item.items if not isinstance(i, Text) and i not in pe and (b := bbox(i)) is not None]
                box = boxes_union(shape) or bbox(item)
                if box is not None:
                    boxes.setdefault(item.id, box)
                    obs.add_box(box)
                for i in item.items:
                    if isinstance(i, Text):
                        obs.add_box(bbox(i))
                return
            if item.id and "board" in cls:
                frame = next((i for i in item.items if isinstance(i, Rect)), None)
                if frame is not None:
                    boxes[item.id] = (frame.x, frame.y, frame.x + frame.w, frame.y + frame.h)
            for i in item.items:
                walk(i)
        elif isinstance(item, Text):
            obs.add_box(bbox(item))
        elif isinstance(item, Rect):
            if item.style.dash:
                obs.add_frame((item.x, item.y, item.x + item.w, item.y + item.h))
            else:
                obs.add_box((item.x, item.y, item.x + item.w, item.y + item.h))
        elif isinstance(item, (Line, Polyline)) and not getattr(item, "closed", False):
            pts = [item.a, item.b] if isinstance(item, Line) else item.points
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if abs(y0 - y1) < 1e-9:
                    obs.add_hline(y0, x0, x1, bus=item.style.width >= THICK)
                    obs.conductors.append(("h", y0, min(x0, x1), max(x0, x1)))
                elif abs(x0 - x1) < 1e-9:
                    obs.add_vline(x0, y0, y1)
                    obs.conductors.append(("v", x0, min(y0, y1), max(y0, y1)))

    walk(g)
    return obs, boxes


SIGNAL_PITCH = 2.2  # per link in the band reserved for the signal links above the feeder cables
ML_FRAME_CLEAR = 6.0  # a link beside a frame: the multi-line sheet is often drawn reduced
ML_LANE = 3.0  # between two parallel links (same reason; room for a label between them)


def _signal_band(doc: Document, roots: list[MLNode]) -> float:
    """Room above the feeder cables for the channels of the links drawn by ``_draw_annex``."""
    from .engine import _device_homes

    ids = {n.node.id for r in roots for n in r.walk() if n.node is not None and n.node.id}
    ids |= {d for d, h in _device_homes(doc).items() if h in ids}
    n = sum(1 for link in doc.links if link.kind not in ML_LINKS and link.from_ in ids and link.to in ids)
    return n * SIGNAL_PITCH + 2.0 * ML_FRAME_CLEAR if n else 0.0  # clear of the board frames above


def _pad_boards(doc: Document, roots: list[MLNode]) -> None:
    """Room at the bottom of each board frame for the channels of the signal links of the devices inside it
    (as in the single-line diagram): the frame does not hug the devices the links run under."""
    ends: dict[str, int] = {}
    for link in doc.links:
        if link.kind not in ML_LINKS:
            for nid in (link.from_, link.to):
                ends[nid] = ends.get(nid, 0) + 1
    for r in roots:
        for b in r.walk():
            if b.is_board:
                n = sum(ends.get(m.node.id, 0) for m in _owned(b) if m.node is not None and m.node.id)
                b.pad_bottom = ML_FRAME_CLEAR + n * ML_LANE if n else 0.0
            elif b.kind == "node" and b.type not in ("fuse", "plc") and not b.bottom and b.node is not None \
                    and ends.get(b.node.id) and (b.type in CONTACT_TYPES or not b.root):
                # a channel between the device and its text: a link comes to its right side and runs down there
                # (as the link of a residual-current toroid), not round the device through its conductors
                b.link_gap = 3.5 + (ends[b.node.id] - 1) * ML_LANE


def _proxy(n: MLNode, box: Box) -> LNode:
    """A drawn node seen as a single-line node of the same footprint (for the shared placement and routing);
    its text on the right, so that no link leaves through it."""
    x0, y0, x1, y1 = box
    # a link to a board ends on its PE bar (or on the PE bar of the busbar it holds)
    bars = next((m for m in n.walk() if m.rail_y0 is not None and "PE" in m.out), None) if n.is_board else None
    if bars is not None:
        ype = bars.rail_y0 + [c for c in bars.out if not (bars.dc_side and c in DC)].index("PE") * S
        x0, y0, x1, y1 = bars.xo("PE") - 0.5, ype - 0.5, bars.xo("PE") + 0.5, ype + 0.5
    if n.type == "plc":  # drawn with its single-line symbol: the ports of its modules are where they are there
        ln = LNode(n.node, "node", symbol_for(n.node))
        ln.sym.extra.update(end_gap=0.0, body_top=0.8 * M + 0.5)  # links beside its body, not above it
        (ln.x, ln.y), ln.bottom = _plc_origin(n), n.bottom
        ln.ann, ln.ann_size = n.ann, n.ann_size  # a protocol it already names is not repeated on its links
        ln.ann_off = (n.x_left + n.right() + 1.0 - (ln.x + ln.sym.right) - 1.0, n.y - ln.y)
        return ln
    extra: dict = {"text_gap": 1.5, "end_gap": 0.0,  # a link leaving below the device's text keeps clear of it
             # a final device (not a switching one, whose conductors go on below it): links may leave below it
             "free_below": not n.children and not n.bottom and not n.is_board and n.type not in CONTACT_TYPES}
    if n.type in CONTACT_TYPES and n.type != "fuse":  # a control or trip link acts on the operating line of the
        live = sorted(n.xi(c) for c in n.inp if c != "PE")  # poles (their dashed mechanical linkage), at its left end
        if live:
            mx, my = _blade_mid(live[0], n.y)
            x0 = min(x0, mx - 0.6)
            extra["end_y"] = my - y0
            extra["right_end"] = (_blade_mid(live[-1], n.y)[0] + 0.6, my)
            extra["turn"] = True  # a link there turns down at once (see engine._draw_links)
    elif n.link_gap and not n.is_board:  # a boxed device with a channel beside it (see _pad_boards)
        extra["right_end"] = (x1, (y0 + y1) / 2)
    if "PE" in n.inp and n.kind == "node" and not n.is_board:  # an earth link leaves from the feeder's PE,
        extra["pe_end"] = (n.xi("PE"), n.y - 1.5)  # just above the device: clear of its text
    ln = LNode(n.node, "node", Symbol("ml-proxy", [], y1 - y0, (x1 - x0) / 2, (x1 - x0) / 2, has_output=False,
                                      extra=extra))
    ln.x, ln.y, ln.bottom = (x0 + x1) / 2, y0, n.bottom
    if n.ann and not n.is_board:
        ln.ann, ln.ann_size = n.ann, n.ann_size
        ln.ann_off = (n.x_left + n.right() + 1.0 - x1 - 1.0, n.y - y0)
    return ln


def _draw_annex(doc: Document, roots: list[MLNode], g: Group, view: View, spec: SheetSpec, lang: str,
                node_folio: Callable[[str], Optional[int]] | None) -> None:
    """Auxiliary devices (``devices``) beside the node they are linked to, and the links the power drawing
    leaves out (control, interlock, trip, measure, data, key, earth, and the ends of links whose other end
    is on another sheet), routed as in the single-line diagram."""
    from .engine import ANN_LINE as SL_LINE
    from .engine import ANN_SIZE as SL_SIZE
    from .engine import _annotate as sl_annotate
    from .engine import _device_homes, _draw_links, _place_devices

    obs, boxes = _scene_obstacles(g)
    obs.box_cross = obs.run_along = 1000.0  # a bundle of conductors is crossed freely, a symbol never, nor a line run on
    obs.frame_clear, obs.frame_along = ML_FRAME_CLEAR, 3 * FRAME_CROSS  # out of a frame and back: better
    obs.min_lane, obs.label_pad = ML_LANE, 1.5  # a label close to a device's text would read as part of it
    obs.label_channel = obs.grid = True
    obs.near_wire = S - 0.5  # between two conductors of a bundle is never a place for a link
    proxies = [_proxy(n, boxes[n.node.id]) for r in roots for n in r.walk()
               if n.kind == "node" and n.node is not None and n.node.id in boxes]
    # devices kept off the frames by the room a link needs to pass between them (edges as boxes, placing only)
    c = ML_FRAME_CLEAR
    edges = [b for f in obs.frames for b in ((f[0] - c, f[1], f[0] + c, f[3]), (f[2] - c, f[1], f[2] + c, f[3]),
                                             (f[0], f[1] - c, f[2], f[1] + c), (f[0], f[3] - c, f[2], f[3] + c))]
    obs.boxes += edges
    from .engine import _right_end

    # a node whose right side is all text takes its links on the left: its devices are put there
    annex = _place_devices(doc, proxies, proxies, view, lang, obs, view.pitch_mm,
                           lambda n: n.sym.name == "ml-proxy" and _right_end(n) is None and not n.sym.extra.get("free_below"))
    obs.boxes = [b for b in obs.boxes if b not in edges]
    by_id = {p.node.id: p for p in proxies if p.node is not None}
    for ln in annex:  # an earth electrode level with the PE its link leaves from: no jog in a short link
        ends = [lk for lk in doc.links if lk.kind == "earth" and ln.node is not None and ln.node.id in (lk.from_, lk.to)]
        other = by_id.get(ends[0].to if ends[0].from_ == ln.node.id else ends[0].from_) if len(ends) == 1 else None
        pe = other.sym.extra.get("pe_end") if other is not None and ln.sym.name in ("earth", "earth_bar") else None
        if pe is not None and 0 < abs(pe[1] - ln.y) <= 2.5:
            old = [ln.sym_box(), ln.ann_box()]
            ln.y = pe[1]
            obs.boxes = [b for b in obs.boxes if b not in old] + [b for b in (ln.sym_box(), ln.ann_box()) if b]
    homes = _device_homes(doc)
    unlinked = [d for d in doc.devices if homes.get(d.id or "") is None]
    if unlinked and not spec.continuation and (not spec.roots or spec.roots == list(doc.sources) or view.root):
        box = boxes_union(obs.boxes)
        ax0 = (box[2] if box else 0) + 12.0
        g.add(Text((ax0 - 2.0, -3.0), _t("render.auxiliary_devices", lang), 2.0, bold=True))
        for i, dev in enumerate(unlinked):
            ln = LNode(dev, "node", symbol_for(dev))
            ln.x, ln.y, ln.width, ln.x_left = ax0 + ln.sym.left, 1.0 + i * 16.0, view.pitch_mm, ax0 - 2
            sl_annotate(ln, view, lang, avail_override=60.0)
            annex.append(ln)
            obs.add_box(ln.sym_box())
            obs.add_box(ln.ann_box())
    for ln in annex:  # without the leads of their symbol, which would read as conductors of a feeder
        ln.sym.extra.update(end_gap=0.0, free_below=True)  # links touch the symbol, may leave below it
        earth = ln.sym.name in ("earth", "earth_bar")  # (an electrode keeps its conductor: the link ends on it)
        items = [i for i in ln.sym.items if earth or not (isinstance(i, Line) and i.a[0] == i.b[0] == 0.0
                                                 and (min(i.a[1], i.b[1]) <= 0.0 or max(i.a[1], i.b[1]) >= ln.sym.height))]
        vis = bbox(Group(items))
        if vis is not None and not earth:  # links leaving below start from what is drawn, not the lead taken off
            ln.sym.extra["bottom_y"] = vis[3]
        g.add(node_group(Group([transform(i, ln.x, ln.y) for i in items], ln.id, f"sym sym-{ln.sym.name}")))
        if ln.ann:
            ab = ln.ann_box()
            assert ab is not None
            for i, t in enumerate(ln.ann):
                g.add(Text((ab[0], ln.y + 0.3 + (i + 0.8) * SL_LINE * ln.ann_size / SL_SIZE), t, ln.ann_size,
                           bold=(i == 0 and ln.tagged)))
    drawn = {ln.node.id for ln in proxies + annex if ln.node is not None}
    only = {i for i, link in enumerate(doc.links)
            if link.kind not in ML_LINKS or not (link.from_ in drawn and link.to in drawn)}
    if not only:
        return
    tops = [ln.y for ln in proxies if ln.bottom]
    y_load = min(tops) if tops else (bbox(g) or (0.0, 0.0, 0.0, 0.0))[3] + 40.0
    # first drawing on copies: the side each link takes; then the links drawn with their ends in order
    import copy

    sides = _draw_links(doc, proxies + annex, {}, Group(), view, copy.deepcopy(obs), y_load, lang, node_folio,
                        None, only)
    _draw_links(doc, proxies + annex, {}, g, view, obs, y_load, lang, node_folio, None, only, sides)


# -------------------------------------------------------------- sheet layout
def _layout(doc: Document, view: View, spec: SheetSpec, index: Index, info: dict[int, Conductors],
            folio_of: Callable[[str], Optional[int]] | None = None,
            continuation: tuple[Optional[int], Optional[int]] = (None, None),
            incoming: Optional[str] = None,
            incoming_ref: tuple[Optional[int], Optional[str]] = (None, None),
            marks: Optional[dict[str, dict[str, str]]] = None,
            node_folio: Callable[[str], Optional[int]] | None = None, annex: bool = True) -> SheetLayout:
    lang = normalize_lang(doc.meta.lang)
    roots = _build_roots(spec, index, info)
    for r in roots:
        _assign_offsets(r, None)
    _annotate(roots, view, lang)
    for r in roots:
        for n in r.walk():
            n.h = _height(n)
    links = _plan_links(doc, roots, lang)
    _pad_boards(doc, roots)
    x = 0.0
    for r in roots:
        _measure(r)
        _place_x(r, x + r.lead)
        x += r.width + COL_GAP
    for r in roots:
        top = 6.0 if r.root and r.kind == "node" and r.type not in SOURCE_TYPES else 0.0
        if r.kind == "bus_in":
            top = 4.0
        _place_y(r, top, None)
        _separate_boards(r)
    _make_room(links, roots)
    everything = [n for r in roots for n in r.walk()]
    bottoms = [n for n in everything if n.bottom]
    others = [n for n in everything if not n.bottom]
    y_base = max([n.content_bottom() for n in others] + [_frame_bottom(n) for n in others if n.is_board] + [0.0])
    y_load = y_base + CABLE_BAND + _signal_band(doc, roots)
    for n in bottoms:
        n.y = max(n.y, y_load)
    g = Group(cls="multiline")
    sheet_left = 0.0
    _route_links(links, roots)
    for r in roots:
        _draw(r, g, lang, view, sheet_left, folio_of or (lambda _: None), continuation, incoming, incoming_ref)
    _draw_links(doc, links, g, lang)
    _draw_frames(roots, g)
    if annex:  # (left out while the sheets are being planned: the band for its links is reserved anyway)
        _draw_annex(doc, roots, g, view, spec, lang, node_folio)
    if marks:
        tops = {n.id: (n.frame_top if n.is_board else n.y) for r in roots for n in r.walk()}
        # a cable carried by a device above a load is drawn as the load's feeder cable: marked there too
        parent = {id(c): n for r in roots for n in r.walk() for c in n.children}
        marks = dict(marks)
        for n in (n for r in roots for n in r.walk() if n.bottom and n.kind == "node"):
            holder = _feeder_cable(n, parent)
            if holder is not None and holder is not n and holder.id in marks and n.id not in marks:
                marks[n.id] = marks.pop(holder.id)
        _draw_wire_marks(g, marks, tops)
    box = bbox(g) or (0.0, 0.0, 10.0, 10.0)
    g = transform(g, -box[0], -box[1])  # type: ignore[assignment]
    return SheetLayout(spec, g, box[2] - box[0], box[3] - box[1], [], [])  # type: ignore[arg-type]


MARK_SIZE = 1.3


def _lowest(items: list[Any]) -> Optional[tuple[float, float, float]]:
    """Lowest end point of the strokes of a conductor group (where it reaches the node it feeds), and the y of
    the top of the vertical segment ending there: (x, y, y_top)."""
    best: Optional[tuple[float, float, float]] = None
    for it in items:
        if isinstance(it, Line):
            segs = [(it.a, it.b)]
        elif isinstance(it, Polyline) and not it.closed:
            segs = list(zip(it.points, it.points[1:]))
        else:
            continue
        for a, b in segs:
            if abs(a[0] - b[0]) > 1e-6:
                continue
            lo, hi = (a, b) if a[1] > b[1] else (b, a)
            if best is None or lo[1] > best[1]:
                best = (lo[0], lo[1], hi[1])
    return best


def _draw_wire_marks(g: Group, marks: dict[str, dict[str, str]], tops: dict[str, float]) -> None:
    """Wire marks (UEP-0001 §3.5.3): ``data-uw-mark`` on each conductor group of the edge feeding a node whose
    cable is marked, and the mark written along the conductor, left of it, just above the node it feeds (above
    the frame of a board). ``marks``: {node id: {drawn conductor: mark}}."""
    for it in g.items:
        if not isinstance(it, Group):
            continue
        nid = it.attrs.get("data-uw-edge")
        if nid is None or nid not in marks:
            _draw_wire_marks(it, marks, tops)
            continue
        written: set[str] = set()
        texts: list[tuple[Group, Text]] = []
        room = True
        for cg in list(it.items):
            if not isinstance(cg, Group) or "data-uw-cond" not in cg.attrs:
                continue
            mark = marks[nid].get(cg.attrs["data-uw-cond"])
            if not mark:
                continue
            cg.attrs["data-uw-mark"] = mark
            end = _lowest(cg.items)
            if end is None or mark in written and cg.attrs["data-uw-cond"] in ("N", "PE"):
                continue  # the N and PE of a PEN split share the PEN core: written once
            written.add(mark)
            y = min(end[1], tops.get(nid, end[1])) - 1.0
            room = room and y - text_width(mark, MARK_SIZE) >= end[2] + 1.5
            texts.append((cg, Text((end[0] - 0.9, y), mark, MARK_SIZE, "start", "middle", rotate=90, color="#333333")))
        if room:  # written only when every conductor of the edge has room (else data-uw-mark only)
            for cg, txt in texts:
                cg.add(txt)


def layout_multiline(doc: Document, view: View, spec: SheetSpec, index: Index | None = None,
                     **kwargs: Any) -> SheetLayout:
    """Lay out one sheet of the multi-line diagram (same sheet description as the single-line one)."""
    index = index or build_index(doc)
    info = _Assigner(doc, getattr(view, "show_pe", True)).info
    return _layout(doc, view, spec, index, info, **kwargs)


def _fit(lay: SheetLayout, view: View) -> float:
    _, _, aw, ah = drawing_area(view)
    return min(1.0, aw / max(lay.width, 1e-6), ah / max(lay.height, 1e-6))


def _in_spec(spec: SheetSpec, nid: str, index: Index) -> bool:
    anc = {a.id for a in index.ancestors(nid)}
    return any(r.id in anc for r in spec.roots)


def _ordered(spec: SheetSpec, index: Index) -> list[str]:
    order: list[str] = []

    def walk(n: NodeBase, top: bool) -> None:
        if not top and n.id in spec.detached:
            order.append(n.id)  # type: ignore[arg-type]
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


def plan_multiline(doc: Document, view: View, index: Index | None = None,
                   info: dict[int, Conductors] | None = None) -> list[SheetSpec]:
    """Split the multi-line diagram into sheets: a sub-board too wide for the sheet goes to a sheet of its own,
    then the most crowded busbar is cut into continuation sheets."""
    index = index or build_index(doc)
    info = info or _Assigner(doc, getattr(view, "show_pe", True)).info
    lang = normalize_lang(doc.meta.lang)
    forced = {n.id for n in index.nodes.values() if n.type == "board" and getattr(n, "own_sheet", False)}  # type: ignore[attr-defined]

    def process(spec: SheetSpec, allow_bus_split: bool = True) -> list[SheetSpec]:
        root_ids = {r.id for r in spec.roots}
        spec.detached |= {f for f in forced if f not in root_ids and _in_spec(spec, f, index)}
        conts: list[SheetSpec] = []
        for _ in range(60):
            lay = _layout(doc, view, spec, index, info, annex=False)
            if view.folio_split == "none" or _fit(lay, view) >= view.min_scale:
                break
            roots = _build_roots(spec, index, info)
            for r in roots:
                _assign_offsets(r, None)
            _annotate(roots, view, lang)
            for r in roots:
                _measure(r)
            boards = [n for r in roots for n in r.walk() if n.is_board and n.node is not None and n.node.id not in root_ids
                      and n.node.id not in spec.detached and len(n.children) >= 1]
            if boards:
                boards.sort(key=lambda n: -n.width)
                spec.detached.add(boards[0].node.id)  # type: ignore[union-attr]
                continue
            if allow_bus_split:
                conts = _split_bus(spec, roots, view, lang)
            break
        out = [spec]
        for c in conts:
            out += process(c, allow_bus_split=False)
        for nid in _ordered(spec, index):
            n = index.nodes[nid]
            out += process(SheetSpec([n], name=_board_name(n)))
        return out

    roots = [index.nodes[view.root]] if view.root else list(doc.sources)
    return process(SheetSpec(roots, name=""))


def _split_bus(spec: SheetSpec, roots: list[MLNode], view: View, lang: str) -> list[SheetSpec]:
    cands = [n for r in roots for n in r.walk() if n.kind == "node" and n.rails and n.node is not None
             and len(n.children) >= 3]
    if not cands:
        return []
    bus = max(cands, key=lambda n: sum(c.width for c in n.children))
    node = bus.node
    assert node is not None
    _, _, aw, _ = drawing_area(view)
    cap = aw / view.min_scale - 20.0
    first_cap = cap - (bus.x_left + bus.lanes_max() + RAIL_IN)
    chunks: list[tuple[int, int]] = []
    start, acc = 0, 0.0
    for i, c in enumerate(bus.children):
        limit = first_cap if not chunks else cap - 30.0
        if acc + c.width > limit and i > start:
            chunks.append((start, i))
            start, acc = i, 0.0
        acc += c.width
    chunks.append((start, len(bus.children)))
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


def multiline_layouts(doc: Document, view: View, index: Index | None = None) -> list[SheetLayout]:
    """All the sheets of the multi-line diagram, laid out (cross-sheet references resolved)."""
    index = index or build_index(doc)
    lang = normalize_lang(doc.meta.lang)
    info = _Assigner(doc, getattr(view, "show_pe", True)).info
    specs = plan_multiline(doc, view, index, info)
    marks: Optional[dict[str, dict[str, str]]] = None
    if marks_shown(view):
        marks = {}
        for w in marked_wires(doc, view, index, specs):
            for c in w.drawn:
                if w.mark:
                    marks.setdefault(w.node, {})[c] = w.mark
    folio_by_root: dict[str, int] = {}
    for i, s in enumerate(specs, 1):
        if s.roots and not s.continuation and i > 1:
            folio_by_root[s.roots[0].id or ""] = i
    number = {id(s): i for i, s in enumerate(specs, 1)}
    sheet_of: dict[str, int] = {}  # sheet of every node and auxiliary device (its first sheet)
    for i, s in enumerate(specs, 1):
        for nid in sheet_node_ids(doc, s, index):
            sheet_of.setdefault(nid, i)
    out = []
    for i, spec in enumerate(specs, 1):
        prev_f = number.get(id(spec.prev)) if spec.prev is not None else None
        next_f = number.get(id(spec.next)) if spec.next is not None else None
        incoming = None
        incoming_ref: tuple[Optional[int], Optional[str]] = (None, None)
        if i > 1 and spec.roots and not spec.continuation:
            rid = spec.roots[0].id
            src = next((j for j, s in enumerate(specs, 1) if rid in s.detached and j != i), None)
            incoming_ref = (src, index.parent.get(rid or ""))
            feeder = next((a for a in index.ancestors(rid or "") if a.ref), None)
            what = _t("render.incoming_from", lang, ref=feeder.ref) if feeder is not None else _t("render.incoming", lang)
            incoming = _t("render.incoming_folio", lang, what=what, folio=src) if src else what
        out.append(_layout(doc, view, spec, index, info, folio_of=folio_by_root.get, continuation=(prev_f, next_f),
                           incoming=incoming, incoming_ref=incoming_ref, marks=marks, node_folio=sheet_of.get))
    return out
