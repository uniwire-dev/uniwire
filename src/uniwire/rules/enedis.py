"""``enedis`` profile: connection of a low-voltage installation to the French public network operated by Enedis.

The connection (service cable, meter, service main breaker or AGCP) is governed by NF C 14-100 and the Enedis
technical reference, not by NF C 15-100, which starts downstream of the AGCP: this profile is separate from
``nfc15100`` and can be combined with it. References:

* **Enedis-NMO-RAC_001E** (version 2, 2025-03-24), technical reference for low-voltage connections: power tiers
  of limited-power connections (§3.1.1) and of monitored-power connections (§3.1.2), injection limits of
  production installations (§3.2.1), connection power carried by the AGCP setting (§4.1);
* **SéQuélec fiche n°2** (service main breaker): NF C 14-100 recommends a 500 mA residual-current service
  breaker in new and renovated-as-new buildings;
* **Consuel, decoupling protections of PV inverters** (2025): certificate of the protection built into the
  inverter, NF EN 50549-1 (or -2) and NF EN 50549-10.

The profile only applies to installations supplied in low voltage by a public grid (no transformer, no
medium-voltage supply). It checks the data of the document; Enedis decides on each connection.
"""

from __future__ import annotations

from ..i18n import t as _t
from ..model import Document
from ..resolve import Index
from . import describe, rule

RAC = "Enedis-NMO-RAC_001E v2 (2025-03-24)"

CONNECTION = describe(
    "enedis.connection",
    f"{RAC} §3.1.1: limited-power connections of 3 to 12 kVA in single-phase (6 to 12 kVA in dwellings) and of 6 "
    "to 36 kVA in three-phase; §3.1.2: monitored power from 37 to 250 kVA, above that a medium-voltage connection",
    "high")
AGCP_SETTING = describe(
    "enedis.agcp-setting",
    f"{RAC} §4.1: the connection power is carried by the AGCP setting (60 A: 12 kVA single-phase, 36 kVA "
    "three-phase); the subscribed power, followed by the meter, cannot exceed it",
    "high")
AGCP_RCD = describe(
    "enedis.agcp-rcd",
    "SéQuélec fiche n°2 (service main breaker): NF C 14-100 recommends a 500 mA residual-current service main "
    "breaker in new and renovated-as-new buildings",
    "medium")
PRODUCTION = describe(
    "enedis.production",
    f"{RAC} §3.2.1: single-phase production, injection up to 6 kVA and installed power up to 18 kVA; "
    "three-phase, installed power up to 250 kVA",
    "high")
DECOUPLING = describe(
    "enedis.decoupling",
    "Consuel, decoupling protections of PV inverters (2025): the protection built into the inverter is certified "
    "to NF EN 50549-1 (or -2), with NF EN 50549-10 for installations up to 36 kVA from 2026-01-01",
    "medium")

LIMITED_MAX_KVA = {"1P+N": 12.0, "3P+N": 36.0, "3P": 36.0}
DWELLING_MIN_KVA = 6.0
MONITORED_MAX_KVA = 250.0
AGCP_MAX_A = 60.0
# connection power carried by one ampere of AGCP setting (60 A: 12 kVA single-phase, 36 kVA three-phase)
KVA_PER_A = {"1P+N": 0.2, "3P+N": 0.6, "3P": 0.6}
SINGLE_PHASE_INJECTION_KVA = 6.0
SINGLE_PHASE_INSTALLED_KVA = 18.0
PV_INVERTERS = (None, "string", "central", "micro", "hybrid")  # battery inverters and chargers are not counted


def _public_lv(doc: Document, idx: Index) -> bool:
    """Supplied in low voltage by a public grid: a grid source, no transformer, no medium voltage."""
    if not any(s.type == "grid" for s in doc.sources):  # type: ignore[attr-defined]
        return False
    if any(n.type == "transformer" for n in idx.nodes.values()):  # type: ignore[attr-defined]
        return False
    un = doc.installation.un_V
    return un is None or un <= 1000


def _main_breakers(idx: Index) -> list:
    """Service main breakers (AGCP): main_breaker nodes upstream of every board."""
    return [n for nid, n in idx.nodes.items() if n.type == "main_breaker"  # type: ignore[attr-defined]
            and not any(a.type == "board" for a in idx.ancestors(nid))]  # type: ignore[attr-defined]


def _limited(doc: Document) -> bool:
    kva, system = doc.installation.subscribed_kVA, doc.installation.system
    return kva is None or kva <= LIMITED_MAX_KVA.get(system or "3P+N", 36.0)


@rule("enedis")
def connection_tier(doc: Document, idx: Index):
    if not _public_lv(doc, idx):
        return
    kva, system = doc.installation.subscribed_kVA, doc.installation.system
    if kva is None:
        return
    if system == "1P+N" and kva > LIMITED_MAX_KVA["1P+N"]:
        yield CONNECTION.finding("error", _t("enedis.single_phase_max", kva=kva))
    elif kva > MONITORED_MAX_KVA:
        yield CONNECTION.finding("warning", _t("enedis.mv", kva=kva))
    elif kva > LIMITED_MAX_KVA["3P+N"]:
        yield CONNECTION.finding("info", _t("enedis.monitored", kva=kva))
    if doc.installation.premises in (None, "dwelling") and kva < DWELLING_MIN_KVA:
        yield CONNECTION.finding("warning", _t("enedis.dwelling_min", kva=kva))


@rule("enedis")
def agcp_setting(doc: Document, idx: Index):
    if not _public_lv(doc, idx) or not _limited(doc):
        return  # monitored power: no AGCP setting tiers
    system = doc.installation.system or "3P+N"
    per_a = KVA_PER_A.get(system)
    kva = doc.installation.subscribed_kVA
    for q in _main_breakers(idx):
        in_a = getattr(q, "in_A", None)
        if in_a is None:
            continue
        if in_a > AGCP_MAX_A:
            yield AGCP_SETTING.finding("error", _t("enedis.agcp_max", in_a=in_a), q.id)
        elif per_a and kva and in_a * per_a < kva - 1e-6:
            yield AGCP_SETTING.finding("error", _t("enedis.agcp_low", in_a=in_a, pr=round(in_a * per_a, 1), kva=kva),
                                       q.id)


@rule("enedis")
def agcp_rcd(doc: Document, idx: Index):
    if not _public_lv(doc, idx) or not _limited(doc):
        return
    for q in _main_breakers(idx):
        idn = getattr(q, "idn_mA", None)
        if idn is None:
            yield AGCP_RCD.finding("info", _t("enedis.agcp_no_rcd"), q.id)
        elif idn != 500:
            yield AGCP_RCD.finding("info", _t("enedis.agcp_rcd_value", idn=idn), q.id)


def _pv_inverters(idx: Index) -> list:
    return [n for n in idx.nodes.values() if n.type == "inverter"  # type: ignore[attr-defined]
            and getattr(n, "kind", None) in PV_INVERTERS]


@rule("enedis")
def production(doc: Document, idx: Index):
    if not _public_lv(doc, idx):
        return
    invs = [n for n in _pv_inverters(idx) if getattr(n, "p_kVA", None)]
    if not invs:
        return
    installed = round(sum(n.p_kVA * (n.count or 1) for n in invs), 2)  # type: ignore[attr-defined]
    if doc.installation.system == "1P+N":
        if installed > SINGLE_PHASE_INSTALLED_KVA:
            yield PRODUCTION.finding("error", _t("enedis.prod_installed_1p", kva=installed))
        elif installed > SINGLE_PHASE_INJECTION_KVA:
            yield PRODUCTION.finding("warning", _t("enedis.prod_injection_1p", kva=installed))
    elif installed > MONITORED_MAX_KVA:
        yield PRODUCTION.finding("error", _t("enedis.prod_installed_3p", kva=installed))


@rule("enedis")
def decoupling(doc: Document, idx: Index):
    if not _public_lv(doc, idx):
        return
    for n in _pv_inverters(idx):
        if not getattr(n, "protection", None):
            yield DECOUPLING.finding("info", _t("enedis.decoupling", what=n.ref or n.label or n.id), n.id)
