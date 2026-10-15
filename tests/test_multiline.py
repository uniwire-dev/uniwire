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
