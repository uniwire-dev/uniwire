"""Modular PLCs, channel ports, product references and bill of materials."""

import copy

from uniwire import check, load
from uniwire.bom import bom, bom_csv

BASE = {
    "sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "breaker", "in_A": 2, "children": [
            {"id": "PS", "type": "power_supply", "u1_V": 230, "u2_V": 24, "children": [
                {"id": "A1", "type": "plc", "product": {"manufacturer": "WAGO", "part_number": "750-8212"},
                 "modules": [
                     {"slot": 1, "kind": "power_feed", "part_number": "750-602"},
                     {"slot": 2, "kind": "do", "part_number": "750-530", "channels": 8, "un_V": 24},
                     {"slot": 3, "kind": "end", "part_number": "750-600"}]}]}]},
        {"type": "breaker", "in_A": 16, "children": [{"id": "KM1", "type": "contactor", "coil_V": 24}]},
        {"type": "breaker", "in_A": 16, "children": [{"id": "KM2", "type": "contactor", "coil_V": 230}]},
    ]}]}],
    "links": [],
}


# controller + remote I/O coupler, each head with a potential feed and an end module
TWO_HEADS = {
    "profiles": ["core"],
    "installation": {"system": "3P+N", "earthing": "TN-S"},
    "sources": [{"type": "grid", "children": [{"type": "board", "ref": "TD", "children": [
        {"type": "breaker", "ref": "-Q10", "in_A": 2, "poles": "1P+N", "children": [
            {"id": "PS1", "type": "power_supply", "ref": "-T1", "u1_V": 230, "u2_V": 24, "output": "DC", "children": [
                {"id": "API1", "type": "plc", "ref": "-A1", "role": "controller",
                 "product": {"manufacturer": "WAGO", "part_number": "750-8212"},
                 "modules": [
                     {"slot": 1, "kind": "power_feed", "part_number": "750-602", "un_V": 24},
                     {"slot": 2, "kind": "relay_out", "part_number": "750-512", "channels": 2, "rating_A": 2},
                     {"slot": 3, "kind": "end", "part_number": "750-600"}]}]}]},
        {"type": "breaker", "ref": "-Q21", "in_A": 16, "poles": "3P", "children": [
            {"id": "KM21", "type": "contactor", "ref": "-KM21", "coil_V": 230, "poles": "3P"}]},
        {"type": "breaker", "ref": "-Q30", "in_A": 10, "poles": "1P+N", "children": [
            {"id": "RIO1", "type": "plc", "ref": "-A2", "role": "coupler",
             "product": {"manufacturer": "WAGO", "part_number": "750-362"},
             "modules": [
                 {"slot": 1, "kind": "power_feed", "part_number": "750-602", "un_V": 24},
                 {"slot": 2, "kind": "ai", "part_number": "750-454", "channels": 2},
                 {"slot": 3, "kind": "end", "part_number": "750-600"}]}]},
    ]}]}],
    "links": [{"kind": "control", "from": "API1", "from_port": "2.1", "to": "KM21"},
              {"kind": "data", "from": "RIO1", "to": "API1", "protocol": "Modbus TCP"}],
}


def rules(doc_dict):
    return {f.rule for f in check(load(doc_dict))}


def with_links(*links, modules=None):
    d = copy.deepcopy(BASE)
    d["links"] = list(links)
    if modules is not None:
        d["sources"][0]["children"][0]["children"][0]["children"][0]["children"][0]["modules"] = modules
    return d


def test_two_heads_are_clean():
    assert not [f for f in check(load(TWO_HEADS)) if f.level in ("error", "warning")]


def test_valid_port():
    assert not {r for r in rules(with_links({"kind": "control", "from": "A1", "from_port": "2.1", "to": "KM1"}))
                if r.startswith("plc")}


def test_port_errors():
    assert "plc.port" in rules(with_links({"kind": "control", "from": "A1", "from_port": "2.9", "to": "KM1"}))
    assert "plc.port" in rules(with_links({"kind": "control", "from": "A1", "from_port": "7.1", "to": "KM1"}))
    assert "plc.port" in rules(with_links({"kind": "control", "from": "A1", "from_port": "x", "to": "KM1"}))


def test_shared_output_and_coil_voltage():
    r = rules(with_links({"kind": "control", "from": "A1", "from_port": "2.1", "to": "KM1"},
                         {"kind": "control", "from": "A1", "from_port": "2.1", "to": "KM2"}))
    assert {"plc.port-shared", "plc.coil"} <= r


def test_wago_end_module():
    mods = [{"slot": 1, "kind": "power_feed", "part_number": "750-602"},
            {"slot": 2, "kind": "do", "part_number": "750-530", "channels": 8}]
    assert "plc.wago-end" in rules(with_links(modules=mods))


def test_bom_aggregates_modules_and_products():
    rows = {r["part_number"]: r for r in bom(load(TWO_HEADS))}
    assert rows["750-600"]["quantity"] == 2  # one end module per head
    assert rows["750-602"]["refs"] == ["-A1.1", "-A2.1"]
    assert rows["750-8212"]["type"] == "plc"
    assert "Manufacturer;Part number" in bom_csv(load(TWO_HEADS))


def test_bom_csv_french(monkeypatch):
    monkeypatch.setenv("UNIWIRE_LANG", "fr")
    assert "Fabricant;Référence" in bom_csv(load(TWO_HEADS))


def test_product_accessories_and_count():
    d = {"sources": [{"type": "grid", "children": [
        {"type": "breaker", "ref": "-Q1", "count": 3,
         "product": {"manufacturer": "Schneider Electric", "part_number": "REF-DISJ",
                     "accessories": [{"part_number": "REF-MX", "description": "MX shunt trip"}]}}]}]}
    rows = {r["part_number"]: r for r in bom(load(d))}
    assert rows["REF-DISJ"]["quantity"] == 3 and rows["REF-MX"]["quantity"] == 3
