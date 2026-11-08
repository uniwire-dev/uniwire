"""Symbol sets: a set registered from outside the library changes the drawing; an unknown one falls back to IEC."""

import sys

import pytest

import uniwire.symbols as symbols
from uniwire import check, load
from uniwire.render import _PAGES, render_views
from uniwire.render.scene import THIN, Line, Rect, Style
from uniwire.render.svg import page_to_svg
from uniwire.symbols import Symbol, register_symbol_set, symbol_sets
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
    yield
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
