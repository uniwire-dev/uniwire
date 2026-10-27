"""Feeds between trees in the single-line view: a tree adding a supply to another one drawn beside it, links
across a third tree interrupted (a stub naming the other end at each end), several feeds on one busbar on their
own taps without crossing."""

from uniwire import load
from uniwire.layout import layout_sheet, plan_sheets
from uniwire.render import default_view
from uniwire.render.scene import Group, Polyline, Rect, Text


def _items(item):
    if isinstance(item, Group):
        for i in item.items:
            yield from _items(i)
    else:
        yield item


def _groups(item):
    if isinstance(item, Group):
        yield item
        for i in item.items:
            yield from _groups(i)


def _sld(doc):
    view = default_view(doc)
    return [layout_sheet(doc, view, s) for s in plan_sheets(doc, view)][0]


def _br(i, children=None):
    n = {"type": "breaker", "id": i, "ref": "-" + i, "in_A": 63, "poles": "4P"}
    if children:
        n["children"] = children
    return n


def _board(k, feeders=3):
    """Supply k -> incomer -> busbar Wk with its feeders."""
    return {"type": "transformer", "id": f"T{k}", "ref": f"-T{k}", "children": [_br(f"Q{k}0", [
        {"type": "board", "id": f"B{k}", "ref": f"B{k}", "label": f"Board {k}", "children": [
            {"type": "busbar", "id": f"W{k}", "ref": f"-W{k}", "children": [
                _br(f"Q{k}{j}", [{"type": "load", "label": f"Load {k}{j}"}]) for j in range(1, feeders + 1)]}]}])]}


def _supply(i, typ="generator"):
    return {"type": typ, "id": i, "ref": "-" + i, "children": [_br("Q" + i)]}


def _doc(sources, links):
    return load({"installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400}, "sources": sources,
                 "links": links})


def _x(lay, nid):
    return next(n.x for n in lay.lnodes if n.node is not None and n.node.id == nid)


def _link_groups(lay, nid_from):
    return [g for g in _groups(lay.group) if "uw-link" in (g.cls or "") and g.attrs.get("data-uw-from") == nid_from]


def _segments(group):
    for it in _items(group):
        if isinstance(it, Polyline) and not it.closed:
            yield from zip(it.points, it.points[1:])


def _cross(s, t):
    """A horizontal and a vertical segment crossing strictly inside both."""
    for h, v in ((s, t), (t, s)):
        if abs(h[0][1] - h[1][1]) < 1e-9 and abs(v[0][0] - v[1][0]) < 1e-9:
            (hx0, hx1), y = sorted((h[0][0], h[1][0])), h[0][1]
            (vy0, vy1), x = sorted((v[0][1], v[1][1])), v[0][0]
            if hx0 + 1e-6 < x < hx1 - 1e-6 and vy0 + 1e-6 < y < vy1 - 1e-6:
                return True
    return False


def test_added_supply_drawn_beside_the_tree_it_feeds():
    # declared after both boards, it adds a supply to board 1: drawn between board 1 and board 2
    doc = _doc([_board(1), _board(2), _supply("G1")], [{"kind": "infeed", "from": "QG1", "to": "W1"}])
    lay = _sld(doc)
    assert _x(lay, "T1") < _x(lay, "G1") < _x(lay, "T2")


def test_tree_feeding_the_head_of_another_keeps_its_place():
    # the supply of a tree (it feeds its head) is not an addition to it: the order of the document is kept
    inverter = {"type": "inverter", "id": "U1", "ref": "-U1", "children": [_br("QU", [{"type": "load"}])]}
    doc = _doc([_board(1), _board(2), inverter], [{"kind": "infeed", "from": "Q11", "to": "U1"}])
    lay = _sld(doc)
    assert _x(lay, "T1") < _x(lay, "T2") < _x(lay, "U1")


def test_link_across_a_tree_interrupted_with_the_other_end_named():
    # the generator backs board 1 with board 2 drawn between them: a stub at each end, no run across board 2
    doc = _doc([_board(1), _board(2), _supply("G1")],
               [{"kind": "infeed", "from": "QG1", "to": "W1", "label": "Standby", "normally_open": True},
                {"kind": "infeed", "from": "QG1", "to": "W2"}])
    lay = _sld(doc)
    g = _link_groups(lay, "QG1")
    across = [x for x in g if x.attrs.get("data-uw-to") == "W1"][0]
    texts = [t.text for t in _items(across) if isinstance(t, Text)]
    assert "-W1" in texts and "-QG1" in texts and texts.count("Standby") == 2
    assert not any("uw-ref" in (x.cls or "") for x in _groups(across))  # one link for the editor, not a sheet ref
    x2 = _x(lay, "T2")
    for (p, q) in _segments(across):  # both stubs short, none reaching board 2
        assert abs(p[0] - q[0]) + abs(p[1] - q[1]) < 8.0
        assert not min(p[0], q[0]) < x2 < max(p[0], q[0])


def test_several_feeds_on_one_busbar_on_their_own_taps():
    doc = _doc([_board(1), _supply("G1"), _supply("U1", "inverter"), _board(2)],
               [{"kind": "infeed", "from": "QG1", "to": "W1"}, {"kind": "infeed", "from": "QU1", "to": "W1"}])
    lay = _sld(doc)
    routes = [list(_segments(x)) for x in _link_groups(lay, "QG1") + _link_groups(lay, "QU1")]
    assert len(routes) == 2
    ends = {r[-1][1] for r in routes}  # the last point of each route: its tap on the busbar
    assert len(ends) == 2 and len({round(p[1], 3) for p in ends}) == 1  # two taps, at busbar height
    assert not any(_cross(s, t) for s in routes[0] for t in routes[1])
    frame = [r for g in _groups(lay.group) if "board" in (g.cls or "") and g.id == "B1"
             for r in g.items if isinstance(r, Rect)][0]
    assert all(frame.x < p[0] < frame.x + frame.w for p in ends)  # the board frame encloses the taps
