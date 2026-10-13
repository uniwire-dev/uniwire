"""``iec60364`` profile: current-carrying capacity of wiring systems (Iz).

The ``iec60364.iz`` rule compares the rating ``in_A`` of the protection feeding a cable with the
current-carrying capacity Iz read from ``registry/data/iz_tables.json`` (GUIA-BT-19, tables of
UNE 20460-5-523:2004, the Spanish transposition of IEC 60364-5-523). It only applies when the cable
specifies ``section_mm2``, ``material``, ``insulation`` and ``install``. Values are given at 40 °C
ambient (Spanish reference): they are conservative compared with the IEC tables at 30 °C, and no
grouping factor is applied. Outcome: warning, never error.
"""

from __future__ import annotations

from .. import registry
from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import describe, rule

IZ = describe(
    "iec60364.iz",
    "GUIA-BT-19 (Ministerio de Industria, feb. 2009 rev. 2), p. 9 Tabla A (= UNE 20460-5-523:2004 "
    "Tabla A.52-1 bis, 40 °C ambient) and p. 12 Tabla D (buried in duct, 25 °C, 1.5 K·m/W)",
    "high")

PROTECTIONS = ("breaker", "rcbo", "fuse", "fuse_switch", "main_breaker", "motor_starter", "thermal_relay")
INSULATION = {"PVC": "PVC", "XLPE": "XLPE", "PR": "XLPE", "EPR": "XLPE"}
METHODS = {"A1", "A2", "B1", "B2", "C", "E", "F", "D-DUCT"}
THREE_PHASE = ("3P", "3P+N", "4P")


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
        p = next((a for a in [n] + idx.ancestors(nid) if a.type in PROTECTIONS), None)  # type: ignore[attr-defined]
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
