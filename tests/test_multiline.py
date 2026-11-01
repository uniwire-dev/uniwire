"""Multi-line power diagram (``views[].kind = "multi-line"``)."""

import re
import xml.etree.ElementTree as ET

import pytest

from tests.conftest import ROOT
from uniwire import load, render_pages, render_svg
from uniwire.layout.multiline import conductors
from uniwire.render import default_view
from uniwire.render.scene import Group, Text, bbox
from uniwire.render.svg import page_to_svg

EXAMPLES = sorted((ROOT / "examples").glob("*.uniwire.json"))

SMALL = {
    "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
    "sources": [{"type": "grid", "children": [{"type": "board", "id": "TD", "ref": "TD", "children": [
        {"type": "switch_disconnector", "id": "QS", "ref": "-Q0", "poles": "4P", "in_A": 63, "children": [
            {"type": "breaker", "id": "QM", "ref": "-Q1", "poles": "3P+N", "in_A": 16, "children": [
                {"type": "motor", "id": "M1", "label": "Pump", "phases": 3, "p_kW": 4}]},
            {"type": "breaker", "id": "QP", "ref": "-Q2", "poles": "1P+N", "in_A": 16, "phase": "L2",
             "cable": {"cores": "3G", "section_mm2": 2.5}, "children": [
                {"type": "socket", "id": "S1", "label": "Sockets"}]},
            {"type": "rcd", "id": "RCD", "ref": "-F1", "poles": "4P", "in_A": 40, "idn_mA": 30, "children": [
                {"type": "breaker", "id": "QL", "ref": "-Q3", "poles": "1P", "in_A": 10, "phase": "L3", "children": [
                    {"type": "lighting", "id": "L1", "label": "Lights"}]},
                {"type": "breaker", "id": "QC", "ref": "-Q4", "poles": "3P", "in_A": 20,
                 "cable": {"cores": "5G", "section_mm2": 4}, "children": [
                    {"type": "cooking", "id": "C1", "label": "Cooker"}]}]}]}]}]}],
    "views": [{"id": "sld"}, {"id": "ml", "kind": "multi-line"}],
}


def _groups(item, out=None):
    out = [] if out is None else out
    if isinstance(item, Group):
        out.append(item)
        for i in item.items:
            _groups(i, out)
    return out


def _texts(item):
    if isinstance(item, Text):
        return [item.text]
    if isinstance(item, Group):
        return [t for i in item.items for t in _texts(i)]
    return []


def _poles(page, node_id):
    sym = next(g for g in _groups(page.root) if g.id == node_id and (g.cls or "").startswith("ml-sym"))
    poles = [g for g in _groups(sym) if g.cls and g.cls.split()[0] == "pole"]
    return len(poles), sum(1 for g in poles if "pole-n" in g.cls)


def test_conductors_derived_from_the_tree():
    c = conductors(load(SMALL))
    assert c["QS"].inp == ["L1", "L2", "L3", "N", "PE"]
    assert c["QP"].inp == ["L2", "N", "PE"]  # single-phase feeder tapped on its 'phase'
    assert c["S1"].inp == ["L2", "N", "PE"]
    assert c["M1"].inp == ["L1", "L2", "L3", "PE"]  # three-phase motor: no neutral
    assert c["QL"].inp == ["L3", "N", "PE"]  # 1P: the neutral goes straight through
    assert c["QC"].inp == ["L1", "L2", "L3", "N", "PE"]  # 3P + '5G' cable: uncut neutral


def test_cable_cores_and_earthing():
    doc = load({"installation": {"earthing": "TN-C-S", "system": "3P+N"}, "sources": [{"type": "grid", "children": [
        {"type": "board", "id": "B", "children": [
            {"type": "breaker", "id": "A", "poles": "3P", "cable": {"cores": "4G"}, "children": [{"type": "load", "id": "LA"}]},
            {"type": "breaker", "id": "C", "poles": "1P", "cable": {"cores": "3G"}, "children": [{"type": "load", "id": "LC"}]}]}]}]})
    c = conductors(doc)
    assert c[doc.sources[0].id].out == ["L1", "L2", "L3", "PEN"]
    assert c["B"].inp == ["L1", "L2", "L3", "N", "PE"] and c["B"].src["PE"] == "PEN"  # PEN split at the first board
    assert c["A"].inp == ["L1", "L2", "L3", "PE"]
    assert c["C"].inp == ["L1", "N", "PE"]  # no phase given: L1
    tt = load({"installation": {"earthing": "TT", "system": "1P+N"}, "sources": [{"type": "grid", "id": "G", "children": [
        {"type": "board", "id": "B", "children": [{"type": "socket", "id": "S"}, {"type": "lighting", "id": "L"}]}]}]})
    c = conductors(tt)
    assert c["G"].out == ["L1", "N"] and c["B"].src["PE"] is None  # TT: PE from the board's earth electrode


def _tt_incomer(earthing="TT", own_sheet=False):
    board = {"type": "board", "id": "B", "children": [{"type": "socket", "id": "S"}, {"type": "lighting", "id": "L"}]}
    if own_sheet:
        board["own_sheet"] = True
    return load({"installation": {"earthing": earthing, "system": "3P+N"}, "sources": [{"type": "grid", "id": "G", "children": [
        {"type": "main_breaker", "id": "Q0", "poles": "4P", "idn_mA": 500, "cable": {"cores": "5G", "section_mm2": 16, "pe_section_mm2": 16},
         "children": [board]}]}]})


@pytest.mark.parametrize("earthing", ["TT", "IT"])
def test_pe_starts_at_the_first_board(earthing):
    # a 5G cable upstream of the first board does not bring the PE from the supply
    c = conductors(_tt_incomer(earthing))
    assert "PE" not in c["Q0"].inp and "PE" not in c["Q0"].out
    assert "PE" in c["B"].inp and c["B"].src["PE"] is None


def test_pe_of_a_board_on_its_own_sheet():
    doc = _tt_incomer(own_sheet=True)
    pages = render_pages(doc, default_view(doc, kind="multi-line"))
    assert len(pages) == 2
    first, board = (page_to_svg(p) for p in pages)
    assert 'data-uw-cond="PE"' not in first  # the incomer sheet carries the live conductors only
    assert 'data-uw-cond="PE"' in board


def test_render_multiline_small(tmp_path):
    doc = load(SMALL)
    view = default_view(doc, "ml")
    assert view.kind == "multi-line"
    pages = render_pages(doc, view)
    assert len(pages) == 1
    page = pages[0]
    assert _poles(page, "QS") == (4, 0)  # 4P: four identical poles
    assert _poles(page, "QM") == (4, 1)  # 3P+N: three protected poles + unprotected neutral
    assert _poles(page, "QP") == (2, 1)  # 1P+N
    assert _poles(page, "QL") == (1, 0)  # 1P
    assert _poles(page, "RCD") == (4, 0)
    texts = _texts(page.root)
    for name in ("L1", "L2", "L3", "N", "PE", "U", "V", "W", "Multi-line power diagram"):
        assert name in texts, name
    paths = render_svg(doc, tmp_path, "ml", view=view)
    root = ET.parse(paths[0]).getroot()
    assert root.tag.endswith("svg")
    assert 'class="pole pole-n"' in paths[0].read_text("utf-8")


def test_french_title_and_cli_kind(tmp_path):
    from uniwire.cli import main

    d = dict(SMALL, meta={"lang": "fr"}, views=[])
    doc = load(d)
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    assert "Schéma multifilaire de puissance" in _texts(page.root)
    src = tmp_path / "small.uniwire.json"
    import json

    src.write_text(json.dumps(SMALL), "utf-8")
    assert main(["render", str(src), "-o", str(tmp_path / "out"), "--kind", "multi-line"]) == 0
    assert (tmp_path / "out" / "small-multiline.svg").exists()
    assert main(["render", str(src), "-o", str(tmp_path / "out2"), "--view", "ml"]) == 0
    assert (tmp_path / "out2" / "small-multiline.svg").exists()


def test_show_pe_false():
    doc = load(SMALL)
    view = default_view(doc, "ml").model_copy(update={"show_pe": False})
    page = render_pages(doc, view)[0]
    assert "PE" not in _texts(page.root)


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name.split(".")[0] for p in EXAMPLES])
def test_every_example_renders_in_multiline(path):
    doc = load(path)
    pages = render_pages(doc, default_view(doc, kind="multi-line"))
    assert pages
    for page in pages:
        b = bbox(page.root)
        assert b is not None
        assert b[0] >= -0.01 and b[1] >= -0.01 and b[2] <= page.width + 0.01 and b[3] <= page.height + 0.01
        svg = page_to_svg(page)
        ET.fromstring(svg.encode("utf-8"))
        scale = re.search(r">(?:scale|échelle) ([\d.,]+)<", svg)
        assert scale is None or float(scale[1].replace(",", ".")) >= 0.5


def test_auxiliary_devices_and_signal_links():
    """Devices beside the tree and the control / data links, routed as in the single-line diagram; a PLC
    drawn with its modules, its links leaving from the module they use."""
    doc = load({**SMALL,
                "sources": [{**SMALL["sources"][0], "children": [{**SMALL["sources"][0]["children"][0], "children": [
                    *SMALL["sources"][0]["children"][0]["children"],
                    {"type": "breaker", "id": "QA", "ref": "-Q9", "poles": "1P+N", "in_A": 2, "children": [
                        {"type": "plc", "id": "PLC", "ref": "-A1", "family": "S7-1200",
                         "modules": [{"slot": 1, "kind": "do"}]}]}]}]}],
                "devices": [{"type": "controller", "id": "RLY", "ref": "-K9", "label": "Pump relay"}],
                "links": [{"kind": "control", "from": "PLC", "from_port": "1.0", "to": "QM"},
                          {"kind": "data", "from": "PLC", "to": "RLY", "protocol": "Modbus"}]})
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    groups = _groups(page.root)
    kinds = {g.attrs.get("data-uw-kind") for g in groups if "uw-link" in (g.cls or "")}
    assert {"control", "data"} <= kinds
    assert any(g.id == "RLY" for g in groups)  # the auxiliary device is drawn
    texts = _texts(page.root)
    assert "1.0" in texts and "DO" in texts  # port label, module of the PLC
    from tests.drawing_audit import audit

    assert audit(page.root) == []


def test_earthing_conductors_of_special_nodes():
    doc = load({
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
        "sources": [{"type": "grid", "children": [{"type": "board", "id": "TD", "children": [
            {"type": "earth_bar", "id": "MET", "ref": "-PE", "kind": "equipotential"},
            {"type": "breaker", "id": "Q5", "poles": "1P+N", "in_A": 10, "children": [
                {"type": "transformer", "id": "T5", "kind": "isolation", "sn_kVA": 0.1, "u1_V": 230, "u2_V": 12,
                 "children": [{"type": "lighting", "id": "L5", "un_V": 12}]}]}]}]}],
        "views": [{"id": "ml", "kind": "multi-line"}],
    })
    info = conductors(doc)
    assert info["MET"].inp == ["PE"]  # an equipotential bar is on the protective conductor only
    assert info["T5"].inp == ["L1", "N", "PE"]
    assert info["T5"].out == ["L1", "N"]  # single-phase safety extra-low voltage: two conductors, not earthed
    render_pages(doc, doc.views[0])


def test_transfer_link_feeds_neutral_from_a_pen():
    doc = load(json_example("27_standby_generator_ats_load_shedding"))
    page = render_pages(doc, type(doc.views[0])(id="ml", kind="multi-line"))[0]
    link = next(g for g in _groups(page.root) if "ml-link-transfer" in (g.cls or ""))
    conds = {g.attrs.get("data-uw-cond") for g in _groups(link)} - {None}
    assert {"L1", "L2", "L3", "N"} <= conds  # the genset's PEN feeds the neutral of the 4-pole ATS


def test_plc_protocols_cut_on_whole_names():
    from uniwire.labels import _protocols
    assert _protocols(["EtherNet/IP", "Modbus TCP", "CANopen"]) == "EtherNet/IP, Modbus TCP …"
    assert _protocols(["PROFINET", "Modbus TCP"]) == "PROFINET, Modbus TCP"


def json_example(name):
    import json
    return json.loads((ROOT / "examples" / f"{name}.uniwire.json").read_text(encoding="utf-8"))


def test_split_phase_two_pole_and_pen_split_at_tn_s_board():
    info = conductors(load(json_example("39_hybrid_inverter_backup_us")))
    assert info["MB"].inp == ["L1", "L2", "N", "PE"]  # a 2P main breaker on L1 and L2, the neutral through
    info = conductors(load(json_example("33_workshop_metering_cts")))
    assert info["SDB"].inp == ["L1", "L2", "L3", "N", "PE"]  # TN-S board of a TN-C installation: PEN split
    assert "PEN" not in info["Q51"].inp


def test_single_phase_drive_feeds_a_three_phase_motor():
    doc = load({"installation": {"earthing": "TN-S", "system": "1P+N"}, "sources": [{"type": "grid", "children": [
        {"type": "breaker", "id": "F1", "poles": "1P+N", "cable": {"cores": "3G", "section_mm2": 2.5}, "children": [
            {"type": "motor_starter", "id": "T1", "method": "vfd", "children": [
                {"type": "motor", "id": "M1", "phases": 3}]}]}]}]})
    info = conductors(doc)
    assert info["T1"].inp == ["L1", "N", "PE"] and info["T1"].out == ["L1", "L2", "L3", "PE"]
    assert info["M1"].inp == ["L1", "L2", "L3", "PE"]
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    texts = _texts(page.root)
    assert texts.count("3G2.5") == 1  # beside its breaker only: the cable feeds the drive, not the motor behind it


def test_dc_motor_and_transformer_pe():
    page = render_pages(load(json_example("11_tiny_house_off_grid_pv")), default_view(
        load(json_example("11_tiny_house_off_grid_pv")), kind="multi-line"))[0]
    pump = next(g for g in _groups(page.root) if "ml-motor" in (g.cls or ""))
    assert "=" in _texts(pump) and "1~" not in _texts(pump)
    doc = load(json_example("30_station_traitement_eau_it"))
    pages = render_pages(doc, default_view(doc, kind="multi-line"))
    tr = next(g for p in pages for g in _groups(p.root) if g.id == "T2")
    pe = next(g for g in _groups(tr) if (g.attrs or {}).get("data-uw-cond") == "PE")
    circles = [i for i in tr.items if type(i).__name__ == "Circle" and i.r > 2]
    edge = max(c.c[0] + c.r for c in circles)
    xs = [x for i in pe.items for x, _ in i.points[2:]]
    assert min(xs) > edge  # the PE jogs above the windings and passes beside them, never into them


def test_annotation_does_not_repeat_what_the_label_says():
    """A characteristic the label already gives ('25 kVA' in '25 kVA spare unit') is not written again below it."""
    doc = load({"sources": [{"type": "grid", "children": [{"type": "breaker", "children": [
        {"type": "transformer", "id": "T", "ref": "-T1", "label": "25 kVA spare unit", "sn_kVA": 25, "u1_V": 400,
         "u2_V": 230, "children": [{"type": "load", "p_kW": 2}]}]}]}]})
    texts = [t.text for pg in render_pages(doc, default_view(doc, kind="multi-line"))
             for t in _all_texts(pg.root)]
    assert "25 kVA spare unit" in texts
    assert "25 kVA" not in texts


def _all_texts(item):
    if isinstance(item, Text):
        return [item]
    return [t for i in item.items for t in _all_texts(i)] if isinstance(item, Group) else []


BYPASS = {
    "installation": {"earthing": "TN-S", "system": "3P", "un_V": 400},
    "sources": [{"type": "grid", "children": [{"type": "board", "id": "B", "children": [
        {"type": "contactor", "id": "K1", "ref": "-K1", "poles": "3P", "in_A": 40, "children": [
            {"type": "motor_starter", "id": "U1", "ref": "-U1", "method": "soft_starter", "in_A": 38, "children": [
                {"type": "motor", "id": "M1", "phases": 3, "p_kW": 18.5}]}]}]}]}],
    "links": [{"kind": "bypass", "from": "K1", "to": "M1",
               "device": {"type": "contactor", "id": "K2", "ref": "-K2", "poles": "3P", "in_A": 40}}],
    "views": [{"id": "ml", "kind": "multi-line"}],
}


def test_link_device_drawn_without_room_on_the_lanes():
    # the bypass runs alongside its device: no horizontal room, so its contactor goes on the verticals
    root = render_pages(load(BYPASS))[0].root
    dev = [g for g in _groups(root) if g.id == "K2" and "ml-link-device" in (g.cls or "")]
    assert len(dev) == 1 and len([g for g in _groups(dev[0]) if "pole" in (g.cls or "").split()]) == 3
    link = next(g for g in _groups(root) if "ml-link-bypass" in (g.cls or ""))
    conds = {g.attrs.get("data-uw-cond") for g in _groups(link) if g.attrs and g.attrs.get("data-uw-cond")}
    assert "PE" not in conds  # a bypass parallels the live conductors only
    motor = next(g for g in _groups(root) if g.id == "M1")
    lowest = max(b[3] for g in _groups(link) if (b := bbox(g)) is not None)
    assert lowest <= bbox(motor)[1] + 0.1  # it reaches the motor's terminals, never below the motor


def test_odd_x_cores_are_a_guess_after_what_the_node_states():
    def doc(cable):
        return load({"installation": {"earthing": "TN-S", "system": "3P", "un_V": 400},
                     "sources": [{"type": "grid", "children": [{"type": "breaker", "id": "Q", "poles": "3P", "children": [
                         {"type": "motor", "id": "M", "phases": 3, "cable": cable}]}]}]})

    for cable in ({"cores": "3x", "section_mm2": 95, "pe_section_mm2": 50}, {"cores": "3x", "section_mm2": 2.5}):
        assert conductors(doc(cable))["M"].inp == ["L1", "L2", "L3", "PE"]


def test_board_frame_holds_a_link_between_its_devices():
    root = render_pages(load(BYPASS))[0].root
    frame, dev = (bbox(next(g for g in _groups(root) if g.id == i)) for i in ("B", "K2"))
    texts = next(g for g in _groups(root) if "ml-link-bypass" in (g.cls or ""))
    assert frame[0] <= min(dev[0], bbox(texts)[0])


def test_motor_without_phases_drawn_as_its_feeder():
    doc = load({"installation": {"earthing": "TT", "system": "3P+N", "un_V": 400},
                "sources": [{"type": "grid", "children": [{"type": "board", "id": "B", "children": [
                    {"type": "breaker", "id": "Q1", "poles": "1P+N", "in_A": 16, "children": [{"type": "motor", "id": "M1"}]},
                    {"type": "breaker", "id": "Q2", "poles": "3P", "in_A": 16, "children": [{"type": "motor", "id": "M2"}]}]}]}],
                "views": [{"id": "sl"}, {"id": "ml", "kind": "multi-line"}]})
    for view in doc.views:
        root = render_pages(doc, view)[0].root
        marks = {i: [t for t in _texts(next(g for g in _groups(root) if g.id == i)) if "~" in t] for i in ("M1", "M2")}
        assert marks == {"M1": ["1~"], "M2": ["3~"]}, view.id
