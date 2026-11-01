"""Conductor-count marks of DC lines: two poles, never a '+N' neutral."""

from pathlib import Path

import uniwire
from uniwire.labels import feeder_mark
from uniwire.layout.engine import _line_marks
from uniwire.resolve import iter_nodes

EX = Path(__file__).resolve().parents[1] / "examples"


def test_dc_feeder_has_no_neutral():
    doc = uniwire.load(EX / "11_tiny_house_off_grid_pv.uniwire.json")
    fuse = next(n for n, *_ in iter_nodes(doc) if n.id == "F31")  # 12 V fuse box, 1P fuse
    assert feeder_mark([*fuse.children, fuse], "DC") == (2, False)
    assert feeder_mark([*fuse.children, fuse], "1P+N") == (1, True)  # same poles on an AC system


def test_dc_lines_marked_two_poles():
    doc = uniwire.load(EX / "11_tiny_house_off_grid_pv.uniwire.json")
    _, m_out = _line_marks(doc)
    nodes = {n.id: n for n, *_ in iter_nodes(doc)}
    for nid in ("F1", "F2", "F31", "Q1"):  # fuses and DC switch behind the 48 V and 12 V boards
        assert m_out[id(nodes[nid])] == (2, False), nid
    assert m_out[id(nodes["Q10"])] == (1, True)  # 230 V side of the inverter: phase and neutral


BATTERY_MOTOR = {  # a battery feeding a DC motor through single-pole devices, no system stated anywhere
    "uniwire": "1.0.0", "installation": {"earthing": "IT", "un_V": 48},
    "sources": [{"type": "battery", "id": "B", "un_V": 48, "children": [
        {"type": "fuse", "id": "F1", "ref": "-F1", "in_A": 40, "poles": "1P", "children": [
            {"type": "switch_disconnector", "id": "S1", "ref": "-S1", "in_A": 40, "poles": "1P", "children": [
                {"type": "motor", "id": "M1", "ref": "-M1", "label": "Pump", "un_V": 48}]}]}]}]}


def test_battery_line_marked_two_poles_and_its_motor_drawn_dc():
    from uniwire.render import render_views
    from uniwire.render.scene import Group, Text

    doc = uniwire.load(BATTERY_MOTOR)
    _, m_out = _line_marks(doc)
    nodes = {n.id: n for n, *_ in iter_nodes(doc)}
    assert m_out[id(nodes["F1"])] == (2, False) and m_out[id(nodes["S1"])] == (2, False)

    def texts(item):
        return [item.text] if isinstance(item, Text) else [t for i in item.items for t in texts(i)] \
            if isinstance(item, Group) else []

    every = [t for pg in render_views(doc) for t in texts(pg.root)]
    assert not any("+N" in t for t in every)
    assert "=" in every and "1~" not in every
