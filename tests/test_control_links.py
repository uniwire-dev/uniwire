"""Readability of documents with many control links: a PLC whose modules drive and read many devices, a safety relay
naming its terminals, drives on a fieldbus. Invented machine panels."""

import pytest

from tests.drawing_audit import _walk, audit
from uniwire import load
from uniwire.layout.engine import _leader_label
from uniwire.layout.routing import Obstacles
from uniwire.render import render_views
from uniwire.render.scene import Group, Line, Rect, Text


def panel(motors: int, drives: int, feedback: bool = True, out_slot: int = 2) -> dict:
    """A machine panel: ``motors`` started by contactors the PLC drives (and reads back), ``drives`` speed drives on
    a fieldbus, every contactor and drive also stopped by a safety relay through its own terminal. ``out_slot``:
    the module driving the contactors (0: the PLC's built-in outputs)."""
    feeders, links = [], []
    for i in range(1, motors + 1):
        feeders.append({"type": "breaker", "id": f"Q{i}", "ref": f"-Q{i}", "in_A": 10, "curve": "D", "poles": "3P",
                        "children": [{"type": "contactor", "id": f"K{i}", "ref": f"-K{i}", "in_A": 12, "poles": "3P",
                                      "children": [{"type": "motor", "ref": f"-M{i}", "label": f"Belt {i}",
                                                    "p_kW": 2.2}]}]})
        links.append({"kind": "control", "from": "PLC", "from_port": f"{out_slot}.{i}", "to": f"K{i}", "label": f"Run {i}"})
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


@pytest.mark.parametrize("motors,drives", [(6, 2), (10, 3), (4, 4)])
def test_many_control_links_each_keep_their_own_run(motors, drives):
    """Every link on its own channel, none along another or along a frame, no text crossed (the channels below the
    PLC were once fewer than its links: they ran on one another)."""
    page = render_views(load(panel(motors, drives)))[0]
    findings = [f for f in audit(page.root) if not (f.kind == "shared_run" and "share 3 mm" in f.what)]
    assert findings == [], "\n".join(map(str, findings))  # (the fieldbus links leave the PLC by one point)


def test_channel_numbers_are_written_at_the_plc_under_its_module():
    """A link's PLC channel is written by its wire under the module (read at the PLC, as on the panel), once."""
    doc = load(panel(10, 3))
    page = render_views(doc)[0]
    x0, _y0, x1, y1 = _box(_node(page.root, "PLC"))
    ports = [l.from_port if l.from_ == "PLC" else l.to_port for l in doc.links if "PLC" in (l.from_, l.to)
             and (l.from_port or l.to_port)]
    texts = [t for t, _l, _o in _walk(page.root) if isinstance(t, Text) and t.text in ports]
    assert sorted(t.text for t in texts) == sorted(ports)
    for t in texts:
        assert t.rotate == 90 and x0 <= t.p[0] <= x1 and y1 < t.p[1] < y1 + 5.0, t


def test_a_module_many_links_leave_is_drawn_wider():
    plain = render_views(load(panel(1, 0, feedback=False)))[0]
    busy = render_views(load(panel(10, 0)))[0]
    w = [_box(_node(p.root, "PLC"))[2] - _box(_node(p.root, "PLC"))[0] for p in (plain, busy)]
    assert w[1] > w[0] + 2 * 9 * 2.0  # ten wires leaving two modules: about 2.6 mm apart


def test_built_in_outputs_many_links_leave_widen_the_head_inside_the_frame():
    """Many links leaving the PLC's built-in I/O (slot 0): its head is drawn wider, their numbers apart from one
    another (they were written on one another), the frame of the board round it."""
    page = render_views(load(panel(10, 0, feedback=False, out_slot=0)))[0]
    assert [f for f in audit(page.root) if f.kind in ("text_overlap", "text_crossed")] == []
    plc = _box(_node(page.root, "PLC"))
    frames = [r for r, _l, _o in _walk(page.root) if isinstance(r, Rect) and r.style.dash
              and r.x < plc[0] + 1e-6 and plc[2] < r.x + r.w]
    assert frames, "the PLC sticks out of its board's frame"


def test_terminal_numbers_of_a_controller_are_written_inside_it():
    """A safety relay naming its terminals: each number inside its box, by the link's point (they were left out)."""
    doc = load(panel(4, 1))
    page = render_views(doc)[0]
    x0, y0, x1, y1 = _box(_node(page.root, "SR"))
    terms = [l.from_port for l in doc.links if l.from_ == "SR"]
    texts = {t.text: t for t, _l, _o in _walk(page.root) if isinstance(t, Text) and t.text in terms}
    assert sorted(texts) == sorted(terms)
    for t in texts.values():
        assert x0 < t.p[0] < x1 and y0 < t.p[1] < y1, t


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


def _belts(page) -> int:
    return sum(1 for t, _l, _o in _walk(page.root) if isinstance(t, Text) and t.text.startswith("Belt "))


def test_links_to_another_sheet_do_not_widen_the_modules():
    """A busbar split over two sheets: the PLC's links to the ways on the second sheet end on off-page stubs, its
    modules are only as wide as the links drawn under them, and its sheet keeps the ways that fit (with every link
    counted, the first sheet kept 4 of 14 ways)."""
    d = panel(14, 0)
    d["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    pages = render_views(load(d))
    assert len(pages) == 2 and _belts(pages[0]) + _belts(pages[1]) == 14
    assert _belts(pages[0]) >= 5
    plc = _node(pages[0].root, "PLC")
    rects = sorted((r for r, _l, _o in _walk(plc) if isinstance(r, Rect)), key=lambda r: r.x)
    on_sheet = _belts(pages[0])  # one output and one input each: modules 1 and 2 hold that many wires
    unit = rects[3].w / 3.4  # the sheet's scale, from a module no link leaves
    assert all(r.w <= (2 * 1.8 + (on_sheet - 1) * 2.6) * unit + 1e-6 for r in rects[1:3]), [r.w for r in rects]


def test_a_link_between_two_plcs_leaves_the_channel_of_its_start():
    """PLC to PLC: drawn out of the first PLC's channel, the second PLC's channel written by the link at its end;
    only the module it leaves is widened (both were, and the second channel was not written)."""
    d = panel(3, 0, feedback=False)
    control = d["sources"][0]["children"][0]["children"][0]["children"][0]["children"][0]
    control["children"].append({"type": "plc", "id": "PLC2", "ref": "-A3",
                                "modules": [{"slot": 1, "kind": "di", "channels": 16}]})
    d["links"] += [{"kind": "control", "from": "PLC", "from_port": "2.4", "to": "PLC2", "to_port": "1.5"},
                   {"kind": "control", "from": "PLC", "from_port": "2.5", "to": "PLC2", "to_port": "1.6"}]
    page = render_views(load(d))[0]
    texts = [t.text for t, _l, _o in _walk(page.root) if isinstance(t, Text)]
    for port in ("2.1", "2.2", "2.3", "2.4", "2.5", "1.5", "1.6"):
        assert texts.count(port) == 1, port
    module = [r for r, _l, _o in _walk(_node(page.root, "PLC2")) if isinstance(r, Rect)][-1]
    plain = sorted((r for r, _l, _o in _walk(_node(page.root, "PLC")) if isinstance(r, Rect)), key=lambda r: r.x)[3]
    assert abs(module.w - plain.w) < 1e-6  # as narrow as a module no link leaves (slot 3)


def test_a_dashed_link_is_interrupted_where_it_crosses_a_conductor():
    """A control link crossing a feeder is not connected to it: the link stops on each side, the conductor stays
    whole (single-line and multi-line views)."""
    doc = panel(6, 2)
    doc["views"] = [{"id": "sld"}, {"id": "ml", "kind": "multi-line"}]
    for page in render_views(load(doc)):
        crossings = [f for f in audit(page.root) if f.kind == "link_across_conductor"]
        assert crossings == [], "\n".join(map(str, crossings))


def _gapped(kind: str, *conductors: Group) -> list[list[tuple[float, float]]]:
    from uniwire.render.scene import Polyline, Style
    from uniwire.render.semantics import gap_link_crossings

    link = Group([Polyline([(0.0, 10.0), (20.0, 10.0), (20.0, 30.0)], Style(dash=(1.0, 0.5)))], cls="uw-link",
                 attrs={"data-uw-kind": kind})
    gap_link_crossings(Group([*conductors, link]))
    return [[(round(x, 6), round(y, 6)) for x, y in p.points] for p in link.items]


def test_gap_link_crossings_cuts_the_link_not_the_conductor():
    from uniwire.render.scene import Polyline, Style
    from uniwire.render.semantics import edge_group, gap_link_crossings

    wire = edge_group("c", "p", [Line((10.0, 0.0), (10.0, 20.0)), Line((0.0, 25.0), (30.0, 25.0))])
    end = edge_group("d", "p", [Line((19.0, 30.0), (30.0, 30.0))])  # the link stops on it: no gap there
    link = Group([Polyline([(0.0, 10.0), (20.0, 10.0), (20.0, 30.0)], Style(dash=(1.0, 0.5)))], cls="uw-link",
                 attrs={"data-uw-kind": "control"})
    root = Group([wire, end, link])
    gap_link_crossings(root)
    parts = [[(round(x, 6), round(y, 6)) for x, y in p.points] for p in link.items]
    assert parts == [[(0.0, 10.0), (9.2, 10.0)], [(10.8, 10.0), (20.0, 10.0), (20.0, 24.2)], [(20.0, 25.8), (20.0, 30.0)]]
    # each piece keeps the dash pattern of the whole line (no short dash beside a gap)
    assert [round(p.style.dash_offset, 6) for p in link.items] == [0.0, round(10.8 % 1.5, 6), round(35.8 % 1.5, 6)]
    assert wire.items[0].a == (10.0, 0.0) and wire.items[0].b == (10.0, 20.0)
    gap_link_crossings(root)  # done once: nothing more to cut
    assert [[(round(x, 6), round(y, 6)) for x, y in p.points] for p in link.items] == parts


def test_gaps_only_in_signal_links_and_at_every_kind_of_conductor():
    from uniwire.render.scene import Polyline
    from uniwire.render.semantics import cond_group, edge_group

    trunk = [Line((10.0, 0.0), (10.0, 20.0))]
    one = [[(0.0, 10.0), (9.2, 10.0)], [(10.8, 10.0), (20.0, 10.0), (20.0, 30.0)]]
    assert _gapped("control", edge_group("c", "p", trunk)) == one
    # the same trunk drawn by two edges is one crossing, not a bundle of two conductors
    assert _gapped("control", edge_group("c", "p", trunk), edge_group("e", "p", list(trunk))) == one
    # a multi-line conductor drawn in a device's group, a solid power link
    assert _gapped("trip", Group([cond_group("PE", *trunk)], "K1", "ml-sym uw-node")) == one
    infeed = Group([Polyline([(10.0, 0.0), (10.0, 20.0)])], cls="uw-link", attrs={"data-uw-kind": "infeed"})
    assert _gapped("measure", infeed) == one
    # earth, data and power links stay whole (a gap would read as a break)
    for kind in ("earth", "data", "infeed"):
        assert _gapped(kind, edge_group("c", "p", trunk)) == [[(0.0, 10.0), (20.0, 10.0), (20.0, 30.0)]]


def test_off_sheet_arrows_keep_their_texts_clear():
    """Links to devices on another sheet, many of them beside a PLC and beside each contactor: each sheet reference
    and label beside its arrow, none on an arrow, a conductor or a symbol, no arrow on the side of a frame."""
    doc = panel(14, 0)
    doc["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    pages = render_views(load(doc))
    assert len(pages) == 2
    for page in pages:
        bad = [f for f in audit(page.root) if f.kind in ("text_crossed", "text_on_conductor", "text_on_symbol",
                                                         "text_overlap")]
        assert bad == [], "\n".join(map(str, bad))


def test_devices_read_by_plc_channels_stay_out_of_the_channel_band():
    """Field devices read by PLC inputs (sensors, an operator box) hang off the board: placed under the band of the
    channels, by the module they are wired to, not inside the band where the channel wires would run through their
    boxes and texts."""
    doc = panel(6, 0)
    names = ["Level sensor controller with relay output", "Operator box", "Limit switch box"]
    doc["devices"] = [{"type": "controller", "id": f"D{k}", "ref": f"-B{k}", "label": name, "symbol_text": "X"}
                      for k, name in enumerate(names)]
    doc["links"] += [{"kind": "measure", "from": f"D{k}", "to": "PLC", "to_port": f"3.{k + 1}"} for k in range(3)]
    page = render_views(load(doc))[0]
    bad = [f for f in audit(page.root) if f.kind in ("link_through_symbol", "text_crossed", "text_on_symbol")]
    assert bad == [], "\n".join(map(str, bad))
    plc = _box(_node(page.root, "PLC"))
    for k in range(3):
        dev = _box(_node(page.root, f"D{k}"))
        assert dev[1] > plc[3]  # under the PLC (its channels leave the modules downwards)


@pytest.mark.parametrize("count", [3, 5])
def test_devices_keep_off_the_stubs_to_other_sheets(count):
    """A PLC whose links reach devices on another sheet: its stubs one under the other beside it; the field devices
    read by its channels are placed clear of that column and its texts, and the channels clear of the safety relay
    hanging into their band."""
    doc = panel(14, 0)
    doc["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    names = ["Level sensor controller with relay output", "Operator box", "Limit switch box", "Pressure switch",
             "Door contact"][:count]
    doc["devices"] = [{"type": "controller", "id": f"D{k}", "ref": f"-B{k}", "label": name, "symbol_text": "X"}
                      for k, name in enumerate(names)]
    doc["links"] += [{"kind": "measure", "from": f"D{k}", "to": "PLC", "to_port": f"1.{k + 15}"} for k in range(count)]
    for page in render_views(load(doc)):
        bad = [f for f in audit(page.root) if f.kind in ("text_on_symbol", "text_overlap", "link_through_symbol")
               or f.kind == "text_crossed" and any(s in f.what for s in ["sheet"] + names)]
        assert bad == [], "\n".join(map(str, bad))


def test_sheet_references_point_to_a_sheet_of_their_own_view_holding_the_other_end():
    """A multi-line view and a single-line view split over sheets: the devices are drawn in both views, each
    "→ sheet n" of a view names the printed number of a sheet of that same view where the other end is drawn."""
    import re

    doc = panel(14, 0)
    doc["views"] = [{"id": "ml", "kind": "multi-line"}, {"id": "sld", "paper": "A4", "min_scale": 1.0}]
    pages = render_views(load(doc))
    kinds = [p.root.items and next((g.cls for g in p.root.items if isinstance(g, Group) and g.cls in
                                    ("diagram", "multiline")), None) for p in pages]
    numbers = [int(p.attrs["data-uw-folio"]) for p in pages]

    def refs(item):
        if isinstance(item, Group):
            if item.cls == "uw-ref":
                yield item
            for i in item.items:
                yield from refs(i)

    checked = 0
    for page, kind in zip(pages, kinds):
        for r in refs(page.root):
            target = r.attrs.get("data-uw-target-id")
            for t in [i for i in r.items if isinstance(i, Text)]:
                for n in map(int, re.findall(r"→ sheet (\d+)", t.text)):
                    there = pages[numbers.index(n)]
                    assert kinds[numbers.index(n)] == kind, (t.text, kind)
                    assert target and _node(there.root, target) is not None, (t.text, target)
                    checked += 1
    assert checked >= 20


def test_a_link_label_is_written_at_both_stubs_of_a_link_between_sheets():
    """Links with long labels between a PLC and contactors on another sheet, beside crowded devices: each label is
    written at the stub on both sheets (beside the sheet reference), never left out for want of room."""
    doc = panel(14, 0)
    doc["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    for link in doc["links"]:
        link["label"] = "Run order line " + link["label"] if "label" in link else "Safety stop"
    pages = render_views(load(doc))
    # (a label may be written on two or three lines, one after the other)
    texts = [" | ".join(t.text for t, _l, _o in _walk(p.root) if isinstance(t, Text)).replace(" | ", " ") + " "
             for p in pages]
    checked = 0
    for link in doc["links"]:
        a = next(i for i, p in enumerate(pages) if _node(p.root, link["from"]) is not None)
        b = next(i for i, p in enumerate(pages) if _node(p.root, link["to"]) is not None)
        if a != b:
            assert link["label"] + " " in texts[a] and link["label"] + " " in texts[b], link
            checked += 1
    assert checked >= 10


def test_the_pdf_of_interrupted_links_has_no_number_in_exponent_notation(tmp_path):
    """The pieces of an interrupted dashed link carry a dash phase: written as a plain number in the PDF (a reader
    does not parse 1e-07 and loses the rest of the page)."""
    import base64
    import re
    import zlib

    from uniwire.render import render_pdf

    doc = panel(10, 3)
    doc["views"] = [{"id": "sld"}, {"id": "ml", "kind": "multi-line"}]
    path = render_pdf(load(doc), tmp_path / "panel.pdf", all_views=True)
    data = path.read_bytes()
    streams = []
    for m in re.finditer(rb"/Filter \[ /ASCII85Decode /FlateDecode \][^>]*>>\s*stream\r?\n", data):
        raw = data[m.end():data.index(b"~>", m.end())]
        streams.append(zlib.decompress(base64.a85decode(raw)))  # the page contents
    dashed = [s for s in streams if re.search(rb"\] [\d.]+ d\b", s)]
    assert dashed
    for s in dashed:
        assert not re.search(rb"(?<![A-Za-z/])\d*\.?\d+[eE][-+]?\d+", s)


def test_a_label_leader_never_crosses_a_symbol():
    """A label with no room along its link is joined to it by a leader only when the leader crosses no symbol and no
    text; otherwise it is written on its link."""
    from uniwire.layout.engine import _leader_label
    from uniwire.layout.routing import Obstacles

    obs = Obstacles()
    obs.add_box((0.0, 2.0, 30.0, 6.0))  # a device right under the link: the only free space is below it
    for b in ((-80.0, -40.0, 80.0, -0.3), (-80.0, 0.3, -0.5, 40.0), (30.5, 0.3, 80.0, 40.0)):
        obs.add_box(b)
    g = Group()
    placed = _leader_label(obs, [(0.0, 0.0), (30.0, 0.0)], "A long label", 1.6, g)
    leaders = [i for i in g.items if isinstance(i, Line)]
    for ln in leaders:
        x0, y0, x1, y1 = min(ln.a[0], ln.b[0]), min(ln.a[1], ln.b[1]), max(ln.a[0], ln.b[0]), max(ln.a[1], ln.b[1])
        assert not (x0 < 30.0 and 0.0 < x1 and y0 < 6.0 and 2.0 < y1), ln
    assert placed == bool(leaders)


def test_off_sheet_stubs_of_a_board_stay_inside_its_frame():
    """A PLC whose links reach ways drawn on the next sheet: the column of its off-sheet stubs goes down beside it,
    lower than the devices of the board; the frame goes down round the whole column (the stubs hung out of its
    bottom, between the loads)."""
    d = panel(14, 2)
    d["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    page = render_views(load(d))[0]
    plc = _box(_node(page.root, "PLC"))
    frame = next(r for r, _l, _o in _walk(page.root) if isinstance(r, Rect) and r.style.dash
                 and r.x < plc[0] and plc[2] < r.x + r.w and r.y < plc[1] < r.y + r.h)
    refs = [t for t, _l, _o in _walk(page.root) if isinstance(t, Text) and "sheet" in t.text and t.p[0] < plc[0]]
    assert len(refs) > 20
    for t in refs:
        assert t.p[1] + t.size < frame.y + frame.h, t


def test_a_board_under_a_frame_grown_round_stubs_stays_below_it():
    """The frame of a board grows down round the off-sheet stubs of its PLC: a sub-board drawn under it is moved
    down with it (the frame ran across the sub-board and its texts)."""
    d = panel(14, 2)
    d["sources"][0]["children"][0]["id"] = "CP1"
    d["sources"][0]["children"][0]["children"][0]["children"].insert(1, {
        "type": "breaker", "ref": "-QS", "in_A": 16, "curve": "C", "poles": "1P+N", "children": [
            {"type": "board", "id": "LB1", "ref": "LB1", "label": "Lighting box", "children": [
                {"type": "breaker", "ref": "-QL1", "in_A": 10, "curve": "C", "poles": "1P+N",
                 "children": [{"type": "lighting", "label": "Lamps"}]}]}]})
    d["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    page = render_views(load(d))[0]
    main, sub = (next(i for i in _node(page.root, b).items if isinstance(i, Rect)) for b in ("CP1", "LB1"))
    assert main.y + main.h < sub.y, (main, sub)


def test_an_auxiliary_device_keeps_room_for_its_off_sheet_stubs():
    """A safety relay off the tree stopping contactors drawn on the next sheet, placed among field devices read by
    the PLC: the column of its stubs is kept free when it is placed, each sheet reference and label written beside
    its own arrow, one column (they were written over the next device's text, or on the far side of the stub)."""
    d = panel(14, 0, feedback=False)
    supply = d["sources"][0]["children"][0]["children"][0]["children"][0]["children"][0]
    supply["children"] = [c for c in supply["children"] if c["id"] != "SR"]
    d["devices"] = [{"type": "protection_relay", "id": "SR", "ref": "-A2", "label": "Safety relay, door and stop"}]
    d["devices"] += [{"type": "controller", "id": f"S{i}", "ref": f"-B{i}", "label": f"Level switch tank {i}"}
                     for i in range(1, 7)]
    d["links"] = [l for l in d["links"] if l.get("from") != "SR"]
    d["links"] += [{"kind": "control", "from": f"S{i}", "to": "PLC", "to_port": f"1.{i}", "label": f"Level {i}"}
                   for i in range(1, 7)]
    d["links"] += [{"kind": "control", "from": "SR", "to": "PLC", "to_port": "1.15", "label": "Chain OK"}]
    d["links"] += [{"kind": "trip", "from": "SR", "to": f"K{i}", "label": "safe stop"} for i in range(11, 15)]
    d["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    page = render_views(load(d))[0]
    bad = [f for f in audit(page.root) if f.kind in ("text_overlap", "text_on_symbol", "text_crossed")]
    assert bad == [], "\n".join(map(str, bad))
    texts = [t for t, _l, _o in _walk(page.root) if isinstance(t, Text)]
    labels = [t for t in texts if t.text == "safe stop"]
    refs = [t for t in texts if "sheet" in t.text and any(0 < s.p[1] - t.p[1] < 3 * t.size for s in labels)]
    assert len(labels) == len(refs) == 4
    assert all(t.anchor == "end" and abs(t.p[0] - labels[0].p[0]) < 1e-6 for t in labels + refs), labels + refs
