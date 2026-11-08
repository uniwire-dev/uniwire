"""Generic rules (always active)."""

from __future__ import annotations

import math
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
    roots = {s.id for s in doc.sources}
    for nid, n in idx.nodes.items():
        if n.type == "battery" and nid in roots:  # the only source of a DC system (vehicle, boat, off-grid site)
            continue
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



@rule("core")
def phases_from_feeder(doc: Document, idx: Index):
    """A three-phase load is fed by a circuit that carries three phases."""
    from ..labels import conductor_count

    for nid, n in idx.nodes.items():
        if getattr(n, "phases", None) != 3:
            continue
        chain, system = [], doc.installation.system
        for a in idx.ancestors(nid):
            if a.type in VOLTAGE_CONVERTERS or getattr(a, "method", None) == "vfd":  # type: ignore[attr-defined]
                chain = []  # phases made downstream of it (a drive fed in single phase makes three): not judged
                break
            if a.type in ("board", "busbar") or len(a.children) >= 2:  # type: ignore[attr-defined]
                system = next((getattr(b, "system", None) for b in [a] + idx.ancestors(a.id or "")
                               if getattr(b, "system", None)), system)
                break
            chain.append(a)
        if not chain or system in ("DC", "split-phase"):
            continue
        cable = n.cable is not None and n.cable.cores and re.fullmatch(r"\d+[Gg]", n.cable.cores)
        live = conductor_count(([n] if cable else []) + chain, system)
        if live is not None and live <= 2:
            yield Finding("warning", "core.phases-feeder", _t("core.phases_feeder", live=live), nid)


def _system_at(doc: Document, idx: Index, nid: str):
    """System (``1P+N``, ``3P``...) of the network a node is on: the nearest one declared on it or above it, not
    across a converter that makes its own (``None`` when not known there)."""
    n = idx.nodes[nid]
    for a in [n, *idx.ancestors(nid)]:
        if getattr(a, "system", None):
            return a.system
        if a is not n and a.type in VOLTAGE_CONVERTERS:  # type: ignore[attr-defined]
            return None
    return doc.installation.system


@rule("core")
def neutral_on_network(doc: Document, idx: Index):
    """A device with a neutral pole (``1P+N``, ``3P+N``) needs a neutral: not on a network without one (``3P``,
    ``2P``)."""
    for nid, n in idx.nodes.items():
        poles = getattr(n, "poles", None)
        system = _system_at(doc, idx, nid) if poles in ("1P+N", "3P+N") else None
        if system in ("3P", "2P"):
            yield Finding("warning", "core.neutral-missing", _t("core.neutral_missing", poles=poles, system=system),
                          nid)


OVERCURRENT = ("breaker", "rcbo", "fuse", "main_breaker")
LOAD_MARGIN = 1.1  # above the rating by more than this: not a rounding of the power (3.7 kW on 16 A)


def _loads_below(n) -> list | None:
    """Loads below ``n`` up to the next overcurrent protection (``None`` when there is one below it)."""
    from ..registry import is_load

    found = []
    for c in n.children:
        if c.type in OVERCURRENT:
            return None
        sub = _loads_below(c)
        if sub is None:
            return None
        found += ([c] if is_load(c.type) else []) + sub
    return found


def _circuit_voltage(doc: Document, idx: Index, n, chain: list, prot) -> float | None:
    """Voltage that gives the current of load ``n`` from its power (phase-to-phase times sqrt(3) when three-phase),
    on the network of its protection ``prot``; ``None`` when it is not clear. The voltage of the load wins; else the
    nearest one declared above (board, source, transformer secondary, installation). Where a circuit may be
    single-phase or between two phases, the higher voltage (the lower current): a false alarm is worse than none."""
    from ..labels import conductor_count

    path = [*chain, prot, *idx.ancestors(prot.id or "")]
    system = net_un = None
    dc, at_installation = False, True
    for a in path:
        system = system or getattr(a, "system", None)
        if a.type in ("battery", "pv_array") or getattr(a, "dc", None) or getattr(a, "kind", None) == "dc_box":
            dc = True
        if a.type in ("board", "busbar") or a is path[-1]:
            net_un = net_un or getattr(a, "un_V", None)
        if a is not n and a.type in VOLTAGE_CONVERTERS:  # its output makes the network below it
            at_installation = False
            net_un = net_un or (getattr(a, "u2_V", None) if a.type == "transformer" else None)
            dc = dc or a.type != "transformer"  # an inverter, a power supply...: the network below is not known here
            break
    else:
        system = system or doc.installation.system
        net_un = net_un or doc.installation.un_V
    load_un = getattr(n, "un_V", None)
    if dc or system == "DC":
        return load_un  # DC: only the voltage the load gives
    devices = [*chain[1:], prot]  # the poles of a load (a socket's "3P+N+T") are not those of a device
    poles = next((getattr(a, "poles", None) for a in devices if getattr(a, "poles", None)), None)
    if getattr(n, "phases", None) == 3 or poles in ("3P", "3P+N", "4P") or str(getattr(n, "poles", "")).startswith("3P"):
        three = True
    elif system in ("3P", "3P+N"):
        three = (conductor_count([*chain, prot], system) or 0) >= 3
    else:
        three = False  # split-phase three wires are not three phases
    if load_un:
        return math.sqrt(3) * load_un if three else load_un
    if not net_un:
        return None
    if three:
        return math.sqrt(3) * net_un
    phase = next((getattr(a, "phase", None) for a in devices if getattr(a, "phase", None)), None)
    to_neutral = (poles in ("1P", "1P+N") and system in ("3P+N", "split-phase")
                  or (poles == "1P+N" or phase in ("L1", "L2", "L3")) and system is None)  # below a transformer
    if to_neutral:
        uln = doc.installation.uln_V if at_installation and net_un == doc.installation.un_V else None
        if uln:
            return uln
        if system in ("3P+N", None) and net_un >= 300:  # 400/230 V
            return net_un / math.sqrt(3)
        if system == "split-phase" and net_un >= 200:  # 240/120 V, 200/100 V
            return net_un / 2
    return net_un  # single-phase network, two phases, or not clear: the higher voltage


@rule("core")
def load_current(doc: Document, idx: Index):
    """The current of a load is not above the rating of the protection that feeds it alone. Powers are per item:
    ``count`` items of a load add up; a protection with ``count`` stands for that many circuits, each feeding the
    load below it."""
    from ..registry import is_load

    for nid, n in idx.nodes.items():
        if not is_load(n.type) or not getattr(n, "p_kW", None):  # type: ignore[attr-defined]
            continue
        chain, prot = [n], None
        for a in idx.ancestors(nid):
            if a.type in VOLTAGE_CONVERTERS or a.type == "motor_starter" or getattr(a, "method", None) == "vfd":  # type: ignore[attr-defined]
                break
            if a.type in OVERCURRENT and getattr(a, "in_A", None):  # type: ignore[attr-defined]
                prot = a
                break
            chain.append(a)
        if prot is None or _loads_below(prot) != [n]:  # several loads: their diversity is not known here
            continue
        u = _circuit_voltage(doc, idx, n, chain, prot)
        if not u:
            continue
        items, circuits = getattr(n, "count", None) or 1, getattr(prot, "count", None) or 1
        current = n.p_kW * 1000 * items / (u * (getattr(n, "cos_phi", None) or 1))  # type: ignore[attr-defined]
        if current > LOAD_MARGIN * prot.in_A:  # type: ignore[attr-defined]
            key = ("core.load_current_count" if items > 1 else "core.load_current_circuits" if circuits > 1
                   else "core.load_current")
            yield Finding("warning", "core.load-current",
                          _t(key, p=float(n.p_kW), count=items if items > 1 else circuits,  # type: ignore[attr-defined]
                             i=float(round(current)), prot=prot.ref or prot.id, in_a=float(prot.in_A)), nid)  # type: ignore[attr-defined]


# Control circuits entered in the power tree: switching devices fed by a control power supply that switch nothing
# (their coils drawn as power devices), coils, push buttons, signal lamps and sensors entered as loads (IEC 81346 letter
# codes K, S, H, B), the same entered as controllers on a control power supply, and lists of PLC inputs and outputs.
# Control links of a distribution diagram (load shedding, off-peak contactor, PLC command) are not concerned.
CONTROL_FED = {"contactor", "impulse_relay", "thermal_relay", "motor_starter"}
CONTROL_REF = re.compile(r"^-?\d*(K[AMT]?|S[ABQ]?|HL?|B)\d", re.I)  # relays, switches, lamps, sensors (IEC 81346),
# after an optional folio number ("-12K3")
CONTROL_WORDS = re.compile(
    r"\b(coils?|relays?|push[- ]?buttons?|emergency stop|e-stop|sensors?|limit switch|time switch|timer|"
    r"(mag)?locks?|electric strike|bobine|relais|serrure|gâche|ventouse|bouton|arrêt d'urgence|voyant|capteur|"
    r"fin de course|minuterie)s?\b|线圈|继电器|按钮|急停|指示灯", re.I)
IO_POINTS = {"di", "do", "ai", "ao", "bi", "bo"}  # a controller standing for one input or output of a PLC or BMS


def _control_node(nid: str, n, idx: Index) -> bool:
    if n.type == "controller" and str(getattr(n, "function", "") or "").strip().lower() in IO_POINTS:
        return True
    looks_control = bool(CONTROL_REF.match(n.ref or "") or CONTROL_WORDS.search(n.label or ""))
    if n.type == "load":  # type: ignore[attr-defined]
        return looks_control
    if n.type == "controller":  # type: ignore[attr-defined]
        if not looks_control:  # a time switch or an emergency stop on a board is part of the distribution
            return False
    elif n.type not in CONTROL_FED or n.children:  # type: ignore[attr-defined]
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


@rule("core")
def view_direction(doc: Document, idx: Index):
    """A view asking for a left-right drawing: drawn top-down for now, say so instead of drawing it silently."""
    for i, v in enumerate(doc.views):
        if v.direction in ("right", "left"):
            yield Finding("info", "core.view-direction",
                          _t("core.view_direction", view=v.id or v.title or i + 1, direction=v.direction))


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


@rule("core")
def folio_duplicate(doc: Document, idx: Index):
    """Two views starting at the same sheet number: the later one is numbered after the sheets before it. A view
    without ``first_folio`` starts at 1 when it comes first, else follows the view before it (no clash)."""
    first: dict[int, str] = {}
    for i, v in enumerate(doc.views):
        if "first_folio" not in v.model_fields_set and i:
            continue
        if v.first_folio in first:
            yield Finding("warning", "core.folio-duplicate", _t("core.folio_duplicate", view=v.id, other=first[v.first_folio],
                                                               folio=v.first_folio))
        else:
            first[v.first_folio] = v.id
