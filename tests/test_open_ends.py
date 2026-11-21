"""Single-line drawings: no conductor lead ending in nothing (unfed roots, devices outside the power path,
nodes feeding nothing) and a way with no load ending on a free terminal, not on an off-sheet arrow."""

from uniwire import load
from uniwire.layout import layout_sheet, plan_sheets
from uniwire.render import default_view
from uniwire.render.scene import Circle, Group, Line, Polyline
from uniwire.symbols import symbol, without_leads


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


def _layout(data):
    doc = load(data)
    view = default_view(doc)
    return [layout_sheet(doc, view, s) for s in plan_sheets(doc, view)][0]


def _node(lay, nid):
    return next(n for n in lay.lnodes + lay.annex if n.node is not None and n.node.id == nid)


def _sym_group(lay, nid):
    return next(g for g in _groups(lay.group) if g.id == nid and "sym" in (g.cls or ""))


def _vertical(group):
    return [i for i in _items(group) if isinstance(i, Line) and abs(i.a[0] - i.b[0]) < 1e-6]


DOC = {
    "installation": {"system": "3P+N", "un_V": 400},
    "sources": [{"type": "busbar", "id": "MB", "ref": "=MB", "label": "Main busbar", "children": [
        {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 32, "children": [{"type": "motor", "id": "M1"}]},
        {"type": "breaker", "id": "Q2", "ref": "-Q2", "in_A": 20},
        {"type": "breaker", "id": "Q3", "ref": "-Q3", "in_A": 40, "children": [
            {"type": "transformer", "id": "T1", "ref": "-T1", "sn_kVA": 10}]}]}],
    "devices": [{"type": "meter", "id": "P1", "ref": "-P1"}, {"type": "controller", "id": "A1", "ref": "-A1"},
                {"type": "battery", "id": "G1", "ref": "-G1"}, {"type": "spd", "id": "F1", "ref": "-F1"},
                {"type": "breaker", "id": "Q9", "ref": "-Q9"}],
    "links": [{"kind": "measure", "from": "Q1", "to": "P1"}, {"kind": "data", "from": "P1", "to": "A1"},
              {"kind": "data", "from": "G1", "to": "A1"}, {"kind": "earth", "from": "F1", "to": "MB"}],
}


def test_root_busbar_has_no_lead_from_above():
    lay = _layout(DOC)
    assert _node(lay, "MB").no_in
    bus = next(g for g in _groups(lay.group) if g.id == "MB" and g.cls == "uw-busbar")
    assert not _vertical(bus)  # the bar alone: no conductor arriving on it from nowhere


def test_devices_outside_the_power_path_have_no_conductor_leads():
    lay = _layout(DOC)
    for nid in ("P1", "A1", "G1", "F1"):
        n = _node(lay, nid)
        drawn = list(_items(_sym_group(lay, nid)))
        assert len(drawn) == len(without_leads(n.sym, True, True).items) < len(n.sym.items), nid


def test_switching_device_outside_the_tree_keeps_its_contacts():
    lay = _layout(DOC)  # Q9: in no link, drawn among the auxiliary devices
    q9 = _node(lay, "Q9")
    assert len(list(_items(_sym_group(lay, "Q9")))) == len(q9.sym.items)  # its fixed contacts: the blade pivots on them


def test_transformer_feeding_nothing_has_no_output_lead():
    lay = _layout(DOC)
    t1 = _node(lay, "T1")
    assert t1.no_out and not t1.no_in
    g = _sym_group(lay, "T1")
    circles = [i for i in _items(g) if isinstance(i, Circle)]
    (lead,) = _vertical(g)  # its input lead only, above the windings
    assert max(lead.a[1], lead.b[1]) <= min(c.c[1] for c in circles)


def test_way_with_no_load_ends_on_a_free_terminal():
    lay = _layout(DOC)
    assert _node(lay, "Q2").open_feeder
    items = list(_items(lay.group))
    assert not [i for i in items if isinstance(i, Polyline) and i.closed and i.style.fill]  # no off-sheet arrow head
    assert [i for i in items if isinstance(i, Circle) and abs(i.r - 0.7) < 1e-6]


def test_power_link_keeps_the_leads_it_lands_on():
    lay = _layout({"sources": [
        {"type": "grid", "children": [{"type": "board", "children": [
            {"type": "breaker", "id": "Q3"}, {"type": "breaker", "children": [{"type": "socket"}]}]}]},
        {"type": "generator", "children": [{"type": "breaker", "id": "QG", "children": [{"type": "load"}]}]}],
        "links": [{"kind": "parallel", "from": "QG", "to": "Q3"}]})
    assert not _node(lay, "Q3").no_out


def test_without_leads_keeps_a_symbol_whose_lead_is_its_body():
    fuse = symbol("fuse")
    assert len(without_leads(fuse, True, True).items) == len(fuse.items)
    meter = symbol("meter")
    assert len(without_leads(meter, True, True).items) == len(meter.items) - 2
