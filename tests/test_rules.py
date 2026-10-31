from uniwire import check, load


def doc(children, system="1P+N", premises=None):
    inst = {"system": system, **({"premises": premises} if premises else {})}
    return load({"profiles": ["nfc15100"], "installation": inst,
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



def test_battery_as_the_only_source_feeds_the_installation():
    d = load({"installation": {"system": "DC", "un_V": 24}, "sources": [
        {"type": "battery", "un_V": 24, "children": [{"type": "fuse", "in_A": 10, "children": [{"type": "load"}]}]}]})
    assert "core.terminal-node" not in rules_of(check(d))
    d = load({"sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 32, "children": [
        {"type": "battery", "children": [{"type": "load"}]}]}]}]})
    assert "core.terminal-node" in rules_of(check(d))  # below a device, it still feeds nothing



def test_profile_without_any_cable_size_says_cables_were_not_checked():
    feeders = [{"type": "breaker", "in_A": 32, "children": [{"type": "load"}]}]
    d = load({"profiles": ["iec60364"], "sources": [{"type": "grid", "children": feeders}]})
    assert "core.no-cables" in rules_of(check(d))
    feeders[0]["cable"] = {"cores": "3G", "section_mm2": 6}
    d = load({"profiles": ["iec60364"], "sources": [{"type": "grid", "children": feeders}]})
    assert "core.no-cables" not in rules_of(check(d))
    d = load({"sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 32}]}]})
    assert "core.no-cables" not in rules_of(check(d))  # no profile: core.no-profile says it already


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


def test_rcd_type_washing_machine_and_rcd_count():
    d = doc([{"type": "rcd", "idn_mA": 30, "rcd_type": "AC", "children": [
        {"type": "breaker", "in_A": 20, "children": [{"type": "appliance", "kind": "washing_machine"}]}]}])
    r = rules_of(check(d))
    assert {"nfc15100.rcd-type-A", "nfc15100.rcd-count"} <= r
    # the dryer is not among the uses that need a type A RCD (table 10-1G rule 2)
    d = doc([{"type": "rcd", "idn_mA": 30, "rcd_type": "AC", "children": [
        {"type": "breaker", "in_A": 20, "children": [{"type": "appliance", "kind": "dryer"}]}]}])
    assert "nfc15100.rcd-type-A" not in rules_of(check(d))


# --- profil iec60364 ------------------------------------------------------------------------

def iz_doc(cable, in_A, poles="1P+N"):
    return load({"profiles": ["iec60364"], "installation": {"system": "1P+N"},
                 "sources": [{"type": "grid", "children": [
                     {"type": "breaker", "in_A": in_A, "poles": poles, "cable": cable,
                      "children": [{"type": "load"}]}]}]})


def test_iz_rule():
    from uniwire.rules.iec60364 import lookup_iz
    cable = {"section_mm2": 2.5, "material": "Cu", "insulation": "PVC", "install": "B1"}
    assert 23 < lookup_iz("Cu", "PVC", "B1", 2, 2.5) < 24  # at 30 °C; 20.6 A at 40 °C, without ambient_C
    assert not [f for f in check(iz_doc(cable, 20)) if f.rule == "iec60364.iz"]
    fs = [f for f in check(iz_doc(cable, 25)) if f.rule == "iec60364.iz"]
    assert len(fs) == 1 and fs[0].level == "warning" and "IEC 60364-5-52" in fs[0].source
    # three-phase: 3 loaded conductors, lower Iz (B1, 3x PVC, 2.5 mm² at 40 °C: 18 A)
    fs = [f for f in check(iz_doc(cable, 20, "3P+N")) if f.rule == "iec60364.iz"]
    assert fs and "18" in fs[0].message
    # PR = XLPE; cables in parallel
    big = {"section_mm2": 95, "material": "Cu", "insulation": "PR", "install": "E", "parallel": 2}
    assert not [f for f in check(iz_doc(big, 500, "4P")) if f.level != "info" and f.rule == "iec60364.iz"]
    # incomplete: the rule does not apply; unknown installation method: info
    assert not [f for f in check(iz_doc({"section_mm2": 2.5}, 63)) if f.rule == "iec60364.iz"]
    odd = dict(cable, install="Z9")
    assert {f.level for f in check(iz_doc(odd, 20)) if f.rule == "iec60364.iz"} == {"info"}


def test_iz_formulas_keep_the_order_of_the_tables():
    """Larger sections carry more, aluminium less than copper, XLPE more than PVC, 3 loaded conductors less than 2,
    a cable in the air on a wall more than one in conduit in an insulating wall; combinations the tables do not give
    (single-core cables in free air below 25 mm²) have no value."""
    from uniwire.rules.iec60364 import lookup_iz
    sections = (1.5, 2.5, 4, 6, 10, 16, 20, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300)
    for m in ("A1", "A2", "B1", "B2", "C", "D1", "D2", "E"):
        for ins in ("PVC", "XLPE"):
            for n in (2, 3):
                cu = [lookup_iz("Cu", ins, m, n, s) for s in sections]
                assert all(a < b for a, b in zip(cu, cu[1:])), (m, ins, n)
                assert lookup_iz("Al", ins, m, n, 50) < lookup_iz("Cu", ins, m, n, 50)
                assert lookup_iz("Cu", "XLPE", m, n, 50) > lookup_iz("Cu", "PVC", m, n, 50)
            assert lookup_iz("Cu", ins, m, 3, 10) < lookup_iz("Cu", ins, m, 2, 10)
    assert lookup_iz("Cu", "PVC", "A1", 2, 10) < lookup_iz("Cu", "PVC", "C", 2, 10)
    assert lookup_iz("Cu", "PVC", "F", 2, 1.5) is None and lookup_iz("Cu", "PVC", "F", 2, 25) is not None
    assert lookup_iz("Cu", "PVC", "C", 2, 400) is None


def test_iz_temperature_factor_follows_the_heating_of_the_conductor():
    from uniwire.rules.iec60364 import temperature_factor as k
    assert k("PVC", 30, False) == 1 and k("XLPE", 20, True) == 1
    assert round(k("PVC", 40, False), 2) == 0.87 and round(k("XLPE", 40, False), 2) == 0.91
    assert k("PVC", 0, False) == k("PVC", 10, False)  # colder than the tables: taken as 10 °C
    assert k("PVC", 61, False) is None and k("XLPE", 80, False) is not None


def test_iz_reads_the_ambient_temperature_and_the_iec_names_d1_d2():
    cable = {"section_mm2": 2.5, "material": "Cu", "insulation": "PVC", "install": "B1"}  # 23.8 A at 30 °C

    def iz_findings(c, in_A=23):
        return [f for f in check(iz_doc(c, in_A)) if f.rule == "iec60364.iz"]
    fs = iz_findings(cable)  # no ambient_C: 40 °C, and the message says so
    assert len(fs) == 1 and fs[0].level == "warning" and "ambient_C" in fs[0].message
    assert not iz_findings(dict(cable, ambient_C=30))
    fs = iz_findings(dict(cable, ambient_C=35))  # 22.3 A at 35 °C
    assert len(fs) == 1 and fs[0].level == "warning" and "35 °C" in fs[0].message and "ambient_C" not in fs[0].message
    fs = iz_findings(dict(cable, ambient_C=65))  # hotter than the tables: not checked, and said
    assert [f.level for f in fs] == ["info"] and "65" in fs[0].message
    duct = iz_findings(dict(cable, install="D-duct"), 32)
    assert [f.message for f in iz_findings(dict(cable, install="D1"), 32)] == [f.message for f in duct]
    assert duct and "20 °C" in duct[0].message  # in the ground: 20 °C without ambient_C
    assert not [f for f in iz_findings(dict(cable, install="D2"), 32) if "not covered" in f.message]


def test_iz_grouping_soil_and_harmonic_factors():
    """Formulas never above the factors of IEC 60364-5-52: fewer circuits, wider spacing, a cooler soil or fewer
    harmonics never lower Iz; beyond their range, Iz is not checked and said."""
    from uniwire.model import Cable
    from uniwire.rules.iec60364 import grouping_factor, harmonic_factor, soil_factor

    def g(method="C", **kw):
        return grouping_factor(Cable(**kw), method)
    assert g() == g(grouped=1) == 1 and g(grouped=1, arrangement="ceiling") < 1
    for arr in ("bunched", "single_layer", "ceiling", "perforated_tray", "ladder"):
        f = [g(grouped=n, arrangement=arr) for n in range(1, 21)]
        assert all(a >= b for a, b in zip(f, f[1:])) and 0.3 < f[-1] < 1, arr
    assert g(grouped=4, arrangement="bunched") < g(grouped=4, arrangement="ladder")
    assert g(grouped=21) is None
    stacked = [g(grouped=4, arrangement="ladder", supports=s) for s in (1, 2, 3)]
    assert stacked[0] > stacked[1] > stacked[2] and g(grouped=4, arrangement="ladder", supports=4) is None
    for m in ("D1", "D2"):
        by_spacing = [g(m, grouped=4, spacing_m=d) for d in (0, 0.125, 0.25, 0.5, 1)]
        assert all(a <= b for a, b in zip(by_spacing, by_spacing[1:])) and by_spacing[0] < 0.8, m
        assert g(m, grouped=7) is None
    assert g("D1", grouped=3, cores="3x(1x95)") < g("D1", grouped=3, cores="4G")  # single cores, one duct each

    def s(m, rho):
        return soil_factor(Cable(soil_resistivity_K_m_W=rho), m)
    for m in ("D1", "D2"):
        f = [s(m, r) for r in (0.5, 0.7, 1, 1.5, 2, 2.5, 3)]
        assert all(a > b for a, b in zip(f, f[1:])) and f[5] == 1, m
        assert s(m, 0.2) == s(m, 0.5) and s(m, 3.5) is None
    assert s("D2", 1) > s("D1", 1) > 1 and s("C", 1) == 1  # in the air, no effect

    def h(pct, neutral=True, **kw):
        return harmonic_factor(Cable(third_harmonic_pct=pct, section_mm2=50, **kw), neutral)
    assert h(0) == h(30, neutral=False) == 1 and h(30) == 0.85 and h(50) == 0.7 and h(55) is None
    assert h(15, neutral_section_mm2=25) < h(15) and h(20, neutral_section_mm2=25) is None

    cable = {"section_mm2": 6, "material": "Cu", "insulation": "PVC", "install": "C", "ambient_C": 30}  # 41 A

    def iz_findings(c, in_A=32, poles="1P+N"):
        return [f for f in check(iz_doc(c, in_A, poles)) if f.rule == "iec60364.iz"]
    assert not iz_findings(cable)
    fs = iz_findings(dict(cable, grouped=4))  # bunched: 0.64
    assert [f.level for f in fs] == ["warning"] and "×0.64" in fs[0].message
    assert not iz_findings(dict(cable, grouped=4, arrangement="single_layer"), 25)
    assert [f.level for f in iz_findings(dict(cable, grouped=30))] == ["info"]
    assert not iz_findings(cable, 40, "3P+N")  # 3 loaded conductors: 41 A
    fs = iz_findings(dict(cable, third_harmonic_pct=40), 40, "3P+N")  # x0.78
    assert [f.level for f in fs] == ["warning"] and "40 %" in fs[0].message
    assert not iz_findings(dict(cable, third_harmonic_pct=40), 40, "3P")  # no neutral: no harmonic current in it


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


def test_nfc15100_premises():
    """Outside dwellings: only the general NF C 15-100 rules; the residential cable table is a warning."""
    children = [
        {"type": "breaker", "in_A": 20, "children": [{"type": "socket", "points": 4}]},  # no 30 mA: all premises
        {"type": "breaker", "in_A": 16, "children": [{"type": "lighting", "points": 12}]},  # 7-771 only
        {"type": "rcd", "idn_mA": 30, "rcd_type": "AC", "children": [
            {"type": "breaker", "in_A": 25, "cable": {"section_mm2": 2.5},
             "children": [{"type": "appliance", "kind": "washing_machine"}, {"type": "lighting"}]}]}]
    home = check(doc(children))
    shop = check(doc(children, premises="commercial"))
    assert {"nfc15100.rcd-30mA", "nfc15100.points", "nfc15100.rcd-type-A", "nfc15100.dedicated-circuit",
            "nfc15100.section"} <= rules_of(home)
    assert rules_of(shop) & {"nfc15100.points", "nfc15100.rcd-type-A", "nfc15100.dedicated-circuit",
                             "nfc15100.rcd-count", "nfc15100.heating", "nfc15100.rcd-circuits"} == set()
    assert any(f.rule == "nfc15100.rcd-30mA" for f in shop)  # socket-outlets: 30 mA in all premises
    section = [f for f in shop if f.rule == "nfc15100.section"]
    assert len(section) == 1 and section[0].level == "warning" and "5-52" in section[0].message
    assert [f.level for f in home if f.rule == "nfc15100.section"] == ["error"]


def test_check_scope_premises():
    from uniwire.llm import tools

    base = {"profiles": ["nfc15100"], "sources": [{"type": "grid", "children": []}]}
    assert "part 7-771) were applied (installation.premises not set" in tools.check(base)["scope"]
    shop = tools.check({**base, "installation": {"premises": "commercial"}})["scope"]
    assert "premises 'commercial': only the general rules" in shop and "ERP" in shop
    assert "7-771" not in tools.check({**base, "profiles": ["iec60364"]})["scope"]


# --- nfc15100: part 10-1 (amendment A5) ----------------------------------------------------------
def _rcd(children, rtype="A", in_a=40, **kw):
    return {"type": "rcd", "idn_mA": 30, "rcd_type": rtype, "in_A": in_a, **kw, "children": children}


def _circuit(in_a, load, section=None, poles="1P+N", **kw):
    b = {"type": "breaker", "in_A": in_a, "poles": poles, **kw, "children": [load]}
    if section:
        b["cable"] = {"section_mm2": section}
    return b


def test_30ma_and_rcd_count_in_three_phase_dwellings():
    d = doc([_circuit(16, {"type": "lighting", "points": 2}, 1.5)], system="3P+N")
    r = rules_of(check(d))
    assert "nfc15100.rcd-30mA" in r  # no longer single-phase only
    d = doc([_rcd([_circuit(16, {"type": "lighting", "points": 2}, 1.5)])], system="3P+N")
    assert {f.level for f in check(d) if f.rule == "nfc15100.rcd-count"} == {"error"}


def test_points_added_up_per_circuit():
    d = doc([_rcd([{"type": "breaker", "in_A": 16, "poles": "1P+N", "cable": {"section_mm2": 1.5}, "children": [
        {"type": "lighting", "points": 5}, {"type": "lighting", "points": 4}]}]),
        _rcd([_circuit(16, {"type": "lighting", "points": 1}, 1.5)], rtype="AC")])
    assert "nfc15100.points" in rules_of(check(d))  # 9 points on one circuit


def test_circuits_per_rcd_counted_through_a_comb():
    comb = {"type": "busbar", "children": [_circuit(16, {"type": "lighting", "points": 1}, 1.5) for _ in range(9)]}
    d = doc([_rcd([comb]), _rcd([], rtype="AC")])
    assert "nfc15100.rcd-circuits" in rules_of(check(d))


def test_dedicated_circuit_sections_and_ratings():
    d = doc([_rcd([_circuit(20, {"type": "appliance", "kind": "washing_machine"}, 1.5),
                   _circuit(40, {"type": "cooking", "kind": "hob"}, 10)]), _rcd([], rtype="AC")])
    msgs = [f for f in check(d) if f.rule == "nfc15100.circuit-section"]
    assert len(msgs) == 2  # 1.5 mm² washing machine, 40 A hob
    d = doc([_rcd([_circuit(20, {"type": "cooking", "kind": "hob"}, 2.5, poles="3P+N")]), _rcd([], rtype="AC")],
            system="3P+N")
    assert "nfc15100.circuit-section" not in rules_of(check(d))  # three-phase cooking: 2.5 mm², 20 A


def test_lighting_and_sockets_spread_over_two_rcds():
    one = doc([_rcd([_circuit(16, {"type": "lighting", "points": 2}, 1.5),
                     _circuit(16, {"type": "lighting", "points": 2}, 1.5)]), _rcd([], rtype="AC")])
    assert "nfc15100.rcd-spread" in rules_of(check(one))
    two = doc([_rcd([_circuit(16, {"type": "lighting", "points": 2}, 1.5)]),
               _rcd([_circuit(16, {"type": "lighting", "points": 2}, 1.5)], rtype="AC")])
    assert "nfc15100.rcd-spread" not in rules_of(check(two))


def test_rcd_rating_from_its_circuits():
    heavy = [_circuit(32, {"type": "heating", "p_kW": 5}, 6), _circuit(32, {"type": "heating", "p_kW": 5}, 6)]
    d = doc([_rcd(heavy, in_a=40), _rcd([], rtype="AC")])
    assert {f.level for f in check(d) if f.rule == "nfc15100.rcd-rating"} == {"warning"}  # 64 A > 40 A


def test_spd_at_the_origin_not_behind_30ma():
    d = doc([_rcd([{"type": "spd"}, _circuit(16, {"type": "lighting", "points": 2}, 1.5)]), _rcd([], rtype="AC")])
    assert "nfc15100.spd-rcd" in rules_of(check(d))


def test_service_breaker_rcd_and_selectivity():
    agcp = {"type": "main_breaker", "in_A": 45, "idn_mA": 650, "idn_range_mA": "30-1000", "children": [
        _rcd([_circuit(16, {"type": "lighting", "points": 2}, 1.5)]), _rcd([], rtype="AC")]}
    fs = check(doc([agcp]))
    assert "nfc15100.agcp-rcd" in rules_of(fs)
    assert {f.level for f in fs if f.rule == "nfc15100.selectivity"} == {"error"}  # dwelling: error


def test_earth_resistance_in_tt():
    def d(r):
        return load({"profiles": ["nfc15100"], "installation": {"earthing": "TT", "earth_resistance_ohm": r},
                     "sources": [{"type": "grid", "children": [{"type": "main_breaker", "in_A": 45, "idn_mA": 500,
                                                                "selective": True}]}]})
    assert "nfc15100.earth-resistance" in rules_of(check(d(150)))  # 150 Ω × 0.5 A = 75 V
    assert "nfc15100.earth-resistance" not in rules_of(check(d(80)))


def test_neutral_pole_and_supply_section():
    d = doc([{"type": "main_breaker", "in_A": 60, "idn_mA": 500, "selective": True, "children": [
        {"type": "board", "cable": {"section_mm2": 10}, "children": [
            _rcd([_circuit(16, {"type": "lighting", "points": 2}, 1.5, poles="1P")]), _rcd([], rtype="AC")]}]}])
    r = rules_of(check(d))
    assert {"nfc15100.neutral-pole", "nfc15100.supply-section"} <= r  # 60 A needs 16 mm²


def test_control_scope():
    def d(*children):
        return load({"sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 2, "children": [
            {"type": "power_supply", "u2_V": 24, "children": list(children)}]}]}]})

    coil = {"type": "contactor", "ref": "-KA1"}  # a relay coil fed by the 24 V supply, switching nothing
    lamp = {"type": "load", "ref": "-HL1", "label": "fault"}
    stop = {"type": "load", "label": "Emergency stop"}
    for c in (coil, lamp, stop):
        fs = [f for f in check(d(c)) if f.rule == "core.scope"]
        assert len(fs) == 1 and fs[0].level == "info"
    assert len([f for f in check(d(coil, lamp, stop)) if f.rule == "core.scope"]) == 1  # said once
    # power devices are not control: a contactor switching a load, a load shedding link, a DC load
    shed = load({"sources": [{"type": "grid", "children": [
        {"type": "controller", "id": "PDL", "function": "load shedder"},
        {"type": "contactor", "id": "KM1", "ref": "-KM1", "children": [{"type": "water_heater"}]}]}],
        "links": [{"kind": "control", "from": "PDL", "to": "KM1"}]})
    assert "core.scope" not in rules_of(check(shed))
    assert "core.scope" not in rules_of(check(d({"type": "contactor", "children": [{"type": "load"}]},
                                                {"type": "load", "ref": "-E1", "label": "router"})))


def test_main_breaker_symbol_follows_rcd():
    from uniwire.symbols import symbol_for

    def texts(**kw):
        node = load({"sources": [{"type": "grid", "children": [{"type": "main_breaker", "id": "Q0", **kw}]}]})
        return [i.text for i in symbol_for(node.sources[0].children[0]).items if hasattr(i, "text")]

    assert "IΔ" in texts(idn_mA=500)
    assert "IΔ" not in texts(in_A=45)  # no sensitivity: a plain circuit breaker


def test_no_profile_said_so():
    base = {"sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 16, "children": [{"type": "load"}]}]}]}
    f = [x for x in check(load(base)) if x.rule == "core.no-profile"]
    assert len(f) == 1 and f[0].level == "info" and "'iec60364'" in f[0].message
    us = [x for x in check(load({**base, "installation": {"standard": "NEC 2023"}})) if x.rule == "core.no-profile"]
    assert "no rule profile covers NEC 2023" in us[0].message and "'iec60364'" not in us[0].message
    assert "core.no-profile" not in rules_of(check(load({**base, "profiles": ["iec60364"]})))


def test_iz_estimated_when_the_cable_is_incomplete():
    # section only: copper, PVC, the most favourable method in air at 30 °C (1.5 mm², 2 loaded: 21.8 A)
    fs = [f for f in check(iz_doc({"section_mm2": 1.5}, 25)) if f.rule == "iec60364.iz-estimate"]
    assert [f.level for f in fs] == ["warning", "info"] and "21.8" in fs[0].message
    fs = [f for f in check(iz_doc({"section_mm2": 1.5}, 16)) if f.rule == "iec60364.iz-estimate"]
    assert [f.level for f in fs] == ["info"]  # within the estimate: still said to be estimated only
    # a stated method is used (A1, PVC, 2 loaded: 14.3 A)
    fs = [f for f in check(iz_doc({"section_mm2": 1.5, "install": "A1"}, 16)) if f.level == "warning"]
    assert [f.rule for f in fs] == ["iec60364.iz-estimate"] and "14.3" in fs[0].message
    # a complete cable is checked exactly, not estimated
    full = {"section_mm2": 2.5, "material": "Cu", "insulation": "PVC", "install": "B1"}
    assert not [f for f in check(iz_doc(full, 20)) if f.rule == "iec60364.iz-estimate"]


def test_iz_not_judged_across_an_inverter():
    # the AC breaker feeds the inverter; the strings behind it are DC cables it does not protect
    doc = load({"profiles": ["iec60364"], "installation": {"system": "1P+N"},
                "sources": [{"type": "grid", "children": [
                    {"type": "breaker", "in_A": 50, "children": [
                        {"type": "inverter", "cable": {"section_mm2": 10}, "children": [
                            {"type": "pv_array", "id": "S1", "cable": {"section_mm2": 4}},
                            {"type": "pv_array", "id": "S2", "cable": {"section_mm2": 4}}]}]}]}]})
    fs = [f for f in check(doc) if f.rule == "iec60364.iz-estimate"]
    assert [f.level for f in fs] == ["info"] and "S1" not in fs[0].message


def test_iec60364_sockets_need_30ma():
    def d(children, premises="commercial", profiles=("iec60364",)):
        return load({"profiles": list(profiles), "installation": {"premises": premises},
                     "sources": [{"type": "grid", "children": children}]})

    def mcb(load, in_a=16):
        return {"type": "breaker", "in_A": in_a, "children": [load]}

    rcd = {"type": "rcd", "idn_mA": 30, "in_A": 40, "children": [mcb({"type": "socket"})]}
    assert [f.node for f in check(d([mcb({"type": "socket", "id": "S"})])) if f.rule == "iec60364.rcd-30mA"] == ["S"]
    assert not [f for f in check(d([rcd])) if f.rule == "iec60364.rcd-30mA"]
    assert not [f for f in check(d([mcb({"type": "socket"}, 63)])) if f.rule == "iec60364.rcd-30mA"]
    # luminaires: dwellings only
    assert [f for f in check(d([mcb({"type": "lighting"})], "dwelling")) if f.rule == "iec60364.rcd-30mA"]
    assert not [f for f in check(d([mcb({"type": "lighting"})])) if f.rule == "iec60364.rcd-30mA"]
    # with a national profile, left to it (no duplicate)
    both = d([mcb({"type": "socket"})], profiles=("vde0100", "iec60364"))
    assert [f.rule for f in check(both) if f.rule.endswith("rcd-30mA")] == ["vde0100.rcd-30mA"]
