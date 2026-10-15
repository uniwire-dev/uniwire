"""An inverter/charger with a DC side (batteries) and an AC side: the DC side is fed from a side terminal."""

import uniwire
from uniwire.layout import engine
from uniwire.render.svg import page_to_svg

DOC = {
    "uniwire": "1.0.0",
    "installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
    "sources": [{"type": "grid", "children": [
        {"type": "inverter", "ref": "-G1", "kind": "battery", "p_kVA": 10, "children": [
            {"type": "switch_disconnector", "ref": "-S2", "in_A": 63, "children": [{"type": "socket"}]},
            {"type": "board", "ref": "=DC", "kind": "dc_box", "un_V": 48, "children": [
                {"type": "switch_disconnector", "ref": "-QDC1", "in_A": 200, "children": [
                    {"type": "battery", "capacity_kWh": 15, "un_V": 51.2}]}]}]}]}],
}


def _inverter(doc):
    spec = engine.SheetSpec(roots=list(doc.sources))
    roots = engine._build_sheet_roots(spec, None)
    return next(n for n in roots[0].walk() if n.type == "inverter")


def test_dc_side_first_and_off_the_bus():
    inv = _inverter(uniwire.load(DOC))
    assert inv.dc_side == 1
    assert inv.children[0].type == "board"  # the DC board comes first, on the left
    assert [c.type for c in inv.bus_children] == ["switch_disconnector"]
    assert not inv.has_bus  # one AC feeder: no busbar joining it to the DC side


def test_draws():
    pages = uniwire.render_pages(uniwire.load(DOC))
    assert pages and "sym-battery" in page_to_svg(pages[0])


def test_single_side_unchanged():
    doc = dict(DOC)
    doc["sources"] = [{"type": "grid", "children": [
        {"type": "inverter", "kind": "battery", "children": [{"type": "battery", "capacity_kWh": 5}]}]}]
    assert _inverter(uniwire.load(doc)).dc_side == 0


def test_battery_behind_its_disconnector_is_dc_side():
    doc = dict(DOC)
    doc["sources"] = [{"type": "grid", "children": [
        {"type": "inverter", "kind": "battery", "children": [
            {"type": "breaker", "children": [{"type": "socket"}]},
            {"type": "switch_disconnector", "children": [{"type": "battery", "capacity_kWh": 5}]}]}]}]
    assert _inverter(uniwire.load(doc)).dc_side == 1


def test_multiline_conductors():
    from uniwire.layout.multiline import conductors

    doc = uniwire.load(DOC)
    by_ref = {n.ref: n.id for n, _, _ in uniwire.resolve.iter_nodes(doc) if n.ref}
    c = conductors(doc)
    assert set(c[by_ref["-G1"]].out) >= {"L1", "N", "L+", "L-"}
    assert set(c[by_ref["-S2"]].inp) & {"L+", "L-"} == set()  # the AC output stays AC
    assert set(c[by_ref["-QDC1"]].inp) == {"L+", "L-"}


def test_multiline_draws():
    from uniwire.model import View

    doc = uniwire.load(DOC)
    pages = uniwire.render_pages(doc, View(id="ml", kind="multi-line"))
    assert pages and 'data-uw-cond="L+"' in page_to_svg(pages[0])
