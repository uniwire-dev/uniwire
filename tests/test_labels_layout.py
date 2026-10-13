"""Displayed texts and placement of auxiliary devices, link routes, frames and notes."""

from uniwire import load, render_pages
from uniwire.labels import annotation, cable_text, cell
from uniwire.layout import layout_sheet, plan_sheets
from uniwire.render import default_view
from uniwire.render.scene import BUS, Group, Line, Polyline, Text


def _items(item):
    if isinstance(item, Group):
        for i in item.items:
            yield from _items(i)
    else:
        yield item


def _texts(item) -> list[str]:
    return [i.text for i in _items(item) if isinstance(i, Text)]


def _hit(a, b, pad=0.0):
    return min(a[2], b[2]) - max(a[0], b[0]) > pad and min(a[3], b[3]) - max(a[1], b[1]) > pad


def _layout(doc):
    view = default_view(doc)
    return [layout_sheet(doc, view, s) for s in plan_sheets(doc, view)]


def test_cable_text_awg_and_kcmil():
    c = load({"sources": [{"type": "grid", "children": [
        {"type": "breaker", "id": "a", "cable": {"size_awg": "12"}},
        {"type": "breaker", "id": "b", "cable": {"cores": "2-", "size_awg": "#12"}},
        {"type": "breaker", "id": "c", "cable": {"cores": "4-", "size_awg": "600 kcmil", "parallel": 3}},
        {"type": "breaker", "id": "d", "cable": {"cores": "2-#12+G", "size_awg": "#12"}},
        {"type": "breaker", "id": "e", "cable": {"cores": "3G", "section_mm2": 2.5, "size_awg": "14"}}]}]})
    texts = [cable_text(n.cable) for n in c.sources[0].children]
    assert texts == ["#12", "2-#12", "3x(4-600 kcmil)", "2-#12+G", "3G2.5"]


def test_feeder_table_shows_awg_with_neutral_header():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "breaker", "in_A": 20, "cable": {"size_awg": "12"}, "children": [{"type": "socket"}]},
        {"type": "breaker", "in_A": 15, "cable": {"size_awg": "14"}, "children": [{"type": "lighting"}]}]}]}],
        "views": [{"cartouche": ["label", "cable"]}]})
    texts = _texts(render_pages(doc)[0].root)
    assert "#12" in texts and "#14" in texts
    assert "Cable" in texts and "Cable (mm²)" not in texts


def test_rcd_free_text_delay_is_displayed():
    doc = load({"sources": [{"type": "grid", "children": [
        {"type": "rcd", "in_A": 63, "idn_mA": 1000, "delay": "0.5 s"},
        {"type": "rcd", "in_A": 63, "idn_mA": 300, "delay": "S"},
        {"type": "rcd", "in_A": 63, "idn_mA": 300, "delay": "60"},
        {"type": "rcd", "in_A": 63, "idn_mA": 30, "delay": "inst"}]}]})
    lines = [" ".join(annotation(n)) for n in doc.sources[0].children]
    assert "0.5 s" in lines[0]
    assert lines[1].endswith(" S")
    assert "60 ms" in lines[2]
    assert "inst" not in lines[3]


def test_points_singular_and_plural():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "lighting", "points": 1}, {"type": "socket", "points": 4}]}]})
    one, four = doc.sources[0].children
    assert cell("points", {"leaf": one}) == "1 pt"
    assert cell("points", {"leaf": four}, "fr") == "4 pts"


def test_spare_imd_and_busway_taps_have_table_cells():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "breaker", "ref": "-Q1", "in_A": 25, "curve": "C", "children": [
            {"type": "busbar", "kind": "busway", "ref": "-WL1", "children": [
                {"type": "lighting", "label": "Aisle 1"}, {"type": "lighting", "label": "Aisle 2"}]}]},
        {"type": "spare", "ref": "-Q2", "in_A": 16, "poles": "2P"},
        {"type": "insulation_monitor", "ref": "-B1", "label": "IMD"}]}]}],
        "views": [{"cartouche": ["label", "ref", "protection", "poles"]}]})
    texts = _texts(render_pages(doc)[0].root)
    assert texts.count("-Q1") == 3  # the protection itself + both trunking tap-offs
    assert texts.count("C25") == 3  # annotation + both tap-off cells
    assert "16A" in texts and "2P" in texts and "-B1" in texts


def test_generator_symbol_follows_supply_system():
    def sub(system):
        doc = load({"installation": {"system": system}, "sources": [{"type": "generator", "id": "G", "children": [
            {"type": "breaker"}]}]})
        lay = _layout(doc)[0]
        g = next(n for n in lay.lnodes if n.node is not None and n.node.id == "G")
        return [t.text for t in g.sym.items if isinstance(t, Text)]
    assert "1~" in sub("1P+N")
    assert "3~" in sub("3P+N")


def test_notes_printed_on_a4_portrait():
    doc = load({"meta": {"notes": ["Remember the spare way"]}, "views": [{"paper": "A4", "orientation": "portrait"}],
                "sources": [{"type": "grid", "children": [{"type": "breaker", "children": [{"type": "socket"}]}]}]})
    texts = _texts(render_pages(doc)[0].root)
    assert any("Remember the spare way" in t for t in texts)


def test_parallel_link_end_has_no_open_feeder_arrow():
    doc = load({"sources": [
        {"type": "grid", "children": [{"type": "board", "children": [
            {"type": "breaker", "id": "Q3"}, {"type": "breaker", "children": [{"type": "socket"}]}]}]},
        {"type": "generator", "children": [{"type": "breaker", "id": "QG", "children": [{"type": "load"}]}]}],
        "links": [{"kind": "parallel", "from": "QG", "to": "Q3"}]})
    q3 = next(n for n in _layout(doc)[0].lnodes if n.node is not None and n.node.id == "Q3")
    assert not q3.open_feeder


DEVICES = {
    "sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "breaker", "id": f"Q{i}", "ref": f"-Q{i}", "in_A": 16, "curve": "C",
         "children": [{"type": "contactor", "id": f"KM{i}", "ref": f"-KM{i}", "in_A": 25,
                       "children": [{"type": "motor"}]}]} for i in range(1, 5)]}]}],
    "devices": [{"type": "protection_relay", "id": f"R{i}", "ref": f"-KF{i}",
                 "label": "Long description of the auxiliary relay"} for i in range(1, 4)],
    "links": [{"kind": "control", "from": f"R{i}", "to": f"KM{i}", "label": "trip"} for i in range(1, 4)],
}


def test_auxiliary_devices_avoid_existing_drawing_and_keep_full_labels():
    lay = _layout(load(DEVICES))[0]
    assert len(lay.annex) == 3
    taken = [n.sym_box() for n in lay.lnodes if n.sym.height > 0] + [n.ann_box() for n in lay.lnodes if n.ann]
    for a in lay.annex:
        assert "Long description of the auxiliary relay" in a.ann
        for box in [a.sym_box(), a.ann_box()]:
            assert not any(_hit(box, t, 0.3) for t in taken)
        taken += [a.sym_box(), a.ann_box()]


def test_device_drawn_on_the_sheet_of_its_linked_node():
    doc = load({"sources": [{"type": "grid", "children": [
        {"type": "breaker", "children": [{"type": "socket"}]},
        {"type": "board", "id": "B2", "own_sheet": True, "children": [
            {"type": "breaker", "children": [{"type": "contactor", "id": "KM", "children": [{"type": "motor"}]}]}]}]}],
        "devices": [{"type": "protection_relay", "id": "R", "ref": "-KF1"}],
        "links": [{"kind": "control", "from": "R", "to": "KM"}]})
    lays = _layout(doc)
    assert len(lays) == 2
    assert [a.node.id for a in lays[0].annex] == []
    assert [a.node.id for a in lays[1].annex] == ["R"]


def test_plc_channel_links_fan_out():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "breaker", "children": [{"type": "plc", "id": "PLC", "modules": [{"slot": 1, "kind": "relay_out"}]}]}] + [
        {"type": "breaker", "children": [{"type": "contactor", "id": f"KM{i}", "children": [{"type": "motor"}]}]}
        for i in range(1, 4)]}]}],
        "links": [{"kind": "control", "from": "PLC", "from_port": f"1.{i}", "to": f"KM{i}"} for i in range(1, 4)]})
    page = render_pages(doc)[0]
    texts = _texts(page.root)
    assert {"1.1", "1.2", "1.3"} <= set(texts)
    routes = [i.points for i in _items(page.root) if isinstance(i, Polyline) and i.style.dash and len(i.points) >= 3]
    starts = {round(p[0][0], 2) for p in routes}
    channels = {round(p[1][1], 2) for p in routes}
    assert len(starts) == 3 and len(channels) == 3  # one lane and one channel per port


def test_link_to_another_sheet_ends_on_offpage_reference():
    doc = load({"sources": [{"type": "grid", "children": [
        {"type": "breaker", "children": [{"type": "contactor", "id": "KM", "children": [{"type": "motor"}]}]},
        {"type": "board", "ref": "B2", "own_sheet": True, "children": [
            {"type": "breaker", "children": [{"type": "plc", "id": "PLC", "ref": "-A1"}]}]}]}],
        "links": [{"kind": "control", "from": "PLC", "to": "KM"}]})
    pages = render_pages(doc)
    assert len(pages) == 2
    assert "-A1 → sheet 2" in _texts(pages[0].root)
    assert any(t.endswith("→ sheet 1") for t in _texts(pages[1].root))


def test_frame_label_kept_off_the_busbar():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "breaker", "id": "A", "children": [{"type": "socket"}]},
        {"type": "breaker", "id": "B", "children": [{"type": "socket"}]}]}]}],
        "views": [{"frames": [{"label": "Cell 1", "nodes": ["A", "B"]}]}]})
    lay = _layout(doc)[0]
    bus_ys = [i.a[1] for i in _items(lay.group) if isinstance(i, Line) and i.style.width == BUS]
    label = next(i for i in _items(lay.group) if isinstance(i, Text) and i.text == "Cell 1")
    top, bottom = label.p[1] - label.size * 0.8, label.p[1] + label.size * 0.2
    assert bus_ys and all(not (top - 0.5 < y < bottom + 0.5) for y in bus_ys)


def test_conductor_count():
    from uniwire.labels import conductor_count
    d = load({"sources": [{"type": "grid", "children": [
        {"type": "breaker", "poles": "1P+N", "children": [{"type": "socket"}]},
        {"type": "breaker", "poles": "3P", "cable": {"cores": "5G", "section_mm2": 2.5}, "children": [{"type": "cooking"}]},
        {"type": "breaker", "poles": "4P", "children": [{"type": "load"}]},
        {"type": "breaker", "children": [{"type": "motor", "phases": 3}]},
        {"type": "breaker", "phase": "L2", "children": [{"type": "lighting"}]},
        {"type": "breaker", "children": [{"type": "load"}]}]}]})
    counts = [conductor_count([b.children[0], b], "3P+N") for b in d.sources[0].children]
    assert counts == [2, 4, 4, 3, 2, 4]


def _sld(view=None, **inst):
    return load({"installation": inst, "views": [view or {}], "sources": [{"type": "grid", "children": [
        {"type": "board", "id": "B", "children": [
            {"type": "breaker", "poles": "1P+N", "phase": "L2", "children": [{"type": "socket"}]},
            {"type": "breaker", "poles": "3P+N", "children": [{"type": "load"}]}]}]}]})


def test_conductor_marks_and_phase_on_feeders():
    texts = _texts(render_pages(_sld({"cartouche": ["label", "phase"]}))[0].root)
    assert "L2+N" in texts and "+N" in texts  # phase + uncut neutral (1P+N), uncut neutral of the 3P+N feeder
    assert "L1L2L3" in texts  # phase cell of the three-phase feeder
    marks = [g for g in _items_groups(render_pages(_sld())[0].root) if g.cls == "conductors"]
    assert marks and len(marks[0].items) > 0
    off = [g for g in _items_groups(render_pages(_sld({"conductor_marks": False}))[0].root) if g.cls == "conductors"]
    assert not off or not off[0].items


def _marks(doc):
    """Conductor marks drawn: [(node id, class suffix)] in drawing order ('cm-4', 'cm-3N'...)."""
    return [(g.id, g.cls.split()[1]) for g in _items_groups(render_pages(doc)[0].root)
            if g.cls and g.cls.startswith("conductor-mark")]


def test_conductor_marks_where_the_conductors_change():
    doc = load({"installation": {"system": "3P+N", "earthing": "TN-S"}, "sources": [{"type": "grid", "id": "G", "children": [
        {"type": "board", "children": [{"type": "switch_disconnector", "id": "QS", "poles": "4P", "children": [
            {"type": "busbar", "children": [
                {"type": "breaker", "id": "Q1", "poles": "3P+N", "children": [
                    {"type": "busbar", "children": [
                        {"type": "breaker", "id": "Q11", "poles": "1P+N", "phase": "L1", "children": [{"type": "socket", "id": "S11"}]},
                        {"type": "breaker", "id": "Q12", "poles": "1P+N", "phase": "L2", "children": [{"type": "lighting", "id": "S12"}]}]}]},
                {"type": "breaker", "id": "Q2", "poles": "3P", "children": [
                    {"type": "contactor", "id": "KM2", "poles": "3P", "children": [{"type": "motor", "id": "M2", "phases": 3}]}]},
                {"type": "breaker", "id": "Q3", "poles": "4P", "children": [
                    {"type": "rcd", "id": "F3", "poles": "4P", "children": [{"type": "load", "id": "L3"}]}]}]}]}]}]}]})
    marks = dict(_marks(doc))
    assert marks["G"] == "cm-4"  # incomer: 3P+N supply, 4 conductors
    assert "QS" not in marks  # 4P main switch: unchanged
    assert marks["Q1"] == "cm-3N"  # 3P+N: three strokes and an uncut neutral, unlike 4P
    assert marks["S11"] == marks["S12"] == "cm-1N"  # 1P+N feeders, with their phase
    assert marks["Q2"] == "cm-3"  # 3P, no neutral downstream
    assert "KM2" not in marks and "M2" not in marks  # same three conductors down to the motor: not repeated
    assert "Q3" not in marks and "F3" not in marks  # 4P below a 4-conductor busbar: unchanged
    assert marks["L3"] == "cm-4"  # an outgoing cable with no mark above it in its column keeps its own
    texts = _texts(render_pages(doc)[0].root)
    assert "L1+N" in texts and "L2+N" in texts and "+N" in texts
    off = load({**doc.model_dump(by_alias=True, exclude_none=True), "views": [{"conductor_marks": False}]})
    assert not _marks(off)


def test_three_pole_device_with_neutral_downstream():
    from uniwire.labels import feeder_mark, poles_mark
    assert poles_mark("3P", True) == (3, True) and poles_mark("3P") == (3, False) and poles_mark("4P") == (4, False)
    assert poles_mark("2P") == (2, False) and poles_mark("1P+N") == (1, True)
    d = load({"sources": [{"type": "grid", "children": [
        {"type": "breaker", "poles": "3P", "cable": {"cores": "5G", "section_mm2": 6}, "children": [{"type": "load"}]},
        {"type": "breaker", "poles": "4P", "cable": {"cores": "5G", "section_mm2": 6}, "children": [{"type": "load"}]},
        {"type": "breaker", "poles": "3P", "cable": {"cores": "4-#10+G"}, "children": [{"type": "load"}]}]}]})
    got = [feeder_mark([b.children[0], b], "3P+N") for b in d.sources[0].children]
    assert got == [(3, True), (4, False), (3, True)]


def _items_groups(item):
    if isinstance(item, Group):
        yield item
        for i in item.items:
            yield from _items_groups(i)


def test_pen_split_marker():
    assert "PEN" in _texts(render_pages(_sld(earthing="TN-C-S"))[0].root)  # default: first board
    assert "PEN" not in _texts(render_pages(_sld(earthing="TN-S"))[0].root)
    doc = load({"installation": {"earthing": "TN-C-S"}, "sources": [{"type": "grid", "children": [
        {"type": "board", "children": [{"type": "breaker", "children": [
            {"type": "board", "pen_split": True, "children": [{"type": "breaker"}, {"type": "breaker"}]}]}]}]}]})
    lay = _layout(doc)[0]
    assert _texts(lay.group).count("PEN") == 1
