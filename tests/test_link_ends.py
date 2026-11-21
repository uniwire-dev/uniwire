"""Each link visibly starts and ends at its own device: two thin links never end on one point of a device (one would
read as branching off the other), an earth bar takes a second earth link on its top; an inverter/charger's text keeps
its size beside its DC side; both lines of a sheet reference stay on one side of the stub they name."""

import copy

import uniwire
from tests.drawing_audit import audit
from uniwire.render import render_views
from uniwire.render.scene import Group, Line, Polyline, Text

DOC = {
    "uniwire": "1.0.0-draft",
    "installation": {"system": "1P+N", "earthing": "TT", "un_V": 230},
    "sources": [
        {"type": "grid", "id": "grid", "label": "Public supply", "children": [
            {"type": "main_breaker", "id": "qm", "ref": "-Q0", "in_A": 40, "children": [
                {"type": "board", "id": "mb", "ref": "=MB", "label": "Main board", "children": [
                    {"type": "meter", "id": "pm", "ref": "-P1", "label": "Export meter", "children": [
                        {"type": "busbar", "id": "w1", "children": [
                            {"type": "breaker", "id": "q1", "ref": "-Q1", "in_A": 16,
                             "children": [{"type": "load", "id": "l1", "label": "Sockets"}]},
                            {"type": "breaker", "id": "q2", "ref": "-Q2", "in_A": 10,
                             "children": [{"type": "lighting", "id": "l2", "label": "Lights"}]},
                            {"type": "rcbo", "id": "qinv", "ref": "-Q3", "in_A": 32, "idn_mA": 30},
                            {"type": "breaker", "id": "q4", "ref": "-Q4", "in_A": 16,
                             "children": [{"type": "load", "id": "l4", "label": "Heat pump"}]}]}]}]}]}]},
        {"type": "inverter", "id": "inv", "ref": "-T1", "kind": "hybrid", "p_kVA": 6,
         "label": "Hybrid inverter with storage and backup output", "children": [
            {"type": "switch_disconnector", "id": "qpv", "ref": "-Q5", "dc": True, "label": "PV isolator",
             "children": [{"type": "pv_array", "id": "pv", "ref": "-G1", "label": "Array"}]},
            {"type": "switch_disconnector", "id": "fbat", "ref": "-Q7", "dc": True, "label": "Battery isolator",
             "children": [{"type": "battery", "id": "bat", "ref": "-G2", "label": "Battery"}]},
            {"type": "board", "id": "bb", "ref": "=BB", "label": "Backup board", "children": [
                {"type": "breaker", "id": "q6", "ref": "-Q6", "in_A": 16,
                 "children": [{"type": "load", "id": "l6", "label": "Fridge"}]}]}]},
        {"type": "earth_bar", "id": "met", "ref": "=E1", "kind": "main_earth", "label": "Main earthing terminal"},
        {"type": "earth", "id": "el", "ref": "=E2", "label": "Earth electrode"},
    ],
    "links": [
        {"kind": "infeed", "from": "qinv", "to": "inv", "label": "AC input"},
        {"kind": "measure", "from": "pm", "to": "inv", "label": "Meter data bus"},
        {"kind": "earth", "from": "met", "to": "el", "label": "Earthing conductor"},
        {"kind": "earth", "from": "inv", "to": "met", "label": "Inverter protective conductor"},
    ],
}


def _small_sheets(doc):
    """The same document on A4 sheets drawn at full size: split over two sheets."""
    d = copy.deepcopy(doc)
    d["views"] = [{"id": "sld", "kind": "single-line", "paper": "A4", "min_scale": 1.0}]
    return d


def _pages(doc):
    return render_views(uniwire.load(doc))


def _findings(doc, kinds):
    return [f for pg in _pages(doc) for f in audit(pg.root) if f.kind in kinds]


def _groups(item):
    if isinstance(item, Group):
        yield item
        for i in item.items:
            yield from _groups(i)


def test_thin_links_never_end_on_one_point():
    for doc in (DOC, _small_sheets(DOC)):
        assert not _findings(doc, {"shared_end", "shared_run"})


def test_second_earth_link_on_top_of_the_earth_bar():
    """The bar takes one earth link on its side, the other on its top: both end on its strokes."""
    (pg,) = _pages(DOC)
    ends = []
    for g in _groups(pg.root):
        if g.attrs.get("data-uw-kind") == "earth" and "met" in (g.attrs.get("data-uw-from"), g.attrs.get("data-uw-to")):
            line = next(i for i in g.items if isinstance(i, Polyline) and not i.closed)
            ends.append(line.points[0] if g.attrs.get("data-uw-from") == "met" else line.points[-1])
    bar = next(g for g in _groups(pg.root) if g.id == "met" and "uw-node" in (g.cls or ""))
    top = min(y for i in bar.items if isinstance(i, Line) for y in (i.a[1], i.b[1]))  # (its bar)
    assert len(ends) == 2 and abs(ends[0][1] - ends[1][1]) > 1.0
    assert any(abs(e[1] - top) < 0.05 for e in ends)  # straight down onto the bar


def test_inverter_text_not_cut_beside_its_dc_side():
    """The column of an inverter's output (its board drawn on a sheet of its own: one narrow off-sheet stub) widens
    for its text: never cut, never drawn smaller."""
    doc = _small_sheets(DOC)
    doc["sources"][1]["children"][2]["children"] = [
        {"type": "breaker", "id": f"q6{k}", "ref": f"-Q6{k}", "in_A": 16,
         "children": [{"type": "load", "id": f"l6{k}", "label": f"Circuit {k}"}]} for k in range(12)]
    assert not _findings(doc, {"truncated", "small_text"})
    texts = [t.text for pg in _pages(doc) for g in _groups(pg.root) for t in g.items if isinstance(t, Text)]
    assert "Hybrid inverter with storage and backup output" in " ".join(texts)


def test_sheet_reference_on_one_side_of_its_stub():
    assert not _findings(_small_sheets(DOC), {"split_reference"})
