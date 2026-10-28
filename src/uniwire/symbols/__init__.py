"""Single-line diagram symbol library (inspired by IEC 60617 / NF C 03-2xx).

All symbols are drawn here, as primitives, on the module grid
M = 2.5 mm. Local frame: origin on the input terminal (at the top), y pointing down.
A symbol declares its height (output terminal at (0, h)), its horizontal
footprint and, for the transfer switch, a side input terminal.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from ..render.scene import (
    THICK,
    THIN,
    Circle,
    Ellipse,
    Group,
    Item,
    Line,
    Point,
    Polyline,
    Rect,
    Style,
    Text,
    arc_points,
    text_width,
)

M = 2.5  # IEC 60617 module

DASH = Style(width=THIN, dash=(1.0, 0.7))


@dataclass
class Symbol:
    name: str
    items: list[Item]
    height: float  # y position of the output terminal
    left: float = 2.5  # footprint to the left of the axis
    right: float = 2.5  # footprint to the right of the axis
    has_output: bool = True
    side_input: Optional[Point] = None  # side input terminal (transfer switch)
    extra: dict[str, Any] = field(default_factory=dict)

    def group(self, x: float, y: float, node_id: str | None = None) -> Group:
        from ..render.scene import transform

        return Group([transform(i, x, y) for i in self.items], node_id, f"sym sym-{self.name}")


# --------------------------------------------------------------- primitives
def _lead(y0: float, y1: float) -> Line:
    return Line((0, y0), (0, y1))


def _contact(top: float = 1.5 * M, pivot: float = 3.5 * M, h: float = 5 * M) -> list[Item]:
    """Make contact (normally open): top terminal, inclined blade starting from the bottom pivot."""
    ang = math.radians(28)
    length = (pivot - top) * 1.08
    tip = (-length * math.sin(ang), pivot - length * math.cos(ang))
    return [_lead(0, top), Line((0, pivot), tip), _lead(pivot, h)]


def _blade_mid(top: float = 1.5 * M, pivot: float = 3.5 * M) -> Point:
    ang = math.radians(28)
    length = (pivot - top) * 1.08
    return (-length * math.sin(ang) / 2, pivot - length * math.cos(ang) / 2)


def _cross(c: Point, s: float = 0.9) -> list[Item]:
    return [Line((c[0] - s, c[1] - s), (c[0] + s, c[1] + s)), Line((c[0] - s, c[1] + s), (c[0] + s, c[1] - s))]


def _bar(c: Point, s: float = 1.0) -> Line:
    return Line((c[0] - s, c[1]), (c[0] + s, c[1]))


def _torus(y: float) -> list[Item]:
    """Residual-current toroid + dashed mechanical link to the blade."""
    bm = _blade_mid()
    return [
        Ellipse((0, y), 1.7, 0.75),
        Polyline([(1.7, y), (2.6, y), (2.6, bm[1]), (bm[0] + 0.3, bm[1])], DASH),
    ]


def _text(p: Point, s: str, size: float = 2.0, bold: bool = False) -> Text:
    return Text(p, s, size, "middle", "middle", bold=bold)


# ------------------------------------------------------------------ symbols
def breaker(node: Any = None) -> Symbol:
    return Symbol("breaker", [*_contact(), *_cross((0, 1.5 * M))], 5 * M, 2.5, 1.5)


def disconnector(node: Any = None) -> Symbol:
    return Symbol("disconnector", [*_contact(), _bar((0, 1.5 * M))], 5 * M, 2.5, 1.5)


def switch_disconnector(node: Any = None) -> Symbol:
    items = [*_contact(), _bar((0, 1.5 * M)), Circle((0, 1.5 * M + 0.6), 0.6)]
    return Symbol("switch_disconnector", items, 5 * M, 2.5, 1.5)


def contactor(node: Any = None) -> Symbol:
    arc = Polyline(arc_points((0, 1.5 * M + 1.2), 1.2, 180, 360, 12))
    return Symbol("contactor", [*_contact(), arc], 5 * M, 2.5, 1.5)


def fuse(node: Any = None) -> Symbol:
    return Symbol("fuse", [_lead(0, 5 * M), Rect(-1.0, 1.25 * M, 2.0, 2.5 * M, Style(fill="#ffffff"))], 5 * M, 1.2, 1.2)


def fuse_switch(node: Any = None) -> Symbol:
    """Fuse switch-disconnector (IEC 60617 S00370): the fuse on the blade of a switch-disconnector."""
    top, pivot = 1.5 * M, 3.5 * M
    ang = math.radians(28)
    length = (pivot - top) * 1.08
    ux, uy = -math.sin(ang), -math.cos(ang)  # blade direction
    nx, ny = -uy, ux
    a = (ux * length * 0.2, pivot + uy * length * 0.2)
    b = (ux * length * 0.8, pivot + uy * length * 0.8)
    w = 0.75
    poly = Polyline([(a[0] + nx * w, a[1] + ny * w), (b[0] + nx * w, b[1] + ny * w),
                     (b[0] - nx * w, b[1] - ny * w), (a[0] - nx * w, a[1] - ny * w)], closed=True)
    return Symbol("fuse_switch", [*_contact(), _bar((0, top)), Circle((0, top + 0.6), 0.6), poly], 5 * M, 3.0, 1.5)


def rcd(node: Any = None) -> Symbol:
    """Residual-current device: toroid linked to the blade, with the differential-current qualifier "IΔ"
    (IEC 60617 S00331)."""
    h = 5.5 * M
    items = [*_contact(h=h), *_torus(4.6 * M), Text((-2.2, 4.6 * M), "IΔ", 1.5, "end", "middle")]
    return Symbol("rcd", items, h, 4.6, 2.8)


def rcbo(node: Any = None) -> Symbol:
    s = rcd()
    s.items += _cross((0, 1.5 * M))
    s.name = "rcbo"
    return s


def main_breaker(node: Any = None) -> Symbol:
    """Main breaker: residual-current (as an RCBO) only when it has a sensitivity, else a plain circuit breaker."""
    s = rcbo() if getattr(node, "idn_mA", None) else breaker()
    s.name = "main_breaker"
    return s


def thermal_relay(node: Any = None) -> Symbol:
    items = [
        _lead(0, 1.25 * M), Rect(-1.6, 1.25 * M, 3.2, 2.5 * M),
        Polyline([(0, 1.25 * M), (0, 1.8 * M), (0.8, 1.8 * M), (0.8, 3.2 * M), (0, 3.2 * M), (0, 3.75 * M)]),
        _lead(3.75 * M, 5 * M),
    ]
    return Symbol("thermal_relay", items, 5 * M, 1.8, 1.8)


def _box(name: str, label: str, h: float = 5 * M, w: float = 6.0, size: float = 1.8) -> Symbol:
    items = [_lead(0, 1.0 * M), Rect(-w / 2, 1.0 * M, w, h - 2 * M), _text((0, 1.0 * M + (h - 2 * M) / 2), label, size),
             _lead(h - 1.0 * M, h)]
    return Symbol(name, items, h, w / 2 + 0.2, w / 2 + 0.2)


def impulse_relay(node: Any = None) -> Symbol:
    s = contactor()
    s.name = "impulse_relay"
    s.items += [Rect(-6.2, 1.6 * M, 2.6, 2.0), _text((-4.9, 1.6 * M + 1.0), _abbr("impulse_relay"), 1.3),
                Line((-3.6, 1.6 * M + 1.0), (-1.0, 1.6 * M + 1.0), DASH)]
    s.left = 6.4
    return s


#: Short texts drawn inside symbols, per render language (English fallback).
ABBREVIATIONS: dict[str, dict[str, str]] = {
    "en": {"starter.vfd": "VFD", "starter.soft_starter": "SS", "starter.star_delta": "Y/Δ", "starter.reversing": "REV",
           "starter.": "MS", "impulse_relay": "IR", "water_heater": "WH", "oven": "OVEN", "washing_machine": "WM",
           "dishwasher": "DW", "dryer": "DRY", "freezer": "FRZ", "fridge": "FRG", "appliance": "APP",
           "ev_charger": "EV", "shutter": "SHUT", "insulation_monitor": "IMD", "plc": "PLC", "ups": "UPS"},
    "ru": {"starter.vfd": "ПЧ", "starter.soft_starter": "УПП", "starter.star_delta": "Y/Δ", "starter.reversing": "РЕВ",
           "starter.": "ПУСК", "impulse_relay": "ИР", "water_heater": "ЭВН", "oven": "ДШ", "washing_machine": "СМ",
           "dishwasher": "ПММ", "dryer": "СУШ", "freezer": "МРЗ", "fridge": "ХОЛ", "appliance": "ПРИБ",
           "ev_charger": "ЭЗС", "shutter": "РОЛ", "insulation_monitor": "УКИ", "plc": "ПЛК", "ups": "ИБП"},
    "zh": {"starter.vfd": "变频", "starter.soft_starter": "软起", "starter.star_delta": "Y/Δ", "starter.reversing": "正反",
           "starter.": "起动", "impulse_relay": "脉冲", "water_heater": "热水", "oven": "烤箱", "washing_machine": "洗衣",
           "dishwasher": "洗碗", "dryer": "干衣", "freezer": "冷冻", "fridge": "冰箱", "appliance": "电器", "ev_charger": "充电",
           "shutter": "卷帘", "insulation_monitor": "IMD", "plc": "PLC", "ups": "UPS"},
    "es": {"starter.vfd": "VDF", "starter.soft_starter": "AS", "starter.star_delta": "Y/Δ",
           "starter.reversing": "REV", "starter.": "ARR", "impulse_relay": "TL", "water_heater": "CAL",
           "oven": "HOR", "washing_machine": "LAV", "dishwasher": "LVJ", "dryer": "SEC", "freezer": "CONG",
           "fridge": "REF", "appliance": "APAR", "ev_charger": "VE", "shutter": "PERS", "insulation_monitor": "DVA",
           "plc": "PLC", "ups": "UPS"},
    "de": {"starter.vfd": "FU", "starter.soft_starter": "SAN", "starter.star_delta": "Y/Δ",
           "starter.reversing": "WEND", "starter.": "DA", "impulse_relay": "STS", "water_heater": "WW",
           "oven": "OFEN", "washing_machine": "WM", "dishwasher": "GSP", "dryer": "WT", "freezer": "GEF",
           "fridge": "KS", "appliance": "GER", "ev_charger": "LP", "shutter": "ROL", "insulation_monitor": "IMD",
           "plc": "SPS", "ups": "USV"},
    "pt": {"starter.vfd": "INV", "starter.soft_starter": "SS", "starter.star_delta": "Y/Δ",
           "starter.reversing": "REV", "starter.": "PD", "impulse_relay": "RI", "water_heater": "AQ",
           "oven": "FOR", "washing_machine": "MLR", "dishwasher": "MLL", "dryer": "SEC", "freezer": "FRZ",
           "fridge": "GEL", "appliance": "APAR", "ev_charger": "VE", "shutter": "PERS", "insulation_monitor": "DSI",
           "plc": "CLP", "ups": "UPS"},
    "it": {"starter.vfd": "INV", "starter.soft_starter": "SS", "starter.star_delta": "Y/Δ",
           "starter.reversing": "TINV", "starter.": "AVV", "impulse_relay": "RI", "water_heater": "SCA",
           "oven": "FOR", "washing_machine": "LAV", "dishwasher": "LST", "dryer": "ASC", "freezer": "CONG",
           "fridge": "FRIG", "appliance": "ELD", "ev_charger": "EV", "shutter": "TAP", "insulation_monitor": "IMD",
           "plc": "PLC", "ups": "UPS"},
    "pl": {"starter.vfd": "PCZ", "starter.soft_starter": "SOFT", "starter.star_delta": "Y/Δ",
           "starter.reversing": "NAWR", "starter.": "ROZR", "impulse_relay": "PB", "water_heater": "BOJ",
           "oven": "PIEK", "washing_machine": "PRAL", "dishwasher": "ZMYW", "dryer": "SUSZ", "freezer": "ZAMR",
           "fridge": "LOD", "appliance": "AGD", "ev_charger": "EV", "shutter": "ROL", "insulation_monitor": "UKI",
           "plc": "PLC", "ups": "UPS"},
    "tr": {"starter.vfd": "SÜR", "starter.soft_starter": "YYV", "starter.star_delta": "Y/Δ",
           "starter.reversing": "TERS", "starter.": "YV", "impulse_relay": "İR", "water_heater": "TERM",
           "oven": "FIR", "washing_machine": "ÇM", "dishwasher": "BM", "dryer": "KM", "freezer": "DOND",
           "fridge": "BUZ", "appliance": "CİH", "ev_charger": "ŞARJ", "shutter": "PANJ", "insulation_monitor": "IMD",
           "plc": "PLC", "ups": "UPS"},
    "fr": {"starter.vfd": "VAR", "starter.soft_starter": "DÉM", "starter.star_delta": "Y/Δ", "starter.reversing": "INV",
           "starter.": "DM", "impulse_relay": "TL", "water_heater": "CE", "oven": "Four", "washing_machine": "LL",
           "dishwasher": "LV", "dryer": "SL", "freezer": "CONG", "fridge": "FRIG", "appliance": "APP",
           "ev_charger": "IRVE", "shutter": "VR", "insulation_monitor": "CPI", "plc": "API", "ups": "UPS"},
}


def _abbr(key: str) -> str:
    from ..i18n import render_lang

    table = ABBREVIATIONS.get(render_lang(), ABBREVIATIONS["en"])
    return table.get(key) or ABBREVIATIONS["en"].get(key, "")


def motor_starter(node: Any = None) -> Symbol:
    """Motor starter (IEC 60617 S00297): a square with a "V" from its top corners, the starting method below it.
    A variable-speed drive is a frequency converter (S01904)."""
    method = getattr(node, "method", None) or ""
    if method == "vfd":
        return _converter("motor_starter", "~", "~", False)
    w, h = 7.0, 5 * M
    top, bh = 1.0 * M, h - 2 * M
    items: list[Item] = [_lead(0, top), Rect(-w / 2, top, w, bh), Polyline([(-w / 2, top), (0, top + 1.9), (w / 2, top)]),
                         _lead(h - 1.0 * M, h)]
    label = _abbr(f"starter.{method}") if method else ""
    if label:
        items.append(_text((0, top + bh * 0.68), label, 1.6))
    return Symbol("motor_starter", items, h, w / 2 + 0.2, w / 2 + 0.2)


def controller(node: Any = None) -> Symbol:
    label = getattr(node, "symbol_text", None) or "CTRL"
    return _box("controller", label, 5 * M, max(6.0, 1.1 * len(label) + 2))


def transfer_switch(node: Any = None) -> Symbol:
    """Transfer switch: two contacts (normal on the left, standby arriving from the right) + interlock."""
    h = 6 * M
    y = 2.5 * M
    items: list[Item] = [
        _lead(0, y - 1.5),
        Line((0, y + 1.6), (-1.6, y - 1.4)),  # normal contact
        Line((0, y + 1.6), (0, y + 3.0)),
        # standby path: arrives on the right
        Line((5.0, y - 1.5), (5.0, y - 3.5)),
        Line((5.0, y - 1.5), (5.0, y + 3.0)),
        Line((5.0, y + 3.0), (0, y + 3.0)),
        _lead(y + 3.0, h),
        Polyline([(1.0, y), (2.2, y + 1.6), (3.4, y), (1.0, y)], Style(width=THIN), closed=True),  # interlock ▽
        Rect(-3.0, y - 2.5, 10.0, 7.0, DASH),
    ]
    sym = Symbol("transfer_switch", items, h, 3.2, 7.2, side_input=(5.0, y - 3.5))
    return sym


def spd(node: Any = None) -> Symbol:
    dc = bool(getattr(node, "dc", False))
    items: list[Item] = [
        _lead(0, 1.0 * M), Rect(-1.4, 1.0 * M, 2.8, 2.6 * M),
        Line((0, 1.4 * M), (0, 3.2 * M)), Polyline([(-0.7, 2.6 * M), (0, 3.2 * M), (0.7, 2.6 * M)]),
        _lead(3.6 * M, 4.4 * M),
        *_earth_items(4.4 * M),
    ]
    if dc:
        items.append(_text((-2.6, 1.6 * M), "=", 1.8))
    return Symbol("spd", items, 5.4 * M, 1.6, 1.6, has_output=False)


def _earth_items(y: float) -> list[Item]:
    return [Line((-1.8, y), (1.8, y)), Line((-1.2, y + 0.8), (1.2, y + 0.8)), Line((-0.6, y + 1.6), (0.6, y + 1.6))]


def earth(node: Any = None) -> Symbol:
    return Symbol("earth", [_lead(0, 1.6 * M), *_earth_items(1.6 * M)], 2.4 * M, 1.8, 1.8, has_output=False)


def transformer(node: Any = None) -> Symbol:
    r = 1.3 * M
    c1, c2 = (0, 0.6 * M + r), (0, 0.6 * M + r * 2.5)
    h = c2[1] + r + 0.6 * M
    return Symbol("transformer", [_lead(0, 0.6 * M), Circle(c1, r), Circle(c2, r), _lead(c2[1] + r, h)], h, r, r)


def _machine(name: str, letter: str, sub: str | None, has_output: bool) -> Symbol:
    r = 1.8 * M
    c = (0, 0.6 * M + r)
    items: list[Item] = [_lead(0, 0.6 * M), Circle(c, r), _text((c[0], c[1] - (0.6 if sub else 0)), letter, 3.0, True)]
    if sub:
        items.append(_text((c[0], c[1] + 2.0), sub, 1.6))
    h = c[1] + r
    if has_output:
        items.append(_lead(h, h + 0.6 * M))
        h += 0.6 * M
    return Symbol(name, items, h, r, r, has_output=has_output)


def generator(node: Any = None, system: Optional[str] = None) -> Symbol:
    """``system``: supply system fed by the generator ('1P+N', 'DC'...), three-phase by default."""
    sub = "1~" if system in ("1P+N", "2P", "split-phase") else "=" if system == "DC" else "3~"
    s = _machine("generator", "G", sub, True)
    s.items = s.items[1:]  # source: no input terminal
    return s


def motor(node: Any = None) -> Symbol:
    ph = getattr(node, "phases", None)
    return _machine("motor", "M", "1~" if ph == 1 else "3~", False)


def grid(node: Any = None) -> Symbol:
    """Grid incomer: supply arrow + stylised pylon."""
    items: list[Item] = [
        Polyline([(-2.0, 0.4 * M), (0, 2.0 * M), (2.0, 0.4 * M)]),
        Line((-2.5, 0.4 * M), (2.5, 0.4 * M)),
        Line((0, 0.4 * M), (0, 4 * M)),
        Polyline([(-0.9, 2.8 * M), (0, 3.6 * M), (0.9, 2.8 * M)], Style(fill="#000000"), closed=True),
    ]
    return Symbol("grid", items, 4 * M, 2.6, 2.6)


def meter(node: Any = None) -> Symbol:
    items = [_lead(0, 0.6 * M), Rect(-3.0, 0.6 * M, 6.0, 2.6 * M), Line((-3.0, 1.4 * M), (3.0, 1.4 * M)),
             _text((0, 2.3 * M), "kWh", 1.7), _lead(3.2 * M, 3.8 * M)]
    return Symbol("meter", items, 3.8 * M, 3.1, 3.1)


def _dc_mark(cx: float, cy: float, w: float = 2.6) -> list[Item]:
    """Direct current (IEC 60617 S01401): a full line over a dashed one."""
    d = w / 3
    return [Line((cx - w / 2, cy - 0.45), (cx + w / 2, cy - 0.45)),
            *(Line((cx - w / 2 + i * d + 0.12, cy + 0.45), (cx - w / 2 + (i + 1) * d - 0.28, cy + 0.45)) for i in range(3))]


def _converter_mark(s: str, c: Point) -> list[Item]:
    return _dc_mark(*c) if s == "=" else [_text(c, s, 2.4 if s == "~" else 2.0)]


def _converter(name: str, a: str, b: str, source: bool) -> Symbol:
    """Converter (IEC 60617 S00214): a square cut by a diagonal, ``a`` top left, ``b`` bottom right."""
    s = 3.2 * M
    y0 = 0.6 * M if not source else 0.0
    items: list[Item] = [Rect(-s / 2, y0, s, s), Line((-s / 2, y0 + s), (s / 2, y0)),
                         *_converter_mark(a, (-s / 4, y0 + s / 4 + 0.2)), *_converter_mark(b, (s / 4, y0 + 3 * s / 4)),
                         _lead(y0 + s, y0 + s + 0.6 * M)]
    if not source:
        items.insert(0, _lead(0, y0))
    return Symbol(name, items, y0 + s + 0.6 * M, s / 2, s / 2)


def inverter(node: Any = None) -> Symbol:
    """Inverter (IEC 60617 S00896): direct current top left, alternating current bottom right, whatever the
    direction of the wiring."""
    return _converter("inverter", "=", "~", False)


def ups(node: Any = None) -> Symbol:
    s = _converter("ups", "~", "~", False)
    s.items.append(Text((-s.left - 0.6, s.height / 2), _abbr("ups"), 1.5, "end", "middle"))  # no standard symbol
    s.left += 4.4
    if getattr(node, "bypass", False):
        top, bot = 0.3 * M, s.height - 0.3 * M
        s.items.append(Polyline([(0, top), (5.5, top), (5.5, bot), (0, bot)], DASH))
        s.right = 5.8
    return s


def _arrow(a: Point, b: Point, head: float = 0.8) -> list[Item]:
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    left = (b[0] - head * math.cos(ang - 0.45), b[1] - head * math.sin(ang - 0.45))
    right = (b[0] - head * math.cos(ang + 0.45), b[1] - head * math.sin(ang + 0.45))
    return [Line(a, b, Style(width=THIN)), Polyline([left, b, right], Style(width=THIN, fill="#000000"), closed=True)]


def pv_array(node: Any = None) -> Symbol:
    """Photovoltaic generator (IEC 60617 S00908): a static generator "G" with a cell, light arriving from outside."""
    s = 3.4 * M
    y0 = 0.6 * M
    cy = y0 + s * 0.68
    items: list[Item] = [_lead(0, y0), Rect(-s / 2, y0, s, s), _text((0, y0 + s * 0.3), "G", 2.6, True),
                         Line((-2.2, cy), (-0.35, cy)), Line((-0.35, cy - 1.3), (-0.35, cy + 1.3)),
                         Line((0.35, cy - 0.7), (0.35, cy + 0.7), Style(width=THICK)), Line((0.35, cy), (2.2, cy))]
    for dy in (-1.3, 1.0):  # light
        items += _arrow((-s / 2 - 3.4, y0 + s / 2 + dy - 2.0), (-s / 2 - 0.8, y0 + s / 2 + dy))
    return Symbol("pv_array", items, y0 + s, s / 2 + 3.6, s / 2, has_output=False)


def battery(node: Any = None) -> Symbol:
    """Battery of cells (IEC 60617 S00899): two cells (long thin plate +, short thick plate -) joined by a dashed
    line, with a lead below the last cell and the polarity marked, so that it never reads as an earth symbol."""
    y = 1.4 * M
    gap = 2.2  # dashed link between the cells: the cells in between
    y2 = y + 1.0 + gap
    end = y2 + 1.0 + 0.8 * M
    items = [_lead(0, y),
             Line((-3.0, y), (3.0, y)), Line((-1.5, y + 1.0), (1.5, y + 1.0), Style(width=THICK)),
             Line((0, y + 1.0), (0, y2), DASH),
             Line((-3.0, y2), (3.0, y2)), Line((-1.5, y2 + 1.0), (1.5, y2 + 1.0), Style(width=THICK)),
             _lead(y2 + 1.0, end),
             _text((3.8, y - 0.2), "+", 1.6), _text((3.8, y2 + 1.6), "\u2212", 1.6)]
    return Symbol("battery", items, end, 3.0, 4.2, has_output=False)


def busbar(node: Any = None) -> Symbol:
    if getattr(node, "kind", None) == "busway":
        return busway(node)
    # explicit standalone busbar (no children): plain thick line
    return Symbol("busbar", [Line((-3, 0), (3, 0), Style(width=THICK))], 0.0, 3, 3)


BUSWAY_H = 2.4  # height of the trunk of a busbar trunking system


def busway(node: Any = None) -> Symbol:
    """Prefabricated busbar trunking (busbar ``kind`` 'busway'): a long casing with the bars inside it."""
    w = 8.0
    items: list[Item] = [Rect(-w / 2, 0, w, BUSWAY_H, Style(fill="#ffffff")),
                         Line((-w / 2 + 0.8, BUSWAY_H / 2), (w / 2 - 0.8, BUSWAY_H / 2), Style(width=THICK))]
    return Symbol("busway", items, BUSWAY_H, w / 2, w / 2)


# ---------------------------------------------------------------- loads
def _load_box(name: str, label: str, w: float = 5.6, h: float = 4.4) -> Symbol:
    y0 = 0.8 * M
    items = [_lead(0, y0), Rect(-w / 2, y0, w, h), _text((0, y0 + h / 2), label, 1.6)]
    return Symbol(name, items, y0 + h, w / 2, w / 2, has_output=False)


def socket(node: Any = None) -> Symbol:
    """Socket outlet with protective contact (IEC 60617 S00460): an arc open downwards, the protective-contact
    bar across its top."""
    y0 = 1.6 * M
    r = 2.2
    items: list[Item] = [_lead(0, y0), Line((-r, y0), (r, y0)),
                         Polyline(arc_points((0, y0 + r), r, 180, 360, 14))]
    return Symbol("socket", items, y0 + r, r, r, has_output=False)


def lighting(node: Any = None) -> Symbol:
    r = 2.2
    c = (0, 0.8 * M + r)
    d = r * 0.707
    items = [_lead(0, 0.8 * M), Circle(c, r), Line((c[0] - d, c[1] - d), (c[0] + d, c[1] + d)),
             Line((c[0] - d, c[1] + d), (c[0] + d, c[1] - d))]
    return Symbol("lighting", items, c[1] + r, r, r, has_output=False)


def heating(node: Any = None) -> Symbol:
    w, h = 6.0, 4.0
    y0 = 0.8 * M
    items: list[Item] = [_lead(0, y0), Rect(-w / 2, y0, w, h)]
    step = (w - 0.8 - 1.2) / 3  # four strokes 1.2 wide, 0.4 from the sides
    for i in range(4):
        x = -w / 2 + 0.4 + i * step
        items.append(Line((x, y0 + h - 0.4), (x + 1.2, y0 + 0.4), Style(width=THIN)))
    return Symbol("heating", items, y0 + h, w / 2, w / 2, has_output=False)


def water_heater(node: Any = None) -> Symbol:
    """Water heater (IEC 60617 S00493): a circle hatched vertically."""
    r = 2.6
    c = (0, 0.8 * M + r)
    items: list[Item] = [_lead(0, 0.8 * M), Circle(c, r)]
    for x in (-1.2, -0.4, 0.4, 1.2, 2.0):
        hh = math.sqrt(r * r - x * x)
        items.append(Line((x, c[1] - hh), (x, c[1] + hh), Style(width=THIN)))
    return Symbol("water_heater", items, c[1] + r, r, r, has_output=False)


def cooking(node: Any = None) -> Symbol:
    kind = getattr(node, "kind", None)
    if kind == "oven":
        return _load_box("cooking", _abbr("oven"))
    w, h = 5.6, 5.6
    y0 = 0.8 * M
    items: list[Item] = [_lead(0, y0), Rect(-w / 2, y0, w, h)]
    for cx, cy in ((-1.3, 1.3), (1.3, 1.3), (-1.3, -1.3), (1.3, -1.3)):
        items.append(Circle((cx, y0 + h / 2 + cy), 0.8, Style(width=THIN)))
    return Symbol("cooking", items, y0 + h, w / 2, w / 2, has_output=False)


def appliance(node: Any = None) -> Symbol:
    return _load_box("appliance", _abbr(getattr(node, "kind", None) or "appliance") or _abbr("appliance"))


def ev_charger(node: Any = None) -> Symbol:
    return _load_box("ev_charger", _abbr("ev_charger"), 7.0)


def ventilation(node: Any = None) -> Symbol:
    r = 2.4
    c = (0, 0.8 * M + r)
    items: list[Item] = [_lead(0, 0.8 * M), Circle(c, r)]
    for a in (0, 120, 240):
        items.append(Polyline(arc_points((c[0] + 0.9 * math.cos(math.radians(a)), c[1] + 0.9 * math.sin(math.radians(a))),
                                         0.9, a + 180, a + 360, 6), Style(width=THIN)))
    return Symbol("ventilation", items, c[1] + r, r, r, has_output=False)


def shutter(node: Any = None) -> Symbol:
    return _load_box("shutter", _abbr("shutter"))


def load(node: Any = None) -> Symbol:
    return _load_box("load", getattr(node, "symbol_text", None) or "")


def spare(node: Any = None) -> Symbol:
    items = [_lead(0, 1.2 * M), Circle((0, 1.2 * M + 0.7), 0.7)]
    return Symbol("spare", items, 1.2 * M + 1.4, 0.8, 0.8, has_output=False)


def board(node: Any = None) -> Symbol:
    # a board with no content of its own: plain pass-through
    return Symbol("board", [_lead(0, 0.0)], 0.0, 0.5, 0.5)


def offpage(label: Any = "") -> Symbol:
    """Cross-reference to another sheet (arrow + text). Accepts a label or an ``offpage`` node."""
    if not isinstance(label, str):
        label = getattr(label, "target", None) or getattr(label, "label", None) or ""
    items: list[Item] = [_lead(0, 1.6 * M),
                         Polyline([(-1.2, 1.6 * M), (0, 2.6 * M), (1.2, 1.6 * M)], Style(fill="#000000"), closed=True)]
    return Symbol("offpage", items, 2.6 * M, 1.4, 1.4, has_output=False, extra={"label": label})


# ------------------------------------------------------------ instrument transformers, MV equipment, auxiliaries
def instrument_transformer(node: Any = None) -> Symbol:
    """CT: circle crossed by the conductor; VT: two circles."""
    kind = getattr(node, "kind", None)
    if kind == "vt":
        r = 1.2 * M
        items: list[Item] = [_lead(0, 0.6 * M), Circle((0, 0.6 * M + r), r), Circle((0, 0.6 * M + 2.4 * r), r),
                             _lead(0.6 * M + 3.4 * r, 0.6 * M + 3.4 * r + 0.6 * M)]
        return Symbol("instrument_transformer", items, 0.6 * M + 3.4 * r + 0.6 * M, r, r)
    r = 0.9 * M
    items = [_lead(0, 3 * M), Circle((0, 1.5 * M), r)]
    if kind == "toroid":
        items = [_lead(0, 3 * M), Ellipse((0, 1.5 * M), 1.9, 0.8)]
    return Symbol("instrument_transformer", items, 3 * M, r, r)


def protection_relay(node: Any = None) -> Symbol:
    fns = getattr(node, "functions", None) or []
    label = (fns[0] if fns else "I>")[:6]
    return _box("protection_relay", label, 4 * M, max(6.0, 1.1 * len(label) + 2))


def earthing_switch(node: Any = None) -> Symbol:
    items = [*_contact(), _bar((0, 1.5 * M)), *_earth_items(5 * M)]
    return Symbol("earthing_switch", items, 5 * M + 1.6, 2.5, 1.8, has_output=False)


def voltage_indicator(node: Any = None) -> Symbol:
    items: list[Item] = [_lead(0, 0.8 * M), Circle((0, 0.8 * M + 1.2), 1.2), _text((0, 0.8 * M + 1.2), "V", 1.4)]  # voltmeter, S00913
    return Symbol("voltage_indicator", items, 0.8 * M + 2.4, 1.3, 1.3, has_output=False)


def insulation_monitor(node: Any = None) -> Symbol:
    return _box("insulation_monitor", _abbr("insulation_monitor"), 4 * M, 6.4)


def surge_limiter(node: Any = None) -> Symbol:
    s = spd(node)
    s.name = "surge_limiter"
    s.items.append(_text((2.8, 2.0 * M), "L", 1.5))
    s.right = max(s.right, 3.6)  # the 'L' beside the box: the device text starts after it
    return s


def neutral_impedance(node: Any = None) -> Symbol:
    items = [_lead(0, 0.8 * M), Rect(-1.0, 0.8 * M, 2.0, 2.4 * M), _lead(3.2 * M, 3.8 * M), *_earth_items(3.8 * M)]
    return Symbol("neutral_impedance", items, 3.8 * M + 1.6, 1.8, 1.8, has_output=False)


def terminal_block(node: Any = None) -> Symbol:
    items = [_lead(0, 0.8 * M), Circle((0, 0.8 * M + 0.7), 0.7), _lead(0.8 * M + 1.4, 2 * M)]
    return Symbol("terminal_block", items, 2 * M, 0.8, 0.8)


def junction_box(node: Any = None) -> Symbol:
    """Junction box (IEC 60617 S00454): a small circle with a dot (the square with a dot, S00455, is a consumer's
    terminal)."""
    items = [_lead(0, 0.6 * M), Circle((0, 0.6 * M + 1.4), 1.4), Circle((0, 0.6 * M + 1.4), 0.35, Style(fill="#000000")),
             _lead(0.6 * M + 2.8, 2.4 * M)]
    return Symbol("junction_box", items, 2.4 * M, 1.5, 1.5)


def connector(node: Any = None) -> Symbol:
    y = 1.2 * M
    items = [_lead(0, y), Polyline([(-1.2, y - 1.0), (0, y), (1.2, y - 1.0)]),
             Polyline([(-1.2, y + 0.4), (0, y + 1.4), (1.2, y + 0.4)]), _lead(y + 1.4, 2.6 * M)]
    return Symbol("connector", items, 2.6 * M, 1.3, 1.3)


def dc_converter(node: Any = None) -> Symbol:
    return _converter("dc_converter", "=", "=", False)


def earth_bar(node: Any = None) -> Symbol:
    if getattr(node, "kind", None) == "neutral_bar":
        items = [_lead(0, 0.8 * M), Line((-2.5, 0.8 * M), (2.5, 0.8 * M), Style(width=THICK)), _text((0, 1.6 * M), "N", 1.8)]
        return Symbol("earth_bar", items, 2.0 * M, 2.6, 2.6, has_output=False)
    y = 1.9 * M  # protective earthing (IEC 60617 S00202): the earth in a circle
    items = [_lead(0, 0.8 * M), Line((-2.5, 0.8 * M), (2.5, 0.8 * M), Style(width=THICK)), _lead(0.8 * M, y),
             *_earth_items(y), Circle((0, y + 0.55), 2.4)]
    return Symbol("earth_bar", items, y + 3.0, 2.6, 2.6, has_output=False)


# ------------------------------------------------------------ PLCs, power supplies
PLC_SLOT_W = 3.4


def plc(node: Any = None) -> Symbol:
    """PLC (automate): head + strip of modules (one rectangle per slot), ports addressed by slot."""
    modules = list(getattr(node, "modules", None) or [])
    h = 4.0 * M
    label = getattr(node, "family", None) or _abbr("plc")
    if len(label) > 10:  # 'Automation Series 7' -> 'Automation': the head shows the family, the annotation the rest
        label = label.split()[0][:12]
    head_w = max(7.0, text_width(label, 1.5) * 1.1 + 1.2)  # wide enough for the family name (bold)
    n = len(modules)
    w = head_w + n * PLC_SLOT_W
    x0 = -head_w / 2  # the supply axis arrives at the centre of the head
    y0 = 0.8 * M
    body = h - 1.6 * M
    head = {"coupler": "I/O", "expansion": "I/O", "hmi": "HMI"}.get(getattr(node, "role", None) or "", "CPU")
    items: list[Item] = [_lead(0, y0), Rect(x0, y0, head_w, body, Style(fill="#ffffff")),
                         _text((0, y0 + body / 2 - 0.9), label, 1.5, True), _text((0, y0 + body / 2 + 1.1), head, 1.2)]
    ports: dict[int, float] = {0: 0.0}
    for i, m in enumerate(modules):
        xs = x0 + head_w + i * PLC_SLOT_W
        fill = {"di": "#e3f2fd", "ai": "#e3f2fd", "do": "#fff3e0", "relay_out": "#fff3e0", "ao": "#fff3e0",
                "power_feed": "#ffebee", "power_supply": "#ffebee", "end": "#eeeeee", "comm": "#e8f5e9"}.get(m.kind, "#ffffff")
        items.append(Rect(xs, y0, PLC_SLOT_W, body, Style(width=THIN, fill=fill)))
        tag = {"di": "DI", "do": "DO", "ai": "AI", "ao": "AO", "relay_out": "RO", "power_feed": "PW", "power_supply": "PS",
               "end": "END", "comm": "COM", "counter": "CNT", "temperature": "T°", "power_measurement": "kW",
               "safety": "SF", "motor": "M", "mixed_io": "IO", "cpu": "CPU", "coupler": "BC"}.get(m.kind, "?")
        items.append(Text((xs + PLC_SLOT_W / 2, y0 + body / 2 + 0.4), tag, 1.1, "middle", "middle", 90))
        items.append(Text((xs + PLC_SLOT_W / 2, y0 - 0.4), str(m.slot), 1.0, "middle"))
        ports[m.slot] = xs + PLC_SLOT_W / 2
    has_out = bool(getattr(node, "children", None))
    if has_out:
        items.append(_lead(y0 + body, h))
    return Symbol("plc", items, h if has_out else y0 + body, head_w / 2 + 0.2, w - head_w / 2 + 0.2,
                  has_output=has_out, extra={"ports": ports, "port_y": y0 + body})


def power_supply(node: Any = None) -> Symbol:
    out = getattr(node, "output", "DC") or "DC"
    return _converter("power_supply", "~", "=" if out == "DC" else "~", False)


SYMBOLS: dict[str, Callable[[Any], Symbol]] = {
    "grid": grid, "transformer": transformer, "generator": generator, "ups": ups, "pv_array": pv_array,
    "battery": battery, "inverter": inverter, "meter": meter,
    "breaker": breaker, "rcd": rcd, "rcbo": rcbo, "main_breaker": main_breaker, "fuse": fuse,
    "fuse_switch": fuse_switch, "switch_disconnector": switch_disconnector, "disconnector": disconnector,
    "contactor": contactor, "impulse_relay": impulse_relay, "thermal_relay": thermal_relay,
    "motor_starter": motor_starter, "transfer_switch": transfer_switch, "spd": spd, "controller": controller,
    "busbar": busbar, "board": board, "earth": earth,
    "lighting": lighting, "socket": socket, "heating": heating, "water_heater": water_heater, "cooking": cooking,
    "appliance": appliance, "motor": motor, "ev_charger": ev_charger, "ventilation": ventilation,
    "shutter": shutter, "load": load, "spare": spare, "offpage": offpage,
    "instrument_transformer": instrument_transformer, "protection_relay": protection_relay,
    "earthing_switch": earthing_switch, "voltage_indicator": voltage_indicator,
    "insulation_monitor": insulation_monitor, "surge_limiter": surge_limiter,
    "neutral_impedance": neutral_impedance, "terminal_block": terminal_block, "junction_box": junction_box,
    "connector": connector, "dc_converter": dc_converter, "earth_bar": earth_bar,
    "plc": plc, "power_supply": power_supply,
}


def symbol_for(node: Any, system: Optional[str] = None) -> Symbol:
    """Symbol of a node; ``system`` (supply system around a source) refines rotating-machine symbols."""
    if system is not None and node.type == "generator":
        return generator(node, system)
    return SYMBOLS[node.type](node)
