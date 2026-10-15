"""``enedis`` profile: connection of a low-voltage installation to the French public network."""

import pytest

from uniwire import check, load


def _doc(system="1P+N", kva=9, agcp=None, inverters=(), premises=None, transformer=False):
    q0 = {"type": "main_breaker", "id": "Q0", "children": [{"type": "board", "id": "TD", "children": [
        {"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]}]}]}
    q0.update(agcp or {})
    for i, (kind, p) in enumerate(inverters):
        q0["children"][0]["children"].append({"type": "breaker", "in_A": 32, "children": [
            {"type": "inverter", "id": f"G{i}", "kind": kind, "p_kVA": p}]})
    top = {"type": "transformer", "children": [q0]} if transformer else q0
    inst = {"earthing": "TT", "system": system, "subscribed_kVA": kva}
    if premises:
        inst["premises"] = premises
    return load({"installation": inst, "profiles": ["enedis"], "sources": [{"type": "grid", "children": [top]}]})


def _rules(doc, level=None):
    return sorted(f.rule for f in check(doc) if f.rule.startswith("enedis") and (level is None or f.level == level))


def test_clean_single_phase_connection():
    assert _rules(_doc(agcp={"in_A": 45, "idn_mA": 500, "selective": True})) == []


def test_connection_tiers():
    assert _rules(_doc(kva=18), "error") == ["enedis.connection"]  # single-phase limited power: 12 kVA at most
    assert _rules(_doc(system="3P+N", kva=60), "info") == ["enedis.connection"]  # monitored power
    assert _rules(_doc(system="3P+N", kva=300), "warning") == ["enedis.connection"]  # medium voltage
    assert _rules(_doc(kva=3), "warning") == ["enedis.connection"]  # dwellings start at 6 kVA
    assert _rules(_doc(kva=3, premises="commercial"), "warning") == []


@pytest.mark.parametrize(("system", "kva", "in_a", "error"), [
    ("1P+N", 9, 45, False), ("1P+N", 9, 30, True),  # 30 A carries 6 kVA < 9 kVA
    ("3P+N", 24, 40, False), ("3P+N", 24, 60, False),  # Linky: AGCP at the connection power, above is normal
    ("3P+N", 24, 30, True), ("3P+N", 36, 63, True),  # 63 A: above the 60 A of limited power
])
def test_agcp_setting(system, kva, in_a, error):
    doc = _doc(system=system, kva=kva, agcp={"in_A": in_a, "idn_mA": 500})
    assert ("enedis.agcp-setting" in _rules(doc, "error")) is error


def test_agcp_rcd():
    assert _rules(_doc(agcp={"in_A": 45}), "info") == ["enedis.agcp-rcd"]
    assert _rules(_doc(agcp={"in_A": 45, "idn_mA": 300}), "info") == ["enedis.agcp-rcd"]


def test_production_limits():
    agcp = {"in_A": 60, "idn_mA": 500}
    assert "enedis.production" in _rules(_doc(kva=12, agcp=agcp, inverters=[("string", 8.2)]), "warning")
    assert "enedis.production" in _rules(_doc(kva=12, agcp=agcp, inverters=[("micro", 10), ("micro", 10)]), "error")
    assert "enedis.production" not in _rules(_doc(kva=12, agcp=agcp, inverters=[("string", 5)]))
    # storage counts in the installed power (Enedis-NMO-RES_032E): 10 + 8.2 kVA > 18 kVA in single-phase
    assert "enedis.production" in _rules(_doc(kva=12, agcp=agcp, inverters=[("battery", 10), ("string", 8.2)]), "error")
    assert "enedis.production" not in _rules(_doc(kva=12, agcp=agcp, inverters=[("charger", 10)]))  # draws only
    assert "enedis.production" not in _rules(_doc(system="3P+N", kva=36, agcp=agcp, inverters=[("string", 30)]))


def test_decoupling_protection():
    doc = _doc(inverters=[("string", 5)])
    assert "enedis.decoupling" in _rules(doc, "info")


def test_only_for_a_low_voltage_public_supply():
    assert _rules(_doc(kva=18, transformer=True)) == []


def test_production_finding_points_at_a_single_inverter():
    doc = _doc(kva=12, agcp={"in_A": 60, "idn_mA": 500}, inverters=[("string", 8.2)])
    f = next(f for f in check(doc) if f.rule == "enedis.production")
    assert f.node == "G0" and "8.2 kVA" in f.message


def test_production_above_36_kva_three_phase():
    agcp = {"in_A": 60, "idn_mA": 500}
    assert "enedis.production" in _rules(_doc(system="3P+N", kva=36, agcp=agcp, inverters=[("string", 50)]), "info")


def _with_meter_cable(cable):
    doc = _doc(agcp={"in_A": 45, "idn_mA": 500})
    raw = doc.model_dump(exclude_none=True, by_alias=True)
    q0 = raw["sources"][0]["children"][0]
    raw["sources"][0]["children"][0] = {"type": "meter", "id": "P1", "cable": cable, "children": [q0]}
    return load(raw)


def test_service_cable():
    assert _rules(_with_meter_cable({"cores": "2x", "section_mm2": 35, "material": "Al", "length_m": 20})) == []
    assert _rules(_with_meter_cable({"section_mm2": 35, "length_m": 45}), "warning") == ["enedis.service-cable"]
    assert _rules(_with_meter_cable({"section_mm2": 16, "length_m": 10}), "warning") == ["enedis.service-cable"]
