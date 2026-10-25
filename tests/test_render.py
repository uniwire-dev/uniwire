import re
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.conftest import ROOT
from uniwire import load, render_pages, render_pdf, render_svg
from uniwire.graph import to_graph

SMALL = {"sources": [{"type": "grid", "children": [{"type": "board", "ref": "TD", "children": [
    {"type": "rcd", "idn_mA": 30, "rcd_type": "A", "children": [
        {"type": "breaker", "in_A": 16, "cable": {"section_mm2": 1.5}, "children": [{"type": "lighting", "points": 5}]},
        {"type": "breaker", "in_A": 20, "cable": {"section_mm2": 2.5}, "children": [{"type": "socket", "points": 6}]}]}]}]}]}


def test_render_svg_and_pdf(tmp_path):
    doc = load(SMALL)
    paths = render_svg(doc, tmp_path, "t")
    assert paths
    for p in paths:
        assert ET.parse(p).getroot().tag.endswith("svg")  # well-formed XML
    pdf = render_pdf(doc, tmp_path / "t.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


def test_folio_split_on_wide_board():
    children = [{"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]} for _ in range(40)]
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "ref": "TD", "children": children}]}]})
    pages = render_pages(doc)
    assert len(pages) >= 2


def test_graph_export_busbar_is_one_node():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "id": "TD", "children": [
        {"type": "breaker", "id": "A"}, {"type": "breaker", "id": "B", "cable": {"section_mm2": 2.5}}]}]}]})
    g = to_graph(doc)
    bus = next(n for n in g["connectivity_nodes"] if n["id"] == "cn:TD")
    assert set(bus["terminals"]) == {"TD.out", "A.in", "B.cable.in"}


def test_normally_open_link_dashed_with_its_device(tmp_path):
    from pathlib import Path
    ex = Path(__file__).resolve().parents[1] / "examples" / "52_dual_source_selectable_feeders.uniwire.json"
    doc = load(ex)
    svg = render_svg(doc, tmp_path, "alt", view=doc.views[0])[0].read_text("utf-8")
    # long dash of the normally-open power links (3 1.2, scaled with the drawing when it is enlarged)
    dashes = [(float(a), float(b)) for a, b in re.findall(r'stroke-dasharray="([\d.]+) ([\d.]+)"', svg)]
    assert any(abs(a / b - 2.5) < 0.01 for a, b in dashes)
    for dev in ("X21", "X22", "X13"):  # the removable links carried by the infeed links are drawn
        assert f'id="{dev}"' in svg
    assert "N.O., key LA" in svg


def test_normally_open_annotation_in_french():
    from uniwire.labels import annotation
    doc = load({"meta": {"lang": "fr"}, "sources": [{"type": "grid", "children": [
        {"id": "Q", "type": "disconnector", "normal_state": "open", "locks": ["K1"]}]}]})
    q = doc.sources[0].children[0]
    assert annotation(q, "fr")[-1] == "NO, clé K1"
    assert annotation(q, "en")[-1] == "N.O., key K1"


def test_paper_chosen_when_the_document_has_none():
    """No paper in the document: the smallest sheet holding the drawing at full size (A4 landscape here)."""
    assert (render_pages(load(SMALL))[0].width, render_pages(load(SMALL))[0].height) == (297.0, 210.0)
    big = load(Path(__file__).resolve().parents[1] / "examples" / "18_office_building_main_lv_switchboard.uniwire.json")
    big.views = []  # the example says A3: without it, its switchboard does not fit an A4 at full size
    assert render_pages(big)[0].width > 297.0


def test_small_drawing_enlarged_on_a_given_paper():
    """A paper given by the document is kept; a drawing using little of it is enlarged (one scale per view)."""
    doc = dict(SMALL)
    doc["views"] = [{"id": "v", "paper": "A3"}]
    from uniwire.render.svg import page_to_svg

    svg = page_to_svg(render_pages(load(doc))[0])
    assert 'width="420mm"' in svg
    assert 'font-size="2.5"' in svg  # annotations: 2 mm x 1.25


def test_layout_reused_for_the_same_document_and_never_shared():
    import json

    from uniwire.render import _PAGES
    path = sorted((ROOT / "examples").glob("01_*.uniwire.json"))[0]
    first = render_pages(load(json.loads(path.read_text())))
    first[0].root.items.clear()  # a caller altering its pages does not alter the next caller's
    second = render_pages(load(json.loads(path.read_text())))
    assert len(_PAGES) == 1 and second[0].root.items
