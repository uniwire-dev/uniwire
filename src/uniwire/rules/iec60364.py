"""``iec60364`` profile: current-carrying capacity of wiring systems (Iz) and the 30 mA RCD of socket-outlets.

The ``iec60364.iz`` rule compares the rating ``in_A`` of the protection feeding a cable with the
current-carrying capacity Iz read from ``registry/data/iz_tables.json`` (GUIA-BT-19, tables of
UNE 20460-5-523:2004, the Spanish transposition of IEC 60364-5-523). It only applies when the cable
specifies ``section_mm2``, ``material``, ``insulation`` and ``install``. Values are given at 40 °C
ambient (Spanish reference): they are conservative compared with the IEC tables at 30 °C, and no
grouping factor is applied. Outcome: warning, never error.

A cable giving its section but not its material, insulation or installation method is estimated by the
``iec60364.iz-estimate`` rule: copper and PVC unless stated, the most favourable method in air (A1 to F) unless
stated, values brought back to 30 °C (IEC 60364-5-52, table B.52.14: 0.87 for PVC, 0.91 for XLPE at 40 °C). A
protection above that Iz is too high under these assumptions: warning. The cables estimated are listed in one
info finding, so that an empty result is not read as a checked cable.

The ``iec60364.rcd-30mA`` rule (IEC 60364-4-41:2005+AMD1:2017, 411.3.3 and 411.3.4): socket-outlets up to 32 A
protected by an RCD of at most 30 mA in all premises, final circuits of luminaires the same in dwellings (the 2005
edition without its amendment: socket-outlets up to 20 A, no requirement for luminaires). A circuit of a medical
IT system (below an isolation transformer, IEC 60364-7-710) is monitored by an insulation monitoring device instead.
Left to the ``nfc15100`` and ``vde0100`` profiles when the document declares one of them (they check it with their
national scope).
"""

from __future__ import annotations

from .. import registry
from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import describe, rule
from .nfc15100 import _rcds, _socket_rating

IZ = describe(
    "iec60364.iz",
    "GUIA-BT-19 (Ministerio de Industria, feb. 2009 rev. 2), p. 9 Tabla A (= UNE 20460-5-523:2004 "
    "Tabla A.52-1 bis, 40 °C ambient) and p. 12 Tabla D (buried in duct, 25 °C, 1.5 K·m/W)",
    "high")
IZ_ESTIMATE = describe(
    "iec60364.iz-estimate",
    "GUIA-BT-19 Tabla A (as iec60364.iz) brought back to 30 °C with IEC 60364-5-52, table B.52.14; copper, PVC "
    "and the most favourable method in air when the cable does not state them",
    "medium")
RCD_30MA = describe(
    "iec60364.rcd-30mA",
    "IEC 60364-4-41:2005+AMD1:2017, 411.3.3: socket-outlets up to 32 A protected by an RCD of at most 30 mA, all "
    "premises; 411.3.4: final circuits of luminaires in dwellings, the same; IEC 60364-7-710: a medical IT system "
    "(isolation transformer) is monitored by an insulation monitoring device instead",
    "high")

PROTECTIONS = ("breaker", "rcbo", "fuse", "fuse_switch", "main_breaker", "motor_starter", "thermal_relay")
INSULATION = {"PVC": "PVC", "XLPE": "XLPE", "PR": "XLPE", "EPR": "XLPE"}
METHODS = {"A1", "A2", "B1", "B2", "C", "E", "F", "D-DUCT"}
THREE_PHASE = ("3P", "3P+N", "4P")
AIR_METHODS = ("A1", "A2", "B1", "B2", "C", "E", "F")
AT_40C = {"PVC": 0.87, "XLPE": 0.91}  # IEC 60364-5-52, table B.52.14: ambient 40 °C against the 30 °C reference


def _method(install: str) -> str | None:
    m = install.strip().upper().replace(" ", "")
    return ("D-duct" if m == "D-DUCT" else m) if m in METHODS else None


def lookup_iz(material: str, insulation: str, method: str, loaded: int, section_mm2: float) -> float | None:
    """Iz (A) from the table, or ``None`` if the combination is not covered by the source."""
    t = registry.iz_tables()["tables"]
    try:
        return t[material][INSULATION[insulation]][method][str(loaded)][f"{section_mm2:g}"]
    except KeyError:
        return None


def _rating(p) -> float | None:
    r = (getattr(p, "ir_A", None) or getattr(p, "setting_A", None) or getattr(p, "fuse_A", None)
         or getattr(p, "in_A", None))
    if r is None and getattr(p, "range_A", None) and p.type == "thermal_relay":
        # thermal relay without explicit setting: upper bound of its setting range
        try:
            r = float(str(p.range_A).replace(",", ".").split("-")[-1])
        except ValueError:
            r = None
    return r


def _loaded_conductors(doc: Document, p, node) -> int:
    poles = getattr(p, "poles", None)
    if poles in THREE_PHASE:
        return 3
    if poles is not None or getattr(node, "phase", None) in ("L1", "L2", "L3"):
        return 2
    return 2 if doc.installation.system in (None, "1P+N") else 3


@rule("iec60364")
def iz_check(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        c = n.cable
        if c is None or None in (c.section_mm2, c.material, c.insulation, c.install):
            continue
        method = _method(c.install)  # type: ignore[arg-type]
        if method is None:
            yield IZ.finding("info", _t("iec60364.install_uncovered", install=c.install), nid)
            continue
        # protection feeding this cable: the node itself if it is a protection at the head of the cable,
        # otherwise the nearest protective ancestor (motor starter, overload relay, breaker...)
        p = _protection(idx, nid, n)
        rating = _rating(p) if p is not None else None
        if rating is None:
            continue
        loaded = _loaded_conductors(doc, p, n)
        iz = lookup_iz(c.material, c.insulation, method, loaded, c.section_mm2)  # type: ignore[arg-type]
        if iz is None:
            yield IZ.finding("info", _t("iec60364.iz_unavailable", material=c.material, insulation=c.insulation,
                                section=c.section_mm2, method=method, loaded=loaded), nid)
            continue
        iz *= c.parallel or 1
        if rating > iz:
            yield IZ.finding("warning", _t("iec60364.iz_exceeded", rating=rating, iz=iz, material=c.material,
                                insulation=c.insulation, section=c.section_mm2, method=method, loaded=loaded,
                                ambient=_t("iec60364.ambient_ground" if method == "D-duct"
                                           else "iec60364.ambient_air")), nid)


def _protection(idx: Index, nid: str, n):
    """The protection feeding the cable of ``n``: the node itself if it is one, otherwise its nearest protective
    ancestor."""
    return next((a for a in [n] + idx.ancestors(nid) if a.type in PROTECTIONS), None)  # type: ignore[attr-defined]


def _tag(n, nid: str) -> str:
    return getattr(n, "ref", None) or getattr(n, "label", None) or nid


@rule("iec60364")
def iz_estimate(doc: Document, idx: Index):
    estimated: list[str] = []
    for nid, n in idx.nodes.items():
        c = n.cable
        if c is None or c.section_mm2 is None or None not in (c.material, c.insulation, c.install):
            continue
        given = _method(c.install) if c.install else None
        if c.install and given is None:
            continue  # an unknown method: reported by iec60364.iz when the cable is otherwise complete
        p = _protection(idx, nid, n)
        rating = _rating(p) if p is not None else None
        if rating is None:
            continue
        material, insulation = c.material or "Cu", INSULATION.get(c.insulation or "PVC")
        if insulation is None:
            continue
        loaded = _loaded_conductors(doc, p, n)
        methods = [given] if given else AIR_METHODS
        values = [lookup_iz(material, insulation, m, loaded, c.section_mm2) for m in methods]
        best = max((v for v in values if v is not None), default=None)
        if best is None:
            continue
        iz = round(best / AT_40C[insulation] * (c.parallel or 1), 1)
        estimated.append(_tag(n, nid))
        if rating > iz:
            yield IZ_ESTIMATE.finding("warning", _t("iec60364.iz_estimate_exceeded", rating=rating, iz=iz,
                                      material=material, insulation=insulation, section=c.section_mm2,
                                      method=given or _t("iec60364.any_air_method"), loaded=loaded), nid)
    if estimated:
        tags = ", ".join(estimated[:6]) + (", …" if len(estimated) > 6 else "")
        yield IZ_ESTIMATE.finding("info", _t("iec60364.iz_estimated", count=len(estimated), tags=tags))


def _medical_it(idx: Index, nid: str) -> bool:
    """Below an isolation transformer feeding an IT system (IEC 60364-7-710)."""
    up = idx.ancestors(nid)
    isolation = any(a.type == "transformer" and getattr(a, "kind", None) == "isolation"  # type: ignore[attr-defined]
                    for a in up)
    return isolation and any(getattr(a, "earthing", None) == "IT" for a in up)


@rule("iec60364")
def rcd_30ma(doc: Document, idx: Index):
    if {"nfc15100", "vde0100"} & set(doc.profiles):
        return
    dwelling = doc.installation.premises == "dwelling"
    for nid, n in idx.nodes.items():
        t = n.type  # type: ignore[attr-defined]
        if t not in ("socket", "lighting") or t == "lighting" and not dwelling:
            continue
        if t == "socket" and (_socket_rating(idx, nid) or 0) > 32:
            continue
        if any(a.idn_mA <= 30 for a in _rcds(idx, nid)):  # type: ignore[attr-defined]
            continue
        if _medical_it(idx, nid):
            continue
        what = n.label or registry.label(t)  # type: ignore[attr-defined]
        yield RCD_30MA.finding("error", _t(f"iec60364.rcd_30mA_{t}", what=what), nid)
