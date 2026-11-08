"""What a board frame encloses: its devices, not the equipment at the far end of its outgoing cables."""

import pytest

import uniwire
from uniwire.model import View
from uniwire.render.scene import Group, Rect

CABLE = {"cores": "3G", "section_mm2": 6, "length_m": 30}
DOC = {"installation": {"earthing": "TT", "system": "3P+N", "un_V": 400}, "sources": [{"type": "grid", "children": [
    {"type": "board", "id": "DB", "ref": "DB1", "children": [
        {"type": "switch_disconnector", "id": "Q0", "in_A": 63, "cable": CABLE, "children": [  # its incoming cable
            {"type": "busbar", "id": "BB", "in_A": 63, "children": [
                {"type": "breaker", "id": "QPV", "in_A": 25, "cable": CABLE, "children": [
                    {"type": "inverter", "id": "INV", "p_kVA": 5, "children": [
                        {"type": "switch_disconnector", "id": "QDC", "dc": True, "children": [
                            {"type": "pv_array", "p_kW": 5}]}]}]},
                {"type": "breaker", "id": "QA", "in_A": 16, "cable": CABLE, "children": [
                    {"type": "contactor", "id": "KA", "in_A": 20, "children": [{"type": "water_heater"}]}]},
                {"type": "breaker", "id": "QT", "in_A": 6, "cable": CABLE, "children": [
                    {"type": "transformer", "id": "T1", "sn_kVA": 0.4, "u1_V": 400, "u2_V": 230, "children": [
                        {"type": "socket"}]}]},
            ]}]}]}]}]}


def _drawn(doc, view):
    """Board frame (dashed rectangle) and the extent of each node group."""
    page = uniwire.render_pages(uniwire.load(doc), view)[0]
    frames, boxes = [], {}

    def pts(x, out):
        if isinstance(x, Group):
            for c in x.items:
                pts(c, out)
        elif isinstance(x, Rect):
            out += [(x.x, x.y), (x.x + x.w, x.y + x.h)]
        else:
            out += [getattr(x, a) for a in ("p", "a", "b") if isinstance(getattr(x, a, None), tuple)]
            out += list(getattr(x, "points", []))

    def walk(g):
        for i in g.items:
            if isinstance(i, Group):
                if i.id and i.id not in boxes:
                    p = []
                    pts(i, p)
                    if p:
                        boxes[i.id] = (min(q[1] for q in p), max(q[1] for q in p))
                walk(i)
            elif isinstance(i, Rect) and i.style.dash and i.w > 20:
                frames.append((i.y, i.y + i.h))
    walk(page.root)
    return frames[0], boxes


@pytest.mark.parametrize("view", [None, View(id="ml", kind="multi-line")])
def test_equipment_beyond_a_cable_is_outside_the_board(view):
    (top, bottom), boxes = _drawn(DOC, view)
    assert boxes["INV"][0] > bottom and boxes["QDC"][0] > bottom  # an inverter at the end of a cable, and its side
    for nid in ("BB", "KA", "T1"):  # the busbar after the incomer, a contactor after a breaker with a cable, and
        assert top < boxes[nid][0] and boxes[nid][1] < bottom, nid  # a control transformer: in the board


def test_changeover_at_the_end_of_the_only_feeder_is_outside():
    doc = {"installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400}, "sources": [{"type": "grid", "children": [
        {"type": "board", "id": "MCC", "children": [{"type": "breaker", "id": "Q2", "in_A": 32, "cable": CABLE, "children": [
            {"type": "transfer_switch", "id": "TS", "children": [{"type": "motor", "p_kW": 7.5}]}]}]}]}]}
    (top, bottom), boxes = _drawn(doc, None)
    assert boxes["Q2"][1] < bottom < boxes["TS"][0]


def test_accessories_beside_the_incomer_keep_the_board_busbar_inside():
    ways = [{"type": "breaker", "id": f"Q{i}", "in_A": 16, "children": [{"type": "socket"}]} for i in (1, 2)]
    doc = {"installation": {"earthing": "TT", "system": "3P+N", "un_V": 400}, "sources": [{"type": "grid", "children": [
        {"type": "board", "id": "TD", "children": [
            {"type": "spd", "id": "F0", "spd_type": "2"},
            {"type": "meter", "id": "P0"},
            {"type": "switch_disconnector", "id": "Q0", "in_A": 63, "cable": CABLE, "children": [
                {"type": "busbar", "id": "JdB", "children": ways + [{"type": "spare"}]}]}]}]}]}
    for view in (None, View(id="ml", kind="multi-line")):
        (top, bottom), boxes = _drawn(doc, view)
        for nid in ("JdB", "Q1", "Q2"):
            assert top < boxes[nid][0] and boxes[nid][1] < bottom, (view, nid)


RING = {"installation": {"earthing": "TN-S", "system": "3P", "un_V": 11000}, "sources": [{"type": "grid", "children": [
    {"type": "board", "id": "RMU", "ref": "RMU", "children": [
        {"type": "breaker", "id": "QF1", "in_A": 400, "poles": "3P", "cable": CABLE, "children": [
            {"type": "transformer", "id": "TA", "sn_kVA": 1000, "u1_V": 11000, "u2_V": 415}]},
        {"type": "breaker", "id": "QF2", "in_A": 400, "poles": "3P", "cable": CABLE, "children": [
            {"type": "switch_disconnector", "id": "QL2", "in_A": 400, "poles": "3P", "children": [
                {"type": "transformer", "id": "TB", "sn_kVA": 1000, "u1_V": 11000, "u2_V": 415}]},
            {"type": "spd", "id": "F2"}]}]}]}]}


@pytest.mark.parametrize("view", [None, View(id="ml", kind="multi-line")])
def test_transformer_behind_its_local_switch_is_outside_the_board_too(view):
    (top, bottom), boxes = _drawn(RING, view)
    assert boxes["TA"][0] > bottom  # a transformer at the end of a cable
    assert boxes["TB"][0] > bottom and boxes["QL2"][0] > bottom  # and one behind its local switch, with the switch
    assert boxes["QF2"][1] < bottom  # the outgoing breaker stays in the board
