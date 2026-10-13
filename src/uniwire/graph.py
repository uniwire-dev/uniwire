"""Expansion of tree + links -> graph of terminals / connectivity nodes.

Canonical "network" form (CIM / IEC 61850 style: ConductingEquipment -> Terminal ->
ConnectivityNode), the basis for exports to calculation tools (pandapower, CIM, IFC...).

* every component has an ``in`` terminal (except sources) and an ``out`` terminal
  (except loads); the transfer switch additionally has ``in2``;
* every parent -> child(ren) connection creates a connectivity node ``cn:<parent>``;
  a busbar is therefore a single node shared by all its outgoing feeders;
* a node's cable becomes a ``cable`` component inserted between the parent's node and the component;
* ``transfer``/``tie``/``bypass``/``parallel`` links create power connections,
  the others (control, interlock...) are output separately in ``signals``.
"""

from __future__ import annotations

from typing import Any

from . import registry
from .model import Document, NodeBase
from .resolve import iter_nodes

SOURCES_WITHOUT_INPUT = {"grid", "generator", "pv_array", "battery"}
POWER_LINKS = {"transfer", "tie", "bypass", "parallel"}


def to_graph(doc: Document) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    cnodes: dict[str, list[str]] = {}

    def connect(cn: str, terminal: str) -> None:
        cnodes.setdefault(cn, []).append(terminal)

    def add_component(n: NodeBase) -> None:
        t = n.type  # type: ignore[attr-defined]
        terms = []
        if t not in SOURCES_WITHOUT_INPUT:
            terms.append("in")
        if registry.category(t) != "load" and t not in ("spd", "earth", "pv_array", "battery") or n.children:
            terms.append("out")
        if t == "transfer_switch":
            terms.append("in2")
        attrs = n.model_dump(mode="json", exclude={"children", "cable", "id", "type", "use"}, exclude_none=True)
        components.append({"id": n.id, "type": t, "terminals": terms, "attributes": attrs,
                           "map": registry.info(t)["map"]})

    for n, parent, _ in iter_nodes(doc):
        add_component(n)
        if parent is None:
            continue
        upstream = f"cn:{parent.id}"
        connect(upstream, f"{parent.id}.out")
        if n.cable is not None:
            cid = f"{n.id}.cable"
            components.append({"id": cid, "type": "cable", "terminals": ["in", "out"],
                               "attributes": n.cable.model_dump(mode="json", exclude_none=True),
                               "map": {"cim": "ACLineSegment", "ifc": "IfcCableSegment/CABLESEGMENT", "scl": "CAB"}})
            connect(upstream, f"{cid}.in")
            connect(f"cn:{cid}", f"{cid}.out")
            connect(f"cn:{cid}", f"{n.id}.in")
        else:
            connect(upstream, f"{n.id}.in")

    signals = []
    for l in doc.links:
        if l.kind in POWER_LINKS:
            a_term = f"{l.from_}.out"
            b_term = f"{l.to}.in2" if l.kind == "transfer" else f"{l.to}.out"
            if l.device is not None:
                connect(f"cn:{l.from_}", a_term)
                connect(f"cn:{l.from_}", f"{l.device.id}.in")
                connect(f"cn:{l.to}", f"{l.device.id}.out")
                connect(f"cn:{l.to}", b_term)
            else:
                cn = f"cn:{l.from_}" if l.kind != "transfer" else f"cn:{l.from_}->{l.to}"
                connect(cn, a_term)
                connect(cn, b_term)
        else:
            signals.append({"kind": l.kind, "from": l.from_, "to": l.to, "label": l.label})

    nodes = [{"id": k, "terminals": sorted(set(v))} for k, v in cnodes.items()]
    return {"components": components, "connectivity_nodes": nodes, "signals": signals}
