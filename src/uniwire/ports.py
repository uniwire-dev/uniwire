"""Terminals (ports) of the nodes and of the terminal strips, and port references (format 1.1, UEP-0001 §3.1-3.2).

Each node has a set of ports: the defaults of its type (:func:`default_ports`, the usual terminal markings of
low-voltage equipment), merged by ``id`` with the node's own ``ports`` (``port_defaults: false`` drops the
defaults). A terminal strip's ports are its terminals. A port is referenced as ``<node or strip id>#<port>``, the
port part matched against the ids, then the aliases; it is displayed ``<ref>:<marking>`` (``-KM1:A1``).

>>> from uniwire import load
>>> from uniwire.ports import Ports
>>> ports = Ports(load(doc))                              # doctest: +SKIP
>>> ports.resolve("KM1#A1").display                        # doctest: +SKIP
'-KM1:A1'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .model import Document, NodeBase
from .model.base import Port
from .model.document import TerminalStrip
from .resolve import Index, build_index

SWITCHING = {"breaker", "fuse", "fuse_switch", "switch_disconnector", "disconnector", "main_breaker", "rcd", "rcbo",
             "contactor", "impulse_relay", "motor_starter"}
SUPPLIES = {"grid", "generator", "ups", "offpage", "busbar"}
LOADS = {"lighting", "socket", "heating", "water_heater", "cooking", "appliance", "ev_charger", "ventilation",
         "shutter", "load"}
INPUTS = {"di", "ai", "counter", "temperature"}
OUTPUTS = {"do", "ao", "relay_out"}


def _pair(a: str, b: str, fa: str, fb: str, **kw) -> list[Port]:
    return [Port(id=a, function=fa, pair=b, **kw), Port(id=b, function=fb, pair=a, **kw)]  # type: ignore[arg-type]


def _poles(poles: Optional[str], aliases: bool = False) -> list[Port]:
    """One pair per pole, odd on the line side: 1-2, 3-4, 5-6 (7-8 for 4P); an unprotected neutral pole N1-N2."""
    n = {"1P": 1, "1P+N": 1, "2P": 2, "3P": 3, "3P+N": 3, "4P": 4}.get(poles or "3P", 3)
    out: list[Port] = []
    for k in range(n):
        a, b = str(2 * k + 1), str(2 * k + 2)
        line, load = (Port(id=a, function="pole_in", pole=k + 1, pair=b), Port(id=b, function="pole_out", pole=k + 1,
                                                                                 pair=a))
        if aliases and k < 3:  # contactor and overload relay markings: 1/L1 - 2/T1
            line.aliases, load.aliases = [f"L{k + 1}"], [f"T{k + 1}"]
        out += [line, load]
    if poles in ("1P+N", "3P+N"):
        out += _pair("N1", "N2", "neutral", "neutral", marking="N", conductor="N")
    return out


def contact_ports(contacts: list[str], first: int = 1) -> list[Port]:
    """Auxiliary contacts in the two-digit convention: the position, then the function (1-2 NC, 3-4 NO; a
    changeover: common 1 with 2 and 4). ``['NO', 'NC']`` gives 13-14 and 21-22."""
    out: list[Port] = []
    for k, c in enumerate(contacts, first):
        if c == "NO":
            out += _pair(f"{k}3", f"{k}4", "contact_no", "contact_no")
        elif c == "NC":
            out += _pair(f"{k}1", f"{k}2", "contact_nc", "contact_nc")
        else:
            out += [Port(id=f"{k}1", function="contact_co"), Port(id=f"{k}2", function="contact_nc", pair=f"{k}1"),
                    Port(id=f"{k}4", function="contact_no", pair=f"{k}1")]
    return out


def _conductors(doc: Document, node: NodeBase) -> list[str]:
    """Conductors of a supply or a load: three phases or one, a neutral, the PE."""
    three = getattr(node, "phases", None) == 3 or getattr(node, "poles", None) in ("3P", "3P+N", "4P") or (
        getattr(node, "phases", None) is None and node.phase is None and doc.installation.system in ("3P", "3P+N"))
    if doc.installation.system == "DC" or getattr(node, "system", None) == "DC":
        return ["L+", "L-", "PE"]
    return (["L1", "L2", "L3"] if three else ["L"]) + (["N"] if doc.installation.system != "3P" else []) + ["PE"]


def default_ports(doc: Document, node: NodeBase) -> list[Port]:
    """The terminals of ``node`` from its type (UEP-0001 §3.1.3), before the node's own ``ports``."""
    t = node.type  # type: ignore[attr-defined]
    poles = getattr(node, "poles", None)
    if t in ("rcd", "rcbo") and poles == "2P":
        poles = "1P+N"  # a 2-pole RCD: 1-2 and N1-N2
    if t in SWITCHING:
        out = _poles(poles, aliases=t in ("contactor", "motor_starter"))
        if t in ("contactor", "impulse_relay"):
            out += _pair("A1", "A2", "coil", "coil", mandatory=True)
            out += contact_ports(list(getattr(node, "contacts", []) or []))
        return out
    if t == "thermal_relay":
        return _poles("3P", aliases=True) + _pair("95", "96", "contact_nc", "contact_nc") + \
            _pair("97", "98", "contact_no", "contact_no")
    if t == "motor":
        if getattr(node, "phases", None) == 1:
            return [Port(id="U1", function="power_in"), Port(id="U2", function="power_in"),
                    Port(id="PE", function="earth", conductor="PE")]
        return [Port(id=w + "1", function="power_in", pole=k + 1, aliases=[w]) for k, w in enumerate("UVW")] + \
            [Port(id="PE", function="earth", conductor="PE")]
    if t == "transformer":
        out = [Port(id=f"{s}{w}", function="power_in" if s == "1" else "power_out") for s in "12" for w in "UVW"]
        if "n" in (getattr(node, "coupling", None) or "").lower()[1:]:
            out.append(Port(id="2N", aliases=["N"], function="neutral", conductor="N"))
        return out + [Port(id="PE", function="earth", conductor="PE")]
    if t == "power_supply":
        out = [Port(id="L", function="power_in"), Port(id="N", function="neutral"),
               Port(id="PE", function="earth", conductor="PE")]
        if getattr(node, "output", "DC") == "AC":
            return out + [Port(id="2L", function="power_out"), Port(id="2N", function="neutral")]
        return out + [Port(id="L+", aliases=["+"], function="power_out", conductor="L+"),
                      Port(id="L-", aliases=["-"], function="power_out", conductor="L-")]
    if t == "plc":
        out = [Port(id="L+", function="supply"), Port(id="M", function="supply"),
               Port(id="PE", function="earth", conductor="PE")]
        last: dict[int, int] = {}  # channels already numbered in a slot: built-in modules all are slot 0
        for slot, m in [(0, m) for m in getattr(node, "onboard", [])] + [(m.slot, m) for m in getattr(node, "modules", [])]:
            fn = "signal_in" if m.kind in INPUTS else "signal_out" if m.kind in OUTPUTS else "other"
            for ch in range(1, (m.channels or 0) + 1):
                n = last.get(slot, 0) + ch
                out.append(Port(id=f"{slot}.{n}", function=fn, capacity=1,  # type: ignore[arg-type]
                                label=(m.channel_labels or {}).get(str(ch))))
            last[slot] = last.get(slot, 0) + (m.channels or 0)
        return out
    if t == "spd":
        return [Port(id=c, function="power_in") for c in _conductors(doc, node) if c != "PE"] + \
            [Port(id="PE", function="earth", conductor="PE")]
    if t in SUPPLIES or t in LOADS:
        fn = "power_out" if t in SUPPLIES else "power_in"
        return [Port(id=c, function="earth" if c == "PE" else "neutral" if c == "N" else fn,  # type: ignore[arg-type]
                     conductor=c if c in ("N", "PE", "L+", "L-") else None) for c in _conductors(doc, node)]
    if t == "board":
        return [Port(id="PE", function="earth", conductor="PE", capacity=99),
                Port(id="N", function="neutral", conductor="N", capacity=99)]
    if t == "earth_bar":
        return [Port(id="PE", function="earth", conductor="PE", capacity=99)]
    return []


def node_ports(doc: Document, node: NodeBase) -> list[Port]:
    """All the terminals of ``node``: the defaults of its type merged by ``id`` with its ``ports``."""
    own = {p.id: p for p in node.ports}
    base = [] if node.port_defaults is False else default_ports(doc, node)
    out = [own.pop(p.id, p) for p in base]
    return out + list(own.values())


@dataclass(frozen=True)
class Target:
    """A resolved port reference."""

    owner: str  # id of the node or terminal strip
    port: str  # canonical port id (terminal number for a strip)
    display: str  # '-KM1:A1'
    strip: bool  # a terminal of a terminal strip
    info: Port  # the port (for a strip terminal: a port built from the terminal)


class Ports:
    """Ports of every node and strip of a document, and resolution of references (:meth:`resolve`)."""

    def __init__(self, doc: Document, index: Optional[Index] = None):
        self.doc = doc
        self.index = index or build_index(doc)
        self.strips: dict[str, TerminalStrip] = {s.id: s for s in doc.terminal_strips}
        self._cache: dict[str, list[Port]] = {}

    def of(self, owner: str) -> list[Port]:
        """Ports of a node or a strip (``[]`` when unknown)."""
        if owner not in self._cache:
            if owner in self.strips:
                s = self.strips[owner]
                self._cache[owner] = [Port(id=t.no, label=t.label, section_max_mm2=t.section_max_mm2,
                                           function="earth" if t.kind == "earth" else None,
                                           capacity=2 * (t.points or 1)) for t in s.terminals]
            elif owner in self.index.nodes:
                self._cache[owner] = node_ports(self.doc, self.index.nodes[owner])
            else:
                self._cache[owner] = []
        return self._cache[owner]

    def display(self, owner: str, port: Port) -> str:
        o = self.strips.get(owner) or self.index.nodes.get(owner)
        name = (getattr(o, "ref", None) or owner) if o is not None else owner
        return f"{name}:{port.marking or port.id}"

    def resolve(self, ref: str) -> Target | str:
        """The port a reference designates, or the reason it designates none (a message key and its fields, as
        ``'<key>|<field>=<value>…'``, turned into text by the rule that reports it)."""
        owner, _, pid = ref.partition("#")
        if owner not in self.strips and owner not in self.index.nodes:
            return f"wiring.no_owner|ref={ref}|owner={owner}"
        if owner not in self.doc._explicit_ids:
            return f"wiring.generated_id|ref={ref}|owner={owner}"
        ports = self.of(owner)
        hit = [p for p in ports if p.id == pid] or [p for p in ports if pid in p.aliases]
        if not hit:
            known = ", ".join(p.id for p in ports[:24]) or "-"
            return f"wiring.no_port|ref={ref}|owner={owner}|port={pid}|known={known}"
        if len(hit) > 1:  # two ports with this id (declared twice), or an alias of two ports
            return f"wiring.ambiguous|ref={ref}|port={pid}"
        p = hit[0]
        return Target(owner, p.id, self.display(owner, p), owner in self.strips, p)

