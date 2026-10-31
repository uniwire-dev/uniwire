"""``iec60364`` profile: current-carrying capacity of wiring systems (Iz) and the 30 mA RCD of socket-outlets.

The ``iec60364.iz`` rule compares the rating ``in_A`` of the protection feeding a cable with its current-carrying
capacity Iz, given by the formulas of ``registry/data/iz_iec60364.json`` (after IEC 60364-5-52, never above its
values). It only applies when the cable specifies
``section_mm2``, ``material``, ``insulation`` and ``install`` (``D-duct`` is read as ``D1``, cables in ducts in the
ground). The formulas give Iz at 30 °C in air, 20 °C in the ground (2.5 K·m/W). The cable's ``ambient_C`` corrects
them by sqrt((θmax - θ) / (θmax - θref)), θmax 70 °C for PVC and 90 °C for XLPE, from 10 °C up to 60 °C (PVC) or
80 °C (XLPE); above, Iz is not checked (info). Without ``ambient_C``,
40 °C in air and 20 °C in the ground, as the message says. The cable's ``grouped`` (with ``arrangement``,
``supports`` or, in the ground, ``spacing_m``), ``soil_resistivity_K_m_W`` (D1, D2) and ``third_harmonic_pct``
(three-phase circuit with a neutral) apply the grouping, soil and harmonic factors, formulas of the same file;
beyond their range, Iz is not checked (info). Outcome: warning, never error.

A cable giving its section but not its material, insulation or installation method is estimated by the
``iec60364.iz-estimate`` rule: copper and PVC unless stated, the most favourable method in air (A1 to F) unless
stated, at 30 °C unless ``ambient_C`` says otherwise. A protection above that Iz is too high under these
assumptions: warning. The cables estimated are listed in one info finding, so that an empty result is not read as a
checked cable.

The ``iec60364.rcd-30mA`` rule (IEC 60364-4-41:2005+AMD1:2017, 411.3.3 and 411.3.4): socket-outlets up to 32 A
protected by an RCD of at most 30 mA in all premises, final circuits of luminaires the same in dwellings (the 2005
edition without its amendment: socket-outlets up to 20 A, no requirement for luminaires). A circuit of a medical
IT system (below an isolation transformer, IEC 60364-7-710) is monitored by an insulation monitoring device instead.
Left to the ``nfc15100`` and ``vde0100`` profiles when the document declares one of them (they check it with their
national scope).
"""

from __future__ import annotations

import math

from .. import registry
from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import PROFILES, describe, rule
from .core import VOLTAGE_CONVERTERS

SOURCE = "IEC 60364-5-52"
IZ = describe("iec60364.iz", SOURCE, "high")
IZ_ESTIMATE = describe(
    "iec60364.iz-estimate",
    SOURCE + "; copper, PVC and the most favourable method in air when the cable does not state them",
    "medium")
RCD_30MA = describe(
    "iec60364.rcd-30mA",
    "IEC 60364-4-41:2005+AMD1:2017, 411.3.3: socket-outlets up to 32 A protected by an RCD of at most 30 mA, all "
    "premises; 411.3.4: final circuits of luminaires in dwellings, the same; IEC 60364-7-710: a medical IT system "
    "(isolation transformer) is monitored by an insulation monitoring device instead",
    "high")

PROTECTIONS = ("breaker", "rcbo", "fuse", "fuse_switch", "main_breaker", "motor_starter", "thermal_relay")
INSULATION = {"PVC": "PVC", "XLPE": "XLPE", "PR": "XLPE", "EPR": "XLPE"}
METHODS = {"A1", "A2", "B1", "B2", "C", "D1", "D2", "E", "F"}
THREE_PHASE = ("3P", "3P+N", "4P")
AIR_METHODS = ("A1", "A2", "B1", "B2", "C", "E", "F")
BURIED = ("D1", "D2")
THETA_MAX = {"PVC": 70.0, "XLPE": 90.0}  # conductor temperature in normal operation (IEC 60364-5-52, 52.1)
THETA_LIMIT = {"PVC": 60.0, "XLPE": 80.0}  # highest ambient corrected (IEC 60364-5-52)
THETA_MIN = 10.0  # lowest: a colder ambient is taken as this


def _method(install: str) -> str | None:
    m = install.strip().upper().replace(" ", "")
    m = "D1" if m == "D-DUCT" else m
    return m if m in METHODS else None


def temperature_factor(insulation: str, ambient: float, buried: bool) -> float | None:
    """Correction of Iz for an ambient (air) or ground temperature other than the reference (30 °C in air, 20 °C in
    the ground); ``None`` above the range of IEC 60364-5-52."""
    ins = INSULATION.get(insulation)
    if ins is None or ambient > THETA_LIMIT[ins]:
        return None
    ref = 20.0 if buried else 30.0
    return ((THETA_MAX[ins] - max(ambient, THETA_MIN)) / (THETA_MAX[ins] - ref)) ** 0.5


def _ambient(c, method: str, insulation: str, default_air: float) -> tuple[float, float, bool] | None:
    """(factor on Iz, temperature used, ambient_C given) for a cable; ``None`` when its ambient is above what the
    tables cover: Iz is then not checked."""
    buried = method in BURIED
    given = c.ambient_C
    temp = given if given is not None else 20.0 if buried else default_air
    k = temperature_factor(insulation, temp, buried)
    return None if k is None else (k, temp, given is not None)


def _ambient_text(method: str, temp: float, given: bool) -> str:
    where = _t("iec60364.ambient_ground" if method in BURIED else "iec60364.ambient_air", t=temp)
    return where if given else where + _t("iec60364.ambient_default")


def _group(p: list[float], n: int) -> float:
    f1, b, floor = p
    return max(floor, f1 * n ** -b)


def _single_core(c) -> bool:
    """A cable made of single cores (``4x(1x240)``, ``3x1x95``): one duct per core in the ground."""
    return "1x" in (c.cores or "").replace(" ", "").lower()


def grouping_factor(c, method: str) -> float | None:
    """Factor of Iz for the cables laid with this one (``grouped``, ``arrangement``, ``supports``, ``spacing_m``);
    ``None`` beyond the formulas."""
    n = c.grouped or 1
    data = registry.iz_iec60364()["factors"]["grouping"]
    if method in BURIED:
        if n == 1:
            return 1.0
        ground = data["ground"]
        if n > ground["n_max"]:
            return None
        key = "D2" if method == "D2" else "D1_single_core" if _single_core(c) else "D1_multicore"
        spacing = c.spacing_m or 0.0  # the classes up to the actual distance: the best of them holds
        return max(_group(p, n) for d, p in ground["methods"][key].items() if float(d) <= spacing)
    arrangement = c.arrangement or "bunched"
    if (c.supports or 1) > 1 and arrangement in ("perforated_tray", "ladder"):
        stacked = data["stacked"]
        p = stacked["supports"][arrangement].get(str(c.supports))
        return None if p is None or n > stacked["n_max"] else _group(p, n)
    air = data["air"]
    return None if n > air["n_max"] else _group(air["arrangements"][arrangement], n)


def soil_factor(c, method: str) -> float | None:
    """Factor of Iz for the thermal resistivity of the soil (D1, D2), 2.5 K·m/W when not given; ``None`` above
    the formulas. A resistivity below their range is taken as its lowest value."""
    if method not in BURIED:
        return 1.0
    rho = max(c.soil_resistivity_K_m_W or 2.5, 0.5)
    piece = next((p for p in registry.iz_iec60364()["factors"]["soil"][method] if p[0] <= rho <= p[1]), None)
    return None if piece is None else ((piece[2] + 2.5) / (piece[2] + rho)) ** piece[3]


def harmonic_factor(c, neutral: bool) -> float | None:
    """Factor of Iz of a three-phase cable whose neutral carries the third harmonics of the phase currents
    (``third_harmonic_pct``); ``None`` above the formulas (the neutral is then sized for its own current)."""
    if not c.third_harmonic_pct or not neutral:
        return 1.0
    reduced = c.neutral_section_mm2 is not None and c.neutral_section_mm2 < (c.section_mm2 or 0)
    p = registry.iz_iec60364()["factors"]["harmonics"]["reduced_neutral" if reduced else "full_neutral"]
    h = c.third_harmonic_pct / 100
    return None if h > p["h_max"] else math.floor(100 / math.sqrt(1 + p["c"] * h * h)) / 100


def _factors(c, method: str, neutral: bool) -> tuple[float, str] | str:
    """(product of the grouping, soil and harmonic factors, their text for the message), or the text of the
    first condition beyond the formulas."""
    k, parts = 1.0, []
    g = grouping_factor(c, method)
    if g is None:
        if (c.supports or 1) > 3 and method not in BURIED:
            return _t("iec60364.u_supports", s=c.supports)
        return _t("iec60364.u_grouped", n=c.grouped)
    if g != 1.0:
        k *= g
        parts.append(_t("iec60364.k_grouped", n=c.grouped or 1, k=round(g, 2)))
    s = soil_factor(c, method)
    if s is None:
        return _t("iec60364.u_soil", rho=c.soil_resistivity_K_m_W)
    if c.soil_resistivity_K_m_W is not None and method in BURIED:
        k *= s
        parts.append(_t("iec60364.k_soil", rho=c.soil_resistivity_K_m_W, k=round(s, 2)))
    h = harmonic_factor(c, neutral)
    if h is None:
        return _t("iec60364.u_harmonic", h=c.third_harmonic_pct)
    if h != 1.0:
        k *= h
        parts.append(_t("iec60364.k_harmonic", h=c.third_harmonic_pct, k=h))
    return k, "".join(", " + x for x in parts)


def lookup_iz(material: str, insulation: str, method: str, loaded: int, section_mm2: float) -> float | None:
    """Iz (A) at the reference conditions, or ``None`` if the tables do not give this combination."""
    try:
        pieces = registry.iz_iec60364()["pieces"][method][INSULATION[insulation]][material][str(loaded)]
    except KeyError:
        return None
    values = [a * section_mm2 ** m for lo, hi, a, m in pieces if lo <= section_mm2 <= hi]
    if not values and pieces[0][0] <= section_mm2 <= pieces[-1][1]:  # between two ranges (16 to 25 mm²)
        values = [a * section_mm2 ** m for _lo, _hi, a, m in pieces]
    return min(values) if values else None


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


def _neutral(doc: Document, p, loaded: int) -> bool:
    """A three-phase circuit with a loaded neutral (``3P+N``, ``4P``, or the system when the poles are not
    given): the third harmonics of the phases add up in it."""
    poles = getattr(p, "poles", None)
    return loaded == 3 and (poles in ("3P+N", "4P") or poles is None and doc.installation.system == "3P+N")


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
        amb = _ambient(c, method, c.insulation, 40.0)  # type: ignore[arg-type]
        if amb is None:
            yield IZ.finding("info", _t("iec60364.ambient_uncovered", ambient=c.ambient_C, method=method,
                                limit=THETA_LIMIT[INSULATION[c.insulation]]), nid)  # type: ignore[index]
            continue
        iz = lookup_iz(c.material, c.insulation, method, loaded, c.section_mm2)  # type: ignore[arg-type]
        if iz is None:
            yield IZ.finding("info", _t("iec60364.iz_unavailable", material=c.material, insulation=c.insulation,
                                section=c.section_mm2, method=method, loaded=loaded), nid)
            continue
        f = _factors(c, method, _neutral(doc, p, loaded))
        if isinstance(f, str):
            yield IZ.finding("info", _t("iec60364.factor_uncovered", what=f), nid)
            continue
        iz = round(iz * amb[0] * f[0] * (c.parallel or 1), 1)
        if rating > iz:
            yield IZ.finding("warning", _t("iec60364.iz_exceeded", rating=rating, iz=iz, material=c.material,
                                insulation=c.insulation, section=c.section_mm2, method=method, loaded=loaded,
                                ambient=_ambient_text(method, amb[1], amb[2]) + f[1]), nid)


def _protection(idx: Index, nid: str, n):
    """The protection feeding the cable of ``n``: the node itself if it is one, otherwise its nearest protective
    ancestor on the same side of any converter (a breaker on the AC side does not protect the DC cables of an
    inverter's strings)."""
    if n.type in PROTECTIONS:  # type: ignore[attr-defined]
        return n
    for a in idx.ancestors(nid):
        if a.type in VOLTAGE_CONVERTERS:  # type: ignore[attr-defined]
            return None
        if a.type in PROTECTIONS:  # type: ignore[attr-defined]
            return a
    return None


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
        amb = _ambient(c, given or "air", insulation, 30.0)
        f = _factors(c, given or "air", _neutral(doc, p, loaded))
        if amb is None or isinstance(f, str):
            continue  # beyond the tables: not estimated either
        iz = round(best * amb[0] * f[0] * (c.parallel or 1), 1)
        estimated.append(_tag(n, nid))
        if rating > iz:
            yield IZ_ESTIMATE.finding("warning", _t("iec60364.iz_estimate_exceeded", rating=rating, iz=iz,
                                      material=material, insulation=insulation, section=c.section_mm2,
                                      method=given or _t("iec60364.any_air_method"), loaded=loaded, t=amb[1]), nid)
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
    if {"nfc15100", "vde0100"} & set(doc.profiles) & set(PROFILES):  # a national profile checks it
        return
    from .nfc15100 import _rcds, _socket_rating  # here: importing it first would register its profile first
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
