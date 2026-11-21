import json

import pytest

from uniwire import UniwireError, dump, load
from uniwire.units import fmt, fmt_power, parse_quantity

MINI = {
    "templates": {"C16": {"type": "breaker", "in_A": 16, "curve": "C"}},
    "sources": [{"type": "grid", "children": [
        {"type": "breaker", "ref": "-Q1", "use": "C16", "children": [{"type": "socket", "points": 6}]},
        {"type": "breaker", "ref": "-Q2", "use": "C16", "in_A": 20},
    ]}],
}


def test_templates_and_ids():
    doc = load(MINI)
    q1, q2 = doc.sources[0].children
    assert (q1.id, q1.in_A, q1.curve) == ("Q1", 16, "C")
    assert (q2.id, q2.in_A) == ("Q2", 20)  # valeur locale prioritaire
    assert doc.sources[0].id == "grid"


@pytest.mark.parametrize("raw,unit,expected", [
    ("16 A", "A", 16), ("2,5 mm²", "mm2", 2.5), ("0,03 A", "mA", 30), ("30mA", "mA", 30),
    ("1 kA", "A", 1000), ("12 kVA", "kVA", 12), ("400V", "V", 400), (16, "A", 16),
    ({"value": 300, "unit": "mA"}, "mA", 300),
])
def test_units(raw, unit, expected):
    assert parse_quantity(raw, unit) == pytest.approx(expected)


def test_units_rejects_wrong_dimension():
    with pytest.raises(ValueError):
        parse_quantity("16 V", "A")


def test_lenient_input_canonical_output():
    data = json.loads(json.dumps(MINI))
    data["sources"][0]["children"][0]["in_A"] = "16 A"
    data["sources"][0]["children"][0]["cable"] = {"section_mm2": "2,5 mm²"}
    out = json.loads(dump(load(data)))
    q1 = out["sources"][0]["children"][0]
    assert q1["in_A"] == 16 and q1["cable"]["section_mm2"] == 2.5


def test_fmt():
    from uniwire.i18n import RENDER_LANG
    token = RENDER_LANG.set("en")
    try:
        assert fmt(16.0) == "16" and fmt(2.5) == "2.5" and fmt(4.5, "kA") == "4.5kA"
    finally:
        RENDER_LANG.reset(token)
    token = RENDER_LANG.set("fr")
    try:
        assert fmt(2.5) == "2,5" and fmt(4.5, "kA") == "4,5kA"
    finally:
        RENDER_LANG.reset(token)


@pytest.mark.parametrize("bad,needle", [
    ({"sources": [{"type": "breakr"}]}, "unknown node type"),
    ({"sources": [{"type": "breaker", "calibre": 16}]}, "unknown field"),
    ({"sources": [{"type": "breaker", "curve": "X"}]}, "curve"),
    ({"sources": [{"type": "breaker", "use": "nope"}]}, "unknown 'use' template"),
    ({"sources": [{"type": "grid", "id": "A"}, {"type": "grid", "id": "A"}]}, "duplicate identifier"),
    ({"sources": [{"type": "grid", "id": "A"}], "links": [{"kind": "control", "from": "A", "to": "Z"}]}, "'Z'"),
    ({"templates": {"T": {"type": "rcd"}}, "sources": [{"type": "breaker", "use": "T"}]}, "is of type 'rcd'"),
    ({"sources": []}, "sources"),
])
def test_errors_are_explicit(bad, needle):
    with pytest.raises(UniwireError) as e:
        load(bad)
    assert needle in str(e.value)


@pytest.mark.parametrize("bad,needle", [
    ({"sources": [{"type": "breakr"}]}, "type de nœud inconnu"),
    ({"sources": [{"type": "breaker", "calibre": 16}]}, "champ inconnu"),
    ({"sources": [{"type": "breaker", "use": "nope"}]}, "modèle 'use' inconnu"),
    ({"sources": [{"type": "grid", "id": "A"}, {"type": "grid", "id": "A"}]}, "dupliqué"),
    ({"templates": {"T": {"type": "rcd"}}, "sources": [{"type": "breaker", "use": "T"}]}, "est de type 'rcd'"),
])
def test_errors_in_french(bad, needle, monkeypatch):
    monkeypatch.setenv("UNIWIRE_LANG", "fr")
    with pytest.raises(UniwireError) as e:
        load(bad)
    assert needle in str(e.value)


@pytest.mark.parametrize("version", ["1.0.0", "1.0.3", "1.3.0", "1.12.1"])
def test_any_1y_format_version_loads(version):
    doc = load({**MINI, "uniwire": version})
    assert doc.uniwire == version


@pytest.mark.parametrize("version", ["2.0.0", "0.9.0", "1.0", "one"])
def test_other_major_versions_are_rejected(version):
    with pytest.raises(UniwireError):
        load({**MINI, "uniwire": version})


def test_newer_minor_with_unknown_fields_hints_at_upgrade():
    data = json.loads(json.dumps(MINI))
    data["uniwire"] = "1.9.0"
    data["sources"][0]["future_field"] = 1
    with pytest.raises(UniwireError) as exc:
        load(data)
    assert any("1.9.0" in i and "upgrade" in i for i in exc.value.issues)


def test_current_minor_with_unknown_fields_has_no_upgrade_hint():
    data = json.loads(json.dumps(MINI))
    data["sources"][0]["future_field"] = 1
    with pytest.raises(UniwireError) as exc:
        load(data)
    assert not any("upgrade" in i for i in exc.value.issues)


def test_cli_version(capsys):
    import uniwire
    from uniwire.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert uniwire.__version__ in out and uniwire.FORMAT_VERSION in out


def test_fmt_power_in_watts_below_1_kw():
    assert fmt_power(0.0162) == "16.2 W" and fmt_power(0.00075) == "0.75 W" and fmt_power(0.5) == "500 W"
    assert fmt_power(1) == "1 kW" and fmt_power(3.5) == "3.5 kW" and fmt_power(None) == ""


def _refusal(doc):
    with pytest.raises(UniwireError) as e:
        load(doc)
    return "\n".join(e.value.issues)


_BASE = {"uniwire": "1.0.0", "installation": {"earthing": "TT", "system": "3P+N", "un_V": 400}}


def _one(*children, **extra):
    return {**_BASE, **extra, "sources": [{"type": "grid", "id": "G", "children": list(children)}]}


def test_duplicate_id_message_gives_both_paths():
    msg = _refusal(_one({"type": "board", "id": "B1", "children": [{"type": "meter", "id": "P1"}]},
                        {"type": "breaker", "id": "Q1", "in_A": 16, "children": [{"type": "meter", "id": "P1"}]}))
    assert "'P1'" in msg
    assert "sources/0/grid/children/0/board/children/0/meter" in msg
    assert "sources/0/grid/children/1/breaker/children/0/meter" in msg


def test_unknown_field_names_what_to_write():
    msg = _refusal(_one({"type": "breaker", "id": "Q1", "in_A": 16, "children": [
        {"type": "load", "id": "L1", "in_A": 10}]}))
    assert "did you mean 'ib_A'?" in msg
    msg = _refusal(_one({"type": "breaker", "id": "Q1", "in_A": 16, "dc": True}))
    assert "'dc' is a field of switch_disconnector, spd, not of breaker" in msg
    msg = _refusal(_one({"type": "motor_starter", "id": "Q1", "ip_address": "10.0.0.1"}))
    assert "'ip_address' is a field of plc, not of motor_starter" in msg


def test_value_not_allowed_names_the_value():
    msg = _refusal(_one({"type": "socket"}, views=[{"kind": "single-line", "cartouche": ["ref", "colour"]}]))
    assert "'colour' is not one of the values allowed here" in msg and "label, ref" in msg
    msg = _refusal(_one({"type": "socket"}, views=[{"kind": "single-line", "pitch_mm": 8}]))
    assert "views/0/pitch_mm: 8 is below the smallest value allowed here; write 10 or more" in msg


def test_text_where_an_object_is_expected():
    msg = _refusal(_one({"type": "busbar", "id": "W1"}, {"type": "busbar", "id": "W2"},
                        {"type": "breaker", "id": "Q9", "in_A": 63}) | {
        "links": [{"kind": "tie", "from": "W1", "to": "W2", "device": "Q9"}]})
    assert "links/0/device: a node object is expected here, not the text 'Q9'" in msg
    msg = _refusal(_one({"type": "breaker", "id": "Q1", "in_A": 16,
                         "product": {"part_number": "X-100", "accessories": ["X-AUX"]}}))
    assert "an object is expected here, not the text 'X-AUX'" in msg and "part_number" in msg
