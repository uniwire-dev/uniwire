"""Board, enclosure and view frames drawn round what they enclose, with no edge through a text."""

import uniwire
from tests.drawing_audit import audit
from uniwire.render import render_views
from uniwire.render.scene import Group, Rect


def _ways(prefix, n):
    return [{"type": "breaker", "ref": f"-{prefix}{i}", "in_A": 16, "children": [{"type": "socket"}]}
            for i in range(1, n + 1)]


def _cut(doc):
    return [str(f) for page in render_views(uniwire.load(doc)) for f in audit(page.root)
            if f.kind == "frame_crosses_text"]


def _board_frames(item, out=None):
    out = {} if out is None else out
    if isinstance(item, Group):
        if item.cls and "board" in item.cls.split():
            out[item.id] = next(i for i in item.items if isinstance(i, Rect))
        for i in item.items:
            _board_frames(i, out)
    return out


def test_bus_coupler_text_between_two_boards_is_not_cut_by_their_frames():
    """Two boards side by side joined by a coupler: its text has room between the two frames."""
    doc = {"sources": [
        {"type": "transformer", "ref": "-TA", "children": [{"type": "board", "ref": "=MA", "children": [
            {"type": "breaker", "ref": "-QA0", "in_A": 1000, "children": [
                {"type": "busbar", "id": "BA", "children": _ways("A", 3)}]}]}]},
        {"type": "transformer", "ref": "-TB", "children": [{"type": "board", "ref": "=MB", "children": [
            {"type": "breaker", "ref": "-QB0", "in_A": 1000, "children": [
                {"type": "busbar", "id": "BB", "children": _ways("B", 3)}]}]}]}],
        "links": [{"kind": "tie", "from": "BA", "to": "BB", "normally_open": True, "device": {
            "type": "breaker", "ref": "-QT", "in_A": 2000, "poles": 4, "ir_A": 1800, "label": "Example coupler"}}]}
    assert _cut(doc) == []


def test_enclosure_round_an_auxiliary_device_clears_the_row_title():
    """An enclosure holding an auxiliary device: its top edge is not drawn through the "Auxiliary devices" title."""
    doc = {"sources": [{"type": "grid", "children": [{"type": "board", "id": "MB", "ref": "=MB", "children": [
        {"type": "breaker", "id": "Q0", "ref": "-Q0", "in_A": 40, "children": _ways("F", 3)}]}]}],
        "devices": [{"type": "earth_bar", "id": "PE1", "ref": "-PE1", "label": "Example earth bar"}],
        "enclosures": [{"id": "C1", "kind": "cabinet", "ref": "+C1", "nodes": ["Q0", "PE1"]}]}
    assert _cut(doc) == []


def test_upstream_board_frame_ends_after_its_own_ways():
    """A board feeding two wide sub-boards: its frame ends after its last way, not over the width of the sub-boards
    hanging below it (a large empty dashed box)."""
    cable = {"cores": "5G", "section_mm2": 6, "length_m": 20}
    doc = {"sources": [{"type": "grid", "children": [{"type": "board", "id": "MB", "ref": "=MB", "label": "Main board",
                                                      "children": [
        {"type": "switch_disconnector", "ref": "-Q0", "in_A": 63, "children": [{"type": "busbar", "children": [
            {"type": "breaker", "ref": "-Q1", "in_A": 32, "cable": cable, "children": [
                {"type": "board", "id": "SB1", "ref": "=SB1", "children": _ways("F1", 6)}]},
            {"type": "breaker", "ref": "-Q2", "in_A": 32, "cable": cable, "children": [
                {"type": "board", "id": "SB2", "ref": "=SB2", "children": _ways("F2", 7)}]}]}]}]}]}]}
    frames = _board_frames(render_views(uniwire.load(doc))[0].root)
    mb, sb2 = frames["MB"], frames["SB2"]
    assert mb.x + mb.w < sb2.x + 0.5 * sb2.w  # (it ran to the right end of the second sub-board)
    assert mb.x + mb.w > sb2.x + 10.0  # its last way, above the second sub-board, stays inside


def test_board_name_is_not_written_across_its_incoming_conductor():
    """The first way of a board with room on its left (off-sheet stubs with long texts): the incoming conductor is
    far from the frame's left side, and the name of the board is not written across it."""
    from uniwire.render.scene import Line, Text, text_width

    doc = {"sources": [{"type": "grid", "children": [{"type": "board", "id": "MB", "ref": "=MB",
                                                      "label": "Example main control panel, north building", "children": [
        {"type": "breaker", "id": "Q0", "ref": "-Q0", "in_A": 63, "children": [
            {"type": "breaker", "ref": "-Q1", "in_A": 16, "children": [
                {"type": "motor_starter", "id": "U1", "ref": "-U1", "children": [{"type": "motor"}]}]},
            {"type": "breaker", "ref": "-Q2", "in_A": 16, "children": [{"type": "motor"}]},
            {"type": "breaker", "ref": "-Q9", "in_A": 32, "children": [{"type": "board", "ref": "=SB", "own_sheet": True,
             "children": [{"type": "controller", "id": "A1", "ref": "-A1"}]}]}]}]}]}],
        "links": [{"kind": "control", "from": "U1", "to": "A1", "label": "Example enable signal, wired per risk study"}]}
    page = render_views(uniwire.load(doc))[0]
    board = next(g for g in _groups(page.root) if g.id == "MB")
    name = next(t for t in board.items if isinstance(t, Text) and "Example main" in t.text)
    x0, x1 = name.p[0], name.p[0] + text_width(name.text, name.size)
    q0 = next(g for g in _groups(page.root) if g.id == "Q0")
    xs = {round(i.a[0], 2) for i in _leaves(q0) if isinstance(i, Line) and abs(i.a[0] - i.b[0]) < 1e-6}
    assert xs  # its conductor, through the frame and under the name
    assert not any(x0 < x < x1 for x in xs), (x0, x1, xs)


def _leaves(item):
    if isinstance(item, Group):
        for i in item.items:
            yield from _leaves(i)
    else:
        yield item


def _groups(item):
    if isinstance(item, Group):
        yield item
        for i in item.items:
            yield from _groups(i)
