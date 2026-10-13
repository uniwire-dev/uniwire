"""CSV exports of the wiring (UEP-0001 §3.5.2, the part available in the current format): wire list, wire marker list and cable
schedule.

UTF-8, comma separated, one header line with stable English ``snake_case`` column names, so that other tools can
read them. Display values (``-KM1``) follow the document's ``ref`` fields and are not translated. In the current format
the wires are the conductors of the cables of the power tree (:mod:`uniwire.marks`); the columns that need
format 2.0 data (ports, potentials, cores, colours) are present and left empty.

>>> from uniwire.exports import wires_csv, markers_csv, cables_csv
>>> print(cables_csv(doc))                      # doctest: +SKIP
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from typing import Any, Optional

from .marks import Wire, _enclosures, cable_wires, enclosure_at, marked_wires
from .model import Cable, Document, View
from .render.semantics import link_key
from .render.svg import xml_safe
from .resolve import Index, build_index, iter_nodes

WIRE_COLUMNS = ["wire_id", "mark", "from", "from_display", "from_enclosure", "to", "to_display", "to_enclosure",
                "potential", "conductor", "section_mm2", "color", "cable", "core", "length_m", "status"]
MARKER_COLUMNS = ["mark", "wire_id", "end", "terminal_display", "section_mm2", "color", "enclosure", "quantity"]
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
_REF = r"(?:[-=+][A-Za-z0-9._:/]+)+"
_REF_CELL = re.compile(rf"{_REF}(?: {_REF})*")
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


def wires_csv(doc: Document, view: Optional[View] = None) -> str:
    """Wire list (``uniwire wires``)."""
    return _csv(WIRE_COLUMNS, wire_rows(marked_wires(doc, view)))


def markers_csv(doc: Document, view: Optional[View] = None) -> str:
    """Wire marker list (``uniwire markers``)."""
    return _csv(MARKER_COLUMNS, marker_rows(marked_wires(doc, view)))


def cables_csv(doc: Document) -> str:
    """Cable schedule (``uniwire cables``)."""
    return _csv(CABLE_COLUMNS, cable_rows(doc))
