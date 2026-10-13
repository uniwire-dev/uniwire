from uniwire import check, load


def doc(children, system="1P+N"):
    return load({"profiles": ["nfc15100"], "installation": {"system": system},
                 "sources": [{"type": "grid", "children": children}]})


def rules_of(findings):
    return {f.rule for f in findings}


def test_section_vs_rating():
    d = doc([{"type": "rcd", "idn_mA": 30, "rcd_type": "A", "children": [
        {"type": "breaker", "in_A": 20, "cable": {"section_mm2": 1.5}, "children": [{"type": "socket", "points": 4}]}]}])
    assert "nfc15100.section" in rules_of(check(d))


def test_missing_30ma_and_type_a():
    d = doc([{"type": "breaker", "in_A": 20, "children": [{"type": "socket", "points": 4}]},
             {"type": "rcd", "idn_mA": 30, "rcd_type": "AC", "children": [
                 {"type": "breaker", "in_A": 20, "children": [{"type": "appliance", "kind": "washing_machine"}]}]}])
    r = rules_of(check(d))
    assert {"nfc15100.rcd-30mA", "nfc15100.rcd-type-A"} <= r


def test_points_and_rcd_circuit_count():
    breakers = [{"type": "breaker", "in_A": 16, "children": [{"type": "lighting", "points": 10}]} for _ in range(9)]
    d = doc([{"type": "rcd", "idn_mA": 30, "children": breakers}])
    r = rules_of(check(d))
    assert {"nfc15100.points", "nfc15100.rcd-circuits"} <= r


def test_core_rules_without_profile():
    d = load({"sources": [{"type": "grid", "children": [
        {"type": "breaker", "in_A": 16, "children": [{"type": "breaker", "in_A": 32}]},
        {"id": "TS", "type": "transfer_switch"}]}]})
    r = rules_of(check(d))
    assert {"core.rating-cascade", "core.transfer-source"} <= r


# --- sources and NF C 15-100 rules ------- ----------------------------------------------

def test_nfc15100_rules_carry_source_and_confidence():
    from uniwire.rules import RULE_INFO
    names = {"nfc15100.section", "nfc15100.points", "nfc15100.lighting-rating", "nfc15100.rcd-30mA",
             "nfc15100.rcd-type-A", "nfc15100.rcd-circuits", "nfc15100.heating", "nfc15100.selectivity",
             "iec60364.iz"}
    assert names <= set(RULE_INFO)
    for info in RULE_INFO.values():
        assert info.source and info.confidence in ("high", "medium")
    d = doc([{"type": "rcd", "idn_mA": 30, "rcd_type": "A", "children": [
        {"type": "breaker", "in_A": 20, "cable": {"section_mm2": 1.5}, "children": [{"type": "socket", "points": 4}]}]}])
    f = next(f for f in check(d) if f.rule == "nfc15100.section")
    assert "NF C 15-100" in f.source


def test_sockets_on_1_5_mm2_and_heating_power():
    d = doc([{"type": "rcd", "idn_mA": 30, "rcd_type": "A", "children": [
        {"type": "breaker", "in_A": 16, "cable": {"section_mm2": 1.5}, "children": [{"type": "socket", "points": 9}]},
        {"type": "breaker", "in_A": 20, "cable": {"section_mm2": 2.5}, "children": [
            {"type": "heating", "p_kW": 3}, {"type": "heating", "p_kW": 2}]},
        {"type": "breaker", "in_A": 32, "cable": {"section_mm2": 6}, "children": [{"type": "heating", "p_kW": 7}]}]},
        {"type": "rcd", "idn_mA": 30, "rcd_type": "AC"}])
    fs = check(d)
    assert [f.rule for f in fs if f.rule == "nfc15100.points"] == ["nfc15100.points"]
    heat = [f for f in fs if f.rule == "nfc15100.heating"]
    assert len(heat) == 1 and "5 kW" in heat[0].message


def test_dedicated_circuits_and_ev():
    d = doc([{"type": "rcd", "idn_mA": 30, "rcd_type": "A", "children": [
        {"type": "breaker", "in_A": 20, "cable": {"section_mm2": 2.5}, "children": [
            {"type": "appliance", "kind": "washing_machine"}, {"type": "socket", "points": 2}]},
        {"type": "breaker", "in_A": 20, "children": [{"type": "heating", "p_kW": 2}, {"type": "lighting", "points": 1}]}]},
        {"type": "rcd", "idn_mA": 30, "rcd_type": "A", "poles": "4P", "children": [
            {"type": "breaker", "in_A": 16, "poles": "3P+N", "children": [{"type": "ev_charger", "mode": "2"}]},
            {"type": "breaker", "in_A": 32, "children": [{"type": "ev_charger", "mode": "3"}]}]}])
    fs = check(d)
    ded = [f for f in fs if f.rule == "nfc15100.dedicated-circuit"]
    assert len(ded) == 2
    ev = {f.level for f in fs if f.rule == "nfc15100.ev-rcd"}
    assert ev == {"error", "info"}


def test_rcd_type_dryer_and_rcd_count():
    d = doc([{"type": "rcd", "idn_mA": 30, "rcd_type": "AC", "children": [
        {"type": "breaker", "in_A": 20, "children": [{"type": "appliance", "kind": "dryer"}]}]}])
    r = rules_of(check(d))
    assert {"nfc15100.rcd-type-A", "nfc15100.rcd-count"} <= r


# --- profil iec60364 ------------------------------------------------------------------------

def iz_doc(cable, in_A, poles="1P+N"):
    return load({"profiles": ["iec60364"], "installation": {"system": "1P+N"},
                 "sources": [{"type": "grid", "children": [
                     {"type": "breaker", "in_A": in_A, "poles": poles, "cable": cable,
                      "children": [{"type": "load"}]}]}]})


def test_iz_rule():
    from uniwire.rules.iec60364 import lookup_iz
    cable = {"section_mm2": 2.5, "material": "Cu", "insulation": "PVC", "install": "B1"}
    assert lookup_iz("Cu", "PVC", "B1", 2, 2.5) == 21
    assert not [f for f in check(iz_doc(cable, 20)) if f.rule == "iec60364.iz"]
    fs = [f for f in check(iz_doc(cable, 25)) if f.rule == "iec60364.iz"]
    assert len(fs) == 1 and fs[0].level == "warning" and "GUIA-BT-19" in fs[0].source
    # three-phase: 3 loaded conductors, lower Iz (B1, 3x PVC, 2.5 mm²: 18.5 A)
    fs = [f for f in check(iz_doc(cable, 20, "3P+N")) if f.rule == "iec60364.iz"]
    assert fs and "18.5" in fs[0].message
    # PR = XLPE; cables in parallel
    big = {"section_mm2": 95, "material": "Cu", "insulation": "PR", "install": "E", "parallel": 2}
    assert not [f for f in check(iz_doc(big, 500, "4P")) if f.level != "info" and f.rule == "iec60364.iz"]
    # incomplete: the rule does not apply; unknown installation method: info
    assert not [f for f in check(iz_doc({"section_mm2": 2.5}, 63)) if f.rule == "iec60364.iz"]
    odd = dict(cable, install="Z9")
    assert {f.level for f in check(iz_doc(odd, 20)) if f.rule == "iec60364.iz"} == {"info"}


def test_iz_profile_not_active_by_default():
    d = load({"sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 63, "cable": {
        "section_mm2": 1.5, "material": "Cu", "insulation": "PVC", "install": "C"}}]}]})
    assert not [f for f in check(d) if f.rule == "iec60364.iz"]


def test_rating_cascade_stops_at_voltage_converter():
    from uniwire import check, load
    doc = load({"uniwire": "1.0.0", "sources": [{"type": "grid", "children": [
        {"type": "breaker", "id": "QA", "in_A": 20, "children": [
            {"type": "power_supply", "u1_V": 230, "u2_V": 48, "output": "DC", "children": [
                {"type": "breaker", "id": "QD", "in_A": 63}]}]},
        {"type": "breaker", "id": "QB", "in_A": 20, "children": [{"type": "breaker", "id": "QC", "in_A": 32}]}]}]})
    ids = {f.node for f in check(doc) if f.rule == "core.rating-cascade"}
    assert ids == {"QC"}


def test_bom_ignores_pv_module_count():
    from uniwire import load
    from uniwire.bom import bom
    doc = load({"uniwire": "1.0.0", "sources": [{"type": "pv_array", "modules": 12,
                                                  "product": {"manufacturer": "X", "part_number": "PV-400"}}]})
    assert [r["part_number"] for r in bom(doc)] == ["PV-400"]


def test_iz_uses_nearest_protection_motor_starter_and_overload_relay():
    cable = {"section_mm2": 4, "material": "Cu", "insulation": "XLPE", "install": "C"}
    d = load({"profiles": ["iec60364"], "installation": {"system": "3P+N"},
              "sources": [{"type": "grid", "children": [
                  {"type": "breaker", "in_A": 250, "poles": "3P", "children": [
                      {"type": "motor_starter", "in_A": 32, "poles": "3P", "cable": cable,
                       "children": [{"type": "motor"}]},
                      {"type": "contactor", "children": [
                          {"type": "thermal_relay", "range_A": "28-40", "setting_A": 29,
                           "children": [{"type": "motor", "cable": cable}]}]},
                      {"type": "thermal_relay", "range_A": "28-40",
                       "children": [{"type": "motor", "cable": cable}]}]}]}]})
    fs = [f for f in check(d) if f.rule == "iec60364.iz" and f.level == "warning"]
    # starter 32 A and relay set at 29 A are within Iz; a relay range up to 40 A is not
    assert len(fs) == 1 and "40" in fs[0].message


# --- key interlocks ('locks' + 'interlocks') ---------------------------------------------

def _two_bus(feeder_state="closed", link_open=True, interlocks=None, extra_link=None):
    """Feeder -QF selectable between busbars W1 / W2 by removable links (lock 'PA')."""
    links = [{"kind": "infeed", "from": "W2", "to": "QF", "normally_open": link_open,
              "device": {"type": "disconnector", "ref": "-X2", "normal_state": "open" if link_open else "closed",
                         "locks": ["PA"]}}]
    if extra_link:
        links.append(extra_link)
    return load({"sources": [
        {"type": "grid", "children": [{"id": "W1", "type": "busbar", "children": [
            {"type": "disconnector", "id": "X1", "ref": "-X1", "normal_state": feeder_state, "locks": ["PA"],
             "children": [{"id": "QF", "type": "breaker", "in_A": 63}]},
            {"type": "breaker", "in_A": 16}]}]},
        {"type": "grid", "children": [{"id": "W2", "type": "busbar", "children": [
            {"type": "breaker", "in_A": 16}, {"type": "breaker", "in_A": 16}]}]}],
        "links": links, "interlocks": interlocks or []})


def _interlock(doc):
    return [f for f in check(doc) if f.rule == "core.interlock"]


def test_interlock_removable_links_one_of_two():
    assert _interlock(_two_bus()) == []
    assert _interlock(_two_bus(interlocks=[{"key": "PA", "kind": "removable_link"}])) == []
    both = _interlock(_two_bus(link_open=False))
    assert [f.level for f in both] == ["error"] and "X1" in both[0].message
    # the link's own 'locks' and normally_open count the same way
    d = _two_bus(feeder_state="open", link_open=True,
                 extra_link={"kind": "infeed", "from": "W2", "to": "QF", "locks": ["PA"]})
    assert _interlock(d) == []


def _two_of_three(tie_state):
    return load({"sources": [
        {"type": "transformer", "children": [{"id": "QA", "type": "breaker", "locks": ["K1"], "children": [
            {"id": "WA", "type": "busbar", "children": [{"type": "load"}, {"type": "load"}]}]}]},
        {"type": "transformer", "children": [{"id": "QB", "type": "breaker", "locks": ["K1"], "children": [
            {"id": "WB", "type": "busbar", "children": [{"type": "load"}, {"type": "load"}]}]}]}],
        "links": [{"kind": "tie", "from": "WA", "to": "WB",
                   "device": {"id": "QT", "type": "breaker", "normal_state": tie_state, "locks": ["K1"]}}],
        "interlocks": [{"key": "K1", "keys": 2, "kind": "trapped_key"}]})


def test_interlock_two_of_three():
    assert _interlock(_two_of_three("open")) == []
    f = _interlock(_two_of_three("closed"))
    assert [x.level for x in f] == ["error"] and "QT" in f[0].message


def test_interlock_lone_lock_and_unused_declaration():
    d = load({"sources": [{"type": "grid", "children": [
        {"id": "Q1", "type": "breaker", "locks": ["K9"]}, {"type": "breaker"}]}],
        "interlocks": [{"key": "K7"}]})
    f = {(x.level, x.node) for x in _interlock(d)}
    assert f == {("warning", "Q1"), ("warning", None)}


def test_interlock_messages_in_french(monkeypatch):
    monkeypatch.setenv("UNIWIRE_LANG", "fr")
    f = _interlock(_two_bus(link_open=False))
    assert "verrouillage" in f[0].message
