"""Links to an inverter/charger or a UPS land on the side that carries what they carry: the AC input on top, the DC
terminal on the left, the AC output at the bottom; control and data links on a free side, never on a power terminal."""

import copy

import uniwire
from uniwire.layout import engine, layout_sheet, plan_sheets
from uniwire.model import View
from uniwire.render import default_view
from uniwire.render.scene import Circle, Group, Polyline, Rect, bbox

DOC = {
    "uniwire": "1.0.0",
    "installation": {"system": "1P+N", "earthing": "TT", "un_V": 230},
    "sources": [
        {"type": "grid", "id": "grid", "children": [
            {"type": "main_breaker", "id": "qm", "ref": "-Q0", "in_A": 40, "children": [
                {"type": "board", "id": "mb", "ref": "=MB", "children": [
                    {"type": "breaker", "id": "qinv", "ref": "-Q1", "in_A": 32},
                    {"type": "transfer_switch", "id": "ats", "ref": "-S1", "children": [
                        {"type": "board", "id": "eb", "ref": "=EB", "children": [
                            {"type": "breaker", "id": "q11", "ref": "-Q11", "in_A": 16,
                             "children": [{"type": "load", "id": "l1", "label": "Sockets"}]},
                            {"type": "breaker", "id": "q12", "ref": "-Q12", "in_A": 10,
                             "children": [{"type": "lighting", "id": "l2", "label": "Lights"}]}]}]}]}]}]},
        {"type": "inverter", "id": "inv", "ref": "-T1", "kind": "hybrid", "p_kVA": 6, "children": [
            {"type": "breaker", "id": "qout", "ref": "-Q2", "in_A": 32}]},
        {"type": "pv_array", "id": "pv", "ref": "-G1", "children": [
            {"type": "switch_disconnector", "id": "qpv", "ref": "-Q3", "dc": True}]},
        {"type": "battery", "id": "bat", "ref": "-G2", "children": [
            {"type": "fuse", "id": "fbat", "ref": "-F1", "in_A": 125}]},
        {"type": "controller", "id": "ems", "ref": "-K1", "label": "Energy manager"},
    ],
    "links": [
        {"kind": "infeed", "from": "qinv", "to": "inv"},
        {"kind": "infeed", "from": "qpv", "to": "inv"},
        {"kind": "infeed", "from": "fbat", "to": "inv"},
        {"kind": "transfer", "from": "qout", "to": "ats"},
        {"kind": "data", "from": "ems", "to": "inv", "protocol": "Modbus"},
    ],
}


def _groups(item):
    if isinstance(item, Group):
        yield item
        for i in item.items:
            yield from _groups(i)


def _sld(doc):
    view = default_view(doc)
    return [layout_sheet(doc, view, s) for s in plan_sheets(doc, view)]


def _link_paths(lay, frm, to):
    """The polylines of the link from ``frm`` to ``to`` (its own group, hit areas left out)."""
    g = next(g for g in _groups(lay.group) if g.attrs.get("data-uw-from") == frm and g.attrs.get("data-uw-to") == to)
    return [it for it in g.items if isinstance(it, Polyline) and not it.closed], g


def _inv(lay):
    """The inverter as drawn: (x of its axis, top of its input lead, bottom of its output lead, left of its body,
    height of its DC terminal)."""
    g = next(g for g in _groups(lay.group) if g.id == "inv" and "uw-node" in (g.cls or ""))
    body = next(it for it in g.items if isinstance(it, Rect))
    _x0, top, _x1, bottom = bbox(g)
    return body.x + body.w / 2, top, bottom, body.x, top + (bottom - top) * 0.3


def _touches(paths, x, y, tol=0.05):
    return any(abs(p[0] - x) < tol and abs(p[1] - y) < tol for pl in paths for p in (pl.points[0], pl.points[-1]))


def test_sides_of_an_inverter_charger():
    index = uniwire.resolve.build_index(doc := uniwire.load(DOC))
    where = {(l.from_, l.to): engine._port_where(l, 1 if l.to == "inv" else 0, index) for l in doc.links[:4]}
    assert where == {("qinv", "inv"): "top", ("qpv", "inv"): "left", ("fbat", "inv"): "left",
                     ("qout", "ats"): None}  # (the transfer leaves -Q2, below the inverter: not on it)


def test_ac_input_on_top_dc_on_the_left():
    lay = _sld(uniwire.load(DOC))[0]
    x, top, _bottom, tx, ty = _inv(lay)
    ac, _ = _link_paths(lay, "qinv", "inv")
    assert _touches(ac, x, top)  # on the top of its input lead
    for frm in ("qpv", "fbat"):  # both DC links on its DC terminal, never on the AC input
        dc, _ = _link_paths(lay, frm, "inv")
        assert _touches(dc, tx, ty)
        assert not _touches(dc, x, top)


def test_two_kinds_never_on_one_point():
    lay = _sld(uniwire.load(DOC))[0]
    ends = {}
    for frm in ("qinv", "qpv", "fbat"):
        paths, _ = _link_paths(lay, frm, "inv")
        ends[frm] = {(round(p[0], 2), round(p[1], 2)) for pl in paths for p in (pl.points[-1],)}
    assert not ends["qinv"] & (ends["qpv"] | ends["fbat"])


def test_data_link_off_the_dc_terminal():
    lay = _sld(uniwire.load(DOC))[0]
    x, _top, _bottom, left, _ty = _inv(lay)
    paths, _ = _link_paths(lay, "ems", "inv")
    end = paths[0].points[-1] if abs(paths[0].points[-1][0] - x) < 10 else paths[0].points[0]
    assert end[0] > left + 0.5  # its right side or its top, not its left side


def test_battery_into_a_ups_on_its_dc_side():
    doc = copy.deepcopy(DOC)
    doc["sources"][1] = {"type": "grid", "id": "g2", "children": [
        {"type": "breaker", "id": "qu", "ref": "-Q5", "in_A": 32, "children": [
            {"type": "ups", "id": "inv", "ref": "-U1", "children": [{"type": "breaker", "id": "qout", "ref": "-Q2"}]}]}]}
    doc["links"] = [{"kind": "infeed", "from": "fbat", "to": "inv"}]
    lay = _sld(uniwire.load(doc))[0]
    _x, _top, _bottom, tx, ty = _inv(lay)
    paths, g = _link_paths(lay, "fbat", "inv")
    assert _touches(paths, tx, ty)  # on its body (past the "UPS" text beside it), not on its AC input conductor
    assert not any(isinstance(it, Circle) for it in g.items)  # (no junction on that conductor)


def test_ac_output_link_from_the_bottom():
    doc = copy.deepcopy(DOC)
    doc["sources"][1]["children"] = [{"type": "battery", "id": "bat2"}]  # only a DC side in the tree
    doc["links"] = [{"kind": "infeed", "from": "qinv", "to": "inv"}, {"kind": "infeed", "from": "inv", "to": "q11"}]
    lay = _sld(uniwire.load(doc))[0]
    assert next(n for n in lay.lnodes if n.node is not None and n.node.id == "inv").dc_side == 1  # its battery on
    x, _top, bottom, _tx, _ty = _inv(lay)  # its DC side, on the left: its output free for its AC links
    paths, _ = _link_paths(lay, "inv", "q11")
    assert _touches(paths, x, bottom)


def test_multiline_dc_links_on_the_dc_pair():
    from uniwire.layout.multiline import conductors

    doc = uniwire.load({**DOC, "views": [{"id": "ml", "kind": "multi-line"}]})
    c = conductors(doc)
    assert {"L+", "L-"} <= set(c["inv"].out) and {"L1", "N"} <= set(c["inv"].out)
    pages = uniwire.render_pages(doc, View(id="ml", kind="multi-line"))
    drawn = {(g.attrs.get("data-uw-from"), g.attrs.get("data-uw-to")): g for p in pages for g in _groups(p.root)
             if "uw-link" in (g.cls or "")}
    for frm in ("qpv", "fbat"):  # drawn (they were left out: no AC conductor to land on), conductor by conductor
        g = drawn[(frm, "inv")]
        conds = {x.attrs.get("data-uw-cond") for x in _groups(g)}
        assert {"L+", "L-"} <= conds and not conds & {"L1", "N"}
