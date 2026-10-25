"""Displayed text: annotations next to symbols and cells of the outgoing-feeder table."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Optional

from . import registry
from .i18n import normalize_lang, render_lang
from .i18n import t as _t
from .model import Cable, NodeBase
from .units import fmt, fmt_sensitivity

PROTECTIVE = {"breaker", "rcbo", "main_breaker", "fuse", "fuse_switch", "rcd", "switch_disconnector",
              "disconnector", "motor_starter"}


def _g(node: Any, name: str) -> Any:
    return getattr(node, name, None)


def _rcd_text(node: Any) -> str:
    parts = []
    if _g(node, "idn_mA") is not None:
        parts.append(fmt_sensitivity(node.idn_mA))
    if _g(node, "rcd_type"):
        parts.append(_t("label.rcd_type", render_lang(), type=node.rcd_type))
    delay = str(_g(node, "delay") or "").strip()
    if delay.upper() == "S" or _g(node, "selective"):
        parts.append("S")
    elif delay and delay.lower() not in ("inst", "instantaneous"):
        # free-text delay: '0.5 s', 'retardable', or a bare number of milliseconds
        parts.append(f"{delay} ms" if delay.replace(".", "", 1).isdigit() else delay)
    return " ".join(parts)


def part_number(node: Any) -> Optional[str]:
    """Part number: ``product.part_number`` takes precedence over ``part_number``."""
    prod = _g(node, "product")
    return (prod.part_number if prod is not None and prod.part_number else None) or _g(node, "part_number")


def protection_short(node: Any) -> str:
    """'C16', '40A 30mA A', 'gG 32A', 'IS 63A'..."""
    t = node.type
    in_a = _g(node, "in_A")
    if t == "breaker":
        return f"{node.curve or ''}{fmt(in_a)}" if node.curve else (fmt(in_a, "A") if in_a else "")
    if t == "rcbo":  # 'C16 30mA', or '20A 5mA' without a curve (the rating alone would read as part of the mA)
        rating = f"{node.curve}{fmt(in_a)}" if node.curve else (fmt(in_a, "A") if in_a else "")
        return f"{rating} {fmt_sensitivity(node.idn_mA)}".strip()
    if t == "main_breaker":
        r = node.range_A or fmt(in_a)
        return f"{r}A {fmt_sensitivity(node.idn_mA)}".strip()
    if t == "rcd":
        return f"{fmt(in_a, 'A')} {fmt_sensitivity(node.idn_mA)}".strip()
    if t == "fuse":
        return f"{node.fuse_class or ''} {fmt(in_a, 'A')}".strip()
    if t == "fuse_switch":
        return f"{fmt(in_a, 'A')} / {fmt(node.fuse_A, 'A')}".strip(" /")
    if t in ("switch_disconnector", "disconnector"):
        return fmt(in_a, "A")
    if t == "motor_starter":
        return f"{fmt(in_a, 'A')}"
    if t == "spare":
        return fmt(in_a, "A") if in_a else ""
    return ""


def _ratio(u1: float, u2: float) -> str:
    """Voltage ratio of a transformer, in one unit when both sides allow it: '22/11 kV', '400/230 V', '20 kV/400 V'."""
    if u1 >= 1000 and u2 >= 1000:
        return f"{fmt(u1 / 1000)}/{fmt(u2 / 1000)} kV"
    if u1 < 1000 and u2 < 1000:
        return f"{fmt(u1)}/{fmt(u2)} V"
    return f"{fmt(u1 / 1000)} kV/{fmt(u2)} V" if u1 >= 1000 else f"{fmt(u1)} V/{fmt(u2 / 1000)} kV"


def ref_label(ref: Optional[str], label: Optional[str]) -> str:
    """Name of a node from its tag and label, the tag once when the label already starts with it."""
    if ref and label and (label == ref or label.startswith(ref + " ")):
        return label
    return " ".join(x for x in (ref, label) if x)


def without_ref(label: str, ref: Optional[str]) -> str:
    """``label`` without a leading copy of the tag printed above it ('TX-A 3150 kVA' under 'TX-A')."""
    if ref and label.startswith(ref) and (len(label) == len(ref) or label[len(ref)] in " -:,/"):
        return label[len(ref):].strip(" -:,/")
    return label


def awg_text(size: str) -> str:
    """'12' -> '#12', '4/0' and '250 kcmil' unchanged."""
    size = size.strip()
    return f"#{size}" if size.isdigit() else size


POLES_CONDUCTORS = {"1P": 2, "1P+N": 2, "2P": 2, "3P": 3, "3P+N": 4, "4P": 4}
SYSTEM_CONDUCTORS = {"1P+N": 2, "2P": 2, "DC": 2, "3P": 3, "3P+N": 4, "split-phase": 3}
THREE_PHASE_POLES = ("3P", "3P+N", "4P")


def conductor_count(chain: list[Any], system: Optional[str] = None) -> Optional[int]:
    """Live conductors (phases + neutral, without PE) of a feeder.

    ``chain``: the final node then its ancestors up to the feeding busbar. In order of precedence: cable
    cores ('3G' -> 2, '5G' -> 4, '4-#10+G' -> 4), poles of the nearest protection, phase of a single-phase circuit, number of
    phases of a motor, then the supply ``system``.
    """
    for n in chain:
        c = _g(n, "cable")
        cores = (c.cores or "") if c is not None else ""
        if len(cores) == 2 and cores[0].isdigit() and cores[1] in "Gg":  # 'G' composition includes the PE
            return int(cores[0]) - 1
        m = re.match(r"(?:\d+x\()?(\d)-[^+]*\+G", cores)  # North-American '4-#10+G', '3x(4-600 kcmil)+G'
        if m:
            return int(m[1])
    for n in chain:
        poles = _g(n, "poles")
        if poles in POLES_CONDUCTORS and n.type in PROTECTIVE | {"spare"}:
            return POLES_CONDUCTORS[poles]
    for n in chain:
        ph = _g(n, "phase")
        if ph:
            return 3 if ph == "L1L2L3" else 2
    if chain and _g(chain[0], "phases"):
        return 2 if chain[0].phases == 1 else 3
    return SYSTEM_CONDUCTORS.get(system or "")


Mark = tuple[int, bool]  # conductor-count mark: (counted conductors, separate uncut neutral)
SWITCHING = PROTECTIVE | {"contactor", "transfer_switch", "impulse_relay"}
POLES_MARK: dict[str, Mark] = {"1P": (1, True), "1P+N": (1, True), "2P": (2, False), "3P": (3, False),
                               "3P+N": (3, True), "4P": (4, False)}


def system_mark(system: Optional[str]) -> Optional[Mark]:
    """Mark of a supply line: every live conductor counted ('3P+N' -> 4)."""
    n = SYSTEM_CONDUCTORS.get(system or "")
    return (n, False) if n else None


def poles_mark(poles: Optional[str], neutral_downstream: bool = False) -> Optional[Mark]:
    """Mark of the line leaving a switching device of ``poles``.

    '4P' (neutral switched): 4 conductors; '3P+N' / '1P+N' / '1P': the phases plus a neutral that is not
    cut; '3P': three conductors, or three plus an uncut neutral when circuits below need one.
    """
    if poles == "3P" and neutral_downstream:
        return (3, True)
    return POLES_MARK.get(poles or "")


def feeder_mark(chain: list[Any], system: Optional[str] = None) -> Optional[Mark]:
    """Mark of an outgoing cable: :func:`conductor_count`, with the neutral shown apart ('3+N', '1+N') when
    the nearest switching device leaves it uncut. A DC feeder has no neutral: its two poles are counted."""
    n = conductor_count(chain, system)
    if not n:
        return None
    if system == "DC":
        return (n, False)
    poles = next((_g(c, "poles") for c in chain if c.type in SWITCHING | {"spare"} and _g(c, "poles")), None)
    if poles in ("1P", "1P+N", "3P", "3P+N") and n == int(poles[0]) + 1:
        return (n - 1, True)
    return (n, False)


def cable_in_awg(c: Optional[Cable]) -> bool:
    """Whether a cable is written with its North-American size: an AWG / kcmil size, unless the composition is
    written the IEC way with a section in mm² ('3G' + 2.5)."""
    if c is None or not c.size_awg:
        return False
    cores = (c.cores or "").rstrip()
    return c.section_mm2 is None or not (cores and cores[-1] in "Gx×")


def cable_text(c: Optional[Cable]) -> str:
    """'3G2,5', '4x(2x1x240)', '2x(5G16)'; North-American sizes when given, unless the composition is written the
    IEC way ('3G' + mm²): '2-#12', '3x(4-600 kcmil)' (the section in mm² then only serves the checks)."""
    if c is None:
        return ""
    s = ""
    cores = c.cores or ""
    if c.section_mm2 is not None and not cable_in_awg(c):
        sec = fmt(c.section_mm2)
        if cores.isdigit():  # a bare count of conductors: '2' and 1.5 mm² -> '2x1.5', not '21.5'
            cores += "x"
        glue = "" if cores[-1:] in ("G", "x", "×", "-") else " "  # '5G2.5', '2x1.5'; 'busbar 2000'
        if cores and (cores.endswith(")") or re.search(r"\d$", cores)):
            s = cores  # the composition already has its sections ('3x150+70', '4x(1x240)')
        else:
            s = f"{cores}{glue}{sec}" if cores else sec
    elif c.size_awg:
        size = awg_text(c.size_awg)
        if not cores:
            s = size
        elif c.size_awg.strip().lstrip("#") in cores:  # composition already spells the size: '2-#12+G'
            return cores
        else:
            s = f"{cores}{size}" if cores[-1] in "-x×" else f"{cores} {size}"
    elif cores:
        return cores
    if s and c.parallel and c.parallel > 1:
        s = f"{c.parallel}x({s})"
    return s


def annotation(node: NodeBase, lang: str = "en", show_label: bool = False) -> list[str]:
    """Text lines to the right of the symbol (without the tag, which the renderer adds in bold).

    ``lang`` selects the language of the few translated words (see :mod:`uniwire.i18n`).
    """
    lang = normalize_lang(lang)
    t = node.type  # type: ignore[attr-defined]
    g = lambda n: _g(node, n)  # noqa: E731
    lines: list[str] = []
    if t == "grid":
        lines += [node.label or g("supply") or ""]
        if g("supply") and node.label:
            lines.append(g("supply"))
        if g("un_V"):
            lines.append(fmt(g("un_V"), " V"))
        return [x for x in lines if x]
    if node.label and (show_label or t not in ("breaker", "rcbo", "rcd", "fuse", "fuse_switch")) \
            and registry.category(t) != "load":
        lines.append(node.label)
    if t == "transformer":
        lines += [fmt(g("sn_kVA"), " kVA") if g("sn_kVA") else "",
                  _ratio(g("u1_V"), g("u2_V")) if g("u1_V") and g("u2_V") else "",
                  " ".join(x for x in (g("coupling"), f"ucc {fmt(g('ucc_pct'))}%" if g("ucc_pct") else "") if x)]
    elif t == "generator":
        lines += [fmt(g("sn_kVA"), " kVA") if g("sn_kVA") else fmt(g("p_kW"), " kW") if g("p_kW") else "",
                  fmt(g("un_V"), " V") if g("un_V") else ""]
    elif t == "ups":
        lines += [fmt(g("sn_kVA"), " kVA") if g("sn_kVA") else "",
                  f"{fmt(g('autonomy_min'))} min" if g("autonomy_min") else ""]
    elif t == "inverter":
        n = f"{g('count')} x " if g("count") and g("count") > 1 else ""
        lines += [f"{n}{fmt(g('p_kVA'), ' kVA')}" if g("p_kVA") else ""]
    elif t == "meter":
        lines += [g("kind") or "", fmt(g("in_A"), " A") if g("in_A") else ""]
    elif t in ("breaker", "rcbo"):
        if g("frame_A") and not g("in_A"):
            lines.append(_t("ann.frame", lang, frame=fmt(g("frame_A"))))
        lines.append(protection_short(node))
        extra = []
        if g("icn_kA"):
            extra.append(fmt(g("icn_kA"), "kA"))
        if g("poles"):
            extra.append(g("poles"))
        if extra:
            lines.append(" ".join(extra))
        if t == "rcbo":
            lines.append(_rcd_text(node).replace(fmt_sensitivity(g("idn_mA")), "").strip())
            if g("idn_range_mA"):
                lines.append(f"IΔn {g('idn_range_mA')} mA")
        if g("ir_A"):
            lines.append(f"Ir {fmt(g('ir_A'))}A")
        if g("range") and len(lines) < 4:
            lines.insert(0, g("range"))
    elif t == "main_breaker":
        r = g("range_A")
        lines += [f"{r} A" if r else fmt(g("in_A"), " A") if g("in_A") else "", _rcd_text(node), g("poles") or "",
                  fmt(g("subscribed_kVA"), " kVA") if g("subscribed_kVA") else ""]
    elif t == "rcd":
        lines += [fmt(g("in_A"), " A") if g("in_A") else "", _rcd_text(node),
                  f"IΔn {g('idn_range_mA')} mA" if g("idn_range_mA") else ""]
    elif t in ("fuse", "fuse_switch", "switch_disconnector", "disconnector"):
        lines += [protection_short(node), g("poles") or ""]
    elif t == "contactor":
        lines += [fmt(g("in_A"), " A") if g("in_A") else "", _t("ann.off_peak", lang) if g("function") == "HC" else ""]
    elif t == "impulse_relay":
        lines += [fmt(g("in_A"), " A") if g("in_A") else ""]
    elif t == "thermal_relay":
        rng = str(g("range_A") or "")
        if normalize_lang(lang) in ("fr", "ru"):  # the decimal comma of the rest of the text
            rng = re.sub(r"(?<=\d)\.(?=\d)", ",", rng)
        lines += [f"{rng} A" if rng else "", f"Ir {fmt(g('setting_A'))} A" if g("setting_A") else ""]
    elif t == "motor_starter":
        lines += [fmt(g("p_kW"), " kW") if g("p_kW") else "", fmt(g("in_A"), " A") if g("in_A") else ""]
    elif t == "transfer_switch":
        lines += [fmt(g("in_A"), " A") if g("in_A") else "", {"automatic": _t("ann.automatic", lang), "manual": _t("ann.manual", lang)}.get(g("mode") or "", "")]
    elif t == "spd":
        lines += [f"Type {g('spd_type')}" if g("spd_type") else "", fmt(g("imax_kA"), " kA") if g("imax_kA") else ""]
    elif t == "busbar":
        lines += [fmt(g("in_A"), " A") if g("in_A") else "", g("dimensions") or ""]
    elif t == "board":
        lines += [fmt(g("ik_kA"), " kA") if g("ik_kA") else ""]
    elif t == "earth":
        lines += [fmt(g("resistance_ohm"), " Ω") if g("resistance_ohm") else ""]
    elif t == "pv_array":
        mod = f"{g('modules')} x {fmt(g('module_W'))} {_t('ann.peak_power_unit', lang)}" if g("modules") and g("module_W") else ""
        lines += [mod, fmt(g("p_kW"), " " + _t("ann.peak_power_kunit", lang)) if g("p_kW") else ""]
    elif t == "battery":
        lines += [fmt(g("capacity_kWh"), " kWh") if g("capacity_kWh") else "", fmt(g("un_V"), " V") if g("un_V") else ""]
    elif t == "motor":
        lines += [fmt(g("p_kW"), " kW") if g("p_kW") else ""]
    elif t == "offpage":
        lines += [g("target") or ""]
    elif t == "plc":
        mods = g("modules") or []
        lines += [part_number(node) or "", _t("ann.modules", lang, count=len(mods)) if mods else "",
                  ", ".join(g("protocols") or [])[:24]]
    elif t == "power_supply":
        u = f"{fmt(g('u1_V'))}/{fmt(g('u2_V'))} V {g('output') or ''}".strip() if g("u1_V") and g("u2_V") else ""
        lines += [u, fmt(g("in_A"), " A") if g("in_A") else ""]
    lines.append(state_text(node, lang))
    return [x for x in lines if x]


def state_text(node: Any, lang: str = "en", normally_open: bool = False, locks: Iterable[str] = ()) -> str:
    """'N.O., key K1': normally-open state and interlock keys of a switching device (or of a link)."""
    parts = []
    if normally_open or _g(node, "normal_state") == "open":
        parts.append(_t("ann.normally_open", lang))
    keys = list(dict.fromkeys([*(_g(node, "locks") or []), *locks]))
    if keys:
        parts.append(_t("ann.locks", lang, keys=" ".join(keys)))
    return ", ".join(parts)


def cell(field: str, column: dict[str, Any], lang: str = "en") -> str:
    """Value of a cell of the outgoing-feeder table.

    ``column``: {'leaf': final node, 'prot': feeder protection, 'cable': cable, 'rcd': upstream RCD}
    """
    leaf, prot, cable = column.get("leaf"), column.get("prot"), column.get("cable")
    rcd_node = column.get("rcd")
    if field == "label":
        return column.get("label") or ""
    if field == "ref":
        # tag of the feeder protection, else of the final node itself (spare way, IMD, busway tap-off...)
        if column.get("own_ref"):  # protected from upstream (sub-busbar way, busway tap-off): its own tag
            return column["own_ref"]
        return (prot.ref if prot is not None and prot.ref else _g(leaf, "ref")) or ""
    if field == "protection":
        return protection_short(prot) if prot is not None else ""
    if field == "in_A":
        return fmt(_g(prot, "in_A"), " A") if prot is not None and _g(prot, "in_A") else ""
    if field == "curve":
        return _g(prot, "curve") or ""
    if field == "icn_kA":
        return fmt(_g(prot, "icn_kA"), " kA") if _g(prot, "icn_kA") else ""
    if field == "idn_mA":
        src = prot if _g(prot, "idn_mA") else rcd_node
        if src is None or not _g(src, "idn_mA"):
            return ""
        rcd_type = _g(src, "rcd_type") if not column.get("rcd_type_column") else None  # else in its own row
        txt = fmt_sensitivity(_g(src, "idn_mA")) + (f" {rcd_type}" if rcd_type else "")
        # residual-current protection carried by a device upstream of the feeder (incomer, group RCD): marked
        return _t("cell.upstream", lang, value=txt) if src is rcd_node and column.get("rcd_upstream") else txt
    if field == "rcd_type":
        src = prot if _g(prot, "rcd_type") else rcd_node
        return _g(src, "rcd_type") or ""
    if field == "poles":
        return _g(prot, "poles") or ""
    if field == "cable":
        return cable_text(cable)
    if field == "section_mm2":
        return fmt(cable.section_mm2, " mm²") if cable is not None and cable.section_mm2 else ""
    if field == "length_m":
        return fmt(cable.length_m, " m") if cable is not None and cable.length_m else ""
    if field == "p_kW":
        p = _g(leaf, "p_kW")
        if not p and _g(leaf, "p_max_kW"):
            return f"≤ {fmt(_g(leaf, 'p_max_kW'), ' kW')}"
        return fmt(p, " kW") if p else ""
    if field == "phase":
        ph = _g(leaf, "phase") or _g(prot, "phase")
        if not ph and (_g(prot, "poles") in THREE_PHASE_POLES or _g(leaf, "phases") == 3):
            ph = "L1L2L3"  # three-phase feeder
        return re.sub(r"(?<=\d)(?=L)", "-", ph) if ph else ""  # 'L1-L2-L3'
    if field == "room":
        return _g(leaf, "room") or ""
    if field == "points":
        pts = _g(leaf, "points")
        return _t("cell.points_one" if pts == 1 else "cell.points", lang, count=pts) if pts else ""
    # --- 1.2
    first = lambda name: next((v for v in (_g(leaf, name), _g(prot, name)) if v not in (None, "", [])), None)  # noqa: E731
    if field == "circuit":
        return first("circuit") or ""
    if field == "ib_A":
        v = first("ib_A")
        return fmt(v, " A") if v else ""
    if field == "cos_phi":
        v = first("cos_phi")
        return fmt(v) if v else ""
    if field == "count":
        v = first("count")
        return f"x {v}" if v else ""
    if field == "un_V":
        v = first("un_V")
        return fmt(v, " V") if v else ""
    if field == "frame_A":
        v = _g(prot, "frame_A")
        return fmt(v, " AF") if v else ""
    if cable is not None:
        if field == "cable_type":
            return cable.designation or ""
        if field == "cable_ref":
            return cable.ref or ""
        if field == "install":
            return cable.install or cable.raceway or ""
    return ""


CARTOUCHE_TITLES = {
    "fr": {
        "label": "Désignation", "ref": "Repère", "protection": "Protection", "in_A": "Calibre", "curve": "Courbe",
        "icn_kA": "PdC", "idn_mA": "Différentiel", "rcd_type": "Type diff.", "poles": "Pôles", "cable": "Câble (mm²)", "cable_awg": "Câble",
        "section_mm2": "Section", "length_m": "Longueur", "p_kW": "Puissance", "phase": "Phase", "room": "Local",
        "points": "Points", "circuit": "Circuit", "ib_A": "Ib", "cos_phi": "cos φ", "count": "Nombre",
        "un_V": "Tension", "frame_A": "Boîtier", "cable_type": "Type de câble", "cable_ref": "Repère câble",
        "install": "Mode de pose",
    },
    "ru": {
        "label": "Наименование", "ref": "Обозначение", "protection": "Защита", "in_A": "Ном. ток", "curve": "Характеристика",
        "icn_kA": "Откл. способн.", "idn_mA": "УЗО", "rcd_type": "Тип УЗО", "poles": "Полюса", "cable": "Кабель (мм²)", "cable_awg": "Кабель",
        "section_mm2": "Сечение", "length_m": "Длина", "p_kW": "Мощность", "phase": "Фаза", "room": "Помещение",
        "points": "Точки", "circuit": "Цепь", "ib_A": "Ib", "cos_phi": "cos φ", "count": "Кол-во",
        "un_V": "Напряжение", "frame_A": "Корпус", "cable_type": "Марка кабеля", "cable_ref": "Обозн. кабеля",
        "install": "Способ прокладки",
    },
    "en": {
        "label": "Description", "ref": "Tag", "protection": "Protection", "in_A": "Rating", "curve": "Curve",
        "icn_kA": "Breaking cap.", "idn_mA": "RCD", "rcd_type": "RCD type", "poles": "Poles", "cable": "Cable (mm²)", "cable_awg": "Cable",
        "section_mm2": "Section", "length_m": "Length", "p_kW": "Power", "phase": "Phase", "room": "Room",
        "points": "Points", "circuit": "Circuit", "ib_A": "Ib", "cos_phi": "Power factor", "count": "Qty",
        "un_V": "Voltage", "frame_A": "Frame", "cable_type": "Cable type", "cable_ref": "Cable tag",
        "install": "Raceway / method",
    },
}
