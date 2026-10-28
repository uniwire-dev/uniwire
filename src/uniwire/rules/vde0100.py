"""``vde0100`` profile: usual checks of a German low-voltage installation (DIN VDE 0100).

DIN VDE 0100 is the German adoption of IEC 60364 (through HD 60364), with the same part numbers. This profile
checks the German requirements that go beyond the general rules; combine it with ``iec60364`` for the
current-carrying capacity of cables. Rules and references:

* **DIN VDE 0100-410:2018, 411.3.3**: additional protection by an RCD of at most 30 mA for socket-outlets up to
  32 A for use by ordinary persons, in all premises;
* **DIN VDE 0100-410:2018, 411.3.4**: the same for final circuits supplying luminaires in dwellings;
* **DIN VDE 0100-701**: every circuit of a room with a bath or a shower protected by an RCD of at most 30 mA,
  except a circuit supplying only a permanently connected water heater;
* **DIN VDE 0100-722**: each charging point of an electric vehicle supplied by its own final circuit and protected
  by its own RCD of at most 30 mA, of type B or of type A/F with 6 mA DC fault detection (RDC-DD, IEC 62955);
* **DIN VDE 0100-443 and -534**: surge protective devices, required for most buildings since 2016;
* **DIN VDE 0100-540, 543.4**: a PEN conductor only from 10 mm² copper (16 mm² aluminium).

Requirements this profile does not check: arc fault detection devices (DIN VDE 0100-420, required in some
premises only), the grid connection rules of VDE-AR-N 4100 (meter cabinet, selective main circuit breaker) and the
minimum equipment of dwellings (DIN 18015-2). These are consistency checks for common cases: they do not replace
the standard, which remains the authoritative text.
"""

from __future__ import annotations

import re

from .. import registry
from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import describe, rule
from .nfc15100 import _dwelling, _feeder_protection, _loads_below, _rcds, _socket_rating

RCD_30MA = describe(
    "vde0100.rcd-30mA",
    "DIN VDE 0100-410:2018, 411.3.3: socket-outlets up to 32 A protected by an RCD of at most 30 mA, all premises; "
    "411.3.4: final circuits of luminaires in dwellings, the same",
    "high")
BATHROOM = describe(
    "vde0100.bathroom",
    "DIN VDE 0100-701: every circuit of a room with a bath or a shower protected by an RCD of at most 30 mA, "
    "except a circuit supplying only a permanently connected water heater (the room is read from the load's room "
    "or label)",
    "medium")
EV_CIRCUIT = describe(
    "vde0100.ev-circuit",
    "DIN VDE 0100-722: each charging point supplied by its own final circuit and protected by its own RCD of at "
    "most 30 mA",
    "high")
EV_RCD = describe(
    "vde0100.ev-rcd",
    "DIN VDE 0100-722: RCD of type B, or type A / F with 6 mA DC fault detection (RDC-DD, IEC 62955) in the "
    "charging point; type AC excluded",
    "high")
SPD = describe(
    "vde0100.spd",
    "DIN VDE 0100-443:2016 and DIN VDE 0100-534:2016: surge protection required for most buildings (risk "
    "assessment otherwise)",
    "medium")
PEN = describe(
    "vde0100.pen-section",
    "DIN VDE 0100-540, 543.4: a PEN conductor only in fixed installations from 10 mm² copper or 16 mm² aluminium",
    "high")

BATH_WORDS = re.compile(r"\b(bad|badezimmer|duschbad|dusche|duschraum|bath|bathroom|shower|salle de bains?|"
                        r"salle d'eau)\b", re.I)
PEN_MIN_MM2 = {"Cu": 10.0, "Al": 16.0}


def _rcd_30(idx: Index, nid: str) -> list:
    return [a for a in _rcds(idx, nid) if a.idn_mA <= 30]  # type: ignore[attr-defined]


def _what(n) -> str:
    return n.label or registry.label(n.type)  # type: ignore[attr-defined]


@rule("vde0100")
def rcd_30ma(doc: Document, idx: Index):
    dwelling = _dwelling(doc)
    for nid, n in idx.nodes.items():
        t = n.type  # type: ignore[attr-defined]
        if t == "socket" and (_socket_rating(idx, nid) or 0) <= 32 and not _rcd_30(idx, nid):
            yield RCD_30MA.finding("error", _t("vde0100.rcd_30mA_socket", what=_what(n)), nid)
        elif t == "lighting" and dwelling and not _rcd_30(idx, nid):
            yield RCD_30MA.finding("error", _t("vde0100.rcd_30mA_lighting", what=_what(n)), nid)


@rule("vde0100")
def bathroom(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        if registry.category(n.type) != "load" or n.type in ("spare", "water_heater"):  # type: ignore[attr-defined]
            continue  # a circuit supplying only a fixed water heater is exempt
        where = " ".join(x for x in (getattr(n, "room", None), n.label) if x)
        if BATH_WORDS.search(where) and not _rcd_30(idx, nid):
            yield BATHROOM.finding("error", _t("vde0100.bathroom", what=_what(n)), nid)


@rule("vde0100")
def ev_charging(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        if n.type != "ev_charger":  # type: ignore[attr-defined]
            continue
        what = _what(n)
        p = _feeder_protection(idx, nid)
        if p is not None and any(x is not n for x in _loads_below(p)):
            yield EV_CIRCUIT.finding("error", _t("vde0100.ev_own_circuit", what=what), nid)
        hr = _rcd_30(idx, nid)
        if not hr:
            yield EV_CIRCUIT.finding("error", _t("vde0100.ev_no_rcd", what=what), nid)
            continue
        if any(x is not n for x in _loads_below(hr[0])):
            yield EV_CIRCUIT.finding("error", _t("vde0100.ev_own_rcd", what=what), nid)
        rtype = getattr(hr[0], "rcd_type", None)
        if rtype == "AC" or rtype is None:
            yield EV_RCD.finding("error", _t("vde0100.ev_rcd_type", what=what, rtype=rtype or "?"), nid)
        elif rtype in ("A", "F", "A-SI", "Hpi"):
            yield EV_RCD.finding("info", _t("vde0100.ev_rdc_dd", what=what, rtype=rtype), nid)


@rule("vde0100")
def spd(doc: Document, idx: Index):
    if not any(n.type == "spd" for n in idx.nodes.values()):  # type: ignore[attr-defined]
        yield SPD.finding("warning", _t("vde0100.spd"))


@rule("vde0100")
def pen_section(doc: Document, idx: Index):
    for nid, n in idx.nodes.items():
        c = n.cable
        if c is None or c.section_mm2 is None or "PEN" not in (c.conductors or "").upper():
            continue
        material = c.material or "Cu"
        minimum = PEN_MIN_MM2.get(material, PEN_MIN_MM2["Cu"])
        if c.section_mm2 < minimum:
            yield PEN.finding("warning", _t("vde0100.pen_section", section=c.section_mm2, material=material,
                                             minimum=minimum), nid)
