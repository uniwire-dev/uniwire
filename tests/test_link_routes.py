"""Where links end and how they run (single-line): a route never closes round what it passes (it reads as a frame),
a power link joins a conductor rather than the body of a device (it reads as a bypass of it) and crosses as few
conductors as it can, a link between two stacked devices stays on the side facing the other one. Invented boards."""

import pytest

from tests.drawing_audit import _groups, _hover_paths, _symbol_boxes
from uniwire import load
from uniwire.layout.routing import (
    BUS_CROSS,
    DASHED_BUS_CROSS,
    WIRE_CROSS,
    End,
    Obstacles,
    path_cost,
    route_grid,
    wraps,
)
from uniwire.render import render_views
from uniwire.render.scene import Circle, Group
from uniwire.render.semantics import _conductor_segments, _crossings, has_cls

DOC = {"uniwire": "1.0.0-draft", "meta": {"title": "Routes"}, "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
       "views": [{"kind": "single-line", "paper": "A3"}]}


def _feeders(prefix: str, n: int) -> list[dict]:
    return [{"type": "breaker", "id": f"{prefix}{i}", "ref": f"-{prefix}{i}", "in_A": 16, "curve": "C", "poles": "3P",
             "children": [{"type": "load", "ref": f"-E{prefix}{i}", "label": f"Zone {i}"}]} for i in range(1, n + 1)]


def _links(root: Group) -> dict[str, Group]:
    return {g.attrs["data-uw-link"]: g for g in _groups(root) if has_cls(g, "uw-link") and "data-uw-link" in g.attrs}


def _route(page, kind: str) -> tuple[str, list[tuple[float, float]]]:
    kinds = {k: g.attrs.get("data-uw-kind") for k, g in _links(page.root).items()}
    return next((k, pl.points) for k, pl in _hover_paths(page.root) if kinds.get(k) == kind)


def _crossed(page, link: str, pts: list[tuple[float, float]]) -> int:
    """Conductors the route crosses, its own strokes and its ends left out."""
    own = set(_conductor_segments(_links(page.root)[link], True))
    total = sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(pts, pts[1:]))
    return len([c for c in _crossings(pts, [s for s in _conductor_segments(page.root) if s not in own], 0.3)
                if 1.0 < c < total - 1.0])


def _axis(page, nid: str) -> tuple[float, tuple[float, float, float, float]]:
    """x of the leads of a drawn device (its longest vertical stroke), and the box of its strokes."""
    boxes = next(b for n, b, _g in _symbol_boxes(page.root) if n == nid)
    lead = max((b for b in boxes if b[2] - b[0] < 0.3), key=lambda b: b[3] - b[1])
    return (lead[0] + lead[2]) / 2, (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                                     max(b[3] for b in boxes))


def _dots(g: Group) -> list[tuple[float, float]]:
    return [it.c for it in g.items if isinstance(it, Circle)]


# ---------------------------------------------------------------- the cost of going round
def test_wraps_counts_the_turns_closing_a_route_round():
    assert wraps([(0, 0), (0, 5), (5, 5), (5, 0)]) == 0  # a U: open on one side
    assert wraps([(0, 0), (0, 5), (5, 5), (5, 0), (10, 0), (10, 5)]) == 0  # a meander
    assert wraps([(6, 2), (5, 2), (5, -3), (-1, -3), (-1, 10), (3, 10)]) == 1  # left, up, left, down, right: round
    assert wraps([(6, 2), (5, 2), (5, -3), (-1, -3), (-1, 10)], then=0) == 1  # ... with the trunk it joins
    assert wraps([(5, 0), (5, 5), (-1, 5), (-1, 8), (-2, 8), (-2, 0), (3, 0)]) == 1  # a jog does not hide it


def test_grid_route_does_not_close_round_a_symbol():
    """From the left side of a symbol to a line going on to the right below it: down beside the symbol, across one
    conductor, rather than round the top of the text on its left (with the line, that closes a frame round it)."""
    obs = Obstacles()
    obs.add_box((5, 5, 15, 15))  # the symbol
    obs.add_box((-6, 8, 2, 30))  # a text on its left
    obs.add_hline(20, 2.7, 4.3)  # a conductor between them
    start, goal, window = [End(4.4, 10, "left")], [End(-12, 34, "up")], (-20, -10, 25, 40)
    plain, _a, _b = route_grid(obs, start, goal, window, record=False, then=[0], bend=4.0)
    assert wraps(plain, then=0) == 1  # (the cheapest way without the cost: round the top of the text)
    pts, _a, _b = route_grid(obs, start, goal, window, record=False, then=[0], bend=4.0, wrap=50.0)
    assert wraps(pts, then=0) == 0, pts


# ---------------------------------------------------------------- interlocked contactors
def test_interlock_between_stacked_contactors_stays_on_their_facing_side():
    doc = {**DOC, "sources": [{"type": "grid", "id": "S", "children": [
        {"type": "breaker", "id": "Q0", "ref": "-Q0", "in_A": 32, "poles": "3P", "children": _feeders("Q", 2)}]}],
        "devices": [{"type": "contactor", "id": f"K{i}", "ref": f"-K{i}", "label": f"Contactor {i}",
                     "normal_state": "open", "locks": ["LOCK_A"]} for i in (1, 2)],
        "links": [{"kind": "interlock", "from": "K1", "to": "K2", "label": "mechanical interlock, one at a time"}]}
    page = render_views(load(doc))[0]
    _k, pts = _route(page, "interlock")
    axes = {nid: _axis(page, nid)[0] for nid in ("K1", "K2")}
    for p, q in zip(pts, pts[1:]):  # no run across the axis (the leads) of either contactor
        if abs(p[1] - q[1]) < 1e-9:
            assert not any(min(p[0], q[0]) + 1e-6 < x < max(p[0], q[0]) - 1e-6 for x in axes.values()), pts
    assert len({round(p[0], 3) for p in (pts[0], pts[-1])}) == 1  # both ends on the same side: a bracket


# ---------------------------------------------------------------- power links
def _sections() -> dict:
    """Two incomers: the first section feeds a UPS, its output through a transfer switch whose second input is a bypass
    from the first section; the second section is also fed by a generator ending on an outgoing arrow."""
    ups = {"type": "breaker", "id": "QU", "ref": "-QU", "in_A": 250, "poles": "3P", "children": [
        {"type": "ups", "id": "U1", "ref": "-U1", "sn_kVA": 100, "children": [
            {"type": "transfer_switch", "id": "TS", "ref": "-TS", "in_A": 250, "poles": "3P", "mode": "manual",
             "children": [{"type": "busbar", "id": "BUS2", "ref": "BUS2", "label": "Secured section",
                           "children": _feeders("R", 3)}]}]}]}
    return {**DOC, "sources": [
        {"type": "grid", "id": "S1", "children": [{"type": "breaker", "id": "QA", "ref": "-QA", "in_A": 400, "poles": "3P",
                                                    "children": [{"type": "busbar", "id": "BUS1", "ref": "BUS1", "label": "Section A",
                                                                  "children": _feeders("A", 6) + [ups]}]}]},
        {"type": "grid", "id": "S2", "children": [{"type": "breaker", "id": "QB", "ref": "-QB", "in_A": 400, "poles": "3P",
                                                    "children": [{"type": "busbar", "id": "BUS3", "ref": "BUS3", "label": "Section B",
                                                                  "children": _feeders("B", 3)}]}]},
        {"type": "generator", "id": "G1", "children": [{"type": "breaker", "id": "QG", "ref": "-QG", "in_A": 400, "poles": "3P",
                                                         "children": [{"type": "offpage", "id": "OG", "label": "To section B"}]}]}],
        "links": [{"kind": "transfer", "from": "BUS1", "to": "TS", "label": "bypass"},
                  {"kind": "infeed", "from": "OG", "to": "BUS3", "label": "standby"}]}


def test_bypass_from_a_busbar_taps_it_near_the_transfer_switch():
    """The bypass leaves its busbar where its run to the side input crosses the fewest feeders: not from the far end
    of the busbar across every feeder of the section."""
    page = render_views(load(_sections()))[0]
    k, pts = _route(page, "transfer")
    assert _crossed(page, k, pts) <= 1, pts


def test_power_link_from_an_outgoing_arrow_joins_its_conductor():
    """A generator conductor ending on an arrow and feeding a busbar: the link leaves the conductor (a junction dot), at
    the level of the busbar, not the arrow (the busbar end turned down to the arrow reads as one more outgoing line)."""
    page = render_views(load(_sections()))[0]
    k, pts = _route(page, "infeed")
    assert len(pts) == 2 and abs(pts[0][1] - pts[1][1]) < 1e-6, pts  # straight across, level with the busbar
    assert any(abs(d[0] - pts[0][0]) < 1e-6 and abs(d[1] - pts[0][1]) < 1e-6 for d in _dots(_links(page.root)[k]))


def test_parallel_device_lands_on_the_output_of_the_device_it_follows():
    """A surge arrester connected after a fuse: its link ends on the conductor below the fuse (a junction dot), not on
    the side of the fuse body (that reads as a bypass of the fuse)."""
    doc = {**DOC, "sources": [{"type": "pv_array", "id": "PV", "ref": "PV1", "children": [
        {"type": "busbar", "id": "BD", "ref": "BD", "label": "DC box", "children": [
            {"type": "fuse", "id": "F1", "ref": "-F1", "in_A": 16, "poles": "2P", "children": [
                {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 16, "poles": "2P", "children": [
                    {"type": "load", "ref": "-E1", "label": "Inverter input"}]}]},
            {"type": "spd", "id": "SPD1", "ref": "-F2", "label": "Surge arrester"}]}]}],
        "links": [{"kind": "parallel", "from": "SPD1", "to": "F1"}]}
    page = render_views(load(doc))[0]
    k, pts = _route(page, "parallel")
    x, box = _axis(page, "F1")
    end = pts[-1]
    assert abs(end[0] - x) < 1e-6 and end[1] > box[3], (end, x, box)
    assert any(abs(d[0] - end[0]) < 1e-6 and abs(d[1] - end[1]) < 1e-6 for d in _dots(_links(page.root)[k]))


# ---------------------------------------------------------------- a signal link into a board
def _group(g: int, n: int, contactor: bool = False) -> dict:
    feeders = [{"type": "breaker", "id": f"Q{g}{i}", "ref": f"-Q{g}{i}", "in_A": 16, "curve": "C", "poles": "1P+N",
                "children": [{"type": "load", "ref": f"-E{g}{i}", "label": f"Circuit {g}.{i}"}]} for i in range(1, n + 1)]
    if contactor:  # a contactor under one feeder in the middle of the board
        feeders[-2]["children"] = [{"type": "contactor", "id": "KM1", "ref": "-KM1", "in_A": 20,
                                    "children": feeders[-2]["children"]}]
    return {"type": "rcd", "id": f"F{g}", "ref": f"-F{g}", "in_A": 40, "idn_mA": 30, "poles": "2P", "children": feeders}


def test_signal_link_into_a_board_crosses_its_busbars_rather_than_every_feeder():
    """A control link from the meter above a board to a contactor under one of its feeders: down into the board
    across its busbars (drawn with a gap there), not along the board below the breakers across every feeder."""
    doc = {"uniwire": "1.0.0-draft", "meta": {"title": "Meter signal"},
           "installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
           "views": [{"kind": "single-line", "paper": "A3"}],
           "sources": [{"type": "grid", "id": "S", "label": "Public network", "supply": "Example tariff", "un_V": 230,
                        "children": [
               {"type": "meter", "id": "M", "ref": "-P1", "label": "Smart meter", "kind": "Example model", "in_A": 90,
                "children": [
                   {"type": "main_breaker", "id": "Q0", "ref": "-Q0", "label": "Main switch", "range_A": "15-45",
                    "in_A": 45, "idn_mA": 500, "selective": True, "poles": "2P",
                    "cable": {"cores": "3G", "section_mm2": 16, "length_m": 20}, "children": [
                       {"type": "board", "id": "DB", "ref": "=DB", "label": "Distribution board", "children": [
                           _group(1, 7), _group(2, 6, contactor=True), _group(3, 6)]}]}]}]}],
           "links": [{"kind": "control", "from": "M", "to": "KM1", "label": "Tariff contact"}]}
    page = render_views(load(doc))[0]
    k, pts = _route(page, "control")
    own = set(_conductor_segments(_links(page.root)[k], True))
    feeders = [s for s in _conductor_segments(page.root) if s not in own and abs(s[0][0] - s[1][0]) < 1e-6]
    assert not _crossings(pts, feeders, 0.3), pts
    assert _crossed(page, k, pts) <= 2, pts  # the board's busbar and that of the group


def test_a_busbar_costs_a_dashed_link_a_crossing_and_a_solid_one_a_tap():
    """A solid link across a busbar reads as a tap; a dashed one, drawn with a gap there, is a crossing like that of a
    few feeders: cheaper than running along a board across every feeder."""
    obs = Obstacles()
    obs.buses.append((10.0, 0.0, 100.0))
    obs.hlines.append((10.0, 0.0, 100.0))
    across = [(50.0, 0.0), (50.0, 20.0)]
    assert path_cost(obs, across, solid=True) - path_cost(obs, across) == pytest.approx(BUS_CROSS - DASHED_BUS_CROSS)
    assert DASHED_BUS_CROSS < 10 * WIRE_CROSS < BUS_CROSS
