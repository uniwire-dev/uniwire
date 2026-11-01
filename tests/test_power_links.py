"""Power links outside the tree: alternative supplies band (single-line), link conductors (multi-line),
busbar trunking symbols, upstream RCD in the feeder table."""

from tests.conftest import ROOT
from uniwire import load, render_pages
from uniwire.labels import cell
from uniwire.layout import layout_sheet, plan_sheets
from uniwire.render import default_view
from uniwire.render.scene import Circle, Group, Polyline, Rect, Text, bbox
from uniwire.symbols import symbol_for

EX52 = ROOT / "examples" / "52_dual_source_selectable_feeders.uniwire.json"


def _items(item):
    if isinstance(item, Group):
        for i in item.items:
            yield from _items(i)
    else:
        yield item


def _groups(item):
    if isinstance(item, Group):
        yield item
        for i in item.items:
            yield from _groups(i)


def _sld(doc):
    view = default_view(doc)
    return [layout_sheet(doc, view, s) for s in plan_sheets(doc, view)]


def _dual(device: bool = True, label: str = "Alternative W2 -> A") -> dict:
    """Two supplies, feeder A fed from W1 or (normally open) from W2."""
    link = {"kind": "infeed", "from": "W2", "to": "QA", "normally_open": True, "label": label}
    if device:
        link["device"] = {"id": "X21", "ref": "-X21", "type": "disconnector", "poles": "4P", "normal_state": "open"}
    feeder = lambda i, q: {"id": f"X{i}", "ref": f"-X{i}", "type": "disconnector", "poles": "4P", "children": [  # noqa: E731
        {"id": q, "ref": f"-{q}", "type": "breaker", "poles": "4P", "in_A": 63, "children": [
            {"type": "load", "label": f"Load {q}"}]}]}
    return {
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
        "sources": [
            {"id": "S1", "type": "grid", "children": [{"id": "W1", "type": "busbar", "ref": "-W1", "children": [
                feeder(11, "QA"), feeder(12, "QB")]}]},
            {"id": "S2", "type": "grid", "children": [{"id": "W2", "type": "busbar", "ref": "-W2", "children": [
                feeder(23, "QC"), {"type": "spd", "ref": "-F2"}]}]},
        ],
        "links": [link],
        "views": [{"id": "sld"}, {"id": "ml", "kind": "multi-line"}],
    }


# ------------------------------------------------------------------ single-line
def test_link_label_not_repeated_when_a_device_is_annotated():
    lay = _sld(load(EX52))[0]
    texts = [i.text for i in _items(lay.group) if isinstance(i, Text)]
    assert "-X21" in texts and "-X13" in texts
    assert not any(t.startswith("Alternative") for t in texts)


def test_link_label_kept_without_device():
    lay = _sld(load(_dual(device=False)))[0]
    assert "Alternative W2 -> A" in [i.text for i in _items(lay.group) if isinstance(i, Text)]


def test_alternative_supply_in_a_band_under_the_busbars():
    doc = load(_dual())
    lay = _sld(doc)[0]
    nodes = {n.node.id: n for n in lay.lnodes if n.node is not None and n.node.id}
    w1, w2, x11 = nodes["W1"], nodes["W2"], nodes["X11"]
    sym = next(g for g in _groups(lay.group) if g.id == "X11")
    dx, dy = bbox(sym)[0] - (x11.x - x11.sym.left), bbox(sym)[1] - x11.y  # layout -> sheet group coordinates
    dev = next(g for g in _groups(lay.group) if g.id == "X21")
    b = bbox(dev)
    # the device sits between the busbars and the first feeder devices, which were pushed down to make room
    assert max(w1.bus_y, w2.bus_y) + dy < b[1] and b[3] < x11.y + dy
    # its tag right next to it (above the lane)
    tag = next(i for i in _items(lay.group) if isinstance(i, Text) and i.text == "-X21")
    assert b[0] - 15 < tag.p[0] < b[2] + 5 and b[1] - 12 < tag.p[1] < b[1]
    # dashed route ending on a junction dot on the input conductor of QA
    qa = nodes["QA"]
    assert any(isinstance(i, Circle) and abs(i.c[0] - qa.x - dx) < 0.3 and qa.y - 3 < i.c[1] - dy < qa.y
               for i in _items(lay.group))


# ------------------------------------------------------------------ feeder table
def test_upstream_rcd_marked_in_the_feeder_table():
    rcd = load({"sources": [{"type": "grid", "children": [
        {"type": "rcd", "id": "F0", "idn_mA": 300, "children": [{"type": "load"}]}]}]}).sources[0].children[0]
    col = {"leaf": None, "prot": None, "cable": None, "rcd": rcd, "rcd_upstream": True}
    assert cell("idn_mA", col, "en") == "300 mA (upstream)"
    assert cell("idn_mA", col, "fr") == "300 mA (amont)"
    assert cell("idn_mA", {**col, "rcd_upstream": False}, "en") == "300 mA"


def test_rcd_of_the_feeder_itself_not_marked():
    doc = load({
        "installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
        "sources": [{"type": "grid", "children": [{"type": "rcd", "ref": "-F0", "idn_mA": 300, "in_A": 63, "children": [
            {"type": "busbar", "id": "W", "children": [
                {"type": "rcbo", "ref": "-Q1", "in_A": 16, "idn_mA": 30, "children": [{"type": "socket", "label": "A"}]},
                {"type": "breaker", "ref": "-Q2", "in_A": 16, "children": [{"type": "lighting", "label": "B"}]}]}]}]}],
        "views": [{"id": "sld", "cartouche": ["label", "idn_mA"]}],
    })
    texts = [i.text for i in _items(_sld(doc)[0].group) if isinstance(i, Text)]
    assert "30 mA" in texts and "300 mA (upstream)" in texts


# ------------------------------------------------------------------ busway
def test_busway_symbol_in_both_views():
    node = load({"sources": [{"type": "grid", "children": [{"type": "busbar", "kind": "busway"}]}]}).sources[0].children[0]
    assert symbol_for(node).name == "busway"
    doc = load({
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
        "sources": [{"type": "grid", "children": [{"type": "board", "children": [
            {"type": "breaker", "ref": "-Q1", "poles": "4P", "in_A": 400,
             "cable": {"cores": "4x", "section_mm2": 185, "pe_section_mm2": 95},
             "children": [{"type": "busbar", "id": "BW", "kind": "busway", "label": "Trunking A"}]},
            {"type": "breaker", "ref": "-Q2", "in_A": 16, "children": [{"type": "load"}]}]}]}],
        "views": [{"id": "sld"}, {"id": "ml", "kind": "multi-line"}],
    })
    sld = _sld(doc)[0]
    assert any("sym-busway" in (g.cls or "") for g in _groups(sld.group))
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    trunk = next(g for g in _groups(page.root) if g.id == "BW" and "ml-busbar" in (g.cls or ""))
    assert any(isinstance(i, Rect) for i in _items(trunk))
    labels = [i.text for i in _items(trunk) if isinstance(i, Text)]
    assert labels == ["L1", "L2", "L3", "N", "PE"]  # the trunk spans every conductor, PE included


def test_feeder_cable_with_pe_brings_the_pe_in_tt():
    from uniwire.layout.multiline import conductors

    doc = load({
        "installation": {"earthing": "TT", "system": "3P+N", "un_V": 400},
        "sources": [{"type": "grid", "children": [{"type": "breaker", "id": "Q1", "poles": "4P", "children": [
            {"type": "breaker", "id": "Q2", "poles": "4P", "cable": {"cores": "4x", "section_mm2": 95, "pe_section_mm2": 50},
             "children": [{"type": "busbar", "id": "BW", "kind": "busway"}]}]}]}],
    })
    c = conductors(doc)
    assert "PE" not in c["Q1"].inp and "PE" in c["Q2"].inp and "PE" in c["BW"].inp


# ------------------------------------------------------------------ multi-line links
def test_multiline_link_conductors_and_poles():
    doc = load(_dual())
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    link = next(g for g in _groups(page.root) if "ml-link-infeed" in (g.cls or ""))
    dev = next(g for g in _groups(link) if g.id == "X21")
    poles = [g for g in _groups(dev) if (g.cls or "").split()[:1] == ["pole"]]
    assert len(poles) == 4  # 4P removable links: one open contact per conductor (L1 L2 L3 N)
    dashed = [i for i in _items(link) if isinstance(i, Polyline) and i.style.dash and len(i.points) >= 2]
    assert not dashed  # the open contacts show the normal state: the conductors stay solid
    dots = [i for i in _items(link) if isinstance(i, Circle)]
    assert len(dots) == 2 * 5  # taps on the source rails + junctions on the target input conductors (PE too)


def test_multiline_tie_and_parallel_links_drawn():
    for name in ("26_two_transformers_bus_tie", "49_chp_parallel_grid", "16_dental_practice_ups"):
        doc = load(ROOT / "examples" / f"{name}.uniwire.json")
        pages = render_pages(doc, default_view(doc, kind="multi-line"))
        assert any("ml-link" in (g.cls or "") for p in pages for g in _groups(p.root)), name


def test_multiline_drawing_enlarged_to_use_the_sheet():
    doc = load(_dual())
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    drawing = next(i for i in page.root.items if isinstance(i, Group) and i.cls == "multiline")
    b = bbox(drawing)
    assert b[2] - b[0] > 0.5 * page.width or b[3] - b[1] > 0.5 * page.height


def test_link_device_text_stays_beside_its_symbol():
    # a bypass along a soft starter: no free corner beside the bypass contactor, its tag still next to it
    from tests.test_multiline import BYPASS

    root = render_pages(load({**BYPASS, "views": [{"id": "sl"}]}))[0].root

    def walk(item):
        yield item
        if isinstance(item, Group):
            for i in item.items:
                yield from walk(i)

    sym = bbox(next(g for g in walk(root) if isinstance(g, Group) and g.id == "K2"))
    tag = next(t for t in walk(root) if isinstance(t, Text) and t.text == "-K2")
    gap = max(sym[0] - tag.p[0] - 6.0, tag.p[0] - sym[2], sym[1] - tag.p[1], tag.p[1] - sym[3] - 3.0, 0.0)
    assert gap <= 8.0


def _breaker(i, amps, label=None):
    return {"type": "breaker", "id": i, "ref": "-" + i, "in_A": amps, "poles": "4P",
            "children": [{"type": "load", "id": "L" + i, "label": label or "Load " + i}]}


STANDBY_ACROSS = {  # a standby generator on the right, reaching a changeover beyond a board fed separately
    "uniwire": "1.0.0", "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
    "sources": [
        {"type": "grid", "id": "SA", "label": "Supply A", "children": [
            {"type": "meter", "id": "PM", "ref": "-P1", "children": [
                {"type": "breaker", "id": "Q0", "ref": "-Q0", "in_A": 630, "poles": "4P", "children": [
                    {"type": "transfer_switch", "id": "ATS", "ref": "-QT", "in_A": 630, "mode": "automatic",
                     "children": [{"type": "board", "id": "MB", "label": "Main board",
                                   "children": [_breaker("QA1", 250), _breaker("QA2", 250)]}]}]}]}]},
        {"type": "grid", "id": "SB", "label": "Supply B", "children": [
            {"type": "breaker", "id": "QB0", "ref": "-QB0", "in_A": 160, "poles": "4P", "children": [
                {"type": "board", "id": "SVB", "label": "Services board",
                 "children": [_breaker("QB1", 63), _breaker("QB2", 63), _breaker("QB3", 63)]}]}]},
        {"type": "generator", "id": "GS", "ref": "-G1", "label": "Standby generator", "children": []}],
    "links": [{"kind": "transfer", "from": "GS", "to": "ATS"}]}


def test_standby_supply_to_a_changeover_goes_round_the_feeders_it_would_cross():
    from tests.drawing_audit import audit
    from uniwire.render import render_views

    findings = [f for pg in render_views(load(STANDBY_ACROSS)) for f in audit(pg.root)]
    assert not [f for f in findings if f.kind in ("text_crossed", "link_on_conductor")], findings
