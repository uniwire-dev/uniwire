"""Bill of materials built from the hardware part references.

Every node (tree, auxiliary devices, coupling devices) and every PLC module that carries a
reference (``product`` or ``manufacturer``/``part_number``) becomes a row; identical rows are aggregated.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from .i18n import t as _t
from .labels import part_number
from .model import Document
from .resolve import iter_nodes

ACCESSORY = "accessory"  # row type of a product accessory (data value; translated in the CSV)


def _prod(obj: Any) -> tuple[str, str, str, str]:
    p = getattr(obj, "product", None)
    manu = (p.manufacturer if p is not None else None) or getattr(obj, "manufacturer", None) or ""
    pn = part_number(obj) or ""
    rng = (p.range if p is not None else None) or getattr(obj, "range", None) or ""
    desc = (p.description if p is not None else None) or ""
    return manu, pn, rng, desc


def bom(doc: Document) -> list[dict[str, Any]]:
    """Bill of materials: one row per (manufacturer, part number, range), sorted.

    Each row has ``manufacturer``, ``part_number``, ``range``, ``description``, ``type`` (node type, ``module
    <kind>`` for PLC modules, or the accessory marker), ``quantity`` (``product.quantity``, else ``count``,
    else 1, summed) and ``refs`` (reference designations involved, ``-A1.3`` for module 3 of ``-A1``).
    Nodes without a manufacturer or part number are left out.
    """
    rows: dict[tuple, dict[str, Any]] = {}

    def add(manu: str, pn: str, rng: str, desc: str, qty: int, ref: str, kind: str) -> None:
        if not pn and not manu:
            return
        key = (manu, pn, rng)
        r = rows.setdefault(key, {"manufacturer": manu, "part_number": pn, "range": rng, "description": desc,
                                  "type": kind, "quantity": 0, "refs": []})
        r["quantity"] += qty
        if ref:
            r["refs"].append(ref)
        if desc and not r["description"]:
            r["description"] = desc

    for n, _, _ in iter_nodes(doc):
        manu, pn, rng, desc = _prod(n)
        qty = (n.product.quantity if n.product is not None and n.product.quantity else None) or n.count or 1
        add(manu, pn, rng, desc, qty, n.ref or n.id or "", n.type)  # type: ignore[attr-defined]
        if n.product is not None:
            for acc in n.product.accessories:
                add(acc.manufacturer or manu, acc.part_number or "", acc.range or "", acc.description or "",
                    acc.quantity or qty, n.ref or "", ACCESSORY)
        if n.type != "plc":  # type: ignore[attr-defined]  # pv_array.modules is a panel count
            continue
        for m in list(n.onboard or []) + list(n.modules or []):  # type: ignore[attr-defined]
            mm, mp, mr, md = _prod(m)
            add(mm or manu, mp, mr, md or m.kind, 1, f"{n.ref or n.id}.{m.slot}", f"module {m.kind}")
    return sorted(rows.values(), key=lambda r: (r["manufacturer"], r["part_number"]))


def bom_csv(doc: Document) -> str:
    """Bill of materials as CSV text (semicolon separated, translated headers, formula-safe cells)."""
    from .exports import csv_cell

    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(_t("bom.headers").split(";"))
    for r in bom(doc):
        kind = _t("bom.accessory") if r["type"] == ACCESSORY else r["type"]
        w.writerow([csv_cell(v) for v in (r["manufacturer"], r["part_number"], r["range"], r["description"], kind,
                                          r["quantity"], " ".join(r["refs"]))])
    return out.getvalue()
