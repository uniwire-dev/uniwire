"""Readability of documents with many control links: a PLC whose modules drive and read many devices, a safety relay
naming its terminals, drives on a fieldbus. Invented machine panels."""

import pytest

from tests.drawing_audit import _walk
from uniwire import load
from uniwire.layout.engine import _leader_label
from uniwire.layout.routing import Obstacles
from uniwire.render import render_views
from uniwire.render.scene import Group, Line, Rect, Text


def panel(motors: int, drives: int, feedback: bool = True) -> dict:
    """A machine panel: ``motors`` started by contactors the PLC drives (and reads back), ``drives`` speed drives on
    a fieldbus, every contactor and drive also stopped by a safety relay through its own terminal."""
    feeders, links = [], []
    for i in range(1, motors + 1):
        feeders.append({"type": "breaker", "id": f"Q{i}", "ref": f"-Q{i}", "in_A": 10, "curve": "D", "poles": "3P",
                        "children": [{"type": "contactor", "id": f"K{i}", "ref": f"-K{i}", "in_A": 12, "poles": "3P",
                                      "children": [{"type": "motor", "ref": f"-M{i}", "label": f"Belt {i}",
                                                    "p_kW": 2.2}]}]})
        links.append({"kind": "control", "from": "PLC", "from_port": f"2.{i}", "to": f"K{i}", "label": f"Run {i}"})
        if feedback:
            links.append({"kind": "measure", "from": f"K{i}", "to": "PLC", "to_port": f"1.{i}", "label": f"Fb {i}"})
        links.append({"kind": "trip", "from": "SR", "from_port": f"S{i}", "to": f"K{i}"})
    for j in range(1, drives + 1):
        feeders.append({"type": "breaker", "id": f"QF{j}", "ref": f"-QF{j}", "in_A": 20, "curve": "D", "poles": "3P",
                        "children": [{"type": "motor_starter", "method": "vfd", "id": f"U{j}", "ref": f"-U{j}",
                                      "in_A": 18, "children": [{"type": "motor", "ref": f"-MV{j}",
                                                                "label": f"Fan {j}", "p_kW": 7.5}]}]})
        links.append({"kind": "data", "from": "PLC", "to": f"U{j}", "protocol": "PROFINET"})
        links.append({"kind": "control", "from": "PLC", "from_port": f"4.{j}", "to": f"U{j}", "label": "Speed"})
        links.append({"kind": "trip", "from": "SR", "from_port": f"T{j}", "to": f"U{j}", "label": "STO"})
    modules = [{"slot": 1, "kind": "di", "channels": 16}, {"slot": 2, "kind": "do", "channels": 16},
               {"slot": 3, "kind": "ai", "channels": 4}, {"slot": 4, "kind": "ao", "channels": 4}]
    control = {"type": "breaker", "ref": "-QC", "in_A": 6, "curve": "C", "poles": "1P+N", "children": [
        {"type": "power_supply", "ref": "-T1", "u1_V": 230, "u2_V": 24, "output": "DC", "in_A": 10, "children": [
            {"type": "plc", "id": "PLC", "ref": "-A1", "role": "controller", "modules": modules},
            {"type": "controller", "id": "SR", "ref": "-A2", "label": "Safety relay", "symbol_text": "SR"}]}]}
    return {"uniwire": "1.0.0", "meta": {"title": "Machine panel"},
            "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
            "sources": [{"type": "grid", "un_V": 400, "children": [
                {"type": "board", "ref": "CP1", "in_A": 100, "system": "3P+N", "children": [
                    {"type": "switch_disconnector", "ref": "-Q0", "in_A": 100, "poles": "4P",
                     "children": [control] + feeders}]}]}],
            "links": links}


def _node(root, nid: str):
    if isinstance(root, Group):
        if root.id == nid and root.cls and "uw-node" in root.cls.split():
            return root
        for i in root.items:
            found = _node(i, nid)
            if found is not None:
                return found
    return None


def _box(g: Group) -> tuple[float, float, float, float]:
    rects = [r for r, _l, _o in _walk(g) if isinstance(r, Rect)]
    return (min(r.x for r in rects), min(r.y for r in rects), max(r.x + r.w for r in rects),
            max(r.y + r.h for r in rects))


@pytest.mark.parametrize("i", [1, 6, 10])
def test_label_of_a_link_read_by_a_plc_goes_near_the_device_it_reads(i):
    """'Fb 10' runs from the contactor to a PLC input: written near the contactor, not among the PLC's wires."""
    page = render_views(load(panel(10, 3)))[0]
    k = next(n.a[0] for n, _l, _o in _walk(_node(page.root, f"K{i}")) if isinstance(n, Line))  # its conductor
    plc = _box(_node(page.root, "PLC"))
    t = next(t for t, _l, _o in _walk(page.root) if isinstance(t, Text) and t.text == f"Fb {i}")
    assert abs(t.p[0] - k) < 15.0 < abs(t.p[0] - plc[2]), t


def test_leader_of_a_label_is_square_to_its_link():
    """A label with no room along its link, beside the link's far stretch: the leader leaves the link at right
    angles (it ran slanting from the middle of the longest stretch: it read as one more link)."""
    obs = Obstacles()
    obs.add_box((20.0, 40.0, 65.0, 75.0))  # all round the middle of the link is taken
    g = Group([])
    assert _leader_label(obs, [(30.0, 50.0), (70.0, 50.0), (70.0, 80.0)], "Feedback", 1.6, g)
    line = next(i for i in g.items if isinstance(i, Line))
    assert abs(line.a[0] - line.b[0]) < 1e-9 or abs(line.a[1] - line.b[1]) < 1e-9, line
