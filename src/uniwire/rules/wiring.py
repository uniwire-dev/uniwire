"""Wiring rules (core profile, format 1.1, UEP-0001 §3.7): port references, terminal capacity, coils left unwired,
protective-conductor colour, terminal strips. They only apply to documents that use ``wires`` or
``terminal_strips``: a single-line document gets no new finding."""

from __future__ import annotations

from collections import Counter

from ..i18n import t as _t
from ..model import Document
from ..ports import Ports, Target
from ..resolve import Index
from . import Finding, rule

DEFAULT_CAPACITY = 2


def _say(code: str) -> tuple[str, str]:
    """(rule name, message) of a reason returned by :meth:`Ports.resolve`."""
    key, *fields = code.split("|")
    return "port.unknown", _t(key, **dict(f.split("=", 1) for f in fields))


@rule("core")
def wires(doc: Document, idx: Index):
    if not doc.wires and not doc.terminal_strips:
        return
    ports = Ports(doc, idx)
    on: Counter = Counter()  # conductors per terminal
    wired: set[str] = set()  # owners with at least one wire
    landed: set[tuple[str, str]] = set()
    for w in doc.wires:
        ends: list[Target] = []
        for ref in (w.from_, w.to):
            r = ports.resolve(ref)
            if isinstance(r, str):
                name, msg = _say(r)
                yield Finding("error", name, msg, w.id)
                continue
            ends.append(r)
        if w.from_ == w.to:
            yield Finding("error", "wire.endpoints", _t("wiring.same_ends", wire=w.id, ref=w.from_), w.id)
        for e in ends:
            on[(e.owner, e.port)] += 1
            wired.add(e.owner)
            landed.add((e.owner, e.port))
            if w.conductor in ("PE", "PEN") and e.info.function not in (None, "earth"):
                yield Finding("error", "port.conductor", _t("wiring.pe_on_live", wire=w.id, display=e.display), w.id)
            if w.section_mm2 and e.info.section_max_mm2 and w.section_mm2 > e.info.section_max_mm2:
                yield Finding("error", "strip.capacity" if e.strip else "port.capacity",
                              _t("wiring.section_max", wire=w.id, section=w.section_mm2, display=e.display,
                                 max=e.info.section_max_mm2), w.id)
        if w.color == "GNYE" and w.conductor not in ("PE", "PEN"):
            yield Finding("error", "port.conductor", _t("wiring.gnye", wire=w.id, conductor=w.conductor
                                                        or _t("wiring.control_wire")), w.id)
    for (owner, pid), n in on.items():
        port = next(p for p in ports.of(owner) if p.id == pid)
        cap = port.capacity or DEFAULT_CAPACITY
        if n > cap:
            yield Finding("error", "port.capacity", _t("wiring.capacity", display=ports.display(owner, port), count=n,
                                                        capacity=cap), owner)
    for owner in sorted(wired - set(ports.strips)):
        for p in ports.of(owner):
            if p.function == "coil" and p.mandatory is not False and (owner, p.id) not in landed:
                node = idx.nodes[owner]
                yield Finding("error", "port.unconnected", _t("wiring.coil_unconnected", display=ports.display(owner, p),
                                                               node=node.ref or owner), owner)
    yield from _strips(doc, idx)


def _strips(doc: Document, idx: Index):
    enclosures = {e.id for e in doc.enclosures} | {n for n, node in idx.nodes.items()
                                                    if node.type == "board"}  # type: ignore[attr-defined]
    for s in doc.terminal_strips:
        for no, n in Counter(t.no for t in s.terminals).items():
            if n > 1:
                yield Finding("error", "strip.terminal", _t("wiring.duplicate_terminal", strip=s.ref or s.id, no=no),
                              s.id)
        if s.enclosure and s.enclosure not in enclosures:
            yield Finding("error", "strip.terminal", _t("wiring.strip_enclosure", strip=s.ref or s.id,
                                                        enclosure=s.enclosure), s.id)
        for group, n in Counter(t.bridge_group for t in s.terminals if t.bridge_group).items():
            if n == 1:
                yield Finding("warning", "strip.bridge", _t("wiring.lone_bridge", strip=s.ref or s.id, group=group),
                              s.id)
