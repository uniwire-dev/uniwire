"""Readability of dense documents (see dense_docs): many auxiliary devices, a controller many links reach, links to
other sheets, long labels. The counts may only go down: lower a number when a fix removes findings."""

import pytest

from tests.dense_docs import DENSE, dense_doc, long_way_doc, split_main_doc
from tests.drawing_audit import audit
from uniwire import load
from uniwire.render import default_view, render_pages, render_views
from uniwire.render.scene import Group, Rect, Text

# findings tolerated per document, single-line views + multi-line view ("mixed": its multi-line main sheet is no
# longer drawn at 56 %: its PLC goes to a sheet of its own, and the texts of the stubs to that sheet still overlap
# symbols; to come down when the stubs place their texts clear of the symbols)
KNOWN = {"hub4": 0, "hub8": 0, "hub12": 2, "long_labels": 2, "spread": 0, "mixed": 11}


@pytest.mark.parametrize("name", sorted(DENSE))
def test_dense_drawing_readable(name):
    doc = load(DENSE[name])
    findings = [f for pg in render_views(doc) for f in audit(pg.root)]
    findings += [f for pg in render_pages(doc, default_view(doc, kind="multi-line")) for f in audit(pg.root)]
    assert len(findings) <= KNOWN[name], "\n".join(map(str, findings))


def _node(root: Group, nid: str):
    if isinstance(root, Group):
        if root.id == nid and root.cls and "uw-node" in root.cls.split():
            return root
        for i in root.items:
            found = _node(i, nid)
            if found is not None:
                return found
    return None


def _texts(item) -> list[Text]:
    if isinstance(item, Text):
        return [item]
    return [t for i in item.items for t in _texts(i)] if isinstance(item, Group) else []


def test_controller_many_links_reach_is_drawn_taller():
    """One point each on its sides: the box grows with the number of links (fewer links: the usual box)."""
    def height(doc):
        g = _node(render_views(load(doc))[0].root, "HUB")
        rect = next(i for i in g.items if isinstance(i, Rect))
        return rect.h

    small, large = height(dense_doc(sensors=1, local=0, remote=0)), height(dense_doc(sensors=10, local=2, remote=0))
    assert large > small * 1.8


def test_links_to_a_busy_controller_do_not_share_a_route():
    findings = [f for pg in render_views(load(dense_doc(sensors=8, local=3, remote=0))) for f in audit(pg.root)]
    assert not [f for f in findings if f.kind == "shared_run"], "\n".join(map(str, findings))


def test_off_page_stubs_of_a_controller_stay_beside_it():
    """Its links to other sheets end on stubs along its side, not hanging below it."""
    doc = load(dense_doc(sensors=2, local=0, remote=3))
    page = render_views(doc)[0]
    g = _node(page.root, "HUB")
    rect = next(i for i in g.items if isinstance(i, Rect))
    refs = [t for t in _texts(page.root) if "→" in t.text and t.text.startswith("-K1")]
    assert len(refs) == 3
    for t in refs:
        assert rect.y - 1.0 < t.p[1] < rect.y + rect.h + 3.0, t.text


def test_label_of_a_controller_at_the_end_of_a_row_is_not_cut():
    """Nothing to its right: its text runs on, whole and at full size, instead of fitting the column."""
    label = "Sequencing and monitoring controller, building 2"
    page = render_views(load(dense_doc(sensors=2, local=2, remote=0, hub_label=label)))[0]
    sizes = {t.text: t.size for t in _texts(page.root)}
    assert label in sizes
    assert sizes[label] == pytest.approx(sizes["Control supply"])


def _multiline(doc):
    return render_pages(load(doc), default_view(load(doc), kind="multi-line"))


def test_controller_many_links_reach_is_drawn_taller_in_the_multi_line_view():
    """As in the single-line diagram: one point each on its side, a lane apart, rather than packed together."""
    def height(doc):
        g = _node(_multiline(doc)[0].root, "HUB")
        return max(i.h for i in _walk_rects(g))

    small, large = height(dense_doc(sensors=1, local=0, remote=0)), height(dense_doc(sensors=6, local=2, remote=2))
    assert large > small * 2


def _walk_rects(item) -> list[Rect]:
    if isinstance(item, Rect) and not item.style.dash:
        return [item]
    return [r for i in item.items for r in _walk_rects(i)] if isinstance(item, Group) else []


def test_multi_line_link_texts_keep_off_the_conductors():
    """The texts of the links of a busy controller, beside it, not written across the feeders next to it."""
    for name in ("hub8", "mixed"):
        findings = [f for pg in _multiline(DENSE[name]) for f in audit(pg.root)]
        assert not [f for f in findings if f.kind == "text_on_conductor"], "\n".join(map(str, findings))



def _ids(item) -> set[str]:
    if not isinstance(item, Group):
        return set()
    return ({item.id} if item.id else set()) | {i for x in item.items for i in _ids(x)}


def test_a_main_board_keeps_its_ways_together_when_its_boards_go_to_other_sheets():
    """Two of its four ways feed boards wider than a sheet: those boards go to sheets of their own, the main board
    stays whole on one sheet (not cut way by way between them)."""
    pages = render_views(load(split_main_doc()))
    holding = [i for i, p in enumerate(pages) if {"Q1", "Q2", "Q3", "Q4"} & _ids(p.root)]
    assert len(holding) == 1 and {"Q1", "Q2", "Q3", "Q4"} <= _ids(pages[holding[0]].root)


def test_texts_of_a_busbar_continued_over_sheets_do_not_overlap():
    """A sheet holding one way of a busbar continued from the sheet before and on the sheet after: its two texts
    ('continued from', 'continued on') clear of each other and of the name of the board."""
    pages = render_views(load(long_way_doc()))
    assert len(pages) >= 3
    findings = [f for p in pages for f in audit(p.root) if f.kind == "text_overlap"]
    assert not findings, "\n".join(map(str, findings))
