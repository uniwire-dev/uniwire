"""Auxiliary devices of a cabinet drawing: never over the circuit table nor in the axis of a load; tidy texts."""

from uniwire import load, render_pages
from uniwire.labels import cable_text
from uniwire.layout import engine
from uniwire.model.base import Cable
from uniwire.render.scene import Group, Rect, bbox
from uniwire.symbols import symbol_for

DOC = {
    "views": [{"id": "sld", "cartouche": ["ref", "label", "protection", "cable"]}],
    "sources": [{"type": "grid", "id": "W1", "children": [{"type": "board", "id": "B", "ref": "+A1", "children": [
        {"type": "breaker", "id": "Q2", "in_A": 10, "children": [{"type": "power_supply", "id": "G1", "u2_V": 24, "children": [
            {"type": "fuse", "id": "F1", "in_A": 4, "cable": {"cores": "2", "section_mm2": 1.5}, "children": [
                {"type": "plc", "id": "A1", "family": "Automation Series 7",
                 "modules": [{"slot": 1, "kind": "di", "channels": 16}, {"slot": 2, "kind": "do", "channels": 8}]}]},
            {"type": "fuse", "id": "F3", "in_A": 2, "children": [{"type": "controller", "id": "SW", "symbol_text": "SW"}]}]}]},
        {"type": "breaker", "id": "Q3", "in_A": 10, "children": [{"type": "ventilation", "id": "FAN", "ref": "M1"}]}]}]}],
    "devices": [{"type": "meter", "id": "MET", "ref": "P1...P4", "label": "Sub-meters (outside)"},
                {"type": "controller", "id": "BMS", "ref": "BMS", "label": "Building management (outside)"},
                {"type": "terminal_block", "id": "FLD", "ref": "X10", "label": "Status inputs"},
                {"type": "offpage", "id": "TO2", "ref": "+A2", "label": "Cabinet +A2"}],
    "links": [{"kind": "data", "from": "SW", "to": "MET", "label": "4x Cat.6"},
              {"kind": "data", "from": "SW", "to": "TO2", "label": "fibre link"},
              {"kind": "data", "from": "TO2", "to": "BMS", "label": "fibre link"},
              {"kind": "measure", "from": "FLD", "to": "A1", "label": "16 DI"}]}


def _find(item, cls):
    if isinstance(item, Group):
        if item.cls and cls in item.cls.split():
            return item
        for c in item.items:
            f = _find(c, cls)
            if f is not None:
                return f
    return None


def test_table_below_auxiliary_devices():
    page = render_pages(load(DOC))[0]
    table = _find(page.root, "cartouche")
    assert table is not None
    top = min(i.y for i in table.items if isinstance(i, Rect))
    diagram = _find(page.root, "diagram")
    others = [bbox(i) for i in diagram.items if i is not table and bbox(i)]
    assert max(b[3] for b in others) < top  # nothing drawn over the table


def test_devices_keep_clear_of_load_axes(monkeypatch):
    seen = {}
    orig = engine._place_devices

    def spy(doc, roots, everything, *a, **k):
        annex = orig(doc, roots, everything, *a, **k)
        seen["loads"] = [n for n in everything if n.bottom]
        seen["annex"] = annex
        return annex

    monkeypatch.setattr(engine, "_place_devices", spy)
    render_pages(load(DOC))
    for ln in seen["annex"]:
        x0, _, x1, _ = ln.sym_box()
        for load_ in seen["loads"]:
            below = ln.y < load_.y + load_.sym.height + engine.DEVICE_AXIS_MM
            assert not (below and x0 - engine.DEVICE_PAD_MM < load_.x < x1 + engine.DEVICE_PAD_MM), ln.node.id
    boxes = [ln.sym_box() for ln in seen["annex"]]
    for i, a in enumerate(boxes):  # devices do not touch each other
        for b in boxes[i + 1:]:
            assert a[2] + 2.0 <= b[0] or b[2] + 2.0 <= a[0] or a[3] + 2.0 <= b[1] or b[3] + 2.0 <= a[1]


def test_bare_core_count_and_plc_family():
    assert cable_text(Cable(cores="2", section_mm2=1.5)) == "2x1.5"
    assert cable_text(Cable(cores="3G", section_mm2=2.5)) == "3G2.5"
    plc = load(DOC).sources[0].children[0].children[0].children[0].children[0].children[0]
    sym = symbol_for(plc)
    head = next(i for i in sym.items if isinstance(i, Rect))
    family = next(i for i in sym.items if getattr(i, "text", None) == "Automation")  # first word, not cut
    from uniwire.render.scene import text_width
    assert head.w >= text_width(family.text, family.size)


def _targets(item) -> list[int]:
    out = []
    if isinstance(item, Group):
        t = item.attrs.get("data-uw-target-sheet", "")
        if t.isdigit():
            out.append(int(t))
        for c in item.items:
            out += _targets(c)
    return out


def test_pdf_holds_every_view():
    """A cabinet drawing set: the multi-line power diagram, then the single-line diagram with the links."""
    import base64

    from uniwire.llm import tools
    from uniwire.render import render_views

    doc = {**DOC, "views": [{"id": "ml", "kind": "multi-line"}, DOC["views"][0]]}
    pages = render_views(load(doc))
    assert [p.attrs["data-uw-view-kind"] for p in pages] == ["multi-line", "single-line"]
    pdf = base64.b64decode(tools.pdf_file(doc)["pdf_base64"])
    assert pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages") == 2  # one page per view
    only = base64.b64decode(tools.pdf_file(doc, kind="single-line")["pdf_base64"])
    assert only.count(b"/Type /Page") - only.count(b"/Type /Pages") == 1


def test_cross_sheet_references_follow_their_view():
    from uniwire.render import render_pages, render_views

    from .conftest import ROOT

    doc = load(ROOT / "examples" / "18_office_building_main_lv_switchboard.uniwire.json")
    first = render_pages(doc)
    both = render_views(doc, [doc.views[0], doc.views[0]])
    assert len(both) == 2 * len(first)
    n = len(first)
    second = [t for p in both[n:] for t in _targets(p.root)]
    assert second and all(n < t <= 2 * n for t in second)  # the second copy points at its own sheets


def test_long_title_block_value_stays_in_its_cell():
    from uniwire.render.frame import _fit_lines
    from uniwire.render.scene import text_width
    name = "Jane Example, Senior Electrical Design Engineer and Reviewer"
    lines, size = _fit_lines(name, 2.2, 26.0, 1.5)
    assert len(lines) == 2 and " ".join(lines) == name
    assert all(text_width(t, size) <= 26.0 for t in lines)
    lines, size = _fit_lines("x" * 200, 2.2, 26.0, 1.5)  # no space to break on: cut
    assert lines[0].endswith("…") and text_width(lines[0], size) <= 26.0
    assert _fit_lines("Short", 2.2, 26.0, 1.5) == (["Short"], 2.2)
