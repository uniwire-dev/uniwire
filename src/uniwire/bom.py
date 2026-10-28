"""Bill of materials of an installation.

Every node (tree, auxiliary devices, coupling devices) and every PLC module that carries a reference (``product`` or
``manufacturer``/``part_number``) becomes a row; identical rows are aggregated. Equipment without a reference is
grouped by type and main characteristics (``spec``: rating, curve, sensitivity, poles, breaking capacity...), and
cables by composition and material, so that the bill is useful before products are chosen. The utility's meter (fed
directly by the grid) is left out unless it carries a reference; sub-meters and terminal blocks are counted.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from . import registry
from .i18n import t as _t
from .labels import cable_text, part_number, protection_short
from .model import Document
from .resolve import iter_nodes
from .units import fmt

ACCESSORY = "accessory"  # row type of a product accessory (data value; translated in the CSV)
CABLE = "cable"  # row type of the cables without reference (data value)

#: Equipment counted without a reference: everything but the utility supply, symbols and loads (except EV chargers),
#: and the utility's own meter (a meter fed directly by the grid: installed by the distributor, never ordered).
_EQUIPMENT_CATEGORIES = {"source", "measure", "protection", "switching", "control", "conductor", "converter"}
_NOT_EQUIPMENT = {"grid", "earth", "offpage"}


def _is_equipment(type_: str, parent_type: str | None = None) -> bool:
    if type_ in _NOT_EQUIPMENT or (type_ == "meter" and parent_type == "grid"):
        return False
    return type_ == "ev_charger" or registry.category(type_) in _EQUIPMENT_CATEGORIES


def spec(node: Any) -> str:
    """Main characteristics of a node, for a bill of materials without references: 'C16 1P+N 6 kA',
    '40 A 30 mA 2P type A', '250 kVA'..."""
    g = lambda name: getattr(node, name, None)  # noqa: E731
    parts: list[str] = []
    rating = protection_short(node) if registry.category(node.type) in ("protection", "switching") else ""
    if not rating and g("in_A"):
        rating = fmt(g("in_A"), " A")
    parts.append(rating)
    if g("poles"):
        parts.append(g("poles"))
    if g("rcd_type") and g("idn_mA"):
        parts.append(f"type {g('rcd_type')}")
    breaking = g("icn_kA") or g("icu_kA")
    if breaking:
        parts.append(fmt(breaking, " kA"))
    if g("imax_kA"):
        parts.append(f"Imax {fmt(g('imax_kA'), ' kA')}")
    for name, unit in (("sn_kVA", "kVA"), ("p_kVA", "kVA"), ("capacity_kWh", "kWh")):
        if g(name):
            parts.append(fmt(g(name), unit, " "))
    if not any(g(n) for n in ("sn_kVA", "p_kVA")) and g("p_kW") and node.type in ("pv_array", "ev_charger", "inverter"):
        parts.append(fmt(g("p_kW"), " kW"))
    return " ".join(p for p in parts if p)


def _prod(obj: Any) -> tuple[str, str, str, str]:
    p = getattr(obj, "product", None)
    manu = (p.manufacturer if p is not None else None) or getattr(obj, "manufacturer", None) or ""
    pn = part_number(obj) or ""
    rng = (p.range if p is not None else None) or getattr(obj, "range", None) or ""
    desc = (p.description if p is not None else None) or ""
    return manu, pn, rng, desc


def bom(doc: Document) -> list[dict[str, Any]]:
    """Bill of materials: one row per (manufacturer, part number, range), then one row per kind of equipment
    without a reference and per kind of cable, sorted.

    Each row has ``manufacturer``, ``part_number``, ``range``, ``description``, ``type`` (node type, ``module
    <kind>`` for PLC modules, ``cable``, or the accessory marker), ``spec`` (main characteristics of the rows
    without a reference: ``C16 1P+N``, ``40 A 30 mA 2P type A``, ``5G2,5 Cu``...; empty for referenced rows),
    ``quantity`` (``product.quantity``, else ``count``, else 1, summed; number of cables for cable rows),
    ``length_m`` (cable rows: total known length, else None) and ``refs`` (reference designations involved,
    ``-A1.3`` for module 3 of ``-A1``). Rows with a reference come first.
    """
    rows: dict[tuple, dict[str, Any]] = {}

    def row(key: tuple, manu: str, pn: str, rng: str, desc: str, kind: str, spec_: str) -> dict[str, Any]:
        return rows.setdefault(key, {"manufacturer": manu, "part_number": pn, "range": rng, "description": desc,
                                     "type": kind, "spec": spec_, "quantity": 0, "length_m": None, "refs": []})

    def add(manu: str, pn: str, rng: str, desc: str, qty: int, ref: str, kind: str, spec_: str = "") -> None:
        if pn or manu:
            r = row((0, manu, pn, rng), manu, pn, rng, desc, kind, "")
        elif spec_ is not None:
            r = row((1, kind, spec_), "", "", "", desc, kind, spec_)
        else:
            return
        r["quantity"] += qty
        if ref:
            r["refs"].append(ref)
        if desc and not r["description"]:
            r["description"] = desc

    def add_cable(c: Any, ref: str) -> None:
        if c is None:
            return
        text = cable_text(c)
        if not text:
            return
        label = " ".join(x for x in (c.designation or "", text, c.material or "") if x)
        r = row((2, label), "", "", "", "", CABLE, label)
        r["quantity"] += 1
        if c.length_m:
            r["length_m"] = (r["length_m"] or 0) + c.length_m
        if ref:
            r["refs"].append(ref)

    for n, parent, _ in iter_nodes(doc):
        manu, pn, rng, desc = _prod(n)
        qty = (n.product.quantity if n.product is not None and n.product.quantity else None) or n.count or 1
        parent_type = parent.type if parent is not None else None  # type: ignore[attr-defined]
        generic = spec(n) if _is_equipment(n.type, parent_type) else None  # type: ignore[attr-defined]
        add(manu, pn, rng, desc, qty, n.ref or n.id or "", n.type, generic)  # type: ignore[attr-defined]
        add_cable(n.cable, n.ref or n.id or "")
        if n.product is not None:
            for acc in n.product.accessories:
                add(acc.manufacturer or manu, acc.part_number or "", acc.range or "", acc.description or "",
                    acc.quantity or qty, n.ref or "", ACCESSORY)
        if n.type != "plc":  # type: ignore[attr-defined]  # pv_array.modules is a panel count
            continue
        for m in list(n.onboard or []) + list(n.modules or []):  # type: ignore[attr-defined]
            mm, mp, mr, md = _prod(m)
            add(mm or manu, mp, mr, md or m.kind, 1, f"{n.ref or n.id}.{m.slot}", f"module {m.kind}", m.kind)
    return [rows[k] for k in sorted(rows, key=lambda k: tuple(str(x) for x in k))]


def bom_csv(doc: Document) -> str:
    """Bill of materials as CSV text (semicolon separated, translated headers, formula-safe cells)."""
    from .exports import csv_cell

    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(_t("bom.headers").split(";"))
    for r in bom(doc):
        kind = _t("bom.accessory") if r["type"] == ACCESSORY else r["type"]
        desc = r["description"] or r["spec"]  # rows without a reference: their characteristics
        if r["length_m"]:
            desc += f" ({fmt(r['length_m'], 'm')})"
        w.writerow([csv_cell(v) for v in (r["manufacturer"], r["part_number"], r["range"], desc, kind,
                                          r["quantity"], " ".join(r["refs"]))])
    return out.getvalue()
