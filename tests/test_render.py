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
    assert "N.O., interlock LA" in svg  # a removable-link interlock, not a key


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
    # sheets that would take numbers already given follow the highest one: never two sheets with one number
    assert sheet_numbers([(View(first_folio=100), 2), (View(first_folio=100), 1)]) == ([100, 101, 102], None)
    assert sheet_numbers([(View(first_folio=1), 2), (View(first_folio=2), 1)]) == ([1, 2, 3], 3)
    assert sheet_numbers([(View(first_folio=5), 1), (View(first_folio=1), 1)]) == ([5, 1], None)  # out of order: kept


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


def test_free_spare_way_is_not_drawn_as_a_conductor():
    from uniwire.render.scene import Group, Line, Polyline

    def edge(g, nid):
        if isinstance(g, Group):
            if g.attrs.get("data-uw-edge") == nid:
                return g
            return next((e for c in g.items if (e := edge(c, nid)) is not None), None)
        return None

    def strokes(g):
        return [i for i in g.items if isinstance(i, (Line, Polyline))] + \
            [s for i in g.items if isinstance(i, Group) for s in strokes(i)]

    for kind in ("single-line", "multi-line"):
        doc = load({"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}, "sources": [{"type": "grid", "children": [
            {"type": "board", "ref": "TD", "children": [
                {"type": "breaker", "id": "q1", "in_A": 16, "children": [{"type": "socket"}]},
                {"type": "spare", "id": "free"}, {"type": "spare", "id": "kept", "in_A": 16},
                {"type": "spare", "id": "poles", "poles": "2P"},
                {"type": "breaker", "id": "q2", "in_A": 16, "children": [{"type": "spare", "id": "q2way"}]}]}]}],
            "views": [{"id": "v", "kind": kind}]})
        root = render_pages(doc)[0].root
        assert all(s.style.dash for s in strokes(edge(root, "free"))), kind  # a free space, dashed
        assert not any(s.style.dash for s in strokes(edge(root, "q1"))), kind
        assert not any(s.style.dash for s in strokes(edge(root, "poles"))), kind  # its poles: a device is there
        assert not any(s.style.dash for s in strokes(edge(root, "q2way"))), kind  # the spare way of a device


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


def test_continuation_of_equipment_beyond_a_cable_is_outside_the_board():
    from uniwire.render.scene import Group
    from uniwire.render.svg import page_to_svg

    def boards(g):
        if isinstance(g, Group):
            return ([g.id] if g.cls and "board" in g.cls.split() else []) + [b for c in g.items for b in boards(c)]
        return []

    ways = [{"type": "breaker", "ref": f"-Q{i}", "in_A": 16, "children": [{"type": "socket"}]} for i in range(40)]
    for kind in ("single-line", "multi-line"):
        doc = load({"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}, "sources": [{"type": "grid", "children": [
            {"type": "board", "id": "tgbt", "ref": "TGBT", "children": [
                {"type": "breaker", "ref": "-Q1", "in_A": 63, "cable": {"section_mm2": 16, "cores": "3G"}, "children": [
                    {"type": "ups", "ref": "UPS1", "sn_kVA": 10, "children": ways}]},
                {"type": "breaker", "ref": "-Q2", "in_A": 16, "children": [{"type": "socket"}]}]}]}],
            "views": [{"id": "v", "kind": kind, "paper": "A4"}]})
        pages = render_pages(doc)
        texts = re.findall(r">([^<>]+)</text>", page_to_svg(pages[1]))
        assert "UPS1 (continued from sheet 1)" in texts, (kind, texts)  # fed through its own cable: not in TGBT
        assert "tgbt" not in boards(pages[1].root), kind


def test_svg_states_the_language_of_the_document():
    import xml.dom.minidom

    from uniwire.render.svg import page_to_svg

    def root(meta):
        doc = load({"meta": meta, "sources": [{"type": "grid", "children": [{"type": "socket"}]}]})
        return xml.dom.minidom.parseString(page_to_svg(render_pages(doc)[0])).documentElement

    ja = root({"lang": "ja-JP"})  # browsers draw Japanese kanji in their Japanese forms, not the Chinese ones
    assert ja.getAttribute("xml:lang") == "ja-JP" and ja.getAttribute("lang") == "ja-JP"
    assert root({}).getAttribute("xml:lang") == "en"
    assert root({"lang": "en_GB"}).getAttribute("xml:lang") == "en-GB"  # a valid tag, whatever was written
    assert root({"lang": " fr "}).getAttribute("lang") == "fr"
    assert root({"lang": "Français"}).getAttribute("xml:lang") == "en"  # not a tag: the language drawn in

def test_device_label_kept_when_its_load_has_another_label():
    from uniwire.render import render_views
    from uniwire.render.svg import page_to_svg

    doc = {"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}, "sources": [{"type": "grid", "children": [
        {"type": "board", "ref": "TD", "children": [
            {"type": "breaker", "ref": "-Q1", "label": "Hut, temporary", "in_A": 16, "children": [
                {"type": "socket", "label": "Sockets"}]},
            {"type": "breaker", "ref": "-Q2", "label": "Heating", "in_A": 20, "children": [{"type": "water_heater"}]},
            {"type": "breaker", "ref": "-Q3", "label": "Lights", "in_A": 10, "children": [
                {"type": "lighting", "label": "Lights"}]},
            {"type": "breaker", "ref": "-Q4", "label": "Pump", "in_A": 10, "children": [
                {"type": "motor", "label": "Pump 2 kW"}]}]}]}],
        "views": [{"id": "sld"}, {"id": "ml", "kind": "multi-line"}]}
    sld, ml = (re.findall(r">([^<>]+)</text>", page_to_svg(p)) for p in render_views(load(doc)))
    assert sld.count("Hut, temporary") == 1 and sld.count("Heating") == 1 and sld.count("Lights") == 1  # table
    assert ml.count("Hut, temporary") == 1 and ml.count("Heating") == 1 and ml.count("Lights") == 1
    assert "Pump" not in ml  # said by the label of its load: not repeated


def test_device_label_said_by_its_load_is_not_repeated_whatever_its_case_spacing_or_tag():
    from uniwire.render import render_views
    from uniwire.render.svg import page_to_svg

    doc = {"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}, "sources": [{"type": "grid", "children": [
        {"type": "board", "ref": "TD", "children": [
            {"type": "breaker", "ref": "-Q1", "label": "-Q1 Garden  lights", "in_A": 10, "children": [
                {"type": "lighting", "label": "garden lights, path"}]},
            {"type": "breaker", "ref": "-Q2", "label": "Workshop", "in_A": 16, "children": [
                {"type": "socket", "label": "Sockets"}]}]}]}],
        "views": [{"id": "ml", "kind": "multi-line"}]}
    texts = " ".join(re.findall(r">([^<>]+)</text>", page_to_svg(render_views(load(doc))[0])))
    assert "Garden" not in texts and "Workshop" in texts


def _label_texts(ways):
    from uniwire.render import render_views
    from uniwire.render.svg import page_to_svg

    doc = {"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}, "sources": [{"type": "grid", "children": [
        {"type": "board", "ref": "TD", "children": ways}]}],
        "views": [{"id": "sld"}, {"id": "ml", "kind": "multi-line"}]}
    return [re.findall(r">([^<>]+)</text>", page_to_svg(p)) for p in render_views(load(doc))]


def test_short_words_and_acronyms_of_a_device_label_count():
    def way(ref, label, load_label):
        return {"type": "breaker", "ref": ref, "label": label, "in_A": 16, "children": [
            {"type": "socket", "label": load_label}]}

    sld, ml = _label_texts([way("-Q1", "照明", "Sockets"), way("-Q2", "PV", "Sockets"), way("-Q3", "WC", "Sockets"),
                            way("-Q4", "Oven 12 kW 3P", "Bakery oven")])
    for t in (sld, ml):
        assert "照明" in t and "PV" in t and "WC" in t  # a word of two letters or two kanji says something
        assert "Oven 12 kW 3P" not in t  # said by its load, the ratings aside


def test_device_label_matched_whatever_its_spacing_in_scripts_without_spaces_or_its_unicode_form():
    import unicodedata

    sld, ml = _label_texts([
        {"type": "breaker", "ref": "-Q1", "label": "厨房照明", "in_A": 10, "children": [
            {"type": "lighting", "label": "厨房 照明"}]},
        {"type": "breaker", "ref": "-Q2", "label": unicodedata.normalize("NFD", "Éclairage cave"), "in_A": 10,
         "children": [{"type": "lighting", "label": "éclairage cave"}]}])
    for t in (sld, ml):
        assert "厨房照明" not in t and not any("clairage cave" in x and x[0] != "é" for x in t)


def test_device_label_over_a_spare_way_is_drawn_in_every_view():
    sld, ml = _label_texts([{"type": "breaker", "ref": "-Q1", "label": "Future kitchen", "in_A": 16, "children": [
        {"type": "spare"}]}, {"type": "breaker", "ref": "-Q2", "in_A": 16, "children": [{"type": "socket"}]}])
    assert "Future kitchen" in sld and "Future kitchen" in ml  # the table shows "Spare" for the way
