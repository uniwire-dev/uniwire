"""Symbol sets: a set registered from outside the library changes the drawing; an unknown one falls back to IEC."""

import sys
import threading
import time
from types import SimpleNamespace

import pytest

import uniwire.symbols as symbols
from uniwire import check, load
from uniwire.render import _PAGES, render_views
from uniwire.render.scene import THIN, Line, Rect, Style
from uniwire.render.svg import page_to_svg
from uniwire.symbols import Symbol, controller, register_symbol_set, symbol_sets
from uniwire.symbols.sheet import symbol_sheet

DOC = {"sources": [{"type": "grid", "children": [
    {"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]},
    {"type": "motor_starter", "children": [{"type": "motor", "p_kW": 4}]}]}]}


def square_breaker(node=None, **kwargs):
    """An invented breaker: a square on the conductor."""
    return Symbol("square-breaker", [Line((0, 0), (0, 4)), Rect(-2, 4, 4, 4, Style(width=THIN)), Line((0, 8), (0, 12))],
                  12.0)


def ring_motor(node=None, *args, **kwargs):
    return Symbol("ring-motor", [Rect(-3, 0, 6, 6, Style(width=THIN))], 6.0, 3.0, 3.0, has_output=False)


@pytest.fixture(autouse=True)
def clean_sets():
    saved, loaded = {k: dict(v) for k, v in symbols._SETS.items()}, symbols._loaded
    failures = {k: dict(v) for k, v in symbols.FAILURES.items()}
    yield
    symbols.FAILURES.clear()
    symbols.FAILURES.update(failures)
    symbols._SETS.clear()
    symbols._SETS.update(saved)
    symbols._loaded = loaded
    _PAGES.clear()


def _svg(doc):
    return "".join(page_to_svg(p) for p in render_views(load(doc)))


def test_registered_set_changes_the_drawing():
    register_symbol_set("invented", {"breaker": square_breaker, "motor": ring_motor})
    iec, own = _svg(DOC), _svg({**DOC, "symbols": "invented"})
    assert "sym-square-breaker" in own and "sym-ring-motor" in own  # the motor too, drawn through its variants
    assert "sym-square-breaker" not in iec and "sym-breaker" in iec
    assert "sym-socket" in own  # symbols the set does not give: IEC
    assert not [f for f in check(load({**DOC, "symbols": "invented"})) if f.rule == "core.symbol-set-unknown"]
    assert "invented" in symbol_sets()
    assert "sym-square-breaker" in page_to_svg(symbol_sheet(symbols="invented"))


def test_unknown_set_falls_back_to_iec_with_a_finding():
    found = [f for f in check(load({**DOC, "symbols": "nowhere"})) if f.rule == "core.symbol-set-unknown"]
    assert len(found) == 1 and "'nowhere'" in found[0].message and found[0].level == "warning"
    assert _svg({**DOC, "symbols": "nowhere"}) == _svg(DOC) == _svg({**DOC, "symbols": "iec"})


def test_default_set_is_not_written_out():
    assert "symbols" not in load(DOC).model_dump(mode="json", exclude_none=True)


def test_registration_errors():
    with pytest.raises(ValueError, match="built-in"):
        register_symbol_set("iec", {"breaker": square_breaker})
    with pytest.raises(ValueError, match="brekaer"):
        register_symbol_set("invented", {"brekaer": square_breaker})


def test_set_from_a_package_entry_point(tmp_path, monkeypatch):
    (tmp_path / "invented_symbols.py").write_text(
        "from uniwire.render.scene import THIN, Rect, Style\n"
        "from uniwire.symbols import Symbol\n"
        "def breaker(node=None, **kwargs):\n"
        "    return Symbol('package-breaker', [Rect(-2, 0, 4, 8, Style(width=THIN))], 8.0)\n"
        "SYMBOLS = {'breaker': breaker}\n")
    info = tmp_path / "invented_symbols-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: invented-symbols\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text("[uniwire.symbol_sets]\npackaged = invented_symbols:SYMBOLS\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(symbols, "_loaded", False)
    try:
        assert "sym-package-breaker" in _svg({**DOC, "symbols": "packaged"})
    finally:
        sys.modules.pop("invented_symbols", None)


def _rules(doc, rule):
    return [f for f in check(load(doc)) if f.rule == rule]


def test_registration_refuses_what_is_not_a_function():
    with pytest.raises(TypeError, match="breaker"):
        register_symbol_set("invented", {"breaker": "square"})
    with pytest.raises(TypeError):
        register_symbol_set("invented", [("breaker", square_breaker)])


def _entry(name, load, value="pkg.mod:SET"):
    return SimpleNamespace(name=name, value=value, load=load)


def _missing():
    raise ModuleNotFoundError("No module named 'pkg'")


def test_broken_packages_do_not_stop_the_others(monkeypatch):
    eps = [_entry("missing", _missing), _entry("iec", lambda: {"breaker": square_breaker}),
           _entry("typo", lambda: {"brekaer": square_breaker}), _entry("notfunc", lambda: {"breaker": 3}),
           _entry("good", lambda: {"breaker": square_breaker})]
    monkeypatch.setattr(symbols, "entry_points", lambda group: eps)
    monkeypatch.setattr(symbols, "_loaded", False)
    assert "sym-square-breaker" in _svg({**DOC, "symbols": "good"})
    assert symbol_sets() == ["iec", "good"]
    assert set(symbols.FAILURES) >= {"missing", "iec", "typo", "notfunc"}
    doc = {**DOC, "symbols": "missing"}
    found = _rules(doc, "core.symbol-set-error")
    assert len(found) == 1 and "ModuleNotFoundError" in found[0].message and "pkg.mod:SET" in found[0].message
    assert not _rules(doc, "core.symbol-set-unknown")  # the error says why, once
    assert _svg(doc) == _svg(DOC)


def test_loading_is_finished_before_another_thread_reads_the_sets(monkeypatch):
    def slow():
        time.sleep(0.2)
        return {"breaker": square_breaker}

    monkeypatch.setattr(symbols, "entry_points", lambda group: [_entry("slow", slow)])
    monkeypatch.setattr(symbols, "_loaded", False)
    seen = []
    threads = [threading.Thread(target=lambda: seen.append(symbols.known_set("slow"))) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert seen == ["slow"] * 4


def test_a_failing_symbol_is_drawn_from_iec_with_a_finding():
    def broken(node=None, *args, **kwargs):
        raise ZeroDivisionError("bad symbol")

    register_symbol_set("invented", {"breaker": broken, "socket": lambda node=None, **kw: "not a symbol"})
    doc = {**DOC, "symbols": "invented"}
    assert _svg(doc) == _svg(DOC)
    found = sorted(f.message for f in _rules(doc, "core.symbol-set-error"))
    assert len(found) == 2 and "ZeroDivisionError: bad symbol" in found[0] and "not a Symbol" in found[1]


CONTROLLED = {"sources": [{"type": "grid", "children": [
    {"type": "breaker", "id": f"q{i}", "ref": f"-Q{i}", "in_A": 16, "children": [{"type": "socket"}]} for i in range(4)]}],
    "devices": [{"type": "controller", "id": "c1", "ref": "-K1"}],
    "links": [{"kind": "control", "from": "c1", "to": f"q{i}"} for i in range(4)]}


def test_layout_knows_a_renamed_symbol_by_its_kind():
    def renamed(*args, **kwargs):
        sym = controller(*args, **kwargs)
        sym.name = "my-controller"
        return sym

    register_symbol_set("invented", {"controller": renamed})
    own = _svg({**CONTROLLED, "symbols": "invented"})
    assert "sym-my-controller" in own
    assert own.replace("sym-my-controller", "sym-controller") == _svg(CONTROLLED)  # links spread the same
