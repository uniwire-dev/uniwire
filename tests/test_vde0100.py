from uniwire import check, load


def doc(children, premises=None, **inst):
    return load({"profiles": ["vde0100"], "installation": {"system": "3P+N", "standard": "DIN VDE 0100",
                                                           **({"premises": premises} if premises else {}), **inst},
                 "sources": [{"type": "grid", "children": [{"type": "spd", "spd_type": "2"}, *children]}]})


def found(d, rule):
    return [f for f in check(d) if f.rule == rule]


def rcd(children, rtype="A", idn=30):
    return {"type": "rcd", "in_A": 40, "idn_mA": idn, "rcd_type": rtype, "children": children}


def mcb(load, in_a=16, **kw):
    return {"type": "breaker", "in_A": in_a, "curve": "B", **kw, "children": [load]}


def test_sockets_need_30ma_in_all_premises():
    bare = doc([mcb({"type": "socket", "id": "S"})], premises="commercial")
    assert [f.node for f in found(bare, "vde0100.rcd-30mA")] == ["S"]
    assert not found(doc([rcd([mcb({"type": "socket"})])], premises="commercial"), "vde0100.rcd-30mA")
    assert not found(doc([mcb({"type": "socket"}, in_a=63)], premises="industrial"), "vde0100.rcd-30mA")


def test_lighting_needs_30ma_in_dwellings_only():
    assert found(doc([mcb({"type": "lighting", "id": "L"})], premises="dwelling"), "vde0100.rcd-30mA")
    assert not found(doc([mcb({"type": "lighting"})], premises="office"), "vde0100.rcd-30mA")


def test_bathroom_circuits_need_30ma():
    heater = {"type": "heating", "id": "H", "room": "Badezimmer", "p_kW": 2}
    assert [f.node for f in found(doc([mcb(heater)]), "vde0100.bathroom")] == ["H"]
    assert not found(doc([rcd([mcb(heater)])]), "vde0100.bathroom")
    assert not found(doc([mcb({"type": "heating", "room": "Wohnzimmer"})]), "vde0100.bathroom")
    boiler = {"type": "water_heater", "room": "Bad", "p_kW": 21}  # fixed water heater: exempt
    assert not found(doc([mcb(boiler, in_a=32, poles="3P")]), "vde0100.bathroom")


def test_charging_point_own_circuit_own_rcd_and_rcd_type():
    ev = {"type": "ev_charger", "id": "EV", "mode": "3", "p_kW": 11}
    shared = doc([rcd([mcb(ev, in_a=20, poles="4P"), mcb({"type": "socket"})], rtype="A")])
    assert found(shared, "vde0100.ev-circuit")  # its RCD also protects the sockets
    ok_b = doc([rcd([mcb(ev, in_a=20, poles="4P")], rtype="B")])
    assert not found(ok_b, "vde0100.ev-circuit") and not found(ok_b, "vde0100.ev-rcd")
    type_a = found(doc([rcd([mcb(ev, in_a=20, poles="4P")], rtype="A")]), "vde0100.ev-rcd")
    assert [f.level for f in type_a] == ["info"] and "RDC-DD" in type_a[0].message
    type_ac = found(doc([rcd([mcb(ev, in_a=20, poles="4P")], rtype="AC")]), "vde0100.ev-rcd")
    assert [f.level for f in type_ac] == ["error"]
    two = doc([mcb({"type": "load", "children": []}, in_a=32) | {"children": [ev, {"type": "ev_charger"}]}])
    assert found(two, "vde0100.ev-circuit")


def test_surge_protection_and_pen_section():
    no_spd = load({"profiles": ["vde0100"], "sources": [{"type": "grid", "children": [mcb({"type": "load"})]}]})
    assert [f.level for f in found(no_spd, "vde0100.spd")] == ["warning"]
    assert not found(doc([]), "vde0100.spd")
    pen = {"type": "board", "id": "UV", "cable": {"conductors": "L1, L2, L3, PEN", "section_mm2": 6, "material": "Cu"},
           "children": []}
    assert [f.node for f in found(doc([pen]), "vde0100.pen-section")] == ["UV"]
    pen16 = {**pen, "cable": {**pen["cable"], "section_mm2": 16}}
    assert not found(doc([pen16]), "vde0100.pen-section")


def test_vde_documents_without_profile_are_pointed_to_it():
    d = load({"installation": {"standard": "DIN VDE 0100"}, "sources": [{"type": "grid"}]})
    msg = next(f.message for f in check(d) if f.rule == "core.no-profile")
    assert "'vde0100' (Germany)" in msg
