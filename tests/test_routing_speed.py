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


def _place_box_plain(obs, w, h, pref, step=1.25, reach=120.0, pad=1.0, dx_weight=1.0, dy_weight=2.0, within=None):
    """``place_box`` as a plain scan: every position by increasing distance, each tested with ``box_free``."""
    px, py = pref
    cands = []
    n = int(reach / step)
    for i in range(-n, n + 1):
        for j in range(-n // 2, n // 2 + 1):
            dx, dy = i * step, j * step
            cands.append((abs(dx) * dx_weight + abs(dy) * dy_weight, dx, dy))
    cands.sort()
    for _, dx, dy in cands:
        b = (px + dx, py + dy, px + dx + w, py + dy + h)
        if within is not None and not (within[0] <= b[0] and b[2] <= within[2] and within[1] <= b[1] and b[3] <= within[3]):
            continue
        if obs.box_free(b, pad):
            return px + dx, py + dy
    if within is not None:
        return None
    return max([b[2] for b in obs.boxes] + [px]) + 4.0, py


def test_place_box_finds_the_position_of_the_plain_scan():
    for seed in range(4):
        obs, rnd = _obstacles(seed), random.Random(200 + seed)
        for _ in range(60):
            w, h = rnd.uniform(2, 20), rnd.uniform(1, 8)
            pref = (round(rnd.uniform(0, 200), 2), round(rnd.uniform(0, 120), 2))
            step, reach, pad = rnd.choice([0.5, 1.25]), rnd.choice([10.0, 25.0, 41.0]), rnd.choice([0.0, 0.6, 1.0])
            within = None if rnd.random() < 0.5 else (pref[0] - 30, pref[1] - 20, pref[0] + 30, pref[1] + 20)
            args = (obs, w, h, pref, step, reach, pad, 1.0, 2.0, within)
            assert routing.place_box(*args) == _place_box_plain(*args)


def test_label_index_counts_as_the_obstacles():
    for seed in range(4):
        obs, rnd = _obstacles(seed), random.Random(300 + seed)
        obs.add_box((50.0, 50.0, 300.0, 52.0))  # a box over many cells of the index
        obs.boxes.append(obs.boxes[3])  # a box listed twice counts twice
        index = routing._Index(obs)
        for _ in range(3000):
            x, y = rnd.uniform(-10, 210), rnd.uniform(-10, 130)
            b = (x, y, x + rnd.uniform(0.5, 25), y + rnd.uniform(0.5, 4))
            pad, wire_pad = rnd.choice([0.0, 0.3, 1.0]), rnd.choice([0.0, 0.1, 0.5])
            near = index.near(b, pad)
            k, (nv, nh) = index.hits(b, pad, near), index.crossed(b, wire_pad)
            assert obs.box_free(b, pad, wire_pad) == (not k and not nv and not nh)
            assert obs.overlap(b, pad, wire_pad) == 10.0 * k + nv + nh


def test_vertical_legs_cost_as_segments():
    for seed in range(4):
        obs, rnd = _obstacles(seed), random.Random(400 + seed)
        for _ in range(300):
            x, lane = round(rnd.uniform(-5, 205), 1), rnd.choice([1.2, 2.4])
            line = routing._VLine(obs, x, lane)
            for _ in range(20):
                ya, yb = round(rnd.uniform(-5, 125), 1), round(rnd.uniform(-5, 125), 1)
                assert line.cost(ya, yb) == line.leg(ya)(yb) == _seg_cost(obs, (x, ya), (x, yb), lane)

