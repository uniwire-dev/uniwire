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
    first = render_pages(load(json.loads(path.read_text(encoding="utf-8"))))
    first[0].root.items.clear()  # a caller altering its pages does not alter the next caller's
    second = render_pages(load(json.loads(path.read_text(encoding="utf-8"))))
    assert len(_PAGES) == 1 and second[0].root.items


def _walk(item):
    yield item
    for c in getattr(item, "items", []):
        yield from _walk(c)


def test_sheet_numbers_of_a_drawing_set():
    from uniwire.model import View
    from uniwire.render import sheet_numbers
    v = View()
    assert sheet_numbers([(v, 2), (v, 1)]) == ([1, 2, 3], 3)
    partial = View(first_folio=3, total_folios=6)
    assert sheet_numbers([(partial, 1), (v, 1)]) == ([3, 4], 6)  # the second view follows the first
    assert sheet_numbers([(partial, 2), (View(first_folio=6), 1)]) == ([3, 4, 6], 6)  # its own first sheet
    assert sheet_numbers([(View(first_folio=3), 2)]) == ([3, 4], None)  # partial set, total unknown: "3"
    assert sheet_numbers([(partial, 5)])[1] == 7  # never "7 / 6"


def test_drawing_set_prints_its_sheet_numbers_in_title_blocks_and_references():
    from tests.dense_docs import split_main_doc
    from uniwire.render import default_view, render_views
    from uniwire.render.scene import Text
    doc = load(split_main_doc())
    v = default_view(doc).model_copy(update={"first_folio": 3, "total_folios": 20})
    pages = render_views(doc, [v, v.model_copy(update={"kind": "multi-line", "first_folio": 1})])
    n = len(pages) // 2
    assert [p.attrs["data-uw-folio"] for p in pages[:n]] == [str(3 + i) for i in range(n)]
    texts = [t.text for t in _walk(pages[0].root) if isinstance(t, Text)]
    assert "3 / 20" in texts
    refs = [int(m) for t in texts for m in re.findall(r"sheet (\d+)", t)]
    assert refs and all(3 < r < 3 + n for r in refs)  # the sheets of the view as printed, not their position


def test_continuation_sheet_keeps_the_board_frame_and_name():
    from uniwire.render.scene import Group
    from uniwire.render.svg import page_to_svg

    def boards(g):
        if isinstance(g, Group):
            return ([g.id] if g.cls and "board" in g.cls.split() else []) + [b for c in g.items for b in boards(c)]
        return []

    feeders = [{"type": "breaker", "ref": f"-Q{i}", "in_A": 16, "children": [{"type": "socket"}]} for i in range(40)]
    for kind in ("single-line", "multi-line"):
        doc = load({"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}, "sources": [{"type": "grid", "children": [
            {"type": "board", "id": "td", "ref": "TD", "children": [{"type": "rcd", "ref": "-F1", "in_A": 63, "idn_mA": 30,
                                                                     "children": feeders}]}]}],
            "views": [{"id": "v", "kind": kind}]})
        pages = render_pages(doc)
        assert len(pages) > 1
        texts = re.findall(r">([^<>]+)</text>", page_to_svg(pages[1]))
        assert any(t.startswith("TD (") for t in texts) and not any(t.startswith("-F1 (") for t in texts), kind
        if kind == "single-line":
            assert "td" in boards(pages[1].root)  # the busbar is in the board: its frame on this sheet too


def test_continuation_of_a_row_of_the_board_names_the_board_and_the_row():
    from uniwire.render.svg import page_to_svg

    def ways(n, p):
        return [{"type": "breaker", "ref": f"-{p}{i}", "in_A": 16, "children": [{"type": "socket"}]} for i in range(n)]

    for kind in ("single-line", "multi-line"):
        doc = load({"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}, "sources": [{"type": "grid", "children": [
            {"type": "board", "ref": "TD", "children": [
                {"type": "rcd", "ref": "-ID1", "in_A": 40, "idn_mA": 30, "children": ways(4, "Qa")},
                {"type": "rcd", "ref": "-ID2", "in_A": 63, "idn_mA": 30, "children": ways(40, "Qb")}]}]}],
            "views": [{"id": "v", "kind": kind, "paper": "A4"}]})
        pages = render_pages(doc)
        assert len(pages) > 1
        texts = re.findall(r">([^<>]+)</text>", page_to_svg(pages[1]))
        assert "TD, -ID2 (continued from sheet 1)" in texts, (kind, texts)
