"""Physical quantities: canonical numeric values, lenient input.

The format always stores numbers in the unit given by the field name suffix
(``in_A``, ``idn_mA``, ``section_mm2``...). The Python API additionally accepts
human-readable strings ("16 A", "2,5 mm²", "0,03 A", "30mA") and converts them.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from .i18n import t as _t

_PREFIXES = {"": 1.0, "m": 1e-3, "k": 1e3, "M": 1e6, "µ": 1e-6, "u": 1e-6}

# base unit -> aliases accepted as input
_BASES = {
    "A": ("A",),
    "V": ("V", "VAC", "VDC", "Vac", "Vdc", "Vca", "Vcc"),
    "W": ("W", "Wc", "Wp", "WATT", "WATTS", "watt", "watts", "Watt", "Watts"),
    "VA": ("VA",),
    "var": ("var", "VAr", "VAR"),
    "Wh": ("Wh",),
    "Ohm": ("Ohm", "ohm", "ohms", "Ω"),
    "Hz": ("Hz",),
    "m": ("m", "ml"),
    "mm2": ("mm2", "mm²"),
    "m2": ("m2", "m²"),
    "%": ("%",),
    "min": ("min",),
    "s": ("s",),
}

_NUM = r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?"
# Applied with fullmatch() to the stripped text: the parts never overlap (number, blanks, then a unit that starts
# with neither a blank nor a digit), so matching stays linear; the length bound caps the work anyway.
_RE = re.compile(rf"({_NUM})\s*([^\s\d].*)?")
MAX_QUANTITY_CHARS = 64


def _split_unit(unit: str) -> tuple[float, str] | None:
    """'kVA' -> (1e3, 'VA'), 'mm²' -> (1, 'mm2'), 'mA' -> (1e-3, 'A')."""
    unit = unit.strip().rstrip(".")
    if unit[:1] == "K" and unit[1:2] in ("V", "W", "A"):  # "KV", "KVA", "KW" (North American drawings)
        unit = "k" + unit[1:]
    for base, aliases in _BASES.items():
        if unit in aliases:
            return 1.0, base
    if unit == "km":
        return 1e3, "m"
    if unit.lower() in ("hp", "ch", "cv"):  # horsepower (also the French 'ch' and Spanish/Italian 'cv') -> W
        return 745.7, "W"
    for prefix, factor in _PREFIXES.items():
        if prefix and unit.startswith(prefix):
            rest = unit[len(prefix):]
            for base, aliases in _BASES.items():
                if rest in aliases and base not in ("mm2", "m2", "%", "min", "m"):
                    return factor, base
    return None


def parse_quantity(value: Any, target: str) -> Any:
    """Convert ``value`` to the ``target`` unit (e.g. 'mA', 'kVA', 'mm2')."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict) and set(value) == {"value", "unit"}:
        value = f"{value['value']} {value['unit']}"
    if not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) > MAX_QUANTITY_CHARS:
        raise ValueError(_t("units.too_long", n=len(text), max=MAX_QUANTITY_CHARS, value=text[:20]))
    m = _RE.fullmatch(text)
    if not m:
        raise ValueError(_t("units.unreadable", value=value))
    number = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "").strip()
    if not unit:
        return number
    src = _split_unit(unit)
    dst = _split_unit(target)
    if src is None:
        raise ValueError(_t("units.unknown_unit", unit=unit))
    if dst is None or src[1] != dst[1]:
        raise ValueError(_t("units.incompatible", unit=unit, target=target))
    result = number * src[0] / dst[0]
    return round(result, 9)


def Q(unit: str, description: str | None = None, **kw: Any) -> Any:
    """Annotated type: number >= 0 expressed in ``unit``, lenient input."""
    return Annotated[
        float,
        BeforeValidator(lambda v, _u=unit: parse_quantity(v, _u)),
        Field(ge=0, description=description or f"in {unit}", **kw),
    ]


def fmt(value: float | None, unit: str = "", sep: str = "") -> str:
    """16.0 -> '16', 2.5 -> '2.5' (English) or '2,5' (French: decimal comma), following the render language."""
    from .i18n import render_lang

    if value is None:
        return ""
    if float(value).is_integer():
        s = str(int(value))
    else:
        s = f"{value:.3f}".rstrip("0").rstrip(".")
        if render_lang() == "fr":
            s = s.replace(".", ",")
    return f"{s}{sep}{unit}" if unit else s


def fmt_current(a: float | None) -> str:
    """30 mA stays in mA, 300 mA stays in mA, 1000 mA -> 1 A."""
    if a is None:
        return ""
    return fmt(a, "A")


def fmt_sensitivity(ma: float | None) -> str:
    if ma is None:
        return ""
    if ma >= 1000:
        return fmt(ma / 1000, "A")
    return fmt(ma, "mA")
