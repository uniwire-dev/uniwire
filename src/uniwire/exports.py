"""CSV exports of the wiring (UEP-0001 §3.5.2): wire list, wire marker list, terminal plan and cable schedule.

UTF-8, comma separated, one header line with stable English ``snake_case`` column names, so that other tools can
read them. Display values (``-KM1:A1``) follow the document's ``ref`` fields and are not translated. The wires are the
conductors of the cables of the power tree (:mod:`uniwire.marks`), then the wires the document declares in ``wires``
(format 1.1) between device terminals and terminal strips (:mod:`uniwire.ports`).

>>> from uniwire.exports import wires_csv, markers_csv, terminals_csv, cables_csv
>>> print(cables_csv(doc))                      # doctest: +SKIP
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from typing import Any, Optional

from . import registry
from .marks import Wire, _enclosures, cable_wires, enclosure_at, marked_wires
from .model import Cable, Document, View
from .ports import Ports
from .render.semantics import link_key
from .render.svg import xml_safe
from .resolve import Index, build_index, iter_nodes

WIRE_COLUMNS = ["wire_id", "mark", "from", "from_display", "from_enclosure", "to", "to_display", "to_enclosure",
                "potential", "conductor", "section_mm2", "color", "cable", "core", "length_m", "status", "wiring"]
MARKER_COLUMNS = ["mark", "wire_id", "end", "terminal_display", "section_mm2", "color", "enclosure", "quantity"]
TERMINAL_COLUMNS = ["strip", "terminal", "kind", "bridge_group", "label", "potential", "mark", "inside_targets",
                    "inside_sections_mm2", "outside_targets", "outside_cable", "outside_cores", "fuse_A", "product",
                    "wiring"]
CABLE_COLUMNS = ["cable_id", "ref", "designation", "cores", "section_mm2", "length_m", "from_enclosure",
                 "to_enclosure", "from", "to", "cores_used", "cores_spare", "status"]


def _num(v: Optional[float]) -> str:
    """Locale-independent number: 2.5, 16."""
    if v is None:
        return ""
    return str(int(v)) if float(v).is_integer() else f"{v:.6f}".rstrip("0").rstrip(".")


# Spreadsheet formula injection: a cell that starts with one of these characters may be evaluated as a formula.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
# Exempted, exact matches only: an IEC 81346 reference designation ("-Q1", "=TD1+L2-Q3", "-X1:PE"), i.e. one or
# more segments made of a prefix sign and [A-Za-z0-9._:/] characters (several designations separated by single
# spaces for the "refs" column of the bill of materials), or a plain number ("-1.5", "+2e-3").
_REF = r"(?:[-=+][A-Za-z0-9._:/]+)+[-+]?"  # a final sign: the terminals L+, L- of a DC supply
_REF_CELL = re.compile(rf"{_REF}(?:;? {_REF})*")  # several, separated by spaces or "; " (terminal plan)
_NUMBER_CELL = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_MAX_EXEMPT_CHARS = 256


def csv_cell(value: Any) -> Any:
    """``value`` made safe for a CSV cell: text that a spreadsheet would read as a formula gets a leading single
    quote (designations and numbers excepted), and characters that cannot be encoded are replaced by U+FFFD."""
    if not isinstance(value, str):
        return value
    value = xml_safe(value)
    if value.startswith(_FORMULA_START) and not (
            len(value) <= _MAX_EXEMPT_CHARS and (_REF_CELL.fullmatch(value) or _NUMBER_CELL.fullmatch(value))):
        return "'" + value
    return value


def _csv(columns: list[str], rows: Iterable[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else csv_cell(r.get(k))) for k in columns})
    return buf.getvalue()


def wire_rows(wires: list[Wire]) -> list[dict[str, Any]]:
    """One row per wire (columns :data:`WIRE_COLUMNS`)."""
    return [{
        "wire_id": w.id, "mark": w.mark, "from": w.from_id, "from_display": w.from_display,
        "from_enclosure": w.from_enclosure, "to": w.to_id, "to_display": w.to_display,
        "to_enclosure": w.to_enclosure, "potential": "", "conductor": w.conductor,
        "section_mm2": _num(w.section_mm2), "color": "", "cable": w.cable_id, "core": "",
        "length_m": _num(w.cable.length_m), "status": w.cable.status or "",
    } for w in wires]


def marker_rows(wires: list[Wire]) -> list[dict[str, Any]]:
    """One row per end of a marked wire (columns :data:`MARKER_COLUMNS`); identical rows merged, ``quantity``
    summed, so that the list can be sent to a marker printer."""
    rows: dict[tuple, dict[str, Any]] = {}
    for w in wires:
        if not w.mark:
            continue
        for end, term, encl in (("from", w.from_display, w.from_enclosure), ("to", w.to_display, w.to_enclosure)):
            r = {"mark": w.mark, "wire_id": w.id, "end": end, "terminal_display": term,
                 "section_mm2": _num(w.section_mm2), "color": "", "enclosure": encl}
            key = tuple(r.values())
            if key in rows:
                rows[key]["quantity"] += 1
            else:
                rows[key] = {**r, "quantity": 1}
    return list(rows.values())


_CORES = re.compile(r"^\s*(\d+)\s*[GgXx×]\s*$")


def _total_cores(c: Cable) -> Optional[int]:
    m = _CORES.match(c.cores or "")
    return int(m[1]) if m else None


def cable_rows(doc: Document, index: Optional[Index] = None) -> list[dict[str, Any]]:
    """One row per cable (columns :data:`CABLE_COLUMNS`): the cables of the tree nodes (``<node id>.cable``),
    then those of the links (``<link id or index>.cable``)."""
    index = index or build_index(doc)
    encl = _enclosures(doc)
    used: dict[str, int] = {}
    for w in cable_wires(doc, index):
        used[w.cable_id] = used.get(w.cable_id, 0) + 1
    rows = []

    def row(cid: str, c: Cable, frm: Any, to: Any, n_used: Optional[int]) -> dict[str, Any]:
        total = _total_cores(c)
        spare = total - n_used if total is not None and n_used is not None and total >= n_used else None
        return {"cable_id": cid, "ref": c.ref or "", "designation": c.designation or "", "cores": c.cores or "",
                "section_mm2": _num(c.section_mm2), "length_m": _num(c.length_m),
                "from_enclosure": enclosure_at(frm, index, encl, True),
                "to_enclosure": enclosure_at(to, index, encl, False),
                "from": getattr(frm, "id", None) or "", "to": getattr(to, "id", None) or "", "cores_used": "" if n_used is None else n_used,
                "cores_spare": "" if spare is None else spare, "status": c.status or ""}

    for node, parent, _ in iter_nodes(doc):
        if node.cable is not None:
            cid = f"{node.id}.cable"
            rows.append(row(cid, node.cable, parent, node, used.get(cid)))
    for i, link in enumerate(doc.links):
        if link.cable is not None:
            rows.append(row(f"{link_key(doc, i)}.cable", link.cable, index.nodes.get(link.from_),
                            index.nodes.get(link.to), None))
    return rows


def _ends(doc: Document, index: Index) -> tuple[Ports, dict[str, str]]:
    return Ports(doc, index), _enclosures(doc)


def _place(ports: Ports, ref: str, index: Index, encl: dict[str, str]) -> tuple[str, str]:
    """(display, enclosure) of a port reference; the reference itself when it designates no port."""
    r = ports.resolve(ref)
    if isinstance(r, str):
        return ref, ""
    if r.strip:
        return r.display, ports.strips[r.owner].enclosure or ""
    node = index.nodes[r.owner]  # a load, or a device fed by a cable, is outside the board above it
    inside = node.cable is None and not registry.is_load(node.type)  # type: ignore[attr-defined]
    return r.display, enclosure_at(node, index, encl, inside)


def declared_wire_rows(doc: Document, index: Optional[Index] = None) -> list[dict[str, Any]]:
    """One row per entry of ``wires[]`` (columns :data:`WIRE_COLUMNS`, format 1.1)."""
    index = index or build_index(doc)
    ports, encl = _ends(doc, index)
    rows = []
    for w in doc.wires:
        (fd, fe), (td, te) = _place(ports, w.from_, index, encl), _place(ports, w.to, index, encl)
        rows.append({"wire_id": w.id, "mark": w.mark or "", "from": w.from_, "from_display": fd, "from_enclosure": fe,
                     "to": w.to, "to_display": td, "to_enclosure": te, "potential": w.potential or "",
                     "conductor": w.conductor or "", "section_mm2": _num(w.section_mm2), "color": w.color or "",
                     "cable": w.cable or "", "core": w.core or "", "length_m": _num(w.length_m),
                     "status": w.status or "", "wiring": w.wiring or ""})
    return rows


def wires_csv(doc: Document, view: Optional[View] = None) -> str:
    """Wire list (``uniwire wires``): the conductors of the cables of the power tree, then the declared wires."""
    return _csv(WIRE_COLUMNS, wire_rows(marked_wires(doc, view)) + declared_wire_rows(doc))


def markers_csv(doc: Document, view: Optional[View] = None) -> str:
    """Wire marker list (``uniwire markers``), the declared wires with a mark included."""
    rows = marker_rows(marked_wires(doc, view))
    merged = {tuple(v for k, v in r.items() if k != "quantity"): r for r in rows}
    for r in declared_wire_rows(doc):
        if not r["mark"]:
            continue
        for end in ("from", "to"):
            m = {"mark": r["mark"], "wire_id": r["wire_id"], "end": end, "terminal_display": r[f"{end}_display"],
                 "section_mm2": r["section_mm2"], "color": r["color"], "enclosure": r[f"{end}_enclosure"]}
            key = tuple(m.values())
            if key in merged:
                merged[key]["quantity"] += 1
            else:
                merged[key] = {**m, "quantity": 1}
    return _csv(MARKER_COLUMNS, merged.values())


def terminal_rows(doc: Document, index: Optional[Index] = None, strip: Optional[str] = None) -> list[dict[str, Any]]:
    """Terminal plan (columns :data:`TERMINAL_COLUMNS`): one row per terminal of each strip, in mounting order. A
    wire lands on the outside (field side) when it is made on site, belongs to a cable or ends in another enclosure
    than the strip's; otherwise on the inside (cabinet side)."""
    index = index or build_index(doc)
    ports, encl = _ends(doc, index)
    rows = []
    for s in doc.terminal_strips:
        if strip is not None and strip not in (s.id, s.ref):
            continue
        for t in s.terminals:
            inside: list[tuple[str, str]] = []
            outside: list[tuple[str, str, str]] = []
            site: list[bool] = []  # per outside wire: made on site
            marks: list[str] = []
            for w in doc.wires:
                for here, other in ((w.from_, w.to), (w.to, w.from_)):
                    r = ports.resolve(here)
                    if isinstance(r, str) or not r.strip or r.owner != s.id or r.port != t.no:
                        continue
                    display, where = _place(ports, other, index, encl)
                    if w.mark and w.mark not in marks:
                        marks.append(w.mark)
                    if w.wiring == "site" or w.cable or (s.enclosure and where and where != s.enclosure):
                        outside.append((display, w.cable or "", w.core or ""))
                        site.append(w.wiring == "site")
                    else:
                        inside.append((display, _num(w.section_mm2)))
            product = t.product or s.product
            rows.append({"strip": s.ref or s.id, "terminal": t.no, "kind": t.kind, "bridge_group": t.bridge_group or "",
                         "label": t.label or "", "potential": t.potential or "", "mark": "; ".join(marks),
                         "inside_targets": "; ".join(d for d, _ in inside),
                         "inside_sections_mm2": "; ".join(x for _, x in inside if x),
                         "outside_targets": "; ".join(d for d, _, _ in outside),
                         "outside_cable": "; ".join(dict.fromkeys(c for _, c, _ in outside if c)),
                         "outside_cores": "; ".join(c for _, _, c in outside if c), "fuse_A": _num(t.fuse_A),
                         "product": (product.part_number or product.description or "") if product else "",
                         "wiring": t.wiring or "",
                         # for the drawn plan (render/terminal_plan.py), not exported
                         "_inside": inside, "_outside": outside, "_site": site, "_strip": s})
    return rows


def terminals_csv(doc: Document, strip: Optional[str] = None) -> str:
    """Terminal plan (``uniwire terminals``)."""
    return _csv(TERMINAL_COLUMNS, terminal_rows(doc, strip=strip))


def cables_csv(doc: Document) -> str:
    """Cable schedule (``uniwire cables``)."""
    return _csv(CABLE_COLUMNS, cable_rows(doc))
