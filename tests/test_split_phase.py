"""Single-phase three-wire supplies (split-phase, 100/200 V or 120/240 V) and three-wire three-phase supplies: checks
without false findings, conductors drawn as wired."""

import uniwire
from uniwire.layout import multiline
from uniwire.render.svg import page_to_svg
from uniwire.resolve import iter_nodes

HOUSE = {
    "installation": {"earthing": "TT", "system": "split-phase", "un_V": 200, "uln_V": 100, "f_Hz": 50},
    "sources": [{"type": "grid", "children": [
        {"type": "main_breaker", "ref": "Q0", "in_A": 60, "poles": "3P", "idn_mA": 30, "children": [
            {"type": "board", "ref": "DB", "children": [
                {"type": "breaker", "ref": "Q1", "in_A": 20, "poles": "1P+N", "children": [{"type": "lighting"}]},
                {"type": "breaker", "ref": "Q2", "in_A": 20, "poles": "1P+N", "children": [{"type": "socket"}]},
                {"type": "breaker", "ref": "Q3", "in_A": 20, "poles": "2P", "children": [
                    {"type": "appliance", "label": "air conditioner", "p_kW": 2.2}]},
                {"type": "breaker", "ref": "Q4", "in_A": 30, "poles": "2P", "children": [
                    {"type": "cooking", "p_kW": 5.8, "un_V": 200}]},
                {"type": "breaker", "ref": "Q5", "in_A": 20, "poles": "2P", "children": [
                    {"type": "appliance", "label": "100 V appliance", "un_V": 100}]},
                {"type": "breaker", "ref": "Q6", "in_A": 20, "poles": "2P", "children": [
                    {"type": "breaker", "ref": "Q61", "in_A": 16, "poles": "1P+N", "children": [{"type": "socket"}]},
                    {"type": "breaker", "ref": "Q62", "in_A": 16, "poles": "2P", "children": [
                        {"type": "heating", "p_kW": 2}]}]}]}]}]}],
}

WORKSHOP = {
    "installation": {"earthing": "TT", "system": "3P", "un_V": 200, "f_Hz": 60},
    "sources": [{"type": "grid", "children": [
        {"type": "main_breaker", "ref": "Q0", "in_A": 75, "poles": "3P", "children": [
            {"type": "board", "ref": "P1", "children": [
                {"type": "rcbo", "ref": "Q1", "in_A": 30, "poles": "3P", "idn_mA": 30, "children": [
                    {"type": "contactor", "ref": "KM1", "children": [
                        {"type": "thermal_relay", "ref": "F1", "range_A": "11-15", "children": [
                            {"type": "motor", "p_kW": 3.7}]}]}]},
                {"type": "rcbo", "ref": "Q2", "in_A": 20, "poles": "2P", "idn_mA": 30, "children": [
                    {"type": "socket", "label": "200 V outlet"}]}]}]}]}],
}


def _out(doc):
    a = multiline._Assigner(doc)
    return {n.ref: a.info[id(n)].out for n, _, _ in iter_nodes(doc) if n.ref and id(n) in a.info}


def test_checks_without_false_findings():
    for d in (HOUSE, WORKSHOP):
        for profiles in ([], ["iec60364"]):
            found = [f for f in uniwire.check(uniwire.load(d | {"profiles": profiles})) if f.level != "info"]
            assert not found, found


def test_two_pole_on_split_phase_feeds_the_neutral_only_when_used():
    out = _out(uniwire.load(HOUSE))
    assert out["Q0"] == ["L1", "L2", "N"]
    assert out["Q1"] == ["L1", "N", "PE"] and out["Q2"] == ["L1", "N", "PE"]
    assert out["Q3"] == ["L1", "L2", "PE"]  # phase-to-phase appliance: no neutral to it
    assert out["Q4"] == ["L1", "L2", "PE"]  # 200 V load
    assert out["Q5"] == ["L1", "L2", "N", "PE"]  # a 100 V load below: the neutral goes with it
    assert out["Q6"] == ["L1", "L2", "N", "PE"] and out["Q62"] == ["L1", "L2", "PE"]  # a 1P+N circuit below


def test_three_wire_three_phase():
    out = _out(uniwire.load(WORKSHOP))
    assert out["Q1"] == ["L1", "L2", "L3", "PE"] and out["Q2"] == ["L1", "L2", "PE"]


def test_title_block_gives_both_voltages():
    svg = page_to_svg(uniwire.render_pages(uniwire.load(HOUSE))[0])
    assert "100/200 V" in svg
    svg = page_to_svg(uniwire.render_pages(uniwire.load(WORKSHOP))[0])
    assert "3P 200 V" in svg


def test_title_block_no_phase_to_neutral_voltage_without_neutral():
    doc = uniwire.load(WORKSHOP | {"installation": WORKSHOP["installation"] | {"uln_V": 115}})
    assert "115/200" not in page_to_svg(uniwire.render_pages(doc)[0])
