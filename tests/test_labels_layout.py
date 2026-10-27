"""Displayed texts and placement of auxiliary devices, link routes, frames and notes."""

from tests.conftest import ROOT
from uniwire import load, render_pages
from uniwire.labels import annotation, cable_text, cell
from uniwire.layout import layout_sheet, plan_sheets
from uniwire.render import default_view
from uniwire.render.scene import BUS, Group, Line, Polyline, Text, text_width


def _items(item):
    if isinstance(item, Group):
        for i in item.items:
            yield from _items(i)
    else:
        yield item


def _texts(item) -> list[str]:
    return [i.text for i in _items(item) if isinstance(i, Text)]


def _items_groups(item):
    if isinstance(item, Group):
        yield item
        for i in item.items:
            yield from _items_groups(i)


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
    assert "16 A" in texts and "2P" in texts and "-B1" in texts


def test_spare_fed_by_its_own_breaker_shows_the_breaker():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "rcd", "ref": "-F1", "in_A": 40, "idn_mA": 30, "children": [
            {"type": "breaker", "ref": "-Q7", "in_A": 20, "curve": "C", "poles": "2P", "children": [
                {"type": "spare", "label": "Spare workshop"}]}]},
        {"type": "socket", "label": "Sockets"}]}]}],
        "views": [{"cartouche": ["ref", "label", "protection", "poles"]}]})
    texts = _texts(render_pages(doc)[0].root)
    assert texts.count("-Q7") == 2  # annotation + table cell
    assert texts.count("C20") == 2


def test_board_fed_through_shows_its_feeder_and_cells_stay_under_their_feeders():
    cab = {"cores": "5G", "section_mm2": 6, "length_m": 20}
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "ref": "TGBT", "children": [
        {"type": "breaker", "ref": "-Q3", "in_A": 40, "curve": "C", "cable": cab, "children": [
            {"type": "transformer", "ref": "-T3", "sn_kVA": 20, "children": [
                {"type": "board", "ref": "TD-N", "label": "Lighting and small power panel of the north workshop",
                 "children": [{"type": "offpage", "label": "TD-N schedule", "target": "sheet 4"}]}]}]},
        {"type": "breaker", "ref": "-Q4", "in_A": 32, "curve": "C", "cable": cab, "children": [
            {"type": "board", "ref": "CT-1", "kind": "enclosure", "children": [
                {"type": "heating", "ref": "-E4", "label": "Dryer heater", "p_kW": 12}]}]},
        {"type": "socket", "label": "Sockets"}]}]}],
        "views": [{"cartouche": ["label", "ref", "protection", "cable"]}]})
    texts = _texts(render_pages(doc)[0].root)
    assert texts.count("C40") == 2 and texts.count("C32") == 2  # annotation + the cell of the board's column
    (lay,) = _layout(doc)
    xs = sorted(c.x for c in lay.columns)  # before the sheet is moved to the origin: compare spacings
    cells = [g for g in _items_groups(lay.group) if g.attrs.get("data-uw-field") == "protection"]
    centres = sorted(t.p[0] for g in cells for t in _items(g) if isinstance(t, Text))
    assert len(centres) == 2 and abs((centres[1] - centres[0]) - (xs[1] - xs[0])) < 0.01


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


def _hybrid_doc():
    """Example 53: hybrid inverter drawn as a source of its own, PV strings with their surge protectors and a
    battery on the DC side, AC input fed from the main board by an infeed link, a narrow rooftop enclosure."""
    return load(ROOT / "examples" / "53_office_hybrid_inverter_pv_battery.uniwire.json")


def _segments(group):
    for i in _items(group):
        if isinstance(i, Line):
            yield i.a, i.b
        elif isinstance(i, Polyline) and not i.closed:
            yield from zip(i.points, i.points[1:])


def test_inverter_dc_side_keeps_a_string_with_its_surge_protector():
    lay = _layout(_hybrid_doc())[0]
    inv = next(n for n in lay.lnodes if n.node is not None and n.node.id == "INV")
    assert [c.node.ref for c in inv.children[:inv.dc_side]] == ["-QS1", "-QS2", "-FB1"]


def test_long_frame_label_wrapped_clear_of_conductors():
    lay = _layout(_hybrid_doc())[0]
    lines = [i for i in _items(lay.group) if isinstance(i, Text) and i.bold and i.text
             and i.text.split()[0] in ("+R1", "Rooftop", "DC", "isolator", "enclosure")]
    assert len(lines) >= 2  # too wide for the box: wrapped
    for t in lines:
        w = text_width(t.text, t.size)
        x0 = t.p[0] - w if t.anchor == "end" else t.p[0]
        box = (x0, t.p[1] - t.size * 0.8, x0 + w, t.p[1] + t.size * 0.2)
        for (ax, ay), (bx, by) in _segments(lay.group):
            seg = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
            assert not _hit(box, seg, 0.05), (t.text, seg)


def test_infeed_to_inverter_lands_on_its_input_away_from_the_busbars():
    lay = _layout(_hybrid_doc())[0]
    inv = next(g for g in _items_groups(lay.group) if g.id == "INV")
    sym = [p for i in _items(inv) for p in ([i.a, i.b] if isinstance(i, Line) else getattr(i, "points", []))]
    left, top, right = min(p[0] for p in sym), min(p[1] for p in sym), max(p[0] for p in sym)
    link = next(g for g in _items_groups(lay.group) if g.attrs.get("data-uw-link") == "L_IN")
    pts = next(i.points for i in _items(link) if isinstance(i, Polyline))
    assert left < pts[-1][0] < right and pts[-1][1] <= top + 0.01  # on top: the side is the DC terminal
    buses = [(i.a, i.b) for i in _items(lay.group) if isinstance(i, Line) and i.style.width == BUS]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        if abs(ay - by) < 1e-9 and abs(ax - bx) > 20:  # long horizontal run: not along a busbar
            assert all(not (abs(a[1] - ay) < 5.0 and min(max(a[0], b[0]), max(ax, bx))
                            - max(min(a[0], b[0]), min(ax, bx)) > 20) for a, b in buses)


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
    assert "L1-L2-L3" in texts  # phase cell of the three-phase feeder
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


def _standby_doc():
    """A board on a generator, also reachable from the main board through a normally open infeed."""
    return load({"sources": [
        {"type": "grid", "children": [{"type": "board", "id": "MB", "children": [
            {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 63, "children": [{"type": "load", "label": "Workshop"}]},
            {"type": "breaker", "id": "Q2", "ref": "-Q2", "in_A": 100, "poles": "4P"}]}]},
        {"type": "generator", "id": "G1", "ref": "G1", "children": [
            {"type": "breaker", "id": "QG", "ref": "-QG", "in_A": 100, "poles": "4P", "children": [
                {"type": "board", "id": "SB", "ref": "SB", "label": "Standby board", "children": [
                    {"type": "breaker", "ref": "-Q21", "in_A": 16, "children": [{"type": "load", "label": "Pumps"}]}]}]}]}],
        "links": [{"id": "L_SB", "kind": "infeed", "from": "Q2", "to": "SB", "normally_open": True}]})


def test_infeed_without_a_channel_above_its_feeder_still_drawn(monkeypatch):
    import uniwire.layout.engine as engine
    route, capped = engine.route, []

    def no_channel_above(obs, a, b, y_min=None, y_max=None, **kw):
        if y_max is not None and y_max < max(a.y, b.y) + 1.0:  # channel kept above the feeder: none free
            capped.append(1)
            return []
        return route(obs, a, b, y_min, y_max, **kw)

    monkeypatch.setattr(engine, "route", no_channel_above)
    lay = _layout(_standby_doc())[0]
    assert capped
    link = next(g for g in _items_groups(lay.group) if g.attrs.get("data-uw-link") == "L_SB")
    assert any(isinstance(i, Polyline) and len(i.points) >= 2 for i in _items(link))


def test_link_without_any_channel_left_out_not_fatal(monkeypatch):
    import uniwire.layout.engine as engine
    monkeypatch.setattr(engine, "route", lambda *a, **kw: [])
    assert render_pages(_standby_doc(), default_view(_standby_doc()))


def _wings_doc(n, own_sheet=None):
    """Building wings, each on a transfer switch with its own standby generator."""
    def wing(c):
        board = {"type": "board", "id": f"SB{c}", "ref": f"SB-{c}", "children": [
            {"type": "transfer_switch", "id": f"ATS{c}", "ref": f"-QA{c}", "in_A": 250, "poles": "4P", "children": [
                {"type": "breaker", "ref": f"-Q{c}1", "in_A": 32, "children": [{"type": "load", "label": f"Wing {c} loads"}]}]}]}
        if c == own_sheet:
            board["own_sheet"] = True
        return {"type": "breaker", "id": f"Q{c}", "ref": f"-Q{c}", "in_A": 250, "poles": "4P", "children": [board]}
    cs = "ABCD"[:n]
    return load({"sources": [{"type": "grid", "children": [{"type": "board", "id": "MSB", "ref": "MSB",
                                                             "children": [wing(c) for c in cs]}]}]
                 + [{"type": "generator", "id": f"G{c}", "ref": f"-G{c}", "children": [
                     {"type": "breaker", "id": f"QG{c}", "ref": f"-QG{c}", "in_A": 250, "poles": "4P"}]} for c in cs],
                 "links": [{"kind": "transfer", "from": f"QG{c}", "to": f"ATS{c}"} for c in cs]})


def _bbox(g):
    pts = [p for i in _items(g) for p in ([i.a, i.b] if isinstance(i, Line) else getattr(i, "points", []))]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def test_standby_generators_of_several_transfer_switches_side_by_side():
    lay = _layout(_wings_doc(3))[0]
    gens = sorted(_bbox(g) for g in _items_groups(lay.group) if g.id in ("GA", "GB", "GC"))
    assert len(gens) == 3
    assert all(b[0] >= a[2] + 3.0 for a, b in zip(gens, gens[1:]))  # no two drawn on top of each other


def test_standby_generator_follows_its_board_to_another_sheet():
    doc = _wings_doc(2, own_sheet="B")
    sheets = _layout(doc)
    ids = [{g.id for g in _items_groups(lay.group)} for lay in sheets]
    assert "GA" in ids[0] and "GB" not in ids[0]
    assert any("GB" in s and "ATSB" in s for s in ids[1:])


def _audit_kinds(doc):
    from tests.drawing_audit import audit
    return [f for pg in render_pages(doc, default_view(doc)) for f in audit(pg.root)]


def test_transfer_links_of_aligned_switches_each_on_their_own_channel():
    assert not [f for f in _audit_kinds(_wings_doc(3)) if f.kind == "shared_run"]


def _test_bench_doc(own_sheet=False):
    """Three trains, each able to feed a common test bench through a normally open infeed."""
    def train(c):
        board = {"type": "board", "id": f"TB{c}", "ref": f"TB-{c}", "label": f"Train {c} board", "children": [
            {"type": "busbar", "id": f"BB{c}", "children": [
                {"type": "breaker", "ref": f"-Q{c}1", "in_A": 400, "children": [{"type": "load", "label": f"Train {c} loads"}]},
                {"type": "breaker", "id": f"QT{c}", "ref": f"-QT{c}", "in_A": 800, "poles": "4P"}]}]}
        if own_sheet:
            board["own_sheet"] = True
        return {"type": "breaker", "ref": f"-QM{c}", "in_A": 800, "poles": "4P", "children": [board]}
    return load({"sources": [
        {"type": "grid", "children": [{"type": "board", "id": "MB", "ref": "MB", "children": [
            {"type": "busbar", "id": "MBB", "children": [train(c) for c in "ABC"] + [
                {"type": "breaker", "id": "QB", "ref": "-QB", "in_A": 800, "poles": "4P", "children": [
                    {"type": "board", "id": "BENCH", "ref": "TEST", "label": "Test bench board", "children": [
                        {"type": "breaker", "ref": "-QB1", "in_A": 800, "children": [{"type": "load", "label": "Test bench"}]}]}]}]}]}]}],
        "links": [{"kind": "infeed", "from": f"QT{c}", "to": "BENCH", "normally_open": True, "label": "to bench"}
                  for c in "ABC"]})


def test_several_infeeds_on_one_input_land_one_above_the_other():
    lay = _layout(_test_bench_doc())[0]
    ends = [next(i.points[-1] for i in _items(g) if isinstance(i, Polyline))
            for g in _items_groups(lay.group) if g.attrs.get("data-uw-link") in ("0", "1", "2")]
    assert len(ends) == 3 and len({round(p[1], 1) for p in ends}) == 3
    assert not [f for f in _audit_kinds(_test_bench_doc()) if f.kind == "text_overlap"]


def test_off_sheet_stubs_on_one_node_drawn_side_by_side():
    findings = _audit_kinds(_test_bench_doc(own_sheet=True))
    assert not [f for f in findings if f.kind == "text_overlap"], findings


def test_link_to_a_board_lands_on_the_nearer_end_of_its_busbar():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "id": "MB", "ref": "MB", "children": [
        {"type": "busbar", "id": "MBB", "children": [
            {"type": "breaker", "ref": "-Q1", "in_A": 400, "poles": "4P", "children": [
                {"type": "board", "id": "DB", "ref": "DB", "children": [
                    {"type": "busbar", "id": "DBB", "ref": "W2", "children": [
                        {"type": "breaker", "ref": f"-Q1{k}", "in_A": 63, "children": [{"type": "load", "label": f"Load {k}"}]}
                        for k in range(1, 4)]}]}]},
            {"type": "breaker", "ref": "-Q2", "in_A": 400, "poles": "4P", "children": [
                {"type": "ups", "ref": "-U1", "children": [
                    {"type": "breaker", "id": "QU", "ref": "-Q3", "in_A": 400, "poles": "4P"}]}]}]}]}]}],
        "links": [{"id": "L_PAR", "kind": "parallel", "from": "QU", "to": "DBB", "label": "UPS parallel"}]})
    lay = _layout(doc)[0]
    link = next(g for g in _items_groups(lay.group) if g.attrs.get("data-uw-link") == "L_PAR")
    pts = next(i.points for i in _items(link) if isinstance(i, Polyline))
    start, end = pts[0], pts[-1]
    assert start[0] > end[0]
    assert sum(abs(q[0] - p[0]) for p, q in zip(pts, pts[1:])) <= abs(start[0] - end[0]) + 6.0  # no detour
    label = next(t for t in _items(link) if isinstance(t, Text) and t.text == "UPS parallel")
    buses = [(i.a, i.b) for i in _items(lay.group) if isinstance(i, Line) and i.style.width == BUS]
    assert all(abs(a[1] - label.p[1]) > 1.0 or not min(a[0], b[0]) < label.p[0] < max(a[0], b[0]) for a, b in buses)


def test_small_texts_rcbo_rating_transformer_ratio_and_tag_once():
    from uniwire.labels import _ratio, protection_short, ref_label, without_ref
    d = load({"sources": [{"type": "grid", "children": [
        {"type": "rcbo", "in_A": 20, "idn_mA": 5}, {"type": "rcbo", "in_A": 16, "curve": "C", "idn_mA": 30}]}]})
    assert [protection_short(n) for n in d.sources[0].children] == ["20 A 5 mA", "C16 30 mA"]
    assert [_ratio(20000, 400), _ratio(400, 230), _ratio(22000, 11000)] == ["20 kV/400 V", "400/230 V", "22/11 kV"]
    assert ref_label("TGBT", "TGBT") == "TGBT" and ref_label("MSB", "Main board") == "MSB Main board"
    assert without_ref("TX-A 3150 kVA", "TX-A") == "3150 kVA" and without_ref("-QA12 x", "-QA1") == "-QA12 x"


def test_text_units_break_cjk_between_characters():
    from uniwire.render.scene import text_units
    units = text_units("TD 公寓配电箱 28 m²")
    assert units[:3] == ["TD", " 公", "寓"] and "".join(units).strip() == "TD 公寓配电箱 28 m²"


def test_long_cjk_note_stays_in_the_notes_cell():
    doc = load({"meta": {"lang": "zh", "notes": ["这是一个非常长的没有任何空格的中文注释" * 6]},
                "sources": [{"type": "grid", "children": [{"type": "breaker", "children": [{"type": "load"}]}]}]})
    page = render_pages(doc)[0]
    notes = next(g for g in _items_groups(page.root) if g.cls == "notes")
    texts = [t for t in _items(notes) if isinstance(t, Text)]
    assert len(texts) > 2 and all(t.size >= 1.6 for t in texts[1:])  # wrapped, not shrunk to fit one line


def test_feeder_of_a_sub_board_shows_its_cable_and_the_board_incoming_cable():
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "id": "MB", "children": [
        {"type": "breaker", "id": "QF", "ref": "-Q1", "in_A": 40, "cable": {"cores": "5G", "section_mm2": 10, "length_m": 15},
         "children": [{"type": "board", "id": "SB", "ref": "SB", "cable": {"ref": "W7", "cores": "5x", "section_mm2": 6},
                       "children": [{"type": "breaker", "ref": "-Q11", "in_A": 16, "children": [{"type": "load"}]},
                                    {"type": "breaker", "ref": "-Q12", "in_A": 16, "children": [{"type": "load"}]}]}]},
        {"type": "breaker", "ref": "-Q2", "in_A": 16, "children": [{"type": "load"}]}]}]}]})
    texts = _texts(render_pages(doc)[0].root)
    assert "5G10 15 m" in texts and "W7 5x6" in texts


def test_reversing_and_star_delta_starters_drawn_with_their_contactors():
    from uniwire.render.scene import Group as G
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "system": "3P", "children": [
        {"type": "breaker", "ref": "-Q1", "in_A": 10, "poles": "3P", "children": [
            {"type": "motor_starter", "ref": "-KM1", "method": "reversing", "children": [{"type": "motor", "phases": 3}]}]},
        {"type": "breaker", "ref": "-Q2", "in_A": 63, "poles": "3P", "children": [
            {"type": "motor_starter", "ref": "-KM2", "method": "star_delta", "children": [{"type": "motor", "phases": 3}]}]}]}]}],
        "views": [{"kind": "multi-line"}]})
    page = render_pages(doc)[0]
    sets = [g for g in _items_groups(page.root) if isinstance(g, G) and g.cls == "starter-contactors"]
    assert len(sets) == 2
    assert {"W2", "U2", "V2"} <= set(_texts(sets[1]))


def _us_board(**inst):
    return load({"installation": {"system": "split-phase", **inst}, "sources": [
        {"type": "grid", "children": [{"type": "board", "id": "P", "children": [
            {"type": "breaker", "id": "PV", "ref": "PV", "in_A": 30, "poles": "2P"},
            {"type": "breaker", "in_A": 30, "poles": "2P",
             "cable": {"cores": "2x", "section_mm2": 5.26, "size_awg": "10"}, "children": [{"type": "water_heater"}]},
            {"type": "rcbo", "id": "G", "in_A": 20, "idn_mA": 5, "rcd_type": "A", "poles": "1P+N",
             "cable": {"cores": "3G", "section_mm2": 3.31, "size_awg": "12"}, "children": [{"type": "socket"}]}]}]},
        {"type": "inverter", "id": "INV", "label": "Rooftop solar array string inverter (south roof)"}],
        "links": [{"id": "L_PV", "from": "INV", "kind": "infeed", "to": "PV"}]})


def test_nec_document_written_with_awg_sizes_and_gfci():
    texts = [t for p in render_pages(_us_board(standard="NEC 2023")) for t in _texts(p.root)]
    assert "2x#10" in texts and "2-#12+G" in texts and "5 mA GFCI" in texts
    assert not any("type A" in t for t in texts)
    iec = [t for p in render_pages(_us_board()) for t in _texts(p.root)]  # same data, IEC practice
    assert "2x#10" in iec and "3G3.31" in iec and "type A" in iec


def test_infeed_to_a_breaker_feeding_nothing_lands_on_its_output():
    lay = _layout(_us_board())[0]
    pv = next(g for g in _items_groups(lay.group) if g.id == "PV")
    ys = [p[1] for i in _items(pv) for p in ([i.a, i.b] if isinstance(i, Line) else getattr(i, "points", []))]
    link = next(g for g in _items_groups(lay.group) if g.attrs.get("data-uw-link") == "L_PV")
    end = next(i.points for i in _items(link) if isinstance(i, Polyline))[-1]
    assert end[1] >= max(ys) - 0.01  # below the contact (load side), not on the busbar side


def test_untagged_label_wrapped_rather_than_cut():
    texts = [t for p in render_pages(_us_board()) for t in _texts(p.root)]
    assert not any(t.endswith("…") and t.startswith("Rooftop") for t in texts)
    assert any(t.startswith("Rooftop") for t in texts)


def test_multiline_infeed_to_a_breaker_feeding_nothing_lands_on_its_outputs():
    doc = _us_board()
    page = render_pages(doc, default_view(doc).model_copy(update={"kind": "multi-line"}))[0]
    pv = next(g for g in _items_groups(page.root) if g.id == "PV")
    ys = [p[1] for i in _items(pv) for p in ([i.a, i.b] if isinstance(i, Line) else getattr(i, "points", []))]
    link = next(g for g in _items_groups(page.root) if g.attrs.get("data-uw-link") == "L_PV")
    ends = [i.points[-1] for i in _items(link) if isinstance(i, Polyline)]
    assert ends and all(e[1] > max(ys) - 0.01 for e in ends)  # below the contacts: the load side


def test_gfci_not_repeated_when_already_shown():
    from uniwire.labels import NORTH_AMERICAN
    d = load({"sources": [{"type": "grid", "children": [
        {"type": "rcbo", "ref": "3", "range": "GFCI", "in_A": 20, "idn_mA": 5, "children": [{"type": "socket"}]},
        {"type": "rcbo", "ref": "5", "label": "Kitchen GFCI", "in_A": 20, "idn_mA": 5, "children": [{"type": "socket"}]}]}]})
    token = NORTH_AMERICAN.set(True)
    try:
        shown, hidden = (annotation(n) for n in d.sources[0].children)
    finally:
        NORTH_AMERICAN.reset(token)
    assert shown.count("GFCI") == 1  # the range says it
    assert "GFCI" in hidden  # the label is not drawn beside a breaker: the kind is


def test_label_of_a_link_between_close_loads_clear_of_their_symbols():
    # labels wider than the gap between two loads: the link runs under the loads, its label clear of the symbols
    def feeder(ref, load):
        return {"type": "breaker", "ref": ref, "in_A": 10, "poles": "1P+N", "children": [load]}
    doc = load({"installation": {"system": "3P+N"}, "sources": [{"type": "grid", "children": [
        {"type": "board", "ref": "PS1", "children": [{"type": "busbar", "children": [
            feeder("-Q1", {"type": "motor", "id": "P1", "label": "Lift pump"}),
            feeder("-Q2", {"type": "load", "id": "CTL", "label": "Pump controller"}),
            feeder("-Q3", {"type": "motor", "id": "P2", "label": "Dosing pump"})]}]}]}],
        "links": [{"kind": "data", "from": "P1", "to": "CTL", "label": "Level probes L1-L2-L3"},
                  {"kind": "control", "from": "CTL", "to": "P2", "label": "Dosing command"}]})
    lay = _layout(doc)[0]
    syms = []
    for g in _items_groups(lay.group):
        if "uw-node" in (g.cls or "") and g.id in ("P1", "CTL", "P2"):
            pts = [p for i in _items(g) for p in ([i.a, i.b] if isinstance(i, Line) else getattr(i, "points", []))]
            pts += [(c.c[0] + dx, c.c[1] + dy) for c in _items(g) if hasattr(c, "r")
                    for dx, dy in ((-c.r, -c.r), (c.r, c.r))]
            syms.append((min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
    for g in _items_groups(lay.group):
        if "uw-link" not in (g.cls or ""):
            continue
        for t in (i for i in _items(g) if isinstance(i, Text)):
            w = text_width(t.text, t.size)
            x0 = t.p[0] - (w if t.anchor == "end" else 0.0)
            box = (x0, t.p[1] - t.size, x0 + w, t.p[1])
            assert not any(_hit(box, s) for s in syms), t.text


def test_long_description_in_the_table_wraps_before_it_shrinks():
    long = "Compressor of the cold room with its condensing unit and the defrost heaters of the evaporator"
    doc = load({"sources": [{"type": "grid", "children": [{"type": "board", "children": [
        {"type": "breaker", "ref": "-Q1", "in_A": 32, "children": [{"type": "load", "label": long}]},
        {"type": "breaker", "ref": "-Q2", "in_A": 16, "children": [{"type": "load", "label": "Lights"}]}]}]}],
        "views": [{"cartouche": ["label", "ref", "protection"]}]})
    (lay,) = _layout(doc)
    cells = [g for g in _items_groups(lay.group) if g.attrs.get("data-uw-field") == "label"]
    texts = [t for g in cells for t in _items(g) if isinstance(t, Text)]
    parts = [t for t in texts if t.text != "Lights"]
    assert len(parts) in (2, 3) and " ".join(t.text for t in parts) == long  # every word kept, none cut
    assert all(t.size == 2.0 for t in texts)  # at the size of the others
