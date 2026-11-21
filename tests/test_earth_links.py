"""Earth links never land on the power path: not on a conductor, a busbar or a switching device."""

import math

import pytest

import uniwire
from uniwire.model import View
from uniwire.render import render_views
from uniwire.render.scene import Circle, Group, Line, Polyline, Text, text_width

SWITCHING = {"breaker", "rcd", "switch_disconnector", "fuse", "contactor"}
POWER_LINKS = {"transfer", "tie", "bypass", "parallel", "infeed"}


def _doc(links, devices=(), electrode=True):
    return {"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
            "sources": [{"type": "grid", "children": [
                {"type": "board", "id": "DB", "ref": "DB1", "children": [
                    {"type": "switch_disconnector", "id": "Q0", "in_A": 63, "children": [
                        {"type": "busbar", "id": "BB", "in_A": 63, "children": [
                            {"type": "rcd", "id": "R1", "in_A": 40, "idn_mA": 30, "children": [
                                {"type": "breaker", "id": "F1", "in_A": 16, "children": [{"type": "socket"}]},
                                {"type": "breaker", "id": "F2", "in_A": 10, "children": [{"type": "lighting"}]}]},
                            {"type": "rcd", "id": "R2", "in_A": 40, "idn_mA": 30, "children": [
                                {"type": "breaker", "id": "F3", "in_A": 20, "children": [
                                    {"type": "inverter", "id": "INV", "p_kVA": 3}]}]},
                            {"type": "breaker", "id": "F4", "in_A": 20, "children": [
                                {"type": "motor", "id": "M1", "p_kW": 1.5}]}]}]}]}]}],
            "devices": [*([{"type": "earth", "id": "E", "label": "Earth electrode"}] if electrode else []), *devices],
            "links": links}


def _segments(item):
    if isinstance(item, Line):
        yield item.a, item.b
    elif isinstance(item, Polyline):
        yield from zip(item.points, item.points[1:])
    elif isinstance(item, Group) and "uw-hit" not in (item.cls or ""):
        for c in item.items:
            yield from _segments(c)


def _dist(p, s):
    (ax, ay), (bx, by) = s
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
    return math.hypot(ax + t * dx - p[0], ay + t * dy - p[1])


def _scan(doc, view=None):
    """Power conductors (tree edges, busbars, incoming feeds), switching symbols, and the earth link groups."""
    page = uniwire.render_pages(uniwire.load(doc), view)[0]
    power, switches, earth = [], [], []
    types = {n.id: n.type for n, _, _ in uniwire.resolve.iter_nodes(uniwire.load(doc))}

    def walk(g):
        cls = (g.cls or "").split()
        if "uw-link" in cls:
            if g.attrs.get("data-uw-kind") == "earth":
                earth.append(g)
            elif g.attrs.get("data-uw-kind") in POWER_LINKS:
                power.extend(_segments(g))
            return
        cond = g.attrs.get("data-uw-cond")  # multi-line: one conductor; the protective one is where earth lands
        if cond is not None or (("uw-edge" in cls or "uw-busbar" in cls)
                                and not any("data-uw-cond" in c.attrs for c in _walk(g))):
            if cond not in ("PE", "PEN"):
                power.extend(_segments(g))
            return
        if "uw-ref" in cls:
            power.extend(s for c in g.items if isinstance(c, Line) for s in _segments(c))
        if g.id and types.get(g.id) in SWITCHING and "sym" in cls:
            switches.extend(_segments(g))
        for c in g.items:
            if isinstance(c, Group):
                walk(c)
    walk(page.root)
    return power, switches, earth


def _ends(g):
    for it in g.items:
        if isinstance(it, Polyline) and not it.closed and len(it.points) > 1:
            yield it.points[0]
            yield it.points[-1]


def _check(doc, view=None):
    power, switches, earth = _scan(doc, view)
    assert earth and power
    for g in earth:
        for p in _ends(g):
            assert min(_dist(p, s) for s in power) > 1.5, (g.attrs, p)
            assert not switches or min(_dist(p, s) for s in switches) > 1.0, (g.attrs, p)
        for t in (i for i in g.items if isinstance(i, Text)):  # its label off every conductor
            w = text_width(t.text, t.size)
            x0 = t.p[0] - {"start": 0.0, "middle": w / 2, "end": w}[t.anchor]
            box = (x0, t.p[1] - 0.8 * t.size, x0 + w, t.p[1] + 0.1 * t.size)
            for a, b in power:
                assert not any(box[0] < a[0] + (b[0] - a[0]) * k / 10 < box[2]
                               and box[1] < a[1] + (b[1] - a[1]) * k / 10 < box[3] for k in range(11)), t.text
    return earth


def _frame(doc):
    page = uniwire.render_pages(uniwire.load(doc))[0]
    return next(i for i in _walk(page.root) if i.cls and "board" in i.cls).items[0]


def test_earth_link_to_a_board_lands_on_an_earth_terminal_of_its_frame():
    doc = _doc([{"kind": "earth", "from": "M1", "to": "DB", "label": "PE 16 mm2"}], electrode=False)
    rect, ends = _frame(doc), [p for g in _check(doc) for p in _ends(g)]
    assert any(abs(p[0] - rect.x) < 0.01 or abs(rect.x + rect.w - p[0]) < 0.01 for p in ends)  # on a side of it


def test_earth_device_inside_a_board_is_its_earth_point():
    """An earth electrode drawn inside the board's frame: the link between them is a short straight lead from it to
    the frame."""
    doc = _doc([{"kind": "earth", "from": "E", "to": "DB"}])
    rect, earth = _frame(doc), _check(doc)
    (line,) = [it for g in earth for it in g.items if isinstance(it, Polyline) and not it.closed]
    assert len(line.points) == 2
    (ax, ay), (bx, by) = line.points
    assert ax == bx or ay == by
    on_frame = [abs(x - rect.x) < 0.01 or abs(x - rect.x - rect.w) < 0.01 or abs(y - rect.y) < 0.01
                or abs(y - rect.y - rect.h) < 0.01 for x, y in line.points]
    assert on_frame.count(True) == 1


def _walk(g):
    for c in g.items:
        if isinstance(c, Group):
            yield c
            yield from _walk(c)


@pytest.mark.parametrize("target", ["R1", "M1", "BB"])
def test_earth_link_to_a_device_or_busbar_stays_off_the_power_path(target):
    _check(_doc([{"kind": "earth", "from": "E", "to": target, "label": "Bonding"}]))


@pytest.mark.parametrize("other", ["DB", "E"])
def test_earth_link_to_a_device_whose_left_side_carries_conductors(other):
    """An inverter/charger at the head of its tree: its DC side and the feed reaching it are on its left side, its
    earth elsewhere on its body."""
    doc = _doc([{"kind": "infeed", "from": "F4", "to": "INV2"}, {"kind": "earth", "from": "INV2", "to": other}])
    doc["sources"].append({"type": "inverter", "id": "INV2", "p_kVA": 3, "children": [
        {"type": "breaker", "id": "QB", "in_A": 63, "children": [{"type": "battery", "id": "BAT"}]},
        {"type": "breaker", "id": "QL", "in_A": 20, "children": [{"type": "socket"}]}]})
    _check(doc)


def test_several_earth_links_on_one_board_get_their_own_points():
    doc = _doc([{"kind": "earth", "from": "E", "to": "DB"}, {"kind": "earth", "from": "M1", "to": "DB"}])
    _, _, earth = _scan(doc)
    ends = {(round(p[0], 2), round(p[1], 2)) for g in earth for p in _ends(g)}
    assert len(ends) == 4
    _check(doc)


def test_multi_line_earth_link_lands_on_the_protective_conductor():
    _check(_doc([{"kind": "earth", "from": "E", "to": "DB"}]), View(id="ml", kind="multi-line", auxiliaries=True))


def test_stacked_stub_leads_are_attached_to_their_device():
    """Several earth links leaving one earth bar as interrupted lines: the stubs below its body start on a riser from
    the stub above (with a junction dot), not in empty space."""
    def board(i):
        return {"type": "board", "id": f"DB{i}", "children": [{"type": "switch_disconnector", "in_A": 40, "children": [
            {"type": "busbar", "children": [{"type": "breaker", "in_A": 16, "children": [
                {"type": "motor", "id": f"M{i}_{k}", "p_kW": 1}]} for k in range(14)]}]}]}
    doc = {"installation": {"earthing": "TT", "system": "3P+N", "un_V": 400},
           "sources": [{"type": "grid", "children": [board(1), board(2)]}],
           "devices": [{"type": "earth_bar", "id": "PEB"}],
           "links": [{"kind": "earth", "from": "PEB", "to": "M1_0"},
                     *({"kind": "earth", "from": "PEB", "to": f"M2_{k}"} for k in range(4))]}
    stubs = 0
    for page in render_views(uniwire.load(doc)):
        sym = next((g for g in _walk(page.root) if g.id == "PEB" and "sym" in (g.cls or "")), None)
        if sym is None:
            continue
        pts = [p for s in _segments(sym) for p in s]
        box = (min(p[0] for p in pts) - 1.3, min(p[1] for p in pts) - 1.3, max(p[0] for p in pts) + 1.3,
               max(p[1] for p in pts) + 1.3)
        links = [g for g in _walk(page.root) if g.attrs.get("data-uw-from") == "PEB"]
        risers = [s for g in links for it in g.items if isinstance(it, Line) for s in _segments(it)]
        for g in links:
            if not any("uw-ref" in (c.cls or "") for c in g.items if isinstance(c, Group)):
                continue
            for it in g.items:
                if isinstance(it, Polyline) and not it.closed and len(it.points) == 2:
                    p, stubs = it.points[0], stubs + 1
                    assert box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3] or any(
                        _dist(p, s) < 0.01 for s in risers), p
    assert stubs >= 3


def test_stubs_of_other_kinds_keep_a_lead_each():
    """Control links from one device to other sheets: past its body each stub has its own lead from the device, never
    a junction dot joining two links (that would tie different signals together)."""
    def board(i):
        return {"type": "board", "id": f"DB{i}", "children": [{"type": "switch_disconnector", "in_A": 40, "children": [
            {"type": "busbar", "children": [{"type": "breaker", "in_A": 16, "children": [
                {"type": "contactor", "id": f"K{i}_{k}", "children": [{"type": "motor", "p_kW": 1}]}]}
                for k in range(14)]}]}]}
    doc = {"installation": {"earthing": "TT", "system": "3P+N", "un_V": 400},
           "sources": [{"type": "grid", "children": [board(1), board(2)]}],
           "devices": [{"type": "meter", "id": "CTL"}],
           "links": [{"kind": "control", "from": "CTL", "to": "K1_0"},
                     *({"kind": "control", "from": "CTL", "to": f"K2_{k}"} for k in range(5))]}
    leads = 0
    for page in render_views(uniwire.load(doc)):
        groups = [g for g in _walk(page.root) if g.attrs.get("data-uw-from") == "CTL"]
        for g in groups:
            assert not any(isinstance(i, Circle) for i in g.items), "a junction dot on a control link"
            mine = [s for i in g.items if isinstance(i, Polyline) and not i.closed for s in _segments(i)]
            others = [s for o in groups if o is not g for i in o.items if isinstance(i, Polyline) and not i.closed
                      for s in _segments(i)]
            for a, b in mine:  # never touching another link's lead
                assert all(_dist(a, s) > 0.3 and _dist(b, s) > 0.3 for s in others)
            leads += sum(1 for i in g.items if isinstance(i, Polyline) and len(i.points) == 3)
    assert leads >= 3  # stubs past the body, each on its own lead
