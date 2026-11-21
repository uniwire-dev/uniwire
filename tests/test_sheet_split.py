"""Use of the sheet: never drawn below the smallest scale when the view may be split into sheets, the scale in the
title block."""

from typing import Optional

import pytest

from uniwire import load, render_pages
from uniwire.layout.engine import MIN_SCALE, build_index, drawing_area, fit_scale, layout_sheet, plan_sheets
from uniwire.layout.multiline import _Assigner, _fit, _layout, plan_multiline
from uniwire.render.scene import Group, Text


def _wide_way(kind: str = "single-line", **view) -> dict:
    """A board of five ways, one of them a distribution of 40 circuits below a device (no board): wider than any
    sheet on its own."""
    fuses = [{"type": "fuse", "ref": f"-F{i}", "in_A": 2, "children": [
        {"type": "load", "ref": f"-E{i}{j}", "label": "Load"} for j in range(10)]} for i in range(1, 5)]
    return {"meta": {"title": "Example machine"}, "views": [{"id": "v", "kind": kind, "paper": "A3", **view}],
            "sources": [{"type": "grid", "ref": "-G1", "children": [{"type": "board", "ref": "=MB", "children": [
                {"type": "breaker", "ref": "-Q1", "in_A": 16, "children": [{"type": "socket", "ref": "-X01"}]},
                {"type": "breaker", "ref": "-Q2", "in_A": 6, "children": [
                    {"type": "power_supply", "ref": "-T1", "children": fuses}]},
                {"type": "breaker", "ref": "-Q3", "in_A": 16, "children": [{"type": "motor", "ref": "-M1", "p_kW": 1.5}]},
                {"type": "breaker", "ref": "-Q4", "in_A": 16, "children": [{"type": "socket", "ref": "-X04"}]},
                {"type": "breaker", "ref": "-Q5", "in_A": 10, "children": [{"type": "lighting", "ref": "-E5"}]}]}]}]}


def _texts(item, out: Optional[list] = None) -> list[str]:
    out = [] if out is None else out
    if isinstance(item, Text):
        out.append(item.text)
    elif isinstance(item, Group):
        for c in item.items:
            _texts(c, out)
    return out


def _group(item, cls: str):
    if isinstance(item, Group):
        if item.cls == cls:
            return item
        for c in item.items:
            g = _group(c, cls)
            if g is not None:
                return g
    return None


def _scale_cell(page) -> str:
    """The value of the cell "Scale" of the title block."""
    texts = _texts(_group(page.root, "title-block"))
    return texts[texts.index("Scale") + 1]


def test_wide_way_split_across_sheets_in_single_line():
    """A way wider than a sheet (a distribution below a device, no board to take out) is not squeezed on one
    sheet: its branches go to sheets of their own, every sheet at the smallest scale or larger."""
    doc = load(_wide_way())
    view = doc.views[0]
    index = build_index(doc)
    specs = plan_sheets(doc, view, index)
    scales = [fit_scale(layout_sheet(doc, view, s, index), view) for s in specs]
    assert len(specs) >= 2 and min(scales) >= view.min_scale
    texts = [t for p in render_pages(doc, view) for t in _texts(p.root)]
    assert any("sheet" in t and t.startswith("-F") for t in texts)  # the off-page references to the branches
    assert any(t.startswith("from -T1") for t in texts)  # ... and the feed on the branch's sheet


def test_wide_way_split_across_sheets_in_multi_line():
    doc = load(_wide_way("multi-line"))
    view = doc.views[0]
    index = build_index(doc)
    info = _Assigner(doc, view.show_pe).info
    specs = plan_multiline(doc, view, index, info)
    assert len(specs) >= 2
    assert all(_fit(_layout(doc, view, s, index, info, annex=False), view) >= view.min_scale for s in specs)


def test_min_scale_never_below_the_smallest_scale():
    """A view asking for a smaller reduction limit is still split before its sheets get below the smallest scale."""
    doc = load(_wide_way(min_scale=0.2))
    view = doc.views[0]
    index = build_index(doc)
    specs = plan_sheets(doc, view, index)
    assert len(specs) >= 2
    assert all(fit_scale(layout_sheet(doc, view, s, index), view) >= MIN_SCALE for s in specs)


def test_folio_split_none_keeps_one_sheet_at_any_scale():
    doc = load(_wide_way(folio_split="none"))
    pages = render_pages(doc, doc.views[0])
    assert len(pages) == 1
    assert float(_scale_cell(pages[0])) < MIN_SCALE


@pytest.mark.parametrize("kind", ["single-line", "multi-line"])
def test_scale_in_the_title_block(kind):
    """The scale is written in a cell of the title block, not in the corner of the sheet."""
    doc = load(_wide_way(kind, folio_split="none"))
    page = render_pages(doc, doc.views[0])[0]
    value = _scale_cell(page)
    assert 0 < float(value) < 1
    assert not any(t.startswith("scale ") for t in _texts(page.root))
    small = load({"views": [{"id": "v", "paper": "A3"}], "sources": [{"type": "grid", "children": [
        {"type": "breaker", "ref": "-Q1", "children": [{"type": "socket"}]}]}]})
    assert float(_scale_cell(render_pages(small)[0])) >= 1  # at full size or enlarged: written too


def test_scale_note_without_title_block():
    doc = load(_wide_way(folio_split="none", title_block=False))
    page = render_pages(doc, doc.views[0])[0]
    assert any(t.startswith("scale 0.") for t in _texts(page.root))


def test_long_list_of_auxiliary_devices_in_columns():
    """Auxiliary devices linked to nothing are listed beside the tree in as many columns as keep the sheet at full
    size, not in one column far taller than the sheet."""
    doc = load({"views": [{"id": "v", "paper": "A3"}],
                "sources": [{"type": "grid", "ref": "-G1", "children": [{"type": "board", "ref": "=MB", "children": [
                    {"type": "breaker", "ref": "-Q1", "children": [{"type": "socket"}]}]}]}],
                "devices": [{"type": "controller", "ref": f"-K{i}", "label": "Relay module"} for i in range(40)]})
    view = doc.views[0]
    index = build_index(doc)
    lay = layout_sheet(doc, view, plan_sheets(doc, view, index)[0], index)
    assert len(lay.annex) == 40
    assert len({round(a.x) for a in lay.annex}) >= 3
    _, _, aw, ah = drawing_area(view)
    assert fit_scale(lay, view) == 1.0 and lay.height <= ah
    few = load({**doc.model_dump(mode="json", by_alias=True, exclude_none=True),
                "devices": [{"type": "controller", "ref": f"-K{i}"} for i in range(3)]})
    lay = layout_sheet(few, view, plan_sheets(few, view, build_index(few))[0], build_index(few))
    assert len({round(a.x) for a in lay.annex}) == 1  # a short list: one column, as before
