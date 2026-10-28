"""Generic rules (always active)."""

from __future__ import annotations

import re
from collections import defaultdict

from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import Finding, rule


@rule("core")
def unique_refs_per_board(doc: Document, idx: Index):
    """A tag must be unique within a board (it may repeat from one board to another)."""
    seen: dict[tuple[str, str], str] = {}
    for nid, n in idx.nodes.items():
        if not n.ref:
            continue
        board = next((a.id for a in idx.ancestors(nid) if a.type == "board"), "")  # type: ignore[attr-defined]
        key = (board or "", n.ref)
        if key in seen:
            yield Finding("warning", "core.ref-unique", _t("core.ref_unique", ref=n.ref, other=seen[key]), nid)
        else:
            seen[key] = nid


@rule("core")
def links_consistency(doc: Document, idx: Index):
    for l in doc.links:
        a, b = idx.nodes.get(l.from_), idx.nodes.get(l.to)
        if a is None or b is None:
            continue
        if l.kind == "transfer" and b.type != "transfer_switch":  # type: ignore[attr-defined]
            yield Finding("error", "core.transfer-target", _t("core.transfer_target"), l.to)
        if l.kind == "tie" and l.device is None:
            yield Finding("info", "core.tie-device", _t("core.tie_device"), l.from_)
    ts = [n for n in idx.nodes.values() if n.type == "transfer_switch"]  # type: ignore[attr-defined]
    for t in ts:
        if not any(l.kind == "transfer" and l.to == t.id for l in doc.links):
            yield Finding("warning", "core.transfer-source", _t("core.transfer_source"), t.id)


@rule("core")
def leaf_after_source(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        if n.type in ("pv_array", "battery", "spd", "earth") and n.children:  # type: ignore[attr-defined]
            yield Finding("warning", "core.terminal-node", _t("core.terminal_node", type=n.type), nid)  # type: ignore[attr-defined]


VOLTAGE_CONVERTERS = {"transformer", "power_supply", "inverter", "ups", "dc_converter"}


@rule("core")
def rating_cascade(doc: Document, idx: Index):
    """A downstream device must not have a higher rating than the directly upstream protection."""
    for nid, n in idx.nodes.items():
        in_a = getattr(n, "in_A", None)
        if in_a is None or n.type not in ("breaker", "rcbo", "fuse"):  # type: ignore[attr-defined]
            continue
        for a in idx.ancestors(nid):
            if a.type in VOLTAGE_CONVERTERS:  # type: ignore[attr-defined]  # currents not comparable across it
                break
            if a.type in ("breaker", "rcbo", "fuse", "main_breaker") and getattr(a, "in_A", None):  # type: ignore[attr-defined]
                if in_a > a.in_A:  # type: ignore[attr-defined]
                    yield Finding("warning", "core.rating-cascade",
                                  _t("core.rating_cascade", in_a=in_a, up=a.ref or a.id, up_in_a=a.in_A), nid)  # type: ignore[attr-defined]
                break



# Control circuits entered in the power tree: switching devices fed by a control power supply that switch nothing
# (their coils drawn as power devices), and coils, push buttons and signal lamps entered as loads (IEC 81346 letter codes K, S, H).
# Control links of a distribution diagram (load shedding, off-peak contactor, PLC command) are not concerned.
CONTROL_FED = {"contactor", "impulse_relay", "thermal_relay", "motor_starter"}
CONTROL_REF = re.compile(r"^-?(K[AMT]?|S[ABQ]?|HL?)\d", re.I)
CONTROL_WORDS = ("coil", "relay", "push button", "pushbutton", "emergency stop", "e-stop", "bobine", "relais",
                 "bouton", "arrêt d'urgence", "voyant", "线圈", "继电器", "按钮", "急停", "指示灯")


def _control_node(nid: str, n, idx: Index) -> bool:
    if n.type == "load":  # type: ignore[attr-defined]
        return bool(CONTROL_REF.match(n.ref or "")) or any(w in (n.label or "").lower() for w in CONTROL_WORDS)
    if n.type not in CONTROL_FED or n.children:  # type: ignore[attr-defined]
        return False
    up = next((a for a in idx.ancestors(nid) if a.type in VOLTAGE_CONVERTERS), None)  # type: ignore[attr-defined]
    return up is not None and up.type == "power_supply"  # type: ignore[attr-defined]


@rule("core")
def control_scope(doc: Document, idx: Index):
    """uniwire draws power distribution, not control schematics: say so once when the document describes
    control circuits, so that the reader knows they are only summarized."""
    nodes = [nid for nid, n in idx.nodes.items() if _control_node(nid, n, idx)]
    if nodes:
        names = [idx.nodes[i].ref or i for i in nodes[:3]] + (["..."] if len(nodes) > 3 else [])
        yield Finding("info", "core.scope", _t("core.control_scope", nodes=", ".join(names)), nodes[0])


def _closed_node(n) -> bool:
    """Closed in normal operation. A transfer switch (changeover) engages its interlocked alternate position
    only when its normal_state says so explicitly."""
    if n.type == "transfer_switch":  # type: ignore[attr-defined]
        return n.normal_state == "closed"
    return n.normal_state != "open"


@rule("core")
def interlocks(doc: Document, idx: Index):
    """Key interlocks (trapped keys, removable links, mechanical interlocks): the nodes and links sharing a
    ``locks`` identifier form one interlock; with K keys, at most K members may be closed at the same time.

    A link and the device it carries are one member (their ``locks`` are merged); the member is closed unless
    the link is ``normally_open`` or the device's ``normal_state`` is ``"open"``.
    """
    members: dict[str, list[tuple[str, bool]]] = defaultdict(list)  # key -> [(member, closed)]
    carried = {id(l.device) for l in doc.links if l.device is not None}
    for l in doc.links:
        dev = l.device
        keys = list(dict.fromkeys([*l.locks, *(dev.locks if dev is not None else [])]))
        if not keys:
            continue
        closed = not l.normally_open and (dev is None or dev.normal_state != "open")
        name = (dev.id if dev is not None and dev.id else None) or l.id or f"{l.from_}->{l.to}"
        for k in keys:
            members[k].append((name, closed))
    for nid, n in idx.nodes.items():
        if id(n) in carried:
            continue
        for k in dict.fromkeys(n.locks):
            members[k].append((nid, _closed_node(n)))
    declared: dict[str, int] = {}
    for il in doc.interlocks:
        if il.key in declared:
            yield Finding("error", "core.interlock", _t("core.interlock_duplicate", lock=il.key))
        declared[il.key] = il.keys
    for key in declared:
        if len(members.get(key, [])) < 2:
            yield Finding("warning", "core.interlock", _t("core.interlock_unused", lock=key,
                                                            count=len(members.get(key, []))))
    for key, ms in members.items():
        if key not in declared and len(ms) == 1:
            yield Finding("warning", "core.interlock", _t("core.interlock_single", lock=key), ms[0][0])
        keys = declared.get(key, 1)
        closed = [m for m, c in ms if c]
        if len(closed) > keys:
            yield Finding("error", "core.interlock", _t("core.interlock_closed", lock=key, keys=keys,
                                                        count=len(closed), members=", ".join(closed)), closed[0])


@rule("core")
def normalized_values(doc: Document, idx: Index):
    """Near-miss values rewritten on load (``poles: 2`` read as ``"2P"``...): write them in canonical form."""
    for note in getattr(doc, "_normalized", []):
        yield Finding("warning", "core.normalized", note)

