"""The compiled search of the grid router (optional package uniwire-native) finds exactly the routes of the pure
Python one: same points, same ends, same cost, hence the same drawings. Skipped when the package is not installed
(the pure Python search is then the one used everywhere). Invented obstacles and documents, and bundled examples."""

import json
import random
import re
from pathlib import Path

import pytest

from uniwire import load
from uniwire.layout import routing
from uniwire.layout.routing import End, Obstacles, route_grid
from uniwire.render import render_views
from uniwire.render.svg import page_to_svg

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_native_search_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("UNIWIRE_NATIVE", "0")
    assert routing._load_native() is None


def test_a_module_that_cannot_be_loaded_falls_back_to_python(monkeypatch):
    """A build that is present but cannot be loaded (another platform, a failed dynamic link in the browser) must
    not break drawing: the pure Python search is used."""
    import builtins
    real = builtins.__import__

    def failing(name, *args, **kwargs):
        if name == "uniwire_native":
            raise OSError("cannot load the compiled module")
        return real(name, *args, **kwargs)

    monkeypatch.delenv("UNIWIRE_NATIVE", raising=False)
    monkeypatch.delitem(__import__("sys").modules, "uniwire_native", raising=False)
    monkeypatch.setattr(builtins, "__import__", failing)
    assert routing._load_native() is None


@pytest.fixture
def native():
    if routing._grid_search is None:
        pytest.skip("uniwire-native not installed (or turned off with UNIWIRE_NATIVE=0)")
    return routing._grid_search


def _both(monkeypatch, native, fn):
    """``fn()`` with the compiled search, then with the pure Python one."""
    with monkeypatch.context() as m:
        m.setattr(routing, "_grid_search", native)
        fast = fn()
    with monkeypatch.context() as m:
        m.setattr(routing, "_grid_search", None)
        slow = fn()
    return fast, slow


def _obstacles(rnd: random.Random) -> Obstacles:
    """Texts and symbols, conductors, busbars, link channels and frames scattered over 120 x 90 mm."""
    obs = Obstacles(near_wire=rnd.choice([0.0, 0.0, 2.5]))
    for _ in range(rnd.randint(4, 14)):
        x, y = rnd.uniform(0, 110), rnd.uniform(0, 80)
        obs.add_box((x, y, x + rnd.uniform(2, 12), y + rnd.uniform(2, 8)))
    for _ in range(rnd.randint(2, 10)):
        x, y = round(rnd.uniform(0, 120), 1), rnd.uniform(0, 60)
        obs.add_vline(x, y, y + rnd.uniform(5, 40))
        obs.conductors.append(("v", x, y, y + 20))
    for _ in range(rnd.randint(1, 6)):
        y, x = round(rnd.uniform(0, 90), 1), rnd.uniform(0, 80)
        obs.add_hline(y, x, x + rnd.uniform(5, 60), bus=rnd.random() < 0.4)
        obs.conductors.append(("h", y, x, x + 30))
    for _ in range(rnd.randint(0, 2)):
        x, y = rnd.uniform(0, 60), rnd.uniform(0, 40)
        obs.add_frame((x, y, x + rnd.uniform(20, 60), y + rnd.uniform(15, 45)))
    return obs


def _end(rnd: random.Random) -> End:
    return End(round(rnd.uniform(5, 115), 2), round(rnd.uniform(5, 85), 2), rnd.choice(["left", "right", "up", "down"]))


def test_same_routes_on_invented_obstacles(monkeypatch, native):
    rnd = random.Random(20261121)
    for case in range(60):
        obs = _obstacles(rnd)
        starts = [_end(rnd) for _ in range(rnd.randint(1, 3))]
        goals = [_end(rnd) for _ in range(rnd.randint(1, 3))]
        wrap = rnd.choice([0.0, 50.0])
        then = [rnd.choice([None, 0, 1, 2, 3]) for _ in goals] if rnd.random() < 0.5 else None
        kw = {"lane": rnd.choice([1.2, 2.0]), "step": rnd.choice([1.0, 2.0]), "bend": rnd.choice([0.0, 4.0, 15.0]),
              "wrap": wrap, "then": then}

        def run(obs=obs, starts=starts, goals=goals, kw=kw):
            cost: list[float] = []
            pts, a, b = route_grid(obs, starts, goals, (0, 0, 120, 90), record=False, cost_out=cost, **kw)
            return pts, a, b, cost

        fast, slow = _both(monkeypatch, native, run)
        assert fast == slow, (case, kw)


def _svgs(doc) -> list[str]:
    return [re.sub(r"_\d{8,}", "_#", page_to_svg(p)) for p in render_views(doc)]  # (ids made per drawing)


INVENTED = {"uniwire": "1.0.0-draft", "meta": {"title": "Interlocks"},
            "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
            "views": [{"kind": "single-line", "paper": "A3"}, {"kind": "multi-line", "paper": "A3"}],
            "sources": [{"type": "grid", "id": "S", "children": [
                {"type": "breaker", "id": "Q0", "ref": "-Q0", "in_A": 63, "poles": "3P", "children": [
                    {"type": "breaker", "id": f"Q{i}", "ref": f"-Q{i}", "in_A": 16, "curve": "C", "poles": "3P",
                     "children": [{"type": "load", "ref": f"-E{i}", "label": f"Zone {i}"}]} for i in range(1, 7)]}]}],
            "devices": [{"type": "contactor", "id": f"K{i}", "ref": f"-K{i}", "label": f"Contactor {i}",
                         "normal_state": "open", "locks": ["LOCK_A"]} for i in (1, 2, 3)],
            "links": [{"kind": "interlock", "from": "K1", "to": "K2", "label": "one at a time"},
                      {"kind": "interlock", "from": "K2", "to": "K3"},
                      {"kind": "control", "from": "K1", "to": "Q4"},
                      {"kind": "control", "from": "K3", "to": "Q2"}]}


@pytest.mark.parametrize("name", ["invented", "23_server_room_ups_2n", "27_standby_generator_ats_load_shedding",
                                  "44_m241_remote_io_480v", "52_dual_source_selectable_feeders"])
def test_same_drawings(monkeypatch, native, name):
    data = INVENTED if name == "invented" else json.loads((EXAMPLES / f"{name}.uniwire.json").read_text("utf-8"))
    fast, slow = _both(monkeypatch, native, lambda: _svgs(load(data)))
    assert fast == slow
