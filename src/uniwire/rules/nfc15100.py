"""``nfc15100`` profile: usual checks of a French low-voltage installation (NF C 15-100).

NF C 15-100 covers every low-voltage installation in France; its part 7-771 adds the rules of dwellings. The
residential rules apply when ``installation.premises`` is ``"dwelling"`` or not set; for other premises
(commercial, office, industrial...) only the general rules apply, and the residential cable table becomes a
reminder to size the cable for its installation method.

Each rule carries a source (the part of the standard it derives from) and a confidence level
(:data:`RULE_INFO`). References:

* **NF C 15-100, part 7-771**: residential premises (circuits, protections, residual-current devices);
* **NF C 15-100, part 4-41 (411.3.3)**: 30 mA additional protection of socket-outlets up to 32 A, all premises;
* **NF C 15-100, part 5-52 and guide UTE C 15-105**: cable sizing for the installation method;
* **NF C 15-100, part 7-722**: supplies for electric vehicles (IEC 60364-7-722).

These are consistency checks for common cases: they do not replace the standard, which remains
the authoritative text.
"""

from __future__ import annotations

from .. import registry
from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import describe, rule

RES = "NF C 15-100, part 7-771 (residential)"
GEN = "NF C 15-100, part 4-41 (411.3.3)"
SIZING = "NF C 15-100, part 5-52 / guide UTE C 15-105 (non-residential premises)"
EV = "NF C 15-100, part 7-722 (EV charging)"

SECTION = describe(
    "nfc15100.section",
    f"{RES}: protection per circuit (copper 1.5 mm² → 16 A, 2.5 mm² → 20 A, 4 mm² → 25 A, 6 mm² → 32 A); "
    f"{SIZING}: beyond these values, size the cable for its installation method",
    "high")
POINTS = describe(
    "nfc15100.points",
    f"{RES}: max 8 lighting points per circuit; 2P+E sockets: max 8 at 1.5 mm² / 16 A, max 12 at 2.5 mm² / 20 A",
    "high")
LIGHTING_RATING = describe(
    "nfc15100.lighting-rating",
    f"{RES}: lighting circuits in 1.5 mm², protection 10 or 16 A max",
    "high")
RCD_30MA = describe(
    "nfc15100.rcd-30mA",
    f"{RES}: all dwelling circuits protected by 30 mA residual-current devices; "
    f"{GEN}: socket-outlet circuits protected by 30 mA RCDs in all premises; "
    f"{EV}: individual RCD ≤ 30 mA per charging point",
    "high")
RCD_TYPE_A = describe(
    "nfc15100.rcd-type-A",
    f"{RES}: washing machine, dryer, hob / cooker and EV charging circuits: type AC excluded "
    f"(type A, F or B); {EV}",
    "high")
RCD_COUNT = describe(
    "nfc15100.rcd-count",
    f"{RES}: at least 2 30 mA residual-current devices per dwelling, at least 1 of them type A",
    "medium")
RCD_CIRCUITS = describe(
    "nfc15100.rcd-circuits",
    f"{RES}: max 8 circuits per 30 mA residual-current switch",
    "high")
HEATING = describe(
    "nfc15100.heating",
    f"{RES}: max heating power per circuit (3500 W / 16 A, 4500 W / 20 A, 5750 W / 25 A, 7250 W / 32 A)",
    "high")
DEDICATED = describe(
    "nfc15100.dedicated-circuit",
    f"{RES}: dedicated circuits (washing machine, dishwasher, dryer, oven, freezer, water heater: "
    f"1 appliance per circuit; hob, heating, roller shutters: dedicated circuit); "
    f"{EV}: 1 charging point per dedicated circuit",
    "high")
EV_RCD = describe(
    "nfc15100.ev-rcd",
    f"{EV}: type A or F RCD for single-phase mode 2, type B for three-phase mode 2, "
    "type B or A/F with 6 mA DC fault detection (RDC-DD, IEC 62955) in mode 3",
    "high")
SELECTIVITY = describe(
    "nfc15100.selectivity",
    "NF C 15-100 / IEC 60364-5-53: selectivity between residual-current devices "
    "(time-delayed type S upstream device)",
    "medium")

NFC15100_RULES = {r.name: r for r in (SECTION, POINTS, LIGHTING_RATING, RCD_30MA, RCD_TYPE_A, RCD_COUNT,
                                 RCD_CIRCUITS, HEATING, DEDICATED, EV_RCD, SELECTIVITY)}

# copper cross-section (mm²) -> maximum breaker rating (NF C 15-100, residential)
MAX_BREAKER_FOR_SECTION = {1.5: 16, 2.5: 20, 4: 25, 6: 32}
MAX_LIGHTING_POINTS = 8
MAX_SOCKETS = {1.5: 8, 2.5: 12}  # per cross-section; 12 if the cross-section is unknown
# breaker rating (A) -> maximum heating power (kW) (NF C 15-100, residential)
MAX_HEATING_KW = {16: 3.5, 20: 4.5, 25: 5.75, 32: 7.25}
# (type, kind) whose RCD cannot be type AC (NF C 15-100, residential)
TYPE_A_LOADS = {("appliance", "washing_machine"), ("appliance", "dryer"), ("cooking", "hob"),
                ("cooking", "range"), ("ev_charger", None)}
NOT_AC = ("A", "F", "B", "A-SI", "Hpi")
# loads that must be alone on their circuit / circuits reserved for a single use
SINGLE_LOAD = {("appliance", "washing_machine"), ("appliance", "dishwasher"), ("appliance", "dryer"),
               ("appliance", "freezer"), ("cooking", "oven"), ("cooking", "hob"), ("cooking", "range"),
               ("water_heater", None), ("ev_charger", None)}
HOMOGENEOUS = {"heating", "shutter"}
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


@rule("nfc15100")
def points_per_circuit(doc: Document, idx: Index):
    if not _dwelling(doc):
        return  # residential rule (part 7-771)
    for nid, n in idx.nodes.items():
        t = n.type  # type: ignore[attr-defined]
        pts = getattr(n, "points", None)
        if t == "lighting":
            if pts and pts > MAX_LIGHTING_POINTS:
                yield POINTS.finding("error", _t("nfc15100.lighting_points", points=pts, limit=MAX_LIGHTING_POINTS), nid)
            p = _feeder_protection(idx, nid)
            if p is not None and getattr(p, "in_A", None) and p.in_A > 16:  # type: ignore[attr-defined]
                yield LIGHTING_RATING.finding("error", _t("nfc15100.lighting_rating", in_a=p.in_A), nid)  # type: ignore[attr-defined]
        if t == "socket" and pts:
            cable = _feeder_cable(idx, nid)
            section = cable.section_mm2 if cable is not None else None
            limit = MAX_SOCKETS.get(section, MAX_SOCKETS[2.5])  # type: ignore[arg-type]
            if pts > limit:
                where = _t("nfc15100.socket_section", section=section) if section in MAX_SOCKETS else ""
                yield POINTS.finding("error", _t("nfc15100.socket_points", points=pts, where=where, limit=limit), nid)


@rule("nfc15100")
def heating_power(doc: Document, idx: Index):
    if not _dwelling(doc):
        return  # residential rule (part 7-771)
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
            if t in ("socket", "ev_charger"):
                yield RCD_30MA.finding("error", _t("nfc15100.rcd_30mA_socket", what=what), nid)
            elif dwelling and doc.installation.system == "1P+N":
                yield RCD_30MA.finding("error", _t("nfc15100.rcd_30mA_dwelling", what=what), nid)
            continue
        if (dwelling or t == "ev_charger") and (t, _kind(n)) in TYPE_A_LOADS \
                and getattr(hr[0], "rcd_type", None) not in NOT_AC:
            yield RCD_TYPE_A.finding("error", _t("nfc15100.rcd_type_A", what=n.label or t), nid)


@rule("nfc15100")
def rcd_count(doc: Document, idx: Index):
    """Dwelling (1P+N): at least 2 30 mA RCDs, one of them type A (RCBOs count). Skipped when
    ``installation.premises`` says the premises are not a dwelling."""
    if doc.installation.system != "1P+N" or not _dwelling(doc):
        return
    if not any(registry.category(n.type) == "load" and n.type != "spare" for n in idx.nodes.values()):  # type: ignore[attr-defined]
        return
    hr = [n for n in idx.nodes.values()
          if n.type in ("rcd", "rcbo") and getattr(n, "idn_mA", None) and n.idn_mA <= 30]  # type: ignore[attr-defined]
    if not hr:
        return  # already reported by nfc15100.rcd-30mA
    if len(hr) < 2:
        yield RCD_COUNT.finding("warning", _t("nfc15100.rcd_count_single"), hr[0].id)
    if not any(getattr(n, "rcd_type", None) in NOT_AC for n in hr):
        yield RCD_COUNT.finding("warning", _t("nfc15100.rcd_count_type_A"), hr[0].id)


@rule("nfc15100")
def circuits_per_rcd(doc: Document, idx: Index):
    if not _dwelling(doc):
        return  # residential rule (part 7-771)
    for nid, n in idx.nodes.items():
        if n.type != "rcd" or not getattr(n, "idn_mA", None) or n.idn_mA > 30:  # type: ignore[attr-defined]
            continue
        count = sum(1 for c in n.children if c.type in PROTECTION_TYPES)  # type: ignore[attr-defined]
        if count > 8:
            yield RCD_CIRCUITS.finding("error", _t("nfc15100.rcd_circuits", count=count), nid)


@rule("nfc15100")
def dedicated_circuits(doc: Document, idx: Index):
    if not _dwelling(doc):
        return  # residential rule (part 7-771)
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
            yield DEDICATED.finding("error", _t("nfc15100.dedicated_single", what=n.label or t, prot=p.ref or p.id,
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


@rule("nfc15100")
def selectivity(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        if n.type != "main_breaker" or not getattr(n, "idn_mA", None):  # type: ignore[attr-defined]
            continue
        down = [d for d in idx.nodes.values() if getattr(d, "idn_mA", None) and n in idx.ancestors(d.id or "")]
        if down and not (n.selective or n.delay == "S" if hasattr(n, "delay") else n.selective):  # type: ignore[attr-defined]
            yield SELECTIVITY.finding("warning", _t("nfc15100.selectivity"), nid)
