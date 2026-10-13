"""Wire marking (UEP-0001 §3.5, current format), cable tags and CSV exports."""

import csv
import io
import json
import xml.etree.ElementTree as ET

import pytest

from tests.conftest import ROOT
from uniwire import UniwireError, load, render_pages
from uniwire.cli import main
from uniwire.exports import CABLE_COLUMNS, MARKER_COLUMNS, WIRE_COLUMNS, cables_csv, markers_csv, wires_csv
from uniwire.labels import cell
from uniwire.marks import cable_wires, freeze, marked_wires
from uniwire.model import View
from uniwire.render import default_view
from uniwire.render.svg import page_to_svg

NS = "{http://www.w3.org/2000/svg}"
EX = ROOT / "examples"


def _doc(**marking):
    data = {
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
        "sources": [{"type": "grid", "id": "G", "children": [
            {"type": "board", "id": "B", "ref": "=B", "children": [
                {"type": "breaker", "id": "Q1", "ref": "-Q1", "poles": "3P", "in_A": 16, "circuit": "C1", "children": [
                    {"type": "motor", "id": "M1", "ref": "-M1", "phases": 3,
                     "cable": {"ref": "W1", "cores": "4G", "section_mm2": 2.5, "length_m": 20}}]},
                {"type": "breaker", "id": "Q2", "ref": "-Q2", "poles": "1P+N", "phase": "L2", "in_A": 16,
                 "circuit": "C2", "children": [
                     {"type": "socket", "id": "S2", "cable": {"ref": "W2", "cores": "3G", "section_mm2": 2.5,
                                                              "marks": {"N": "N7"}}}]},
            ]}]}],
        "views": [{"id": "ml", "kind": "multi-line", **({"wire_marking": marking} if marking else {})}],
    }
    return load(data)


def _marks(doc, view=None):
    return {w.id: w.mark for w in marked_wires(doc, view or doc.views[0])}


def test_cable_wires_follow_the_conductor_derivation():
    doc = _doc()
    ws = {w.id: w for w in cable_wires(doc)}
    assert list(ws) == ["M1.cable.L1", "M1.cable.L2", "M1.cable.L3", "M1.cable.PE",
                        "S2.cable.L2", "S2.cable.N", "S2.cable.PE"]
    w = ws["M1.cable.L1"]
    assert (w.from_id, w.from_display, w.to_display, w.circuit, w.cable_ref, w.from_enclosure) == \
        ("Q1", "-Q1", "-M1", "C1", "W1", "B")
    assert ws["S2.cable.N"].manual == "N7"


def test_manual_scheme_and_no_marking():
    assert _marks(_doc()) == {**{k: "" for k in _marks(_doc()) if k != "S2.cable.N"}, "S2.cable.N": "N7"}
    assert set(_marks(_doc(scheme="manual")).values()) == {"", "N7"}


def test_sequential_numbers_skip_manual_marks():
    m = _marks(_doc(scheme="sequential", power="number", start=1, prefix="W", keep_manual=True))
    assert m["M1.cable.L1"] == "W1" and m["M1.cable.PE"] == "W4"
    assert m["S2.cable.L2"] == "W5" and m["S2.cable.N"] == "N7" and m["S2.cable.PE"] == "W6"
    # keep_manual false: the manual mark is overwritten
    m = _marks(_doc(scheme="sequential", power="number", start=10, step=10, keep_manual=False))
    assert m["S2.cable.N"] == "60" and m["M1.cable.L1"] == "10"


def test_power_conductor_default_marks_with_conductor_names():
    m = _marks(_doc(scheme="sequential"))
    assert m["M1.cable.L1"] == "L1" and m["S2.cable.L2"] == "L2" and m["S2.cable.N"] == "N7"
    assert set(_marks(_doc(scheme="sequential", power="none", keep_manual=False)).values()) == {""}


def test_pattern_tokens():
    m = _marks(_doc(scheme="pattern", pattern="{circuit}-{conductor}"))
    assert m["M1.cable.L3"] == "C1-L3" and m["S2.cable.PE"] == "C2-PE" and m["S2.cable.N"] == "N7"
    m = _marks(_doc(scheme="pattern", pattern="{cable}/{ref}/{to}/{n}{potential}", start=5))
    assert m["M1.cable.L1"] == "W1/-Q1/-M1/5" and m["M1.cable.L2"] == "W1/-Q1/-M1/6"
    with pytest.raises(UniwireError, match="unknown token"):
        _doc(scheme="pattern", pattern="{circuit}-{bogus}")
    with pytest.raises(UniwireError, match="needs a 'pattern'"):
        _doc(scheme="pattern")


def test_potential_scheme_shares_numbers_on_a_net():
    m = _marks(_doc(scheme="potential", power="number", keep_manual=False))
    # each pole output is its own net; the PE is one net through the installation
    assert len({m["M1.cable.L1"], m["M1.cable.L2"], m["M1.cable.L3"]}) == 3
    assert m["M1.cable.PE"] == m["S2.cable.PE"]
    assert m["S2.cable.N"] not in (m["M1.cable.PE"], m["S2.cable.L2"])


def test_per_enclosure_restarts_numbering():
    doc = _doc(scheme="sequential", power="number", per="enclosure", order="document")
    m = _marks(doc)
    assert m["M1.cable.L1"] == "1"


def test_marks_are_deterministic_and_layout_ordered():
    doc = load(next(EX.glob("24_*.uniwire.json")))
    view = default_view(doc, "marks")
    a = _marks(doc, view)
    assert a == _marks(doc, view)
    assert a["MCC.cable.L1"] == "1L1"  # manual marks of the incoming cable
    assert a["M1.cable.L1"] == "101" and a["M1.cable.PE"] == "104"


def test_wire_csv_columns():
    doc = _doc(scheme="sequential", power="number", start=101)
    rows = list(csv.DictReader(io.StringIO(wires_csv(doc, doc.views[0]))))
    assert list(rows[0]) == WIRE_COLUMNS
    r = rows[0]
    assert (r["wire_id"], r["mark"], r["from"], r["from_display"], r["to"], r["to_display"], r["conductor"],
            r["section_mm2"], r["cable"], r["length_m"]) == \
        ("M1.cable.L1", "101", "Q1", "-Q1", "M1", "-M1", "L1", "2.5", "M1.cable", "20")


def test_marker_csv_one_row_per_end():
    doc = _doc(scheme="sequential", power="number")
    rows = list(csv.DictReader(io.StringIO(markers_csv(doc, doc.views[0]))))
    assert list(rows[0]) == MARKER_COLUMNS
    assert len(rows) == 2 * 7
    assert [(r["end"], r["terminal_display"], r["quantity"]) for r in rows[:2]] == [("from", "-Q1", "1"), ("to", "-M1", "1")]
    assert markers_csv(_doc()).count("\n") == 1 + 2  # manual marks only: the N7 core


def test_cable_csv_columns():
    rows = list(csv.DictReader(io.StringIO(cables_csv(_doc()))))
    assert list(rows[0]) == CABLE_COLUMNS
    assert [(r["cable_id"], r["ref"], r["from"], r["to"], r["cores_used"], r["cores_spare"]) for r in rows] == \
        [("M1.cable", "W1", "Q1", "M1", "4", "0"), ("S2.cable", "W2", "Q2", "S2", "3", "0")]


def _svg_root(doc, view):
    return [ET.fromstring(page_to_svg(p).split("?>", 1)[1]) for p in render_pages(doc, view)]


def test_svg_data_uw_mark_and_labels():
    doc = _doc(scheme="sequential", power="number", start=101)
    (svg,) = _svg_root(doc, doc.views[0])
    marked = {(g.get("data-uw-cond"), g.get("data-uw-mark")) for g in svg.iter(NS + "g") if g.get("data-uw-mark")}
    assert {("L1", "101"), ("PE", "104"), ("N", "N7")} <= marked
    edge = next(g for g in svg.iter(NS + "g") if g.get("data-uw-edge") == "M1")
    assert {g.get("data-uw-mark") for g in edge if g.get("data-uw-cond")} == {"101", "102", "103", "104"}
    texts = {t.text for t in svg.iter(NS + "text")}
    assert {"101", "104", "N7"} <= texts
    # hidden with wire_marks = false, absent without wire_marking
    view = doc.views[0].model_copy(update={"wire_marks": False})
    (svg,) = _svg_root(doc, view)
    assert not any(g.get("data-uw-mark") for g in svg.iter(NS + "g"))
    plain = _doc()
    assert page_to_svg(render_pages(plain, plain.views[0])[0]).count("data-uw-mark") == 0


def test_cable_ref_shown_in_drawings():
    doc = _doc()
    sld = page_to_svg(render_pages(doc, View(cartouche=["label", "cable"]))[0])
    assert "W1 · 4G2.5" in sld
    assert "W1 · " not in page_to_svg(render_pages(doc, View(cartouche=["label", "cable", "cable_ref"]))[0])
    ml = page_to_svg(render_pages(doc, doc.views[0])[0])
    assert ">W1<" in ml and ">W2<" in ml
    assert cell("cable_ref", {"cable": doc.sources[0].children[0].children[0].children[0].cable}) == "W1"


def test_freeze_writes_cable_marks(tmp_path):
    src = EX / "24_factory_mcc_motor_starters.uniwire.json"
    path = tmp_path / "mcc.uniwire.json"
    path.write_text(src.read_text("utf-8"), "utf-8")
    assert main(["marks", str(path), "--view", "marks", "--write"]) == 0
    data = json.loads(path.read_text("utf-8"))
    mcc = data["sources"][0]["children"][0]
    assert mcc["cable"]["marks"] == {"L1": "1L1", "L2": "1L2", "L3": "1L3", "PE": "PE"}
    m1 = mcc["children"][0]["children"][0]["children"][0]["children"][0]
    assert m1["cable"]["marks"] == {"L1": "101", "L2": "102", "L3": "103", "PE": "104"}
    # frozen: the manual scheme now gives the same marks
    doc = load(path)
    assert _marks(doc, View(kind="multi-line")) == _marks(doc, default_view(doc, "marks"))
    assert freeze({"sources": []}, doc, marked_wires(doc)) == (0, [])


def test_cli_exports(tmp_path, capsys):
    f = str(EX / "06_german_single_family_house.uniwire.json")
    assert main(["wires", f, "--view", "marks"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(",".join(WIRE_COLUMNS)) and "W11-L1" in out and "W0-PEN" in out
    assert main(["markers", f, "-o", str(tmp_path / "m.csv")]) == 0
    assert (tmp_path / "m.csv").read_text("utf-8").startswith(",".join(MARKER_COLUMNS))
    assert main(["cables", f]) == 0
    assert "W41" in capsys.readouterr().out
