"""I/O list and terminal strip table built from the PLCs, link ports and terminal blocks (SPEC §3b, §7.2)."""

import csv
import io

import pytest

from tests.conftest import ROOT
from uniwire import load
from uniwire.cli import main
from uniwire.exports import (
    IO_COLUMNS,
    TERMINAL_COLUMNS,
    declared_terminals,
    io_csv,
    io_rows,
    terminal_rows,
    terminals_csv,
)
from uniwire.model.nodes import TerminalBlock

EX = ROOT / "examples"


def _panel(extra_links=(), plc_label=None):
    """A small invented machine panel: a PLC with built-in DI/DO, an AI module and a communication module; a flow
    switch and a level transmitter wired to it through the terminal block -X2; a motor fed through -X1."""
    return load({
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
        "sources": [{"type": "grid", "id": "G", "children": [
            {"type": "board", "id": "B", "ref": "=B", "children": [
                {"type": "breaker", "id": "Q1", "ref": "-Q1", "poles": "3P", "in_A": 16, "children": [
                    {"type": "contactor", "id": "KM1", "ref": "-KM1", "coil_V": 24, "children": [
                        {"type": "terminal_block", "id": "X1", "ref": "-X1", "terminals": "1=U; 2=V; 3=W; 4=PE",
                         "cable": {"ref": "W1", "cores": "4G", "section_mm2": 2.5, "marks": {"L1": "11"}},
                         "children": [{"type": "motor", "id": "M1", "ref": "-M1", "phases": 3,
                                       "cable": {"ref": "W2", "cores": "4G", "section_mm2": 2.5}}]}]}]},
                {"type": "breaker", "id": "Q2", "ref": "-Q2", "poles": "1P+N", "in_A": 6, "children": [
                    {"type": "power_supply", "id": "T1", "ref": "-T1", "u2_V": 24, "children": [
                        {"type": "plc", "id": "A1", "ref": "-A1",
                         "onboard": [{"slot": 0, "kind": "di", "channels": 4, "un_V": 24},
                                     {"slot": 0, "kind": "do", "channels": 2, "un_V": 24}],
                         "modules": [{"slot": 1, "kind": "ai", "channels": 2, "signal": "4-20 mA",
                                      "part_number": "AI-2", "channel_labels": {"1": plc_label or "Tank level"}},
                                     {"slot": 2, "kind": "comm", "protocol": "RS485"},
                                     {"slot": 3, "kind": "mixed_io", "channels": 2}]}]}]}]}]}],
        "devices": [
            {"type": "terminal_block", "id": "X2", "ref": "-X2", "terminals": "X2.1-X2.6"},
            {"type": "controller", "id": "S1", "ref": "-S1", "function": "flow switch"},
            {"type": "controller", "id": "B1", "ref": "-B1", "function": "level transmitter"},
            {"type": "meter", "id": "P1", "ref": "-P1"},
        ],
        "links": [
            {"kind": "control", "from": "A1", "from_port": "0.1", "to": "KM1", "label": "Pump run"},
            {"kind": "measure", "from": "X2", "from_port": "X2:3", "to": "A1", "to_port": "0.1"},
            {"kind": "measure", "from": "S1", "from_port": "13", "to": "X2", "to_port": "3", "label": "Pump on",
             "cable": {"ref": "W5", "cores": "2x", "section_mm2": 0.75}},
            {"kind": "measure", "from": "B1", "to": "X2", "to_port": "5"},
            {"kind": "measure", "from": "X2", "from_port": "5", "to": "A1", "to_port": "1.1"},
            {"kind": "data", "from": "A1", "from_port": "2", "to": "P1", "protocol": "Modbus RTU"},
            {"kind": "control", "from": "A1", "from_port": "3.2", "to": "KM1"},
            {"kind": "measure", "from": "KM1", "to": "A1", "to_port": "3.1", "label": "Running"},
            {"kind": "measure", "from": "P1", "to": "A1", "to_port": "1.3"},
            {"kind": "control", "from": "A1", "to": "KM1", "label": "Enable"},
            {"kind": "earth", "from": "A1", "to": "X2"},
            {"kind": "control", "from": "S1", "to": "X2", "label": "Spare pair"},
            *extra_links,
        ],
    })


def _io(doc, address=None, **match):
    rows = [r for r in io_rows(doc) if address is None or r["address"] == address]
    return [r for r in rows if all(r[k] == v for k, v in match.items())]


def test_io_list_one_row_per_channel_connected_or_spare():
    doc = _panel()
    rows = io_rows(doc)
    assert all(list(r) == IO_COLUMNS for r in rows)
    # every channel of the I/O modules, in slot and channel order: 4 DI + 2 DO + 2 AI (+ channel 3 beyond the
    # module, kept so that it can be corrected) + 2 mixed
    io = [(r["slot"], r["module_kind"], r["channel"]) for r in rows if r["module_kind"] != "comm" and r["slot"] != ""]
    assert io == [(0, "di", 1), (0, "di", 2), (0, "di", 3), (0, "di", 4), (0, "do", 1), (0, "do", 2),
                  (1, "ai", 1), (1, "ai", 2), (1, "ai", 3), (3, "mixed_io", 1), (3, "mixed_io", 2)]
    spare = _io(doc, "0.3")
    assert spare[0]["device"] == "" and spare[0]["io_type"] == "DI" and spare[0]["direction"] == "in"


def test_io_list_slot_shared_by_input_and_output_modules():
    doc = _panel()
    out = _io(doc, "0.1", module_kind="do")
    assert len(out) == 1 and out[0]["io_type"] == "DO" and out[0]["device_display"] == "-KM1"
    assert out[0]["label"] == "Pump run" and out[0]["link_kind"] == "control" and out[0]["un_V"] == "24"
    inp = _io(doc, "0.1", module_kind="di")
    assert len(inp) == 1 and inp[0]["io_type"] == "DI" and inp[0]["direction"] == "in"


def test_io_list_follows_the_terminal_to_the_field_device():
    doc = _panel()
    r = _io(doc, "0.1", module_kind="di")[0]
    # the PLC link lands on -X2:3; the flow switch arrives on the same terminal through its own cable
    assert (r["device"], r["device_display"], r["device_port"], r["terminal"]) == ("S1", "-S1", "13", "-X2:3")
    assert r["label"] == "Pump on" and r["cable"] == "W5"
    r = _io(doc, "1.1")[0]
    assert (r["device_display"], r["terminal"], r["label"], r["signal"], r["module"], r["io_type"]) == (
        "-B1", "-X2:5", "Tank level", "4-20 mA", "AI-2", "AI")


def test_io_list_terminal_without_continuation_names_the_block():
    doc = _panel(extra_links=[{"kind": "control", "from": "A1", "from_port": "0.2", "to": "X2", "to_port": "6"}])
    r = _io(doc, "0.2", module_kind="do")[0]
    assert (r["device"], r["device_port"], r["terminal"]) == ("X2", "", "-X2:6")


def test_io_list_mixed_module_comm_module_and_links_without_channel():
    doc = _panel()
    assert _io(doc, "3.1")[0]["io_type"] == "DI" and _io(doc, "3.1")[0]["label"] == "Running"
    assert _io(doc, "3.2")[0]["io_type"] == "DO" and _io(doc, "3.2")[0]["direction"] == "out"
    bus = _io(doc, "2")[0]
    assert (bus["module_kind"], bus["io_type"], bus["direction"], bus["signal"], bus["device_display"]) == (
        "comm", "COM", "bus", "RS485", "-P1")
    loose = [r for r in io_rows(doc) if r["slot"] == ""]
    assert [(r["label"], r["device"], r["direction"]) for r in loose] == [("Enable", "KM1", "out")]
    assert not [r for r in io_rows(doc) if r["link_kind"] == "earth"]


def test_io_list_without_plc_is_empty():
    assert io_csv(load({"sources": [{"type": "grid", "id": "G"}]})) == ",".join(IO_COLUMNS) + "\n"


def _strip(doc, strip):
    return [r for r in terminal_rows(doc) if r["strip"] == strip]


def test_terminal_strip_lists_declared_terminals_and_link_ends():
    doc = _panel()
    rows = _strip(doc, "X2")
    assert all(list(r) == TERMINAL_COLUMNS for r in terminal_rows(doc))
    assert [r["terminal"] for r in rows] == ["1", "2", "3", "4", "5", "6", "", ""]
    t3 = rows[2]
    assert (t3["from_display"], t3["from_port"], t3["from_cable"], t3["to_display"], t3["to_port"]) == (
        "-S1", "13", "W5", "-A1", "0.1")
    assert (t3["link_kind"], t3["label"]) == ("measure", "Pump on")
    assert rows[0]["from"] == rows[0]["to"] == ""  # spare
    # link ends without a terminal number: one row each, at the end
    assert {(r["from"], r["link_kind"]) for r in rows[-2:]} == {("A1", "earth"), ("S1", "control")}


def test_terminal_strip_in_the_power_tree_places_conductors_with_marks():
    rows = _strip(_panel(), "X1")
    got = [(r["terminal"], r["function"], r["from_display"], r["from_mark"], r["from_cable"], r["to_display"],
            r["to_cable"], r["link_kind"]) for r in rows]
    assert got == [("1", "U", "-KM1", "11", "W1", "-M1", "W2", "power"),
                   ("2", "V", "-KM1", "", "W1", "-M1", "W2", "power"),
                   ("3", "W", "-KM1", "", "W1", "-M1", "W2", "power"),
                   ("4", "PE", "-KM1", "", "W1", "-M1", "W2", "power")]


def test_terminal_strip_generated_marks_follow_the_view():
    data = {
        "installation": {"earthing": "TN-S", "system": "1P+N", "un_V": 230},
        "sources": [{"type": "grid", "id": "G", "children": [
            {"type": "breaker", "id": "Q1", "ref": "-Q1", "poles": "1P+N", "in_A": 10, "children": [
                {"type": "terminal_block", "id": "X1", "ref": "-X1", "terminals": "1=L; 2=N; 3=PE", "children": [
                    {"type": "lighting", "id": "E1", "ref": "-E1",
                     "cable": {"cores": "3G", "section_mm2": 1.5}}]}]}]}],
        "views": [{"id": "ml", "kind": "multi-line",
                   "wire_marking": {"scheme": "sequential", "power": "number", "start": 100}}],
    }
    doc = load(data)
    parsed = list(csv.DictReader(io.StringIO(terminals_csv(doc, doc.views[0]))))
    # the parent has no cable: it is on every conductor taken by the child's cable; L lands on the only line
    assert [(r["terminal"], r["function"], r["from_display"], r["to_display"]) for r in parsed] == [
        ("1", "L", "-Q1", "-E1"), ("2", "N", "-Q1", "-E1"), ("3", "PE", "-Q1", "-E1")]
    assert all(r["to_mark"].isdigit() and int(r["to_mark"]) >= 100 for r in parsed)
    assert all(r["to_mark"] == "" for r in terminal_rows(doc))  # without the view: manual marks only


@pytest.mark.parametrize("text, expected", [
    ("X1.1-X1.3", [("1", ""), ("2", ""), ("3", "")]),
    ("1-3, PE", [("1", ""), ("2", ""), ("3", ""), ("PE", "")]),
    ("X1:4-6", [("4", ""), ("5", ""), ("6", "")]),
    ("1=L1; 2=N; 3=PE", [("1", "L1"), ("2", "N"), ("3", "PE")]),
    ("1, 1, 2", [("1", ""), ("2", "")]),
    ("Field terminals for the pumps", []),
    ("1-99999", []),
    (None, []),
])
def test_declared_terminals(text, expected):
    assert declared_terminals(TerminalBlock(type="terminal_block", id="X1", ref="-X1", terminals=text)) == expected


def test_cli_and_tool(tmp_path, capsys):
    import json

    from uniwire.llm import tools as T

    f = tmp_path / "panel.uniwire.json"
    doc = _panel()
    f.write_text(json.dumps(doc.model_dump(by_alias=True, exclude_none=True, mode="json")), "utf-8")
    assert main(["io", str(f)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(",".join(IO_COLUMNS)) and "-X2:3" in out
    assert main(["terminals", str(f), "-o", str(tmp_path / "t.csv")]) == 0
    assert (tmp_path / "t.csv").read_text("utf-8").startswith(",".join(TERMINAL_COLUMNS))
    res = T.wiring(f.read_text("utf-8"), "io")
    assert res["columns"] == IO_COLUMNS and any(r["terminal"] == "-X2:5" for r in res["rows"])
    res = T.wiring(f.read_text("utf-8"), "terminals")
    assert res["columns"] == TERMINAL_COLUMNS and res["view"] is None and res["rows"]


def test_csv_neutralises_formulas():
    text = io_csv(_panel(plc_label="=HYPERLINK(\"x\")"))
    assert "'=HYPERLINK" in text


def test_bundled_examples_export():
    n = 0
    for path in sorted(EX.glob("*.uniwire.json")):
        doc = load(path)
        rows = io_rows(doc)
        terminal_rows(doc)
        n += sum(1 for r in rows if r["device"])
    assert n > 10
