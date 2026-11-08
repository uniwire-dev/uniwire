"""The router's shortcuts give the same costs, hence the same routes, as the plain computation."""

import random

from uniwire.layout import routing
from uniwire.layout.routing import End, Obstacles, _Costs, _narrow, _seg_cost, route, route_grid


def _obstacles(seed: int) -> Obstacles:
    rnd = random.Random(seed)
    obs = Obstacles(near_wire=rnd.choice([0.0, 2.5]))
    for _ in range(60):
        x, y = rnd.uniform(0, 200), rnd.uniform(0, 120)
        obs.add_box((x, y, x + rnd.uniform(1, 12), y + rnd.uniform(1, 5)))
    for _ in range(30):
        x, y = round(rnd.uniform(0, 200), 1), rnd.uniform(0, 120)
        obs.add_vline(x, y, y + rnd.uniform(2, 60))
        obs.conductors.append(("v", x, y, y + 30))
    for _ in range(20):
        x, y = rnd.uniform(0, 200), round(rnd.uniform(0, 120), 1)
        obs.add_hline(y, x, x + rnd.uniform(5, 80), bus=rnd.random() < 0.3)
        obs.conductors.append(("h", y, x, x + 40))
    for _ in range(4):
        x, y = rnd.uniform(0, 150), rnd.uniform(0, 80)
        obs.add_frame((x, y, x + rnd.uniform(20, 60), y + rnd.uniform(15, 40)))
    return obs


def test_narrowed_obstacles_give_the_same_segment_costs():
    for seed in range(5):
        obs, rnd = _obstacles(seed), random.Random(100 + seed)
        for _ in range(2000):
            a = (round(rnd.uniform(-5, 205), 1), round(rnd.uniform(-5, 125), 1))
            b = (a[0], round(rnd.uniform(-5, 125), 1)) if rnd.random() < 0.5 else (round(rnd.uniform(-5, 205), 1), a[1])
            lane, solid = rnd.choice([1.2, 2.4]), rnd.random() < 0.3
            near = _narrow(obs, min(a[0], b[0]), max(a[0], b[0]), lane)
            assert _seg_cost(near, a, b, lane, solid) == _seg_cost(obs, a, b, lane, solid)
            assert _Costs(obs, lane)(a, b, solid) == _seg_cost(obs, a, b, lane, solid)


def test_route_costs_each_segment_once_on_the_obstacles_near_it(monkeypatch):
    obs = _obstacles(1)
    calls: list[int] = []
    plain = routing._seg_cost
    monkeypatch.setattr(routing, "_seg_cost", lambda o, *a, **k: calls.append(len(o.boxes)) or plain(o, *a, **k))
    pts = route(obs, End(20.0, 40.0, "right"), End(180.0, 90.0, "left"), record=False)
    assert pts
    # a stub is costed once, not once per channel height tried, and against the boxes near it only
    assert len(calls) < 6000 and sum(calls) < 0.25 * len(calls) * len(obs.boxes)


def test_grid_route_is_found_and_stable():
    obs = _obstacles(2)
    a, b = [End(10.0, 10.0, "right")], [End(190.0, 110.0, "left")]
    first = route_grid(obs, a, b, (0.0, 0.0, 200.0, 120.0), record=False)
    assert first[0] and route_grid(obs, a, b, (0.0, 0.0, 200.0, 120.0), record=False) == first
