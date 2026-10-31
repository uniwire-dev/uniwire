"""Near-miss values read in canonical form on load, each reported by core.normalized."""

import copy
import json

import pytest

import uniwire
from uniwire.resolve import UniwireError
from uniwire.rules import check
from uniwire.tolerate import tolerate

BASE = {"uniwire": "1.0.0", "installation": {"earthing": "TT", "system": "1P+N", "un_V": 230}}


def _doc(*children, **extra):
    return {**BASE, **extra, "sources": [{"type": "grid", "id": "g", "children": list(children)}]}


def _notes(d):
    return [f.message for f in check(uniwire.load(d)) if f.rule == "core.normalized"]


@pytest.mark.parametrize("raw,canon", [(2, "2P"), (4, "4P"), ("3", "3P"), ("1p+n", "1P+N"), (" 3P+N ", "3P+N")])
def test_poles(raw, canon):
    d = _doc({"type": "breaker", "id": "Q1", "in_A": 16, "poles": raw})
    doc = uniwire.load(d)
    assert doc.sources[0].children[0].poles == canon and len(_notes(d)) == 1


def test_cores_and_ranges():
    d = _doc({"type": "breaker", "id": "Q1", "in_A": 16, "cable": {"cores": "5G2,5"}},
             {"type": "breaker", "id": "Q2", "in_A": 10, "cable": {"cores": 3, "section_mm2": 1.5}},
             {"type": "breaker", "id": "Q3", "in_A": 20, "cable": {"cores": "4x16", "section_mm2": 10}},
             {"type": "main_breaker", "id": "Q0", "range_A": [15, 45], "idn_range_mA": [30, 3000]})
    out = json.loads(uniwire.dump(uniwire.load(d)))["sources"][0]["children"]
    assert out[0]["cable"] == {"cores": "5G", "section_mm2": 2.5}
    assert out[1]["cable"]["cores"] == "3G"
    assert out[2]["cable"] == {"cores": "4x", "section_mm2": 10}  # an explicit section wins
    assert out[3]["range_A"] == "15-45" and out[3]["idn_range_mA"] == "30-3000"
    assert len(_notes(d)) == 5


def test_single_value_range():
    d = _doc({"type": "motor_starter", "id": "M1", "in_A": 16, "children": [
        {"type": "thermal_relay", "id": "F1", "range_A": 10, "children": [{"type": "motor"}]}]})
    relay = uniwire.load(d).sources[0].children[0].children[0]
    assert relay.range_A == "10" and len(_notes(d)) == 1


def test_meta_and_views():
    d = _doc({"type": "socket"}, meta={"title": "Shop", "description": "small shop", "notes": ["n1"]},
             views=[{"type": "multi_line"}])
    doc = uniwire.load(d)
    assert doc.meta.notes == ["n1", "small shop"] and doc.views[0].kind == "multi-line"
    assert len(_notes(d)) == 3


def test_input_untouched_and_canonical_silent():
    d = _doc({"type": "breaker", "id": "Q1", "in_A": 16, "poles": 2})
    before = copy.deepcopy(d)
    uniwire.load(d)
    assert d == before
    canon = _doc({"type": "breaker", "id": "Q1", "in_A": 16, "poles": "2P", "cable": {"cores": "3G", "section_mm2": 2.5}})
    assert _notes(canon) == [] and tolerate(canon)[1] == []


@pytest.mark.parametrize("bad", [{"poles": 5}, {"poles": "two"}, {"poles": True}, {"cable": {"cores": 0}},
                                 {"type": "main_breaker", "range_A": [15, "x"]}])
def test_ambiguous_values_still_fail(bad):
    with pytest.raises(UniwireError):
        uniwire.load(_doc({"type": "breaker", "id": "Q1", "in_A": 16, **bad}))


def test_rcd_count_only_for_dwellings():
    d = {**BASE, "profiles": ["nfc15100"], "sources": [{"type": "grid", "children": [
        {"type": "rcd", "id": "F1", "in_A": 40, "idn_mA": 30, "rcd_type": "A", "children": [
            {"type": "breaker", "id": "Q1", "in_A": 16, "curve": "C", "cable": {"cores": "3G", "section_mm2": 2.5},
             "children": [{"type": "socket", "points": 4}]}]}]}]}
    rules = lambda doc: {f.rule for f in check(uniwire.load(doc))}  # noqa: E731
    assert "nfc15100.rcd-count" in rules(d)
    d["installation"] = {**BASE["installation"], "premises": "dwelling"}
    assert "nfc15100.rcd-count" in rules(d)
    d["installation"] = {**BASE["installation"], "premises": "commercial"}
    assert "nfc15100.rcd-count" not in rules(d)
