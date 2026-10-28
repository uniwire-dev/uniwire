"""``nfc15100`` profile: usual checks of a French low-voltage installation (NF C 15-100).

NF C 15-100 covers every low-voltage installation in France. The version that gives presumption of conformity
(order of 3 August 2016, art. 4) is the 2002 edition with its 2005 update and amendments A1 to A5; amendment A5
(June 2015) adds Title 10, whose part 10-1 replaces parts 7-771 and 7-772 for dwellings. The residential rules
apply when ``installation.premises`` is ``"dwelling"`` or not set; for other premises (commercial, office,
industrial...) only the general rules apply, and the residential cable table becomes a reminder to size the
cable for its installation method.

Each rule carries a source (the part of the standard it derives from) and a confidence level
(:data:`RULE_INFO`). References:

* **NF C 15-100, part 10-1 (amendment A5)**: dwellings (circuits, protections, residual-current devices);
* **order of 3 August 2016** (Légifrance): 30 mA protection of every final circuit of a dwelling;
* **NF C 15-100, 411.3.3 (amendment A4)**: 30 mA additional protection of socket-outlets up to 32 A, all premises;
* **NF C 15-100, 411.5.3, 524, 535, 543**: earth electrode resistance in TT, cross-sections, selectivity of RCDs;
* **NF C 15-100, part 5-52 and guide UTE C 15-105**: cable sizing for the installation method;
* **IEC 60364-7-722 / guide UTE C 15-722**: supplies for electric vehicles (not part of the 2002 edition and its
  amendments, which only set the type A RCD and the cross-sections of charging circuits in dwellings).

These are consistency checks for common cases: they do not replace the standard, which remains
the authoritative text.
"""

from __future__ import annotations

from .. import registry
from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import describe, rule

RES = "NF C 15-100, part 10-1 (amendment A5, dwellings)"
GEN = "NF C 15-100, 411.3.3 (amendment A4)"
SIZING = "NF C 15-100, part 5-52 / guide UTE C 15-105 (non-residential premises)"
EV = "IEC 60364-7-722 / guide UTE C 15-722 (EV charging)"
DECREE = "order of 3 August 2016 on the electrical installations of dwellings, art. 2"

SECTION = describe(
    "nfc15100.section",
    f"{RES}, table 10-1F: protection per circuit (copper 1.5 mm² → 16 A, 2.5 mm² → 20 A, 4 mm² → 25 A, "
    f"6 mm² → 32 A); {SIZING}: beyond these values, size the cable for its installation method",
    "high")
POINTS = describe(
    "nfc15100.points",
    f"{RES}, 10.1.3.2.3 and 10.1.3.3.3: max 8 lighting points per circuit; 16 A 2P+E sockets: max 8 per circuit "
    "at 1.5 mm², max 12 at 2.5 mm²",
    "high")
LIGHTING_RATING = describe(
    "nfc15100.lighting-rating",
    f"{RES}, table 10-1F: lighting circuits in 1.5 mm², protection 16 A max",
    "high")
RCD_30MA = describe(
    "nfc15100.rcd-30mA",
    f"{DECREE} (rule 5) and {RES}, 10.1.4.7.3.1: every final circuit of a dwelling protected by a 30 mA "
    f"residual-current device, whatever the earthing system; {GEN}: socket-outlets up to 32 A protected by a "
    f"30 mA RCD in all premises; {EV}: RCD ≤ 30 mA per charging point",
    "high")
RCD_TYPE_A = describe(
    "nfc15100.rcd-type-A",
    f"{RES}, table 10-1G rule 2: cooker / hob, washing machine and EV charging circuits behind a type A RCD "
    "(type AC excluded)",
    "high")
RCD_COUNT = describe(
    "nfc15100.rcd-count",
    f"{RES}, table 10-1G rule 1: at least 2 30 mA residual-current devices per dwelling, single-phase or "
    "three-phase",
    "high")
RCD_CIRCUITS = describe(
    "nfc15100.rcd-circuits",
    f"{RES}, table 10-1G rule 3: max 8 circuits per 30 mA residual-current device",
    "high")
HEATING = describe(
    "nfc15100.heating",
    f"{RES}, 10.1.3.5 and table 10-1B: max heating power per circuit (3500 W / 16 A, 4500 W / 20 A, "
    "5750 W / 25 A, 7250 W / 32 A)",
    "high")
DEDICATED = describe(
    "nfc15100.dedicated-circuit",
    f"{RES}, 10.1.3.4: dedicated circuits (washing machine, dishwasher, dryer, oven, water heater, cooking: "
    "1 appliance per circuit; heating, roller shutters: circuit reserved for that use; freezer recommended); "
    f"{EV}: 1 charging point per dedicated circuit",
    "high")
EV_RCD = describe(
    "nfc15100.ev-rcd",
    f"{EV}: type A or F RCD for single-phase mode 2, type B for three-phase mode 2, "
    "type B or A/F with 6 mA DC fault detection (RDC-DD, IEC 62955) in mode 3",
    "medium")
SELECTIVITY = describe(
    "nfc15100.selectivity",
    f"{RES}, 10.1.2.2.1: a residual-current service breaker or an intermediate medium-sensitivity RCD upstream "
    "of the 30 mA RCDs is selective (type S); NF C 15-100, 535.4.3.1: selectivity between RCDs (time-delayed "
    "upstream device)",
    "high")
CIRCUIT_SECTION = describe(
    "nfc15100.circuit-section",
    f"{RES}, table 10-1F: minimum cross-section and maximum protection of the dedicated circuits (washing "
    "machine, dishwasher, dryer, oven, water heater: 2.5 mm² and 20 A; single-phase cooking: 6 mm² and 32 A; "
    "three-phase cooking: 2.5 mm² and 20 A; EV charging socket 16 A: 2.5 mm² and 20 A; roller shutters: 1.5 mm² "
    "and 16 A)",
    "high")
RCD_RATING = describe(
    "nfc15100.rcd-rating",
    f"{RES}, table 10-1G rule 4: rated current of a 30 mA RCD at least the current of the service breaker, or "
    "the sum of the ratings of its heating, water heater and EV circuits plus half the sum of the others (the "
    "service current is taken from the subscribed power when known)",
    "medium")
RCD_SPREAD = describe(
    "nfc15100.rcd-spread",
    f"{RES}, table 10-1G rule 5: lighting circuits spread over at least 2 RCDs, and socket-outlet circuits too",
    "high")
SPD_RCD = describe(
    "nfc15100.spd-rcd",
    f"{RES}, 10.1.4.7.3.1: the surge protective device at the origin is not behind a 30 mA RCD",
    "high")
AGCP_RCD = describe(
    "nfc15100.agcp-rcd",
    f"{RES}, 10.1.2.2.1: limited-power supply: the residual-current service breaker and intermediate RCDs are "
    "500 mA at most and have no adjustable sensitivity",
    "high")
EARTH_RESISTANCE = describe(
    "nfc15100.earth-resistance",
    "NF C 15-100, 411.5.3 and 531.2.4.2.2 (table 53B): TT system, earth electrode resistance × highest RCD "
    "sensitivity ≤ 50 V (500 mA → 100 Ω, 300 mA → 167 Ω, 100 mA → 500 Ω)",
    "high")
NEUTRAL_POLE = describe(
    "nfc15100.neutral-pole",
    f"{RES}, 10.1.4.7.1.1: every circuit is isolated at its origin on all its live conductors, neutral "
    "included (a 1P breaker on a circuit with a neutral does not isolate it)",
    "high")
SUPPLY_SECTION = describe(
    "nfc15100.supply-section",
    f"{RES}, 10.1.4.3.2 (table 10-1D): copper link from the service breaker to the main board: 10 mm² for "
    "30 and 45 A, 16 mm² for 60 A, 25 mm² for 90 A",
    "high")

NFC15100_RULES = {r.name: r for r in (SECTION, POINTS, LIGHTING_RATING, RCD_30MA, RCD_TYPE_A, RCD_COUNT,
                                      RCD_CIRCUITS, HEATING, DEDICATED, EV_RCD, SELECTIVITY, CIRCUIT_SECTION,
                                      RCD_RATING, RCD_SPREAD, SPD_RCD, AGCP_RCD, EARTH_RESISTANCE, NEUTRAL_POLE,
                                      SUPPLY_SECTION)}

# copper cross-section (mm²) -> maximum breaker rating (NF C 15-100, residential)
MAX_BREAKER_FOR_SECTION = {1.5: 16, 2.5: 20, 4: 25, 6: 32}
MAX_LIGHTING_POINTS = 8
MAX_SOCKETS = {1.5: 8, 2.5: 12}  # per cross-section; 12 if the cross-section is unknown
# breaker rating (A) -> maximum heating power (kW) (NF C 15-100, residential)
MAX_HEATING_KW = {16: 3.5, 20: 4.5, 25: 5.75, 32: 7.25}
# (type, kind) whose RCD cannot be type AC (part 10-1, table 10-1G rule 2)
TYPE_A_LOADS = {("appliance", "washing_machine"), ("cooking", "hob"), ("cooking", "range"), ("ev_charger", None)}
NOT_AC = ("A", "F", "B", "A-SI", "Hpi")
# loads that must be alone on their circuit / circuits reserved for a single use
SINGLE_LOAD = {("appliance", "washing_machine"), ("appliance", "dishwasher"), ("appliance", "dryer"),
               ("appliance", "freezer"), ("cooking", "oven"), ("cooking", "hob"), ("cooking", "range"),
               ("water_heater", None), ("ev_charger", None)}
RECOMMENDED_SINGLE = {("appliance", "freezer")}  # "it is recommended" (10.1.3.4): a warning, not an error
HOMOGENEOUS = {"heating", "shutter"}
# (type, kind) -> (minimum copper section mm², maximum protection A), single-phase (table 10-1F)
CIRCUIT_MIN = {("appliance", "washing_machine"): (2.5, 20), ("appliance", "dishwasher"): (2.5, 20),
               ("appliance", "dryer"): (2.5, 20), ("cooking", "oven"): (2.5, 20), ("water_heater", None): (2.5, 20),
               ("cooking", "hob"): (6, 32), ("cooking", "range"): (6, 32), ("shutter", None): (1.5, 16)}
COOKING_3PH = (2.5, 20)
EV_16A = (2.5, 20)
# loads counted at their full rating in table 10-1G rule 4 (the others at half)
FULL_RATING_LOADS = ("heating", "water_heater", "ev_charger")
# service breaker rating (A) -> minimum copper section (mm²) of the link to the main board (table 10-1D)
SUPPLY_MIN_MM2 = {30: 10, 45: 10, 60: 16, 90: 25}
LIMITED_MAX_KVA = 36
PROTECTION_TYPES = ("breaker", "rcbo")
THREE_PHASE_POLES = ("3P", "3P+N", "4P")


def _dwelling(doc: Document) -> bool:
    """Residential rules (part 7-771) apply: premises not set (the usual case of this profile) or a dwelling."""
    return doc.installation.premises in (None, "dwelling")


def _kind(n) -> str | None:
    return getattr(n, "kind", None) if n.type in ("appliance", "cooking") else None  # type: ignore[attr-defined]


def _feeder_protection(idx: Index, nid: str):
    for a in idx.ancestors(nid):
        if a.type in PROTECTION_TYPES:  # type: ignore[attr-defined]
            return a
    return None


def _feeder_cable(idx: Index, nid: str):
    n = idx.nodes[nid]
    if n.cable is not None:
        return n.cable
    for a in idx.ancestors(nid):
        if a.cable is not None:
            return a.cable
        if a.type in PROTECTION_TYPES:  # type: ignore[attr-defined]
            return None
    return None


def _loads_below(node) -> list:
    out = []
    for c in node.children:
        if registry.category(c.type) == "load":  # type: ignore[attr-defined]
            if c.type != "spare":  # type: ignore[attr-defined]
                out.append(c)
        else:
            out.extend(_loads_below(c))
    return out


def _socket_rating(idx: Index, nid: str) -> float | None:
    """Rating of a socket-outlet circuit: the socket's own rating, else its protection's."""
    n = idx.nodes[nid]
    if getattr(n, "in_A", None):
        return n.in_A  # type: ignore[attr-defined]
    p = _feeder_protection(idx, nid)
    return getattr(p, "in_A", None) if p is not None else None


def _rcds(idx: Index, nid: str) -> list:
    n = idx.nodes[nid]
    return [a for a in [n, *idx.ancestors(nid)] if getattr(a, "idn_mA", None)]


@rule("nfc15100")
def section_vs_rating(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        if n.type not in PROTECTION_TYPES or n.cable is None and not n.children:  # type: ignore[attr-defined]
            continue
        cable = n.cable or next((c.cable for c in n.children if c.cable is not None), None)
        if cable is None or cable.section_mm2 is None or getattr(n, "in_A", None) is None:
            continue
        if cable.material == "Al" or cable.section_mm2 > max(MAX_BREAKER_FOR_SECTION):
            continue  # beyond that: Iz calculation (iec60364 profile)
        limit = max((a for s, a in MAX_BREAKER_FOR_SECTION.items() if s <= cable.section_mm2), default=None)
        if limit is not None and n.in_A > limit:  # type: ignore[attr-defined]
            if _dwelling(doc):
                yield SECTION.finding("error", _t("nfc15100.section", in_a=n.in_A, section=cable.section_mm2, limit=limit), nid)  # type: ignore[attr-defined]
            else:  # outside dwellings the cable is sized for its installation method (part 5-52)
                yield SECTION.finding("warning", _t("nfc15100.section_sizing", in_a=n.in_A, section=cable.section_mm2, limit=limit), nid)  # type: ignore[attr-defined]


def _points(n) -> int:
    return (getattr(n, "points", None) or 0) * (getattr(n, "count", None) or 1)


@rule("nfc15100")
def points_per_circuit(doc: Document, idx: Index):
    """Points of the lighting and socket loads added up per circuit (the loads under one protective device)."""
    if not _dwelling(doc):
        return  # residential rule (part 10-1)
    circuits: dict[tuple[str, str], list] = {}
    for nid, n in idx.nodes.items():
        t = n.type  # type: ignore[attr-defined]
        if t not in ("lighting", "socket"):
            continue
        p = _feeder_protection(idx, nid)
        if t == "lighting" and p is not None and getattr(p, "in_A", None) and p.in_A > 16:  # type: ignore[attr-defined]
            yield LIGHTING_RATING.finding("error", _t("nfc15100.lighting_rating", in_a=p.in_A), nid)  # type: ignore[attr-defined]
        circuits.setdefault((p.id if p is not None else nid, t), []).append(n)  # type: ignore[union-attr]
    for (key, t), loads in circuits.items():
        pts = sum(_points(n) for n in loads)
        where_id = key if key in idx.nodes else loads[0].id
        if t == "lighting" and pts > MAX_LIGHTING_POINTS:
            yield POINTS.finding("error", _t("nfc15100.lighting_points", points=pts, limit=MAX_LIGHTING_POINTS), where_id)
        if t == "socket" and pts:
            cable = _feeder_cable(idx, loads[0].id)
            section = cable.section_mm2 if cable is not None else None
            limit = MAX_SOCKETS.get(section, MAX_SOCKETS[2.5])  # type: ignore[arg-type]
            if pts > limit:
                where = _t("nfc15100.socket_section", section=section) if section in MAX_SOCKETS else ""
                yield POINTS.finding("error", _t("nfc15100.socket_points", points=pts, where=where, limit=limit), where_id)


@rule("nfc15100")
def heating_power(doc: Document, idx: Index):
    if not _dwelling(doc):
        return  # residential rule (part 10-1)
    seen: set[str] = set()
    for nid, n in idx.nodes.items():
        if n.type != "heating" or not getattr(n, "p_kW", None):  # type: ignore[attr-defined]
            continue
        p = _feeder_protection(idx, nid)
        in_a = getattr(p, "in_A", None) if p is not None else None
        if p is not None and in_a in MAX_HEATING_KW:
            if p.id in seen:
                continue
            seen.add(p.id)  # type: ignore[arg-type]
            limit = MAX_HEATING_KW[in_a]
            total = sum(getattr(l, "p_kW", 0) or 0 for l in _loads_below(p) if l.type == "heating")  # type: ignore[attr-defined]
            if total > limit:
                yield HEATING.finding("warning", _t("nfc15100.heating", total=total, in_a=in_a, limit=limit), nid)
        elif in_a is None and n.p_kW > max(MAX_HEATING_KW.values()):  # type: ignore[attr-defined]
            yield HEATING.finding("warning", _t("nfc15100.heating_unprotected", p=n.p_kW, limit=max(MAX_HEATING_KW.values())), nid)  # type: ignore[attr-defined]


@rule("nfc15100")
def rcd_coverage(doc: Document, idx: Index):
    """Dwellings: every final circuit protected by a 30 mA RCD, no type AC for certain uses (part 7-771). All
    premises: socket-outlet and charging circuits protected by a 30 mA RCD (411.3.3, part 7-722)."""
    dwelling = _dwelling(doc)
    for nid, n in idx.nodes.items():
        t = n.type  # type: ignore[attr-defined]
        if registry.category(t) != "load" or t == "spare":
            continue
        hr = [a for a in _rcds(idx, nid) if a.idn_mA <= 30]  # type: ignore[attr-defined]
        if not hr:
            what = n.label or t
            if dwelling:  # every final circuit of a dwelling, whatever the system and the earthing
                key = "nfc15100.rcd_30mA_socket" if t in ("socket", "ev_charger") else "nfc15100.rcd_30mA_dwelling"
                yield RCD_30MA.finding("error", _t(key, what=what), nid)
            elif t == "ev_charger" or (t == "socket" and (_socket_rating(idx, nid) or 0) <= 32):
                yield RCD_30MA.finding("error", _t("nfc15100.rcd_30mA_socket", what=what), nid)
            continue
        if (dwelling or t == "ev_charger") and (t, _kind(n)) in TYPE_A_LOADS \
                and getattr(hr[0], "rcd_type", None) not in NOT_AC:
            yield RCD_TYPE_A.finding("error", _t("nfc15100.rcd_type_A", what=n.label or t), nid)


@rule("nfc15100")
def rcd_count(doc: Document, idx: Index):
    """Dwelling, single-phase or three-phase: at least 2 30 mA RCDs (RCBOs count). Skipped when
    ``installation.premises`` says the premises are not a dwelling. The type A RCDs follow from the uses
    (nfc15100.rcd-type-A)."""
    if not _dwelling(doc):
        return
    if not any(registry.category(n.type) == "load" and n.type != "spare" for n in idx.nodes.values()):  # type: ignore[attr-defined]
        return
    hr = [n for n in idx.nodes.values()
          if n.type in ("rcd", "rcbo") and getattr(n, "idn_mA", None) and n.idn_mA <= 30]  # type: ignore[attr-defined]
    if not hr:
        return  # already reported by nfc15100.rcd-30mA
    if sum(getattr(n, "count", None) or 1 for n in hr) < 2:
        yield RCD_COUNT.finding("error", _t("nfc15100.rcd_count_single"), hr[0].id)


def _final_protections(rcd) -> list:
    """The circuits behind an RCD: the first protective devices below it (through busbars, combs and boards),
    down to the next RCD."""
    out, stack = [], list(rcd.children)
    while stack:
        n = stack.pop()
        if n.type in ("rcd",) or (getattr(n, "idn_mA", None) and n.type != "rcbo"):  # type: ignore[attr-defined]
            continue  # another RCD: its circuits are counted there
        if n.type in PROTECTION_TYPES or n.type == "fuse":  # type: ignore[attr-defined]
            out.append(n)
            continue
        stack.extend(n.children)
    return out


@rule("nfc15100")
def circuits_per_rcd(doc: Document, idx: Index):
    if not _dwelling(doc):
        return  # residential rule (part 10-1)
    for nid, n in idx.nodes.items():
        if n.type != "rcd" or not getattr(n, "idn_mA", None) or n.idn_mA > 30:  # type: ignore[attr-defined]
            continue
        count = sum(getattr(c, "count", None) or 1 for c in _final_protections(n))
        if count > 8:
            yield RCD_CIRCUITS.finding("error", _t("nfc15100.rcd_circuits", count=count), nid)


@rule("nfc15100")
def dedicated_circuits(doc: Document, idx: Index):
    if not _dwelling(doc):
        return  # residential rule (part 10-1)
    for nid, n in idx.nodes.items():
        t = n.type  # type: ignore[attr-defined]
        single = (t, _kind(n)) in SINGLE_LOAD
        if not single and t not in HOMOGENEOUS:
            continue
        p = _feeder_protection(idx, nid)
        if p is None:
            continue
        others = [l for l in _loads_below(p) if l is not n]
        if single and others:
            level = "warning" if (t, _kind(n)) in RECOMMENDED_SINGLE else "error"
            yield DEDICATED.finding(level, _t("nfc15100.dedicated_single", what=n.label or t, prot=p.ref or p.id,
                                       others=", ".join(o.label or o.type for o in others)), nid)  # type: ignore[attr-defined]
        elif not single and any(o.type != t for o in others):  # type: ignore[attr-defined]
            yield DEDICATED.finding("error", _t("nfc15100.dedicated_shared", what=n.label or t), nid)


@rule("nfc15100")
def ev_rcd(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        if n.type != "ev_charger":  # type: ignore[attr-defined]
            continue
        hr = [a for a in _rcds(idx, nid) if a.idn_mA <= 30]  # type: ignore[attr-defined]
        if not hr:
            continue  # reported by nfc15100.rcd-30mA
        rtype = getattr(hr[0], "rcd_type", None)
        p = _feeder_protection(idx, nid)
        three_phase = getattr(p, "poles", None) in THREE_PHASE_POLES or getattr(hr[0], "poles", None) in THREE_PHASE_POLES
        mode = getattr(n, "mode", None)
        if mode == "2" and three_phase and rtype != "B":
            yield EV_RCD.finding("error", _t("nfc15100.ev_mode2_3ph", what=n.label or _t("nfc15100.ev_default")), nid)
        elif mode == "3" and rtype in ("A", "F", "A-SI", "Hpi"):
            yield EV_RCD.finding("info", _t("nfc15100.ev_mode3", what=n.label or _t("nfc15100.ev_default"), rtype=rtype), nid)


def _selective(n) -> bool:
    return bool(getattr(n, "selective", None)) or getattr(n, "delay", None) in ("S", "retardable")


def _rcd_devices(idx: Index) -> list:
    return [n for n in idx.nodes.values()
            if n.type in ("main_breaker", "rcd", "rcbo") and getattr(n, "idn_mA", None)]  # type: ignore[attr-defined]


def _below(idx: Index, upper, nodes) -> list:
    return [d for d in nodes if d is not upper and any(a is upper for a in idx.ancestors(d.id or ""))]


@rule("nfc15100")
def selectivity(doc: Document, idx: Index):
    """A residual-current service breaker or a medium-sensitivity RCD with other RCDs downstream is selective
    (type S): an error in a dwelling (10.1.2.2.1), a warning elsewhere (535.4.3.1)."""
    devices = _rcd_devices(idx)
    for n in devices:
        if n.idn_mA <= 30 or _selective(n):  # type: ignore[attr-defined]
            continue
        if _below(idx, n, devices):
            yield SELECTIVITY.finding("error" if _dwelling(doc) else "warning", _t("nfc15100.selectivity"), n.id)


def _phase_count(idx: Index, nid: str) -> int:
    p = _feeder_protection(idx, nid)
    poles = getattr(p, "poles", None) if p is not None else None
    return 3 if poles in THREE_PHASE_POLES else 1


@rule("nfc15100")
def circuit_sections(doc: Document, idx: Index):
    """Dwellings: minimum cross-section and maximum protection of the dedicated circuits (table 10-1F)."""
    if not _dwelling(doc):
        return
    for nid, n in idx.nodes.items():
        t, kind = n.type, _kind(n)  # type: ignore[attr-defined]
        if t == "cooking" and kind in ("hob", "range") and _phase_count(idx, nid) == 3:
            need = COOKING_3PH
        elif t == "ev_charger":
            p = _feeder_protection(idx, nid)
            if getattr(p, "in_A", None) and p.in_A > 20:  # type: ignore[union-attr]
                continue  # 32 A charging points: values to be confirmed, not checked
            need = EV_16A
        else:
            need = CIRCUIT_MIN.get((t, kind if t in ("appliance", "cooking") else None))
        if need is None:
            continue
        p = _feeder_protection(idx, nid)
        cable = _feeder_cable(idx, nid)
        section = getattr(cable, "section_mm2", None) if cable is not None else None
        copper = cable is None or getattr(cable, "material", None) in (None, "Cu")
        in_a = getattr(p, "in_A", None) if p is not None else None
        what = n.label or t
        if section is not None and copper and section < need[0]:
            yield CIRCUIT_SECTION.finding("error", _t("nfc15100.circuit_section", what=what, section=section,
                                                      need=need[0]), nid)
        if in_a is not None and in_a > need[1]:
            yield CIRCUIT_SECTION.finding("error", _t("nfc15100.circuit_rating", what=what, in_a=in_a,
                                                      need=need[1]), nid)


@rule("nfc15100")
def rcd_rating(doc: Document, idx: Index):
    """Dwellings: a 30 mA RCD is rated at least the service breaker, or 1 × the ratings of its heating, water
    heater and EV circuits + 0.5 × the others (table 10-1G rule 4)."""
    if not _dwelling(doc):
        return
    kva, system = doc.installation.subscribed_kVA, doc.installation.system
    if kva:  # the current the subscription allows (0.2 kVA per A single-phase, 0.6 three-phase)
        agcp = kva / (0.6 if system in ("3P", "3P+N") else 0.2)
    else:
        agcp = max((getattr(n, "in_A", None) or 0 for n in idx.nodes.values() if n.type == "main_breaker"), default=0)  # type: ignore[attr-defined]
    for n in idx.nodes.values():
        if n.type != "rcd" or not getattr(n, "idn_mA", None) or n.idn_mA > 30 or not getattr(n, "in_A", None):  # type: ignore[attr-defined]
            continue
        if agcp and n.in_A >= agcp:  # type: ignore[attr-defined]
            continue
        full = half = 0.0
        for p in _final_protections(n):
            in_a = (getattr(p, "in_A", None) or 0) * (getattr(p, "count", None) or 1)
            if any(l.type in FULL_RATING_LOADS for l in _loads_below(p)):  # type: ignore[attr-defined]
                full += in_a
            else:
                half += in_a
        need = full + 0.5 * half
        if need and n.in_A < need:  # type: ignore[attr-defined]
            yield RCD_RATING.finding("warning", _t("nfc15100.rcd_rating", in_a=n.in_A, need=round(need, 1)), n.id)  # type: ignore[attr-defined]


@rule("nfc15100")
def rcd_spread(doc: Document, idx: Index):
    """Dwellings: lighting circuits on at least 2 RCDs, socket-outlet circuits too (table 10-1G rule 5)."""
    if not _dwelling(doc):
        return
    for t in ("lighting", "socket"):
        circuits: dict[str, str | None] = {}
        for nid, n in idx.nodes.items():
            if n.type != t:  # type: ignore[attr-defined]
                continue
            p = _feeder_protection(idx, nid)
            hr = [a for a in _rcds(idx, nid) if a.idn_mA <= 30]  # type: ignore[attr-defined]
            circuits[p.id if p is not None else nid] = hr[0].id if hr else None  # type: ignore[union-attr]
        rcds = {r for r in circuits.values() if r}
        if len(circuits) >= 2 and len(rcds) == 1:
            yield RCD_SPREAD.finding("error", _t(f"nfc15100.rcd_spread_{t}", count=len(circuits)), next(iter(rcds)))


@rule("nfc15100")
def spd_behind_30ma(doc: Document, idx: Index):
    """Dwellings: the surge protective device at the origin is not behind a 30 mA RCD (10.1.4.7.3.1)."""
    if not _dwelling(doc):
        return
    for nid, n in idx.nodes.items():
        anc = idx.ancestors(nid)
        at_origin = sum(a.type == "board" for a in anc) <= 1 and not any(a.type == "inverter" for a in anc)  # type: ignore[attr-defined]
        if n.type == "spd" and at_origin and any(a.idn_mA <= 30 for a in _rcds(idx, nid)):  # type: ignore[attr-defined]
            yield SPD_RCD.finding("error", _t("nfc15100.spd_rcd", what=n.ref or n.label or "SPD"), nid)


@rule("nfc15100")
def agcp_rcd(doc: Document, idx: Index):
    """Dwellings on a limited-power supply (36 kVA at most): residual-current service breaker and intermediate
    RCDs at 500 mA at most, without adjustable sensitivity (10.1.2.2.1)."""
    kva = doc.installation.subscribed_kVA
    if not _dwelling(doc) or (kva is not None and kva > LIMITED_MAX_KVA):
        return
    for n in _rcd_devices(idx):
        if getattr(n, "idn_range_mA", None):
            yield AGCP_RCD.finding("error", _t("nfc15100.agcp_rcd_adjustable", what=n.ref or n.label or n.type), n.id)  # type: ignore[attr-defined]
        elif n.idn_mA > 500:  # type: ignore[attr-defined]
            yield AGCP_RCD.finding("error", _t("nfc15100.agcp_rcd_max", what=n.ref or n.label or n.type, idn=n.idn_mA), n.id)  # type: ignore[attr-defined]


@rule("nfc15100")
def earth_resistance(doc: Document, idx: Index):
    """TT: earth electrode resistance × highest RCD sensitivity ≤ 50 V (411.5.3)."""
    if doc.installation.earthing != "TT":
        return
    r = doc.installation.earth_resistance_ohm
    if r is None:
        r = next((getattr(n, "resistance_ohm", None) for n in idx.nodes.values()
                  if n.type == "earth" and getattr(n, "resistance_ohm", None)), None)  # type: ignore[attr-defined]
    devices = _rcd_devices(idx)
    if r is None or not devices:
        return
    top = max(devices, key=lambda n: n.idn_mA)  # type: ignore[attr-defined]
    limit = 50 / (top.idn_mA / 1000)  # type: ignore[attr-defined]
    if r > limit + 1e-9:
        yield EARTH_RESISTANCE.finding("error", _t("nfc15100.earth_resistance", r=r, idn=top.idn_mA,  # type: ignore[attr-defined]
                                                   limit=round(limit)), top.id)


@rule("nfc15100")
def neutral_pole(doc: Document, idx: Index):
    """Dwellings: a breaker on a circuit with a neutral isolates the neutral too: no 1P device (10.1.4.7.1.1)."""
    if not _dwelling(doc) or doc.installation.system not in (None, "1P+N", "3P+N"):
        return
    for nid, n in idx.nodes.items():
        if n.type in PROTECTION_TYPES and getattr(n, "poles", None) == "1P":  # type: ignore[attr-defined]
            yield NEUTRAL_POLE.finding("error", _t("nfc15100.neutral_pole", what=n.ref or n.label or n.type), nid)  # type: ignore[attr-defined]


@rule("nfc15100")
def supply_section(doc: Document, idx: Index):
    """Dwellings: copper section of the link from the service breaker to the main board (table 10-1D)."""
    if not _dwelling(doc):
        return
    for nid, n in idx.nodes.items():
        if n.type != "main_breaker" or not getattr(n, "in_A", None):  # type: ignore[attr-defined]
            continue
        need = next((v for a, v in sorted(SUPPLY_MIN_MM2.items()) if n.in_A <= a), None)  # type: ignore[attr-defined]
        if need is None:
            continue
        board = next((c for c in n.children if c.type == "board"), None)  # type: ignore[attr-defined]
        cable = (board.cable if board is not None and board.cable is not None else n.cable)
        if cable is None or cable.section_mm2 is None or cable.material not in (None, "Cu"):
            continue
        if cable.section_mm2 < need:
            yield SUPPLY_SECTION.finding("error", _t("nfc15100.supply_section", section=cable.section_mm2,
                                                     in_a=n.in_A, need=need), nid)  # type: ignore[attr-defined]
