"""Code-first API (uniwire.build)."""

import pytest

from uniwire.build import (
    PLC,
    RCD,
    Appliance,
    Board,
    Breaker,
    Contactor,
    Cooking,
    Enclosure,
    Generator,
    Grid,
    Installation,
    Lighting,
    MainBreaker,
    Motor,
    Template,
    TransferSwitch,
    control,
    transfer,
)
from uniwire.resolve import UniwireError


def house():
    with Installation("House", earthing="TT", system="1P+N", un="230 V", profiles=["nfc15100"]) as inst:
        with Grid("Utility"), MainBreaker("-Q0", "15-45 A", "500 mA", selective=True), Board("TD1"):
            with RCD("-Q1", "40 A", "30 mA", type="A"):
                Breaker("-Q11", "C20", cable="3G2,5") >> Appliance("Washing machine", kind="washing_machine")
                Breaker("-Q12", "C32", cable="3G6") >> Cooking("Hob", kind="hob", p="7,2 kW")
            with RCD("-Q2", "40 A", "30 mA", type="AC"):
                Breaker("-Q21", "C16", cable="3G1,5 12 m") >> Lighting("Living room", points=6)
    return inst


def test_tree_structure_and_values():
    doc = house().document
    grid = doc.sources[0]
    mb = grid.children[0]
    assert mb.type == "main_breaker" and mb.range_A == "15-45" and mb.idn_mA == 500 and mb.selective
    board = mb.children[0]
    q11 = board.children[0].children[0]
    assert (q11.ref, q11.curve, q11.in_A, q11.cable.cores, q11.cable.section_mm2) == ("-Q11", "C", 20, "3G", 2.5)
    q21 = board.children[1].children[0]
    assert q21.cable.length_m == 12 and q21.children[0].points == 6
    assert board.children[0].children[1].children[0].p_kW == 7.2


def test_rules_and_render(tmp_path):
    inst = house()
    assert not [f for f in inst.check() if f.level == "error"]
    assert inst.render(tmp_path / "h.pdf").read_bytes().startswith(b"%PDF")
    assert inst.save(tmp_path / "h.uniwire.json").exists()


def test_chain_and_template():
    MOT = Template(curve="D", poles="3P", icn_kA=10)
    with Installation() as inst:
        with Grid("G"):
            km = Breaker("-Q1", "D16", **MOT) >> Contactor("-KM1", "18 A") >> Motor("Pump", p="5.5 kW")
    q1 = inst.document.sources[0].children[0]
    assert q1.icn_kA == 10 and q1.children[0].children[0].type == "motor" and km.data["type"] == "motor"


def test_plc_ports_and_transfer():
    with Installation() as inst:
        with Grid("G"):
            with Breaker("-Q1", "C2"):
                api = PLC("-A1", product="WAGO 750-8212")
                ro = api.add("relay_out", "750-512", channels=2)
                api.add("end", "750-600")
            with Breaker("-Q2", "16 A"):
                km = Contactor("-KM1", "18 A", coil_V=230)
            with Breaker("-QN", "100 A"):
                ts = TransferSwitch("-QI", "100 A")
        with Generator("-G1", sn_kVA=60):
            qg = Breaker("-QG", "100 A")
        control(ro[2], km)
        transfer(qg, ts)
    doc = inst.document
    assert doc.links[0].from_port == "1.2" and doc.links[1].kind == "transfer"
    assert doc.sources[0].children[0].children[0].product.part_number == "750-8212"
    assert not [f for f in inst.check() if f.rule.startswith("plc") and f.level != "info"]


def test_enclosure_membership():
    with Installation() as inst:
        with Grid("G"), Board("MDB"):
            with Enclosure("Cell 1", kind="cell", cell_type="IM"):
                b = Breaker("-Q1", "C16")
    enc = inst.document.enclosures[0]
    assert enc.kind == "cell" and enc.nodes == [b.id]


def test_errors_are_explicit():
    with pytest.raises(RuntimeError):
        Breaker("-Q1", "C16")
    with Installation():
        with pytest.raises(TypeError):
            Breaker("-Q1", "C16", calibre=16)
    with Installation() as inst:
        Grid("G") >> Breaker("-Q1", "C16", curve="X")
    with pytest.raises(UniwireError):
        _ = inst.document


def test_declare_interlock():
    with Installation("Interlock", system="3P+N") as inst:
        with Grid("Utility"), Board("TD"):
            Breaker("-Q1", "C16", locks=["K1"], normal_state="open")
            Breaker("-Q2", "C16", locks=["K1"])
        inst.declare_interlock("K1", keys=1, kind="mechanical", label="Q1 / Q2")
    doc = inst.document
    assert doc.interlocks[0].key == "K1" and doc.interlocks[0].kind == "mechanical"
