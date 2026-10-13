"""PLC rules (core profile, 1.3): consistency of modules and addressed channels."""

from __future__ import annotations

from collections import Counter

from ..i18n import t as _t
from ..labels import part_number
from ..model import Document
from ..resolve import Index
from . import Finding, rule

OUTPUT_KINDS = {"do", "relay_out", "ao", "mixed_io", "motor"}


def _modules(plc) -> dict[int, object]:
    mods = {0: None}
    for m in list(plc.onboard) + list(plc.modules):
        mods[m.slot] = m
    return mods


def _parse_port(port: str) -> tuple[int, int | None] | None:
    try:
        parts = str(port).split(".")
        return int(parts[0]), (int(parts[1]) if len(parts) > 1 and parts[1] else None)
    except ValueError:
        return None


@rule("core")
def plc_modules(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        if n.type != "plc":  # type: ignore[attr-defined]
            continue
        slots = [m.slot for m in n.modules]  # type: ignore[attr-defined]
        dup = [s for s, c in Counter(slots).items() if c > 1]
        if dup:
            yield Finding("error", "plc.slots", _t("plc.duplicate_slots", slots=dup), nid)
        if slots != sorted(slots):
            yield Finding("warning", "plc.slots", _t("plc.unsorted_slots"), nid)
        manu = ((n.product.manufacturer if n.product else None) or n.manufacturer or "").lower()
        pns = [m.part_number or (m.product.part_number if m.product else "") or "" for m in n.modules]  # type: ignore[attr-defined]
        if ("wago" in manu or any(p.startswith("750-") or p.startswith("753-") for p in pns)) and n.modules:  # type: ignore[attr-defined]
            if n.modules[-1].kind != "end":  # type: ignore[attr-defined]
                yield Finding("warning", "plc.wago-end", _t("plc.wago_end"), nid)
            if not any(m.kind in ("power_feed", "power_supply") for m in n.modules) and n.role != "coupler":  # type: ignore[attr-defined]
                yield Finding("info", "plc.wago-feed", _t("plc.wago_feed"), nid)


@rule("core")
def plc_ports(doc: Document, idx: Index):
    used: Counter = Counter()
    for l in doc.links:
        for end, port in ((l.from_, l.from_port), (l.to, l.to_port)):
            if port is None:
                continue
            node = idx.nodes.get(end)
            if node is None or node.type != "plc":  # type: ignore[attr-defined]
                continue
            parsed = _parse_port(port)
            if parsed is None:
                yield Finding("error", "plc.port", _t("plc.port_unreadable", port=port), end)
                continue
            slot, ch = parsed
            mods = _modules(node)
            if slot not in mods:
                yield Finding("error", "plc.port", _t("plc.port_missing_slot", port=port, slot=slot), end)
                continue
            m = mods[slot]
            if m is not None and ch is not None and m.channels is not None and ch > m.channels:
                yield Finding("error", "plc.port", _t("plc.port_channels", port=port, module=part_number(m) or m.kind,
                                 channels=m.channels), end)
            if end == l.from_ and l.kind == "control":
                used[(end, port)] += 1
                target = idx.nodes.get(l.to)
                coil = getattr(target, "coil_V", None)
                if m is not None and m.kind == "do" and m.un_V and coil and coil > 2 * m.un_V:
                    yield Finding("warning", "plc.coil", _t("plc.coil", port=port, un_v=m.un_V, coil=coil), l.to)
    for (nid, port), c in used.items():
        if c > 1:
            yield Finding("warning", "plc.port-shared", _t("plc.port_shared", port=port, count=c), nid)
