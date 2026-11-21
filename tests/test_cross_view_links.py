"""Links between two views of a drawing set: each view drawn from its own root, a link whose ends are in different
views drawn at each end as a cross-sheet reference to the sheet of the other end (as within one view split over
several sheets), the folio numbered as in the set."""

import copy

import uniwire
from tests.drawing_audit import audit
from uniwire import load
from uniwire.render import render_pages, render_views
from uniwire.render.scene import BUS, Group, Line, Polyline, Text

DOC = {
    "meta": {"title": "Example house with a hybrid inverter", "lang": "en"},
    "installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
    "sources": [
        {"type": "grid", "id": "G1", "ref": "-G1", "label": "Public grid", "children": [
            {"type": "board", "id": "MB", "ref": "=MB", "label": "Main board", "children": [
                {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 16, "children": [
                    {"type": "socket", "id": "X1", "ref": "-X1", "label": "Sockets"}]},
                {"type": "rcbo", "id": "Q2", "ref": "-Q2", "in_A": 32, "idn_mA": 30, "label": "Inverter line"},
                {"type": "rcbo", "id": "Q3", "ref": "-Q3", "in_A": 25, "idn_mA": 300, "label": "Bypass line"}]}]},
        {"type": "inverter", "id": "T1", "ref": "-T1", "label": "Hybrid inverter", "children": [
            {"type": "board", "id": "BB", "ref": "=BB", "label": "Backup board", "children": [
                {"type": "breaker", "id": "Q7", "ref": "-Q7", "in_A": 32, "children": [
                    {"type": "transfer_switch", "id": "Q8", "ref": "-Q8", "in_A": 40, "children": [
                        {"type": "breaker", "id": "Q81", "ref": "-Q81", "in_A": 16, "children": [
                            {"type": "load", "id": "E1", "ref": "-E1", "label": "Pump"}]}]}]}]}]}],
    "devices": [{"type": "earth_bar", "id": "PE1", "ref": "-PE1", "label": "Main earthing terminal"}],
    "links": [
        {"kind": "infeed", "from": "Q2", "to": "T1", "label": "AC input"},
        {"kind": "transfer", "from": "Q3", "to": "Q8", "label": "Position 2"},
        {"kind": "earth", "from": "MB", "to": "PE1", "label": "Board PE"},
        {"kind": "earth", "from": "T1", "to": "PE1", "label": "Inverter PE"}],
    "views": [{"id": "grid", "root": "G1", "paper": "A3", "title": "Grid side"},
              {"id": "backup", "root": "T1", "paper": "A3", "title": "Backup side"}],
}


def _link(page, frm: str, to: str) -> Group:
    """The group of the link ``frm`` -> ``to`` on ``page``."""
    found = [g for g in _walk(page.root) if isinstance(g, Group) and g.attrs.get("data-uw-from") == frm
             and g.attrs.get("data-uw-to") == to]
    assert len(found) == 1, (frm, to)
    return found[0]


def _ref(page, frm: str, to: str) -> Group:
    """The cross-sheet reference of that link on ``page``."""
    (g,) = [g for g in _walk(_link(page, frm, to)) if isinstance(g, Group) and "uw-ref" in (g.cls or "").split()]
    return g


def _texts(item) -> list[str]:
    return [t.text for t in _walk(item) if isinstance(t, Text)]


def _walk(item):
    yield item
    if isinstance(item, Group):
        for c in item.items:
            yield from _walk(c)


def test_cross_view_links_drawn_with_the_sheet_of_the_other_end():
    first, second = render_views(load(copy.deepcopy(DOC)))
    # the feeder breaker that feeds the inverter of the other view ends on a reference to it, with its label
    assert _ref(first, "Q2", "T1").attrs == {"data-uw-target-sheet": "2", "data-uw-target-id": "T1"}
    assert _texts(_ref(first, "Q2", "T1")) == ["AC input", "-T1 → sheet 2"]
    assert _texts(_ref(first, "Q3", "Q8")) == ["Position 2", "-Q8 → sheet 2"]
    # at the other end, the inverter and the transfer switch name the breakers feeding them
    assert _ref(second, "Q2", "T1").attrs == {"data-uw-target-sheet": "1", "data-uw-target-id": "Q2"}
    assert _texts(_ref(second, "Q2", "T1")) == ["AC input", "-Q2 → sheet 1"]
    assert _texts(_ref(second, "Q3", "Q8")) == ["Position 2", "-Q3 → sheet 1"]
    # an earth link between the inverter and the earthing terminal drawn with the main board
    assert "-PE1 → sheet 1" in _texts(_ref(second, "T1", "PE1"))
    assert "-T1 → sheet 2" in _texts(_ref(first, "T1", "PE1"))
    for page in (first, second):
        assert not audit(page.root), [str(f) for f in audit(page.root)]


def test_folio_numbers_of_the_set_and_first_folio():
    """The reference prints the number the sheet has in the set, also when the views are numbered from a
    ``first_folio``; a view drawn alone prints the same numbers as in the PDF of the whole set."""
    d = copy.deepcopy(DOC)
    d["views"][0]["first_folio"] = 10
    d["views"][1]["first_folio"] = 20
    doc = load(d)
    first, second = render_views(doc)
    assert "-T1 → sheet 20" in _texts(_ref(first, "Q2", "T1"))
    assert _ref(first, "Q2", "T1").attrs["data-uw-target-sheet"] == "2"  # (the link: its page in the PDF)
    assert "-Q2 → sheet 10" in _texts(_ref(second, "Q2", "T1"))
    (alone,) = render_pages(doc, doc.views[1])
    assert "-Q2 → sheet 10" in _texts(_ref(alone, "Q2", "T1"))
    assert _ref(alone, "Q2", "T1").attrs["data-uw-target-sheet"] == ""  # (not in this PDF: no link)


def test_other_end_drawn_in_no_view_keeps_its_name():
    """A link to a node that no sheet of the set draws: the reference names it, without a sheet."""
    d = copy.deepcopy(DOC)
    del d["views"][1]
    (page,) = render_views(load(d))
    assert _texts(_ref(page, "Q2", "T1")) == ["AC input", "-T1"]
    assert _ref(page, "Q2", "T1").attrs["data-uw-target-sheet"] == ""


def test_incoming_arrow_at_the_receiving_end():
    """A power link with a way (infeed, standby supply): its arrow points away at the end it leaves, toward the
    device at the end it comes into; an earth link keeps the off-page arrow."""
    first, second = render_views(load(copy.deepcopy(DOC)))
    for page, frm, to, incoming in ((first, "Q2", "T1", False), (second, "Q2", "T1", True),
                                    (first, "Q3", "Q8", False), (second, "Q3", "Q8", True),
                                    (first, "T1", "PE1", False), (second, "T1", "PE1", False)):
        (h,) = [p for p in _ref(page, frm, to).items if isinstance(p, Polyline) and p.closed]
        a, point, b = h.points
        base = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        start = next(p for p in _link(page, frm, to).items if isinstance(p, Polyline) and not p.closed).points[0]
        dist = lambda p, s=start: abs(p[0] - s[0]) + abs(p[1] - s[1])  # noqa: E731
        assert (dist(point) < dist(base)) is incoming, (frm, to)


def test_feeder_breaker_ends_on_the_reference():
    """The breaker whose only continuation is the link to the other view: its stub leaves its output, downward."""
    first, _ = render_views(load(copy.deepcopy(DOC)))
    sym = next(g for g in _walk(first.root) if isinstance(g, Group) and g.id == "Q2" and "uw-node" in (g.cls or ""))
    pts = [p for item in _walk(sym) for p in getattr(item, "points", ())]
    stub = next(p for p in _link(first, "Q2", "T1").items if isinstance(p, Polyline) and not p.closed).points
    assert all(abs(x - stub[0][0]) < 1e-6 for x, _ in stub)  # straight down from its output
    assert stub[0][1] >= max(y for _, y in pts) - 1.0 and stub[-1][1] > stub[0][1]


def test_checks_unchanged_by_the_views():
    """Splitting the drawing into two views (links between them) adds no finding and removes none."""
    one = copy.deepcopy(DOC)
    one["views"] = [{"id": "all", "paper": "A3"}]
    key = lambda f: (f.rule, str(f))  # noqa: E731
    assert sorted(map(key, uniwire.check(load(one)))) == sorted(map(key, uniwire.check(load(copy.deepcopy(DOC)))))


def test_stub_under_a_busbar_stops_short_of_it():
    """A changeover switch right under a busbar: the reference of its standby supply stays below the busbar (its
    arrow and texts were drawn on it)."""
    d = copy.deepcopy(DOC)
    board = d["sources"][1]["children"][0]
    board["children"] = [board["children"][0]["children"][0],  # (the switch straight on the busbar of the board)
                         {"type": "breaker", "id": "Q9", "ref": "-Q9", "in_A": 10, "children": [
                             {"type": "load", "id": "E9", "ref": "-E9", "label": "Lights"}]}]
    _, second = render_views(load(d))
    (head,) = [p for p in _ref(second, "Q3", "Q8").items if isinstance(p, Polyline) and p.closed]
    stub = next(p for p in _link(second, "Q3", "Q8").items if isinstance(p, Polyline) and not p.closed).points
    x = stub[0][0]
    lines = [(i.a[1], min(i.a[0], i.b[0]), max(i.a[0], i.b[0])) for i in _walk(second.root)
             if isinstance(i, Line) and i.style.width == BUS and abs(i.a[1] - i.b[1]) < 1e-9]  # the busbars
    top = min(p[1] for p in head.points)
    assert lines and not [y for y, x0, x1 in lines if x0 - 0.5 <= x <= x1 + 0.5 and top - 1.0 < y < stub[0][1]]
