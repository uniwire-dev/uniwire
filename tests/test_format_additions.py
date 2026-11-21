"""Format additions without a format version change: circuit schedule rows, `dc` on a breaker, current shunts,
narrow feeder columns read as the narrowest, residual-current fields on a breaker."""

import pytest

from tests.test_multiline import _groups
from uniwire import load, render_pages
from uniwire.i18n import CATALOGS
from uniwire.labels import CARTOUCHE_TITLES, cell
from uniwire.layout.engine import _is_dc
from uniwire.layout.multiline import conductors
from uniwire.model.document import View
from uniwire.render import default_view
from uniwire.render.scene import Circle, Rect
from uniwire.render.svg import page_to_svg
from uniwire.resolve import UniwireError
from uniwire.symbols import symbol_for
from uniwire.tolerate import tolerate

NEW_ROWS = ["status", "manufacturer", "part_number", "icu_kA", "icw_kA", "socket_type"]


def _doc(*children, system="3P+N", views=None):
    d = {"uniwire": "1.0.0-draft", "installation": {"system": system, "earthing": "TN-S"},
         "sources": [{"type": "grid", "id": "G", "children": list(children)}]}
    if views is not None:
        d["views"] = views
    return d


# ---------------------------------------------------------------- circuit schedule rows
def test_new_cartouche_rows_are_accepted_and_titled_in_every_language():
    assert View(cartouche=NEW_ROWS).cartouche == NEW_ROWS
    for lang in CATALOGS:
        titles = CARTOUCHE_TITLES.get(lang)
        assert titles is not None, lang
        for f in NEW_ROWS:
            assert titles.get(f), (lang, f)


def test_new_cartouche_rows_values():
    doc = load(_doc({"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 16, "icu_kA": 10, "icw_kA": 3,
                     "product": {"manufacturer": "Example Co", "part_number": "EX-16"}, "children": [
                         {"type": "socket", "id": "S1", "status": "existing", "socket_type": "2P+E 16 A"}]}))
    q1 = doc.sources[0].children[0]
    col = {"leaf": q1.children[0], "prot": q1, "cable": None}
    assert cell("status", col) == "existing"
    assert cell("status", col, "fr") == "existant"
    assert cell("manufacturer", col) == "Example Co"
    assert cell("part_number", col) == "EX-16"
    assert cell("icu_kA", col) == "10 kA"
    assert cell("icw_kA", col) == "3 kA"
    assert cell("socket_type", col) == "2P+E 16 A"


def test_new_cartouche_rows_drawn_in_the_table():
    doc = load(_doc({"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 16, "icu_kA": 10,
                     "manufacturer": "Example Co", "part_number": "EX-16", "children": [
                         {"type": "socket", "id": "S1", "status": "new", "socket_type": "2P+E 16 A"}]},
                    views=[{"id": "sld", "cartouche": ["label", "ref", *NEW_ROWS]}]))
    svg = page_to_svg(render_pages(doc, doc.views[0])[0])
    for text in ("Manufacturer", "Part number", "Icu", "Icw", "Socket type", "Example Co", "EX-16", "10 kA",
                 "2P+E 16 A"):
        assert text in svg, text


# ---------------------------------------------------------------- dc on a breaker
def test_breaker_dc_makes_its_line_dc():
    doc = load(_doc({"type": "inverter", "id": "INV", "kind": "hybrid", "children": [
        {"type": "breaker", "id": "QD", "in_A": 32, "poles": "2P", "dc": True, "children": [
            {"type": "load", "id": "LD", "label": "DC load"}]},
        {"type": "breaker", "id": "QA", "in_A": 16, "poles": "1P+N", "children": [
            {"type": "socket", "id": "S1"}]}]}, system="1P+N"))
    qd = doc.sources[0].children[0].children[0]
    assert qd.dc is True and _is_dc(qd)
    c = conductors(doc)
    assert [x for x in c["LD"].inp if x != "PE"] == ["L+", "L-"]
    assert "L+" not in c["S1"].inp


# ---------------------------------------------------------------- current shunt
def _shunt_doc(**shunt):
    return _doc({"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 32, "poles": "3P+N", "children": [
        {"type": "instrument_transformer", "id": "RS", "ref": "-R1", "kind": "shunt", **shunt, "children": [
            {"type": "motor", "id": "M1", "p_kW": 4}]}]})


def test_shunt_single_line_symbol_is_a_resistor():
    sym = symbol_for(load(_shunt_doc()).sources[0].children[0].children[0])
    assert any(isinstance(i, Rect) for i in sym.items)
    assert not any(isinstance(i, Circle) for i in sym.items)


@pytest.mark.parametrize("phase, expected", [(None, "L1"), ("L2", "L2")])
def test_shunt_multi_line_on_the_measured_conductor_only(phase, expected):
    doc = load(_shunt_doc(**({"phase": phase} if phase else {})))
    c = conductors(doc)
    assert c["M1"].inp == ["L1", "L2", "L3", "PE"]  # its phase names the measured conductor, not the circuit's
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    sym = next(g for g in _groups(page.root) if g.id == "RS" and (g.cls or "").startswith("ml-sym"))
    rects = [(g.attrs or {}).get("data-uw-cond") for g in _groups(sym)
             if any(isinstance(i, Rect) for i in g.items)]
    assert rects == [expected]
    assert not any(isinstance(i, Circle) for g in _groups(sym) for i in g.items)


def test_shunt_on_a_dc_line_is_in_l_plus():
    doc = load(_doc({"type": "inverter", "id": "INV", "children": [
        {"type": "instrument_transformer", "id": "RS", "kind": "shunt", "children": [
            {"type": "battery", "id": "B1", "un_V": 48}]}]}, system="1P+N"))
    page = render_pages(doc, default_view(doc, kind="multi-line"))[0]
    sym = next(g for g in _groups(page.root) if g.id == "RS" and (g.cls or "").startswith("ml-sym"))
    assert [(g.attrs or {}).get("data-uw-cond") for g in _groups(sym)
            if any(isinstance(i, Rect) for i in g.items)] == ["L+"]


# ---------------------------------------------------------------- pitch_mm
def test_pitch_under_the_minimum_read_as_the_minimum():
    d = _doc({"type": "breaker", "id": "Q1"}, views=[{"id": "sld", "pitch_mm": 6}])
    fixed, notes = tolerate(d)
    assert fixed["views"][0]["pitch_mm"] == 10 and len(notes) == 1 and "pitch_mm" in notes[0]
    assert load(d).views[0].pitch_mm == 10
    with pytest.raises(UniwireError):
        load(_doc({"type": "breaker", "id": "Q1"}, views=[{"id": "sld", "pitch_mm": 60}]))


# ---------------------------------------------------------------- residual current on a breaker
@pytest.mark.parametrize("field, value", [("residual_mA", 30), ("residual_type", "A"), ("idn_mA", 30),
                                          ("rcd_type", "A")])
def test_residual_current_on_a_breaker_points_to_an_rcbo(field, value):
    with pytest.raises(UniwireError) as e:
        load(_doc({"type": "breaker", "id": "Q1", field: value}))
    msg = str(e.value)
    assert field in msg and "'rcbo'" in msg and "'idn_mA'" in msg and "'rcd_type'" in msg


def test_residual_hint_only_for_residual_fields():
    with pytest.raises(UniwireError) as e:
        load(_doc({"type": "breaker", "id": "Q1", "colour": "grey"}))
    assert "rcbo" not in str(e.value)
