"""Terminals, terminal strips and wires (format 1.1, UEP-0001 §3.1-3.3, §3.5.2, §3.7)."""

import csv
import io

from tests.conftest import ROOT
from uniwire import check, load
from uniwire.exports import markers_csv, terminals_csv, wires_csv
from uniwire.ports import Ports, Target, node_ports

WIRING_RULES = ("port.", "wire.", "strip.")


def _starter(wires=None, strips=None, **contactor):
    """A motor starter fed from a board, a PLC beside it: the test bench of the wiring rules."""
    return load({
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
        "sources": [{"type": "grid", "id": "G", "children": [{"type": "board", "id": "MCC", "ref": "MCC", "children": [
            {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 10, "poles": "3P", "children": [
                {"type": "contactor", "id": "KM1", "ref": "-KM1", "in_A": 9, "poles": "3P", "coil_V": 24,
                 "contacts": ["NO", "NC"], **contactor, "children": [
                     {"type": "thermal_relay", "id": "F1", "ref": "-F1", "range_A": "6-10", "children": [
                         {"type": "motor", "id": "M1", "ref": "-M1", "p_kW": 4,
                          "cable": {"cores": "4G", "section_mm2": 2.5}}]}]}]}]}]}],
        "devices": [{"type": "plc", "id": "A1", "ref": "-A1", "onboard": [
            {"slot": 0, "kind": "di", "channels": 8}, {"slot": 0, "kind": "do", "channels": 4}],
            "modules": [{"slot": 1, "kind": "do", "channels": 2}]}],
        "terminal_strips": strips if strips is not None else [{"id": "X1", "ref": "-X1", "enclosure": "MCC", "terminals": [
            {"no": "1"}, {"no": "2"}, {"no": "3"}, {"no": "PE", "kind": "earth"}, {"no": "10", "label": "Command"},
            {"no": "11", "section_max_mm2": 1.5}]}],
        "wires": wires or []})


def _ids(doc, node_id):
    idx = Ports(doc).index
    return [p.id for p in node_ports(doc, idx.nodes[node_id])]


def test_default_terminals_follow_the_usual_markings():
    doc = _starter()
    assert _ids(doc, "Q1") == ["1", "2", "3", "4", "5", "6"]
    assert _ids(doc, "KM1") == ["1", "2", "3", "4", "5", "6", "A1", "A2", "13", "14", "21", "22"]
    assert _ids(doc, "F1")[-4:] == ["95", "96", "97", "98"]
    assert _ids(doc, "M1") == ["U1", "V1", "W1", "PE"]
    # the built-in modules of a PLC are all slot 0: their channels follow one another
    plc = _ids(doc, "A1")
    assert plc[:3] == ["L+", "M", "PE"] and "0.8" in plc and "0.12" in plc and "0.13" not in plc
    assert plc[-2:] == ["1.1", "1.2"]
    ports = Ports(doc)
    assert ports.resolve("KM1#L1").port == "1" and ports.resolve("KM1#T3").port == "6"  # aliases
    assert ports.resolve("M1#U").display == "-M1:U1"
    assert ports.resolve("X1#PE").strip


def test_terminals_declared_on_the_node_add_to_or_replace_the_defaults():
    doc = _starter(ports=[{"id": "A1", "label": "24 V coil"}, {"id": "X5", "function": "other"}])
    km1 = {p.id: p for p in node_ports(doc, Ports(doc).index.nodes["KM1"])}
    assert km1["A1"].label == "24 V coil" and "X5" in km1 and "A2" in km1
    only = _starter(ports=[{"id": "A1"}, {"id": "A2"}], port_defaults=False)
    assert _ids(only, "KM1") == ["A1", "A2"]


def test_references_designate_explicit_ids_and_known_terminals():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 16}]}]})
    ports = Ports(doc)
    generated = next(iter(ports.index.nodes))
    assert ports.resolve(f"{generated}#1").startswith("wiring.generated_id")  # not stable
    doc = _starter()
    ports = Ports(doc)
    assert ports.resolve("Z9#1").startswith("wiring.no_owner")
    missing = Ports(doc).resolve("Q1#7")
    assert missing.startswith("wiring.no_port") and "known=1, 2, 3, 4, 5, 6" in missing
    assert isinstance(ports.resolve("X1#10"), Target)


def test_a_document_without_wires_gets_no_wiring_finding():
    for f in sorted((ROOT / "examples").glob("*.json"))[:20]:
        assert not [x for x in check(load(f)) if x.rule.startswith(WIRING_RULES)], f.name


def test_wiring_rules():
    doc = _starter(wires=[
        {"id": "w1", "from": "A1#0.9", "to": "X1#10", "mark": "101"},
        {"id": "w2", "from": "X1#10", "to": "KM1#A1", "mark": "101"},
        {"id": "w3", "from": "X1#10", "to": "F1#95"},  # a third conductor on X1:10
        {"id": "w4", "from": "KM1#13", "to": "A1#0.1", "color": "GNYE"},  # green-and-yellow on a control wire
        {"id": "w5", "from": "KM1#14", "to": "KM1#14"},
        {"id": "w6", "from": "Q1#7", "to": "X1#1"},
        {"id": "w7", "from": "X1#PE", "to": "M1#U1", "conductor": "PE"},  # PE on a phase terminal
        {"id": "w8", "from": "X1#11", "to": "A1#0.2", "section_mm2": 2.5}])  # too big for the terminal
    found = {(f.rule, f.node) for f in check(doc) if f.rule.startswith(WIRING_RULES)}
    assert found == {("port.capacity", "X1"), ("port.unconnected", "KM1"), ("port.conductor", "w4"),
                     ("wire.endpoints", "w5"), ("port.unknown", "w6"), ("port.conductor", "w7"),
                     ("strip.capacity", "w8")}
    wired = _starter(wires=[{"from": "X1#10", "to": "KM1#A1"}, {"from": "KM1#A2", "to": "X1#11"}])
    assert not [f for f in check(wired) if f.rule.startswith(WIRING_RULES)]


def test_terminal_strip_rules():
    doc = _starter(strips=[{"id": "X1", "enclosure": "NOWHERE", "terminals": [
        {"no": "1", "bridge_group": "B1"}, {"no": "1"}, {"no": "2"}]}])
    found = sorted((f.rule, f.level) for f in check(doc) if f.rule.startswith("strip."))
    assert found == [("strip.bridge", "warning"), ("strip.terminal", "error"), ("strip.terminal", "error")]


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_exports_list_the_declared_wires_and_the_terminal_plan():
    doc = _starter(wires=[
        {"id": "w1", "from": "KM1#2", "to": "X1#1", "conductor": "L1", "section_mm2": 2.5, "mark": "U"},
        {"id": "w2", "from": "X1#1", "to": "M1#U1", "conductor": "L1", "wiring": "site", "mark": "U"},
        {"id": "w3", "from": "A1#0.9", "to": "X1#10", "mark": "101", "section_mm2": 0.75, "color": "BU"}])
    wires = {r["wire_id"]: r for r in _rows(wires_csv(doc))}
    assert wires["w2"]["from_display"] == "-X1:1" and wires["w2"]["to_display"] == "-M1:U1"
    assert wires["w2"]["wiring"] == "site" and wires["w1"]["from_enclosure"] == "MCC"
    assert wires["w2"]["to_enclosure"] == ""  # the motor is in the field, not in the board above it
    plan = {r["terminal"]: r for r in _rows(terminals_csv(doc))}
    assert plan["1"]["inside_targets"] == "-KM1:2" and plan["1"]["outside_targets"] == "-M1:U1"
    assert plan["10"]["inside_targets"] == "-A1:0.9" and plan["10"]["mark"] == "101"
    assert plan["2"]["inside_targets"] == "" and list(plan) == ["1", "2", "3", "PE", "10", "11"]
    assert terminals_csv(doc, strip="-X9").count("\n") == 1  # an unknown strip: the header only
    markers = [r for r in _rows(markers_csv(doc)) if r["mark"] == "101"]
    assert {r["terminal_display"] for r in markers} == {"-A1:0.9", "-X1:10"}


def test_terminal_plan_sheets_go_on_over_the_next_sheet():
    from uniwire import render_pages
    from uniwire.model import View
    from uniwire.render.scene import Group, Text

    strips = [{"id": "X1", "ref": "-X1", "enclosure": "MCC", "terminals": [{"no": str(k)} for k in range(1, 81)]},
              {"id": "X2", "ref": "-X2", "terminals": [{"no": "1", "bridge_group": "B"}, {"no": "2", "bridge_group": "B"}]}]
    doc = _starter(strips=strips, wires=[{"from": "KM1#A1", "to": "X1#1"}, {"from": "KM1#A2", "to": "X1#2"}])
    doc.meta.lang = "fr"
    pages = render_pages(doc, View(kind="terminals", paper="A3"))

    def walk(item):
        if isinstance(item, Group):
            yield item
            for i in item.items:
                yield from walk(i)
    terminals = [g.attrs["data-uw-terminal"] for p in pages for g in walk(p.root) if "data-uw-terminal" in g.attrs]
    assert len(pages) >= 2 and len(terminals) == 82 and len(set(terminals)) == 82  # every terminal once
    texts = [t.text for p in pages[1:] for g in walk(p.root) for t in g.items if isinstance(t, Text)]
    assert any("(suite)" in t for t in texts) and "Borne" in texts  # the title and header repeated, in French
    assert render_pages(load({"sources": [{"type": "grid"}]}), View(kind="terminals")) == []  # no strip, no sheet


def test_terminal_plan_follows_the_cad_terminal_diagram_form():
    from uniwire import render_pages
    from uniwire.render import default_view
    from uniwire.render.scene import Group, Text

    doc = load(ROOT / "examples" / "54_motor_starter_terminals_wires.uniwire.json")
    (page,) = render_pages(doc, default_view(doc, kind="terminals"))

    def texts(item):
        if isinstance(item, Group):
            for i in item.items:
                yield from texts(i)
        elif isinstance(item, Text):
            yield item.text
    found = list(texts(page.root))
    assert "W11" in found and "4G2.5 35 m" in found  # the cable at the head of its column: name, then type
    assert {"BN", "BK", "GY", "GNYE"} <= set(found)  # its cores on the lines of the terminals
    assert "-M1 *" in found and "U1" in found  # the target and its terminal in two columns, as on the CAD form
    assert any(t.startswith("* ") for t in found)  # site wiring starred, and the note
    assert "UT 4-PE" in found  # the part of each terminal
    assert "8 terminals: 7 feed-through (UT 4), 1 earth (UT 4-PE)" in found  # what to order, under the table


def test_bridges_side_by_side_only_where_they_overlap():
    from uniwire import render_pages
    from uniwire.model import View
    from uniwire.render.scene import Circle, Group

    def xs(groups):
        doc = _starter(strips=[{"id": "X1", "terminals": [
            {"no": str(k), "bridge_group": g} for k, g in enumerate(groups, 1)]}],
            wires=[{"from": "KM1#A1", "to": "X1#1"}, {"from": "KM1#A2", "to": "X1#2"}])

        def walk(item):
            if isinstance(item, Group):
                for i in item.items:
                    yield from walk(i)
            elif isinstance(item, Circle):
                yield round(item.c[0], 3)
        return {x for p in render_pages(doc, View(kind="terminals")) for x in walk(p.root)}
    assert len(xs(["A", "A", "B", "B"])) == 1  # one after the other: on one line
    assert len(xs(["A", "B", "A", "B"])) == 2  # interleaved: side by side


def test_strip_terminals_drawn_on_the_conductors_they_cross_in_the_multi_line_view():
    from uniwire import render_pages
    from uniwire.render import default_view
    from uniwire.render.scene import Group

    doc = load(ROOT / "examples" / "54_motor_starter_terminals_wires.uniwire.json")
    (page,) = render_pages(doc, default_view(doc, kind="multi-line"))

    def walk(item):
        if isinstance(item, Group):
            yield item
            for i in item.items:
                yield from walk(i)
    drawn = {g.attrs["data-uw-cond"]: g.attrs["data-uw-terminal"] for g in walk(page.root)
             if "data-uw-terminal" in g.attrs}
    assert drawn == {"L1": "-X1:1", "L2": "-X1:2", "L3": "-X1:3", "PE": "-X1:PE"}  # the motor cable leaves through -X1
    # a strip terminal joined to the node only, not to the cabinet side, is not on its feeder
    lone = _starter(wires=[{"from": "X1#1", "to": "M1#U1"}])
    from uniwire.layout.multiline import _Assigner, strip_terminals
    assert strip_terminals(lone, Ports(lone).index, _Assigner(lone, True).info) == {}
