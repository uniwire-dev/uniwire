"""CSV exports of the wiring (UEP-0001 §3.5.2, the part available in the current format): wire list, wire marker list, cable
schedule, and the control side described by the PLCs (SPEC §3b): I/O list and terminal strip table.

UTF-8, comma separated, one header line with stable English ``snake_case`` column names, so that other tools can
read them. Display values (``-KM1``) follow the document's ``ref`` fields and are not translated. In the current format
the wires are the conductors of the cables of the power tree (:mod:`uniwire.marks`); the columns that need
format 2.0 data (ports, potentials, cores, colours) are present and left empty.

>>> from uniwire.exports import wires_csv, markers_csv, cables_csv, io_csv, terminals_csv
>>> print(cables_csv(doc))                      # doctest: +SKIP
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from typing import Any, Optional

from .labels import part_number
from .marks import Wire, _enclosures, cable_wires, display, enclosure_at, marked_wires
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


# ------------------------------------------------------------------ I/O list and terminal strips

IO_COLUMNS = ["plc", "plc_display", "slot", "module", "module_kind", "io_type", "channel", "address", "direction",
              "signal", "un_V", "label", "device", "device_display", "device_port", "terminal", "link_kind", "cable",
              "status"]
TERMINAL_COLUMNS = ["strip", "strip_display", "terminal", "function", "from", "from_display", "from_port",
                    "from_mark", "from_cable", "to", "to_display", "to_port", "to_mark", "to_cable", "link_kind",
                    "label"]

# Signal type of a channel by module kind; a mixed module takes the direction of its link.
_IO_TYPE = {"di": "DI", "do": "DO", "relay_out": "DO", "ai": "AI", "temperature": "AI", "ao": "AO",
            "counter": "CNT", "safety": "SAFETY", "comm": "COM", "power_measurement": "PM", "motor": "MOTOR"}
_INPUT_KINDS = {"di", "ai", "temperature", "counter", "safety", "power_measurement"}
_OUTPUT_KINDS = {"do", "relay_out", "ao", "motor"}
# Modules whose every channel is listed, connected or spare.
_IO_MODULES = _INPUT_KINDS | _OUTPUT_KINDS | {"mixed_io"}
# Links that carry a signal to or from a PLC channel (power and earth conductors are not I/O).
_SIGNAL_LINKS = {"control", "measure", "data", "trip", "interlock", "key"}
_MAX_CHANNELS = 1024
# Terminal functions naming a line conductor: the phases of a motor terminal board (U, V, W).
_PHASE_ALIAS = {"U": "L1", "V": "L2", "W": "L3", "U1": "L1", "V1": "L2", "W1": "L3"}
_MAX_RANGE = 1000


def _ports(port: Optional[str]) -> list[str]:
    """The ports named by a ``from_port`` / ``to_port`` value: ``"3.1"``, ``"1,3"`` (several), ``""`` (none)."""
    if port is None or not str(port).strip():
        return [""]
    return [p.strip() for p in str(port).split(",") if p.strip()] or [""]


def _slot_channel(port: str) -> Optional[tuple[int, Optional[int]]]:
    """``"3.1"`` -> (3, 1), ``"3"`` -> (3, None); ``None`` when the port is not ``slot.channel``."""
    m = re.fullmatch(r"\s*(\d+)\s*(?:\.\s*(\d+)\s*)?", port)
    return (int(m[1]), int(m[2]) if m[2] else None) if m else None


def _link_direction(link: Any, plc_id: str) -> str:
    """``in`` (signal read by the PLC), ``out`` (signal sent by it), ``bus`` (data link)."""
    if link.kind == "data":
        return "bus"
    if link.kind == "measure":
        return "in"
    return "out" if link.from_ == plc_id else "in"


def _link_cable(doc: Document, i: int) -> str:
    c = doc.links[i].cable
    return "" if c is None else (c.ref or f"{link_key(doc, i)}.cable")


def _natural(text: str) -> tuple:
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"(\d+)", text) if p)


def _strip_prefixes(tb: Any) -> list[str]:
    names = {n for n in (tb.ref, (tb.ref or "").lstrip("-=+"), tb.id) if n}
    return sorted(names, key=len, reverse=True)


def _terminal(tb: Any, port: str) -> str:
    """Terminal number of a port on a terminal block: ``"X1:3"``, ``"-X1.3"`` and ``"3"`` are terminal ``3`` of
    the block ``-X1``."""
    port = port.strip()
    for p in _strip_prefixes(tb):
        if len(port) > len(p) + 1 and port.startswith(p) and port[len(p)] in ".:":
            return port[len(p) + 1:].strip()
    return port


_RANGE = re.compile(r"(?P<p>[^\s=]*?)(?P<a>\d+)\s*[-\u2013\u2026]\s*(?P<q>[^\s=]*?)(?P<b>\d+)")
_FUNCTION = re.compile(r"(?P<n>[^\s=]+)\s*=\s*(?P<f>\S.*)")


def declared_terminals(tb: Any) -> list[tuple[str, str]]:
    """The terminals listed by a terminal block's ``terminals`` field, as (terminal, function) pairs:
    ``"X1.1-X1.12"``, ``"1-12"``, ``"1, 2, PE"`` or ``"1=L; 2=N; 3=PE"`` (function after ``=``). Text that is not
    such a list gives no terminals (it stays a description)."""
    text = getattr(tb, "terminals", None) or ""
    out: list[tuple[str, str]] = []
    for tok in (t.strip() for t in re.split(r"[;,]", text)):
        if not tok:
            continue
        m = _RANGE.fullmatch(tok)
        if m and (not m["q"] or m["q"] == m["p"]):
            if not 0 <= int(m["b"]) - int(m["a"]) <= _MAX_RANGE:
                return []
            out += [(_terminal(tb, f"{m['p']}{k}"), "") for k in range(int(m["a"]), int(m["b"]) + 1)]
            continue
        m = _FUNCTION.fullmatch(tok)
        if m:
            out.append((_terminal(tb, m["n"]), m["f"].strip()))
            continue
        if re.fullmatch(r"\S+", tok):
            out.append((_terminal(tb, tok), ""))
            continue
        return []
    seen: set[str] = set()
    return [t for t in out if not (t[0] in seen or seen.add(t[0]))]  # type: ignore[func-returns-value]


def _tb_links(doc: Document, index: Index) -> dict[tuple[str, str], list[tuple[int, str, str]]]:
    """Links landing on a numbered terminal: (block id, terminal) -> [(link index, far end id, far end port)]."""
    out: dict[tuple[str, str], list[tuple[int, str, str]]] = {}
    for i, link in enumerate(doc.links):
        for here, port, far, far_port in ((link.from_, link.from_port, link.to, link.to_port),
                                          (link.to, link.to_port, link.from_, link.from_port)):
            tb = index.nodes.get(here)
            if tb is None or tb.type != "terminal_block" or here == far:  # type: ignore[attr-defined]
                continue
            for p in _ports(port):
                if p:
                    out.setdefault((here, _terminal(tb, p)), []).append((i, far, far_port or ""))
    return out


def _io_row(doc: Document, index: Index, through: dict, plc: Any, m: Any, slot: Optional[int], ch: Optional[int],
            address: str, i: Optional[int]) -> list[dict[str, Any]]:
    """Rows of one channel of ``plc`` (several when its link reaches several devices through a terminal)."""
    pid = plc.id or ""
    link = doc.links[i] if i is not None else None
    kind = m.kind if m is not None else ""
    direction = _link_direction(link, pid) if link is not None else (
        "in" if kind in _INPUT_KINDS else "out" if kind in _OUTPUT_KINDS else "")
    io_type = _IO_TYPE.get(kind, "")
    if kind == "mixed_io":
        io_type = {"in": "DI", "out": "DO"}.get(direction, "")
    labels = getattr(m, "channel_labels", None) or {}
    base = {
        "plc": pid, "plc_display": display(plc), "slot": "" if slot is None else slot,
        "module": (part_number(m) or m.label or "") if m is not None else "", "module_kind": kind,
        "io_type": io_type, "channel": "" if ch is None else ch, "address": address, "direction": direction,
        "signal": (getattr(m, "signal", None) or getattr(m, "protocol", None) or
                   (link.protocol if link is not None else None) or ""),
        "un_V": _num(getattr(m, "un_V", None)),
        "label": labels.get(str(ch)) or (link.label if link is not None else None) or "",
        "device": "", "device_display": "", "device_port": "", "terminal": "",
        "link_kind": link.kind if link is not None else "", "cable": "", "status": "",
    }
    if link is None:
        return [base]
    far, far_port = (link.to, link.to_port) if link.from_ == pid else (link.from_, link.from_port)
    if link.from_ == link.to:
        far, far_port = "", None
    base.update(cable=_link_cable(doc, i), status=link.status or "")  # type: ignore[arg-type]
    node = index.nodes.get(far)
    out = []
    if node is not None and node.type == "terminal_block":  # type: ignore[attr-defined]
        for p in _ports(far_port):
            term = _terminal(node, p) if p else ""
            tag = f"{display(node)}:{term}" if term else display(node)
            beyond = [x for x in through.get((far, term), []) if x[0] != i] if term else []
            for j, dev, dev_port in beyond or [(None, far, p)]:
                d = index.nodes.get(dev)
                r = {**base, "device": dev, "device_display": display(d) if d else dev,
                     "device_port": dev_port if beyond else "", "terminal": tag}
                if j is not None:  # the field side of the terminal tells what the PLC side left out
                    r["label"] = r["label"] or doc.links[j].label or ""
                    r["cable"] = r["cable"] or _link_cable(doc, j)
                out.append(r)
        return out
    return [{**base, "device": far, "device_display": display(node) if node else far,
             "device_port": far_port or ""}]


def io_rows(doc: Document, index: Optional[Index] = None) -> list[dict[str, Any]]:
    """I/O list (columns :data:`IO_COLUMNS`): for each PLC, one row per channel of its I/O modules (connected or
    spare, in slot and channel order), then the links on its other modules and those without a channel.

    A channel is addressed by a link port ``slot.channel`` (SPEC §3b). The connected device is the other end of
    the link; when that end is a terminal block terminal (``to_port``) that another link continues, the row names
    the device beyond the block and the terminal in ``terminal`` (``-X2:5``)."""
    index = index or build_index(doc)
    through = _tb_links(doc, index)
    rows: list[dict[str, Any]] = []
    for plc in [n for n in index.nodes.values() if n.type == "plc"]:  # type: ignore[attr-defined]
        pid = plc.id or ""
        modules = list(plc.onboard) + list(plc.modules)  # type: ignore[attr-defined]
        by_slot: dict[int, list[Any]] = {}
        for m in modules:
            by_slot.setdefault(m.slot, []).append(m)
        # (module position or None, channel or None) -> connections
        conn: dict[tuple[Optional[int], Optional[int]], list[tuple[int, str, Optional[int], str]]] = {}
        loose: list[tuple[int, str, Optional[int]]] = []  # (link index, port, slot) not tied to a module
        for i, link in enumerate(doc.links):
            if link.kind not in _SIGNAL_LINKS:
                continue
            for here, port in ((link.from_, link.from_port), (link.to, link.to_port)):
                if here != pid:
                    continue
                for p in _ports(port):
                    sc = _slot_channel(p) if p else None
                    cands = by_slot.get(sc[0], []) if sc else []
                    if not cands:
                        loose.append((i, p, sc[0] if sc else None))
                        continue
                    want = _OUTPUT_KINDS if _link_direction(link, pid) == "out" else _INPUT_KINDS
                    m = next((c for c in cands if c.kind in want), None) or next(
                        (c for c in cands if c.kind == "mixed_io"), cands[0])
                    conn.setdefault((modules.index(m), sc[1]), []).append((i, p, sc[0], here))  # type: ignore[index]

        for pos, m in enumerate(modules):
            chans = sorted({c for (mp, c) in conn if mp == pos}, key=lambda c: (c is None, c or 0))
            n = min(m.channels or 0, _MAX_CHANNELS) if m.kind in _IO_MODULES else 0
            for ch in sorted(set(range(1, n + 1)) | {c for c in chans if c is not None}) + (
                    [None] if None in chans else []):
                links = conn.get((pos, ch), [])
                if not links:
                    rows += _io_row(doc, index, through, plc, m, m.slot, ch, f"{m.slot}.{ch}", None)
                for i, p, _, _ in links:
                    rows += _io_row(doc, index, through, plc, m, m.slot, ch, p, i)
        for i, p, slot in loose:
            rows += _io_row(doc, index, through, plc, None, slot, None, p, i)
    return rows


def _place(declared: list[tuple[str, str]], lines: set[str], conductor: str) -> Any:
    """Terminal of a block that takes ``conductor``: the one whose function names it (``L`` for the only line
    conductor ``lines`` of the block), else a key of its own."""
    for t, f in declared:
        f = _PHASE_ALIAS.get(f.strip().upper(), f.strip().upper())
        if f == conductor.upper() or (f == "L" and lines == {conductor}):
            return t
    return ("~", conductor)


def terminal_rows(doc: Document, view: Optional[View] = None, index: Optional[Index] = None) -> list[dict[str, Any]]:
    """Terminal strip table (columns :data:`TERMINAL_COLUMNS`): for each terminal block, one row per terminal with
    what arrives on it (``from``) and what leaves it (``to``).

    The terminals are those listed in ``terminals`` (spare ones included) and those named by the ports of the
    links (``to_port`` on the block side), in that order. A block in the power tree also gets the conductors of
    its cable (from its parent) and of its children's cables, with their wire marks (``wire_marking`` rules of
    ``view``); a ``function`` given in ``terminals`` (``1=L``) places a conductor on its terminal. A link end
    without a terminal number gets a row of its own, at the end."""
    index = index or build_index(doc)
    wires = marked_wires(doc, view, index)
    rows: list[dict[str, Any]] = []
    for tb in [n for n in index.nodes.values() if n.type == "terminal_block"]:  # type: ignore[attr-defined]
        tid = tb.id or ""
        declared = declared_terminals(tb)
        func = dict(declared)
        ins: dict[Any, list[dict[str, Any]]] = {}
        outs: dict[Any, list[dict[str, Any]]] = {}
        loose = 0

        def side(prefix: str, node_id: str, port: str, mark: str = "", cable: str = "") -> dict[str, Any]:
            n = index.nodes.get(node_id)
            return {prefix: node_id, f"{prefix}_display": display(n) if n else node_id, f"{prefix}_port": port,
                    f"{prefix}_mark": mark, f"{prefix}_cable": cable}

        # power tree: the cable from the parent, the cables to the children
        parent = index.parent.get(tid)
        w_in = [w for w in wires if w.node == tid]
        w_kids = {c.id: [w for w in wires if w.node == c.id] for c in tb.children}
        lines = {w.conductor for w in w_in + [w for ws in w_kids.values() for w in ws] if w.conductor[:1] == "L"}

        for w in w_in:
            ins.setdefault(_place(declared, lines, w.conductor), []).append(
                {**side("from", w.from_id, ""), "from_mark": w.mark, "from_cable": w.cable_ref or w.cable_id,
                 "function": w.conductor, "link_kind": "power"})
        for child in tb.children:
            for w in w_kids[child.id]:
                outs.setdefault(_place(declared, lines, w.conductor), []).append(
                    {**side("to", w.to_id, ""), "to_mark": w.mark, "to_cable": w.cable_ref or w.cable_id,
                     "function": w.conductor, "link_kind": "power"})
        # an end without a cable has no known conductors: it takes those of the other side (a block passes them on)
        if parent is not None and not w_in:
            for key in list(outs) or [("~", "")]:
                ins.setdefault(key, []).append({**side("from", parent, ""), "link_kind": "power"})
        known = list(ins) or [("~", "")]
        for child in tb.children:
            if not w_kids[child.id]:
                for key in known:
                    outs.setdefault(key, []).append({**side("to", child.id or "", ""), "link_kind": "power"})
        # links
        for i, link in enumerate(doc.links):
            for here, port, far, far_port, bucket, prefix in (
                    (link.to, link.to_port, link.from_, link.from_port, ins, "from"),
                    (link.from_, link.from_port, link.to, link.to_port, outs, "to")):
                if here != tid or far == tid:
                    continue
                for p in _ports(port):
                    key: Any = _terminal(tb, p) if p else ("~~", loose := loose + 1)
                    bucket.setdefault(key, []).append(
                        {**side(prefix, far, far_port or "", cable=_link_cable(doc, i)), "link_kind": link.kind,
                         "label": link.label or ""})

        keys = [t for t, _ in declared]
        extra = [k for k in set(ins) | set(outs) if isinstance(k, str) and k not in func]
        keys += sorted(extra, key=_natural)
        keys += sorted((k for k in set(ins) | set(outs) if not isinstance(k, str)), key=lambda k: (k[0], str(k[1])))
        for key in keys:
            a, b = ins.get(key, []), outs.get(key, [])
            for k in range(max(len(a), len(b), 1)):
                r: dict[str, Any] = {**dict.fromkeys(TERMINAL_COLUMNS, ""), "strip": tid, "strip_display": display(tb),
                                     "terminal": key if isinstance(key, str) else "",
                                     "function": func.get(key, "") if isinstance(key, str) else ""}
                for part in (a[k] if k < len(a) else {}, b[k] if k < len(b) else {}):
                    for c, v in part.items():
                        if c in ("function", "link_kind", "label"):
                            r[c] = r.get(c) or v
                        else:
                            r[c] = v
                rows.append(r)
    return rows


def io_csv(doc: Document) -> str:
    """I/O list of the PLCs (``uniwire io``)."""
    return _csv(IO_COLUMNS, io_rows(doc))


def terminals_csv(doc: Document, view: Optional[View] = None) -> str:
    """Terminal strip table (``uniwire terminals``)."""
    return _csv(TERMINAL_COLUMNS, terminal_rows(doc, view))
