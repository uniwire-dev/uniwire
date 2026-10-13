"""Wire marking of the power conductors (UEP-0001 §3.5, the part available in the current format).

The current format has no ``wires[]`` section: the wires it can mark are the conductors of the cables of the power tree.
The cable of a node (``node.cable``) feeds it from its parent and carries the conductors that the multi-line
derivation gives to the node's input (:func:`uniwire.layout.multiline.conductors`); a conductor that starts in
the node (a PE at the main earthing terminal) is not part of the cable, and the ``N`` / ``PE`` of a board that
splits a PEN arrive on a single ``PEN`` core.

Each such conductor is a :class:`Wire` with the identifiers that format 2.0 gives to implicit wires: the cable
``<node id>.cable`` and the wire ``<node id>.cable.<conductor>``. Its mark comes from the cable's ``marks``
(manual marks) and from the ``wire_marking`` rules of a view (:class:`uniwire.model.WireMarking`):

>>> from uniwire.marks import marked_wires
>>> for w in marked_wires(doc, view):           # doctest: +SKIP
...     print(w.id, w.mark)                     # M1.cable.L1 101

The CSV exports built on these wires are in :mod:`uniwire.exports`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Optional

from .model import Cable, Document, NodeBase, View
from .model.document import _TOKEN
from .resolve import Index, build_index, iter_nodes

ORDER = {c: i for i, c in enumerate(("L1", "L2", "L3", "L+", "L-", "N", "PEN", "PE"))}
CUTTING = {"breaker", "disconnector", "switch_disconnector", "contactor", "impulse_relay", "rcd", "rcbo",
           "main_breaker", "fuse", "fuse_switch", "transfer_switch", "spare", "thermal_relay", "motor_starter"}
NEW_SYSTEM = {"transformer", "inverter", "dc_converter", "power_supply", "ups"}


@dataclass
class Wire:
    """A conductor of a cable of the power tree, between the device feeding the cable and the node it feeds."""

    id: str  # '<node id>.cable.<conductor>'
    cable_id: str  # '<node id>.cable'
    node: str  # id of the node fed by the cable (the 'to' end)
    conductor: str  # L1, L2, L3, N, PE, PEN, L+, L-
    drawn: tuple[str, ...]  # conductors of the node's input carried by this core (N + PE after a PEN split)
    cable: Cable
    from_id: str = ""
    from_display: str = ""
    from_enclosure: str = ""
    to_id: str = ""
    to_display: str = ""
    to_enclosure: str = ""
    circuit: str = ""
    manual: Optional[str] = None  # mark written in the document (cable 'marks')
    mark: str = ""
    net: tuple = field(default=(), repr=False)  # identity of the potential (derived net) of the conductor

    @property
    def section_mm2(self) -> Optional[float]:
        """Cross-section of this conductor: the cable's PE / neutral section when given, else its phase section."""
        c = self.cable
        if self.conductor in ("PE", "PEN") and c.pe_section_mm2:
            return c.pe_section_mm2
        if self.conductor == "N" and c.neutral_section_mm2:
            return c.neutral_section_mm2
        return c.section_mm2

    @property
    def cable_ref(self) -> str:
        """Tag of the cable carrying the conductor (``cable.ref``), or ``""``."""
        return self.cable.ref or ""


def display(node: Optional[NodeBase]) -> str:
    """Display form of a node in exports: its ``ref``, else its ``id``."""
    if node is None:
        return ""
    return node.ref or node.id or ""  # type: ignore[attr-defined]


def _enclosures(doc: Document) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in doc.enclosures:
        for nid in e.nodes:
            out.setdefault(nid, e.id)
    return out


def enclosure_at(node: Optional[NodeBase], index: Index, encl: dict[str, str], upward: bool) -> str:
    """Enclosure (or ``board`` node) holding ``node``: an ``enclosures[]`` entry listing it, a board it is, and, with
    ``upward`` (the end of a cable leaving a device), the same for its ancestors."""
    if node is None:
        return ""
    chain = [node] + (index.ancestors(node.id or "") if upward else [])
    for n in chain:
        if n.id in encl:
            return encl[n.id]  # type: ignore[index]
        if n.type == "board":  # type: ignore[attr-defined]
            return n.id or ""
    return ""


def _circuit(node: NodeBase, index: Index) -> str:
    """``circuit`` of the feeder: the node's, else that of the devices above it up to the busbar."""
    if getattr(node, "circuit", None):
        return node.circuit  # type: ignore[attr-defined]
    for n in index.ancestors(node.id or ""):
        if n.type in ("board", "busbar") or len(n.children) >= 2:  # type: ignore[attr-defined]
            break
        if getattr(n, "circuit", None):
            return n.circuit  # type: ignore[attr-defined]
    return ""


class _Nets:
    """Potentials of the power conductors (UEP-0001 §3.4.2) from the multi-line derivation: a conductor keeps its
    net through boards, busbars, meters and every device that does not switch it; a pole of a switching device,
    a transformer / converter and the neutral created by a PEN split start a new one."""

    def __init__(self, doc: Document, index: Index, info: dict[int, Any]):
        from .layout.multiline import switched

        self.index, self.info = index, info
        self._switched = switched

    def _cuts(self, node: NodeBase, cond: str) -> bool:
        t = node.type  # type: ignore[attr-defined]
        c = self.info.get(id(node))
        if c is None:
            return True
        if t in NEW_SYSTEM and cond != "PE":
            return True
        if cond not in c.inp:
            return True  # created by the node (output of a transformer...)
        if t in CUTTING:
            if t == "motor_starter" and (getattr(node, "method", None) or "dol") in ("vfd", "soft_starter"):
                return True  # a drive: a new output on every live conductor
            sw, npole = self._switched(node, c.inp)
            return cond in sw or cond in npole
        return False

    def out_net(self, node: NodeBase, cond: str) -> tuple:
        """Net of output conductor ``cond`` of ``node``."""
        while True:
            if self._cuts(node, cond):
                return ("out", node.id, cond)
            c = self.info[id(node)]
            src = c.src.get(cond)
            parent_id = self.index.parent.get(node.id or "")
            if src is None or parent_id is None:
                return ("start", node.id, cond)
            if cond == "N" and src == "PEN":
                return ("split", node.id, "N")  # the PEN continues as the PE; the N is a new net
            node, cond = self.index.nodes[parent_id], src


def cable_wires(doc: Document, index: Optional[Index] = None) -> list[Wire]:
    """The conductors of every cable of the power tree, in document order, without marks."""
    from .layout.multiline import _Assigner

    index = index or build_index(doc)
    info = _Assigner(doc, True).info
    nets = _Nets(doc, index, info)
    encl = _enclosures(doc)
    out: list[Wire] = []
    for node, parent, _ in iter_nodes(doc):
        cable = node.cable
        if cable is None or parent is None or id(node) not in info:
            continue
        c = info[id(node)]
        by_cond: dict[str, list[str]] = {}
        for cond in c.inp:
            s = c.src.get(cond)
            if s is None:
                continue  # starts in the node: not carried by the cable
            by_cond.setdefault("PEN" if s == "PEN" else cond, []).append(cond)
        cid = f"{node.id}.cable"
        for cond in sorted(by_cond, key=lambda k: ORDER.get(k, 99)):
            src = c.src[by_cond[cond][0]] or cond
            out.append(Wire(
                id=f"{cid}.{cond}", cable_id=cid, node=node.id or "", conductor=cond, drawn=tuple(by_cond[cond]),
                cable=cable, from_id=parent.id or "", from_display=display(parent),
                from_enclosure=enclosure_at(parent, index, encl, True), to_id=node.id or "", to_display=display(node),
                to_enclosure=enclosure_at(node, index, encl, False), circuit=_circuit(node, index),
                manual=(cable.marks or {}).get(cond), net=nets.out_net(parent, src)))  # type: ignore[arg-type]
    return out


def _sheet_edges(spec: Any, index: Index) -> Iterable[str]:
    """Ids of the nodes whose feeding edge is drawn on the sheet ``spec``, column by column, top to bottom."""

    def walk(n: NodeBase) -> Iterable[str]:
        yield n.id or ""
        if n.id in spec.detached:
            return
        kids = list(n.children)
        if spec.bus_slice and spec.bus_slice[0] == n.id:
            kids = kids[spec.bus_slice[1]:spec.bus_slice[2]]
        for k in kids:
            yield from walk(k)

    if spec.continuation:
        nid, s, e = spec.continuation
        for k in index.nodes[nid].children[s:e]:
            yield from walk(k)
        return
    for r in spec.roots:
        kids = list(r.children)
        if spec.bus_slice and spec.bus_slice[0] == r.id:
            kids = kids[spec.bus_slice[1]:spec.bus_slice[2]]
        for k in kids:
            yield from walk(k)


def layout_positions(doc: Document, view: View, index: Index, specs: Optional[list[Any]] = None) -> dict[str, tuple[int, int]]:
    """(sheet number, rank) of the edge feeding each node in the multi-line drawing of ``view``."""
    if specs is None:
        from .layout.multiline import plan_multiline

        v = view if view.kind == "multi-line" else view.model_copy(update={"kind": "multi-line"})
        specs = plan_multiline(doc, v, index)
    pos: dict[str, tuple[int, int]] = {}
    for i, spec in enumerate(specs, 1):
        for nid in _sheet_edges(spec, index):
            pos.setdefault(nid, (i, len(pos)))
    return pos


def _fill(pattern: str, tokens: dict[str, str]) -> str:
    return _TOKEN.sub(lambda m: tokens.get(m[1], ""), pattern)


def marked_wires(doc: Document, view: Optional[View] = None, index: Optional[Index] = None,
                 specs: Optional[list[Any]] = None) -> list[Wire]:
    """The cable conductors with their marks, following the ``wire_marking`` rules of ``view`` (none: the manual
    marks only), in numbering order. Deterministic: the same document and view always give the same marks."""
    index = index or build_index(doc)
    wires = cable_wires(doc, index)
    rules = view.wire_marking if view is not None else None
    if rules is None or rules.scheme == "manual":
        for w in wires:
            w.mark = w.manual or ""
        return wires
    assert view is not None
    doc_rank = {w.id: i for i, w in enumerate(wires)}
    pos: dict[str, tuple[int, int]] = {}
    if rules.order == "layout" or rules.per == "sheet":
        pos = layout_positions(doc, view, index, specs)
    far = (1 << 30, 1 << 30)
    if rules.order == "layout":
        wires.sort(key=lambda w: (pos.get(w.node, far), doc_rank[w.id]))

    def group_key(w: Wire) -> Any:
        if rules.per == "sheet":
            return pos.get(w.node, far)[0]
        if rules.per == "enclosure":
            return w.from_enclosure
        return None

    used = {w.manual for w in wires if w.manual} if rules.keep_manual else set()
    counters: dict[Any, int] = {}
    net_marks: dict[tuple[Any, tuple], str] = {}

    def number(g: Any) -> str:
        n = counters.get(g, rules.start)
        while f"{rules.prefix}{n}{rules.suffix}" in used:
            n += rules.step
        counters[g] = n + rules.step
        return f"{rules.prefix}{n}{rules.suffix}"

    for w in wires:
        g = group_key(w)
        if w.manual and rules.keep_manual:
            w.mark = w.manual
            continue
        if rules.power == "none":
            w.mark = ""
            continue
        if rules.scheme == "pattern":
            n = counters.get(g, rules.start)
            counters[g] = n + rules.step
            w.mark = _fill(rules.pattern or "", {
                "circuit": w.circuit, "conductor": w.conductor, "ref": w.from_display, "from": w.from_display,
                "to": w.to_display, "cable": w.cable_ref or w.cable_id, "n": f"{rules.prefix}{n}{rules.suffix}"})
            continue
        if rules.power == "conductor":
            w.mark = w.conductor
            continue
        if rules.scheme == "potential":
            key = (g, w.net)
            if key not in net_marks:
                net_marks[key] = number(g)
            w.mark = net_marks[key]
        else:  # sequential
            w.mark = number(g)
    return wires


def marks_shown(view: Optional[View]) -> bool:
    """True when the multi-line drawing of ``view`` shows wire marks."""
    return view is not None and view.wire_marking is not None and view.wire_marks is not False


def freeze(data: dict[str, Any], doc: Document, wires: list[Wire]) -> tuple[int, list[str]]:
    """Write the marks of ``wires`` into the cable ``marks`` of the raw document ``data`` (the parsed JSON file
    ``doc`` was loaded from), so that later edits do not renumber printed ferrules. Returns the number of marks
    written and the ids of the cables that could not be written (cable given by a template only)."""
    by_node: dict[str, dict[str, str]] = {}
    for w in wires:
        if w.mark:
            by_node.setdefault(w.node, {})[w.conductor] = w.mark
    written, skipped = 0, []

    def walk(node: NodeBase, raw: dict[str, Any]) -> None:
        nonlocal written
        marks = by_node.get(node.id or "")
        if marks:
            cab = raw.get("cable")
            if isinstance(cab, dict):
                cab["marks"] = {**(cab.get("marks") or {}), **marks}
                cab["marks"] = dict(sorted(cab["marks"].items(), key=lambda kv: ORDER.get(kv[0], 99)))
                written += len(marks)
            else:
                skipped.append(f"{node.id}.cable")
        for child, rc in zip(node.children, raw.get("children") or []):
            if isinstance(rc, dict):
                walk(child, rc)

    for src, raw in zip(doc.sources, data.get("sources") or []):
        if isinstance(raw, dict):
            walk(src, raw)
    return written, skipped

