"""SVG structure contract (docs/api.md, "SVG structure"), colour modes and PDF navigation."""

import re
import xml.etree.ElementTree as ET

import pytest

from tests.conftest import ROOT
from uniwire import load, render_pages, render_pdf
from uniwire.render import default_view
from uniwire.render.colors import CONDUCTOR_PRESETS, PE_STRIPE, PHASE_COLORS, SOURCE_COLORS, STATUS_COLORS
from uniwire.render.svg import page_to_svg
from uniwire.resolve import build_index

NS = "{http://www.w3.org/2000/svg}"
EX = ROOT / "examples"


def _example(prefix):
    return load(next(EX.glob(f"{prefix}_*.uniwire.json")))


def _svgs(doc, kind=None, **update):
    view = default_view(doc, kind=kind)
    if update:
        view = view.model_copy(update=update)
    return [ET.fromstring(page_to_svg(p).split("?>", 1)[1]) for p in render_pages(doc, view)]


def _groups(root, cls):
    return [g for g in root.iter(NS + "g") if cls in (g.get("class") or "").split()]


def _strokes(el):
    return {e.get("stroke") for e in el.iter() if e.get("stroke")}


def test_sheet_attributes_and_style():
    doc = _example("07")
    sheets = _svgs(doc)
    assert [s.get("data-uw-sheet") for s in sheets] == [str(i) for i in range(1, len(sheets) + 1)]
    assert {s.get("data-uw-view-kind") for s in sheets} == {"single-line"}
    assert {s.get("data-uw-view-kind") for s in _svgs(doc, "multi-line")} == {"multi-line"}
    style = sheets[0].find(NS + "style").text
    assert "@media screen" in style and ".uw-link:hover" in style and ".uw-node:hover" in style


@pytest.mark.parametrize("kind", ["single-line", "multi-line"])
def test_every_drawn_node_has_its_edge(kind):
    doc = _example("52")
    index = build_index(doc)
    (svg,) = _svgs(doc, kind)
    nodes = {g.get("data-uw-id") for g in _groups(svg, "uw-node") if g.get("data-uw-id") and not g.get("data-uw-link")}
    edges = {g.get("data-uw-edge"): g.get("data-uw-parent") for g in _groups(svg, "uw-edge")}
    tree = {n for n in nodes if n in index.nodes and index.parent.get(n) is not None}
    assert tree and tree <= set(edges)
    for child, parent in edges.items():
        assert index.parent[child] == parent
    assert {g.get("data-uw-id") for g in _groups(svg, "uw-busbar")} >= {"W1", "W2"}


def test_links_have_hit_paths_and_devices():
    doc = _example("52")
    (svg,) = _svgs(doc)
    links = _groups(svg, "uw-link")
    assert len(links) >= 3
    for g in links:
        assert g.get("data-uw-kind") and g.get("data-uw-from") and g.get("data-uw-to") and g.get("data-uw-link")
        hits = [k for k in g if "uw-hit" in (k.get("class") or "")]
        assert len(hits) == 1 and hits[0].get("pointer-events") == "stroke"
        assert _strokes(hits[0]) == {"transparent"}
        assert all(float(e.get("stroke-width")) >= 3 for e in hits[0])
    devices = [d for g in links for d in _groups(g, "uw-node")]
    assert devices and all(d.get("data-uw-link") for d in devices)


@pytest.mark.parametrize("prefix", ["07", "18"])
@pytest.mark.parametrize("kind", ["single-line", "multi-line"])
def test_own_sheet_boards_are_referenced_from_sheet_one(prefix, kind):
    doc = _example(prefix)
    sheets = _svgs(doc, kind)
    refs = [(g.get("data-uw-target-sheet"), g.get("data-uw-target-id")) for g in _groups(sheets[0], "uw-ref")]
    assert len(sheets) > 1
    # sheets 2.. hold one board each (own_sheet): sheet 1 references every one of them, with its id
    targets = {int(s): i for s, i in refs if s}
    assert set(targets) == set(range(2, len(sheets) + 1))
    assert all(targets.values())
    # the "-> sheet n" text of a board drawn on its own sheet belongs to the reference
    assert any("→" in (t.text or "") for g in _groups(sheets[0], "uw-ref") for t in g.iter(NS + "text"))
    # every later sheet points back
    for s in sheets[1:]:
        assert any(g.get("data-uw-target-sheet") for g in _groups(s, "uw-ref"))


def test_multiline_conductors_and_cells():
    doc = _example("06")
    (ml,) = _svgs(doc, "multi-line")
    conds = {e.get("data-uw-cond") for e in ml.iter() if e.get("data-uw-cond")}
    assert {"L1", "L2", "L3", "N", "PE"} <= conds
    rails = _groups(ml, "uw-busbar")
    assert rails and all(r.get("data-uw-cond") for r in rails)
    (sl,) = _svgs(doc)
    cells = _groups(sl, "uw-cell")
    assert cells and all(c.get("data-uw-id") for c in cells)


def test_default_rendering_is_black():
    doc = _example("52")
    for svg in _svgs(doc) + _svgs(doc, "multi-line"):
        assert not _groups(svg, "uw-legend")
        assert not set(SOURCE_COLORS[:2]) & _strokes(svg)


def test_source_colours():
    doc = _example("52")
    (svg,) = _svgs(doc, color="source")
    by_id = {g.get("data-uw-id"): g for g in _groups(svg, "uw-node")}
    assert SOURCE_COLORS[0] in _strokes(by_id["Q1"]) and SOURCE_COLORS[1] in _strokes(by_id["Q2"])
    assert _groups(svg, "uw-legend")
    (svg,) = _svgs(doc, color="source", palette={"S1": "#123456"})
    assert "#123456" in _strokes({g.get("data-uw-id"): g for g in _groups(svg, "uw-node")}["Q1"])


def test_conductor_colours_iec_and_us():
    doc = _example("06")
    (svg,) = _svgs(doc, "multi-line", color="conductors")
    iec = CONDUCTOR_PRESETS["iec"]
    rails = {r.get("data-uw-cond"): _strokes(r) for r in _groups(svg, "uw-busbar")}
    assert iec["L1"] in rails["L1"] and iec["N"] in rails["N"] and {iec["PE"], PE_STRIPE} <= rails["PE"]
    text = page_to_svg(render_pages(doc, default_view(doc, kind="multi-line").model_copy(
        update={"color": "conductors"}))[0])
    assert "Conductors (IEC 60445)" in text
    view = default_view(doc, kind="multi-line").model_copy(update={"color": "conductors", "conductor_colors": "us"})
    text = page_to_svg(render_pages(doc, view)[0])
    assert "Conductors (NEC practice)" in text and CONDUCTOR_PRESETS["us"]["L2"] in text
    doc.meta.lang = "fr"
    assert "Conducteurs (pratique NEC)" in page_to_svg(render_pages(doc, view)[0])
    us = _example("32")  # NEC document: US preset by default, brown / orange / yellow at 480 V
    text = page_to_svg(render_pages(us, default_view(us, kind="multi-line").model_copy(
        update={"color": "conductors"}))[0])
    assert "NEC practice" in text and CONDUCTOR_PRESETS["us480"]["L2"] in text


def test_phase_colours_and_tinted_cells():
    doc = _example("07")
    sheet = _svgs(doc, color="phase")[1]
    by_id = {g.get("data-uw-id"): g for g in _groups(sheet, "uw-node")}
    assert PHASE_COLORS["L1"] in _strokes(by_id["F11"]) and PHASE_COLORS["L2"] in _strokes(by_id["F12"])
    fills = {r.get("fill") for c in _groups(sheet, "uw-cell") for g in c if g.get("data-uw-field") == "phase"
             for r in g.iter(NS + "rect")}
    assert len(fills - {"none"}) == 3


def test_status_colours():
    doc = _example("37")
    (svg,) = _svgs(doc, color="status")
    assert STATUS_COLORS["existing"] in _strokes(svg)
    assert any("existing" in (t.text or "") for g in _groups(svg, "uw-legend") for t in g.iter(NS + "text"))


def test_voltage_colours():
    doc = _example("25")
    (svg,) = _svgs(doc, color="voltage")
    labels = [t.text for g in _groups(svg, "uw-legend") for t in g.iter(NS + "text")]
    assert any("1 kV" in (x or "") for x in labels)


def test_pdf_outline_and_internal_links(tmp_path):
    pytest.importorskip("reportlab")
    doc = _example("18")
    path = render_pdf(doc, tmp_path / "t.pdf")
    data = path.read_bytes()
    pages = len(render_pages(doc))
    assert b"/Outlines" in data
    assert len(re.findall(rb"/Subtype\s*/Link", data)) >= pages - 1
    assert data.count(b"Sheet 1") >= 1 and b"/Annots" in data


def test_wire_marks_on_conductors():
    doc = _example("24")
    (svg,) = _svgs(doc, "multi-line", wire_marking=default_view(doc, "marks").wire_marking)
    marked = [g for g in svg.iter(NS + "g") if g.get("data-uw-mark")]
    assert marked and all(g.get("data-uw-cond") for g in marked)
    edges = {g.get("data-uw-edge") for g in _groups(svg, "uw-edge") for k in g if k.get("data-uw-mark")}
    assert {"M1", "M2", "M3"} <= edges
    assert not any(g.get("data-uw-mark") for s in _svgs(doc, "multi-line") for g in s.iter(NS + "g"))
