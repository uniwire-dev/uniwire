"""Collision-aware placement of auxiliary devices, link routes and link labels.

Everything works on axis-aligned boxes ``(x0, y0, x1, y1)`` in drawing coordinates (mm, y down):

* ``Obstacles`` gathers what is already drawn: symbols and annotation texts (``boxes``), vertical
  feeder wires (``vwires``) and horizontal busbars / link channels (``hlines``);
* ``place_box`` finds the free position closest to a preferred one for a device (symbol + text);
* ``route`` chooses an orthogonal path ``start -> vertical -> horizontal channel -> vertical -> end``
  whose channel avoids texts and symbols, then records it so that later links fan out instead of
  sharing the same horizontal;
* ``place_label`` puts a short text along a route where it overlaps nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Optional

Box = tuple[float, float, float, float]
Point = tuple[float, float]

CLEAR = 0.6  # minimum clearance between a route and a text / symbol box
LANE = 1.2  # spacing between parallel link channels


def _hit(a: Box, b: Box, pad: float = 0.0) -> bool:
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


@dataclass
class Obstacles:
    boxes: list[Box] = field(default_factory=list)  # texts and symbols: nothing may cross them
    vwires: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y0, y1) vertical conductors
    hlines: list[tuple[float, float, float]] = field(default_factory=list)  # (y, x0, x1) busbars, link channels

    def add_box(self, b: Optional[Box]) -> None:
        if b is not None:
            self.boxes.append(b)

    def add_vline(self, x: float, y0: float, y1: float) -> None:
        self.vwires.append((x, min(y0, y1), max(y0, y1)))

    def add_hline(self, y: float, x0: float, x1: float) -> None:
        self.hlines.append((y, min(x0, x1), max(x0, x1)))

    def box_free(self, b: Box, pad: float = 0.0, wire_pad: Optional[float] = None) -> bool:
        if any(_hit(b, o, pad) for o in self.boxes):
            return False
        wp = pad if wire_pad is None else wire_pad
        if any(b[0] - wp < x < b[2] + wp and y0 < b[3] and b[1] < y1 for x, y0, y1 in self.vwires):
            return False
        if any(b[1] - wp < y < b[3] + wp and x0 < b[2] and b[0] < x1 for y, x0, x1 in self.hlines):
            return False
        return True

    def overlap(self, b: Box, pad: float = 0.0, wire_pad: float = 0.0) -> float:
        """How badly ``b`` collides: overlapped boxes weigh more than crossed conductors."""
        n = 3.0 * sum(1 for o in self.boxes if _hit(b, o, pad))
        n += sum(1 for x, y0, y1 in self.vwires if b[0] - wire_pad < x < b[2] + wire_pad and y0 < b[3] and b[1] < y1)
        n += sum(1 for y, x0, x1 in self.hlines if b[1] - wire_pad < y < b[3] + wire_pad and x0 < b[2] and b[0] < x1)
        return n

    def window(self, w: Box) -> Obstacles:
        """Subset of the obstacles intersecting the window ``w`` (speeds up the searches)."""
        return Obstacles([b for b in self.boxes if _hit(b, w)],
                         [v for v in self.vwires if w[0] <= v[0] <= w[2] and v[1] < w[3] and w[1] < v[2]],
                         [h for h in self.hlines if w[1] <= h[0] <= w[3] and h[1] < w[2] and w[0] < h[2]])


def place_box(obs: Obstacles, w: float, h: float, pref: Point, step: float = 1.25, reach: float = 120.0,
              pad: float = 1.0, dx_weight: float = 1.0, dy_weight: float = 2.0) -> Point:
    """Top-left corner of the free ``w`` x ``h`` box closest to ``pref``.

    Positions are tried by increasing (weighted) distance; when nothing is free within ``reach``, the box
    goes to the right of every obstacle, at the preferred height.
    """
    px, py = pref
    sub = obs.window((px - reach - w, py - reach / 2 - h, px + reach + w, py + reach / 2 + h))
    cands = []
    n = int(reach / step)
    for i in range(-n, n + 1):
        for j in range(-n // 2, n // 2 + 1):
            dx, dy = i * step, j * step
            cands.append((abs(dx) * dx_weight + abs(dy) * dy_weight, dx, dy))
    cands.sort()
    for _, dx, dy in cands:
        b = (px + dx, py + dy, px + dx + w, py + dy + h)
        if sub.box_free(b, pad):
            return px + dx, py + dy
    right = max([b[2] for b in obs.boxes] + [px])
    return right + 4.0, py


@dataclass
class End:
    """Link end. ``side``: 'left' (stub to the left, then vertical) or 'down' (vertical from the terminal)."""

    x: float
    y: float
    side: str = "left"
    stubs: tuple[float, ...] = (1.5, 2.5, 3.5, 5.0)


def _seg_cost(obs: Obstacles, a: Point, b: Point, lane: float = LANE) -> float:
    (x0, y0), (x1, y1) = a, b
    if abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9:
        return 0.0
    seg = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    cost = sum(100.0 for o in obs.boxes if _hit(seg, o, CLEAR))
    if abs(x0 - x1) < 1e-9:  # vertical: must not run along a conductor
        cost += sum(40.0 for x, v0, v1 in obs.vwires if abs(x - x0) < lane / 2 and v0 < seg[3] and seg[1] < v1)
    else:  # horizontal: must not run along a busbar or another channel
        cost += sum(40.0 for y, h0, h1 in obs.hlines if abs(y - y0) < lane * 0.9 and h0 < seg[2] and seg[0] < h1)
    return cost


def _leg(obs: Obstacles, e: End, y: float, lane: float = LANE) -> tuple[float, list[Point]]:
    """Cheapest way from the end ``e`` to the channel height ``y``: (cost, points from e to the channel)."""
    if e.side == "down":
        if y < e.y + 1.0:
            return 1e9, []
        return _seg_cost(obs, (e.x, e.y), (e.x, y), lane), [(e.x, e.y), (e.x, y)]
    best: tuple[float, list[Point]] = (1e9, [])
    for s in e.stubs:
        xs = e.x - s
        pts = [(e.x, e.y), (xs, e.y), (xs, y)]
        c = _seg_cost(obs, pts[0], pts[1], lane) + _seg_cost(obs, pts[1], pts[2], lane) + 0.15 * s
        if c < best[0]:
            best = (c, pts)
    return best


def route(obs: Obstacles, a: End, b: End, y_min: Optional[float] = None, y_max: Optional[float] = None,
          step: float = 0.5, record: bool = True, lane: float = LANE) -> list[Point]:
    """Orthogonal route from ``a`` to ``b`` through a horizontal channel that avoids texts and symbols.
    ``lane``: minimum spacing from parallel conductors (wider for a link that will carry a device symbol)."""
    lo = min(a.y, b.y) - 30.0 if y_min is None else y_min
    hi = max(a.y, b.y) + 30.0 if y_max is None else y_max
    sub = obs.window((min(a.x, b.x) - 8.0, lo - 2.0, max(a.x, b.x) + 2.0, hi + 2.0))
    best: tuple[float, list[Point]] = (1e18, [])
    n = int((hi - lo) / step)
    for i in range(n + 1):
        y = lo + i * step
        ca, pa = _leg(sub, a, y, lane)
        if ca >= 1e9:
            continue
        cb, pb = _leg(sub, b, y, lane)
        if cb >= 1e9:
            continue
        ch = _seg_cost(sub, pa[-1], pb[-1], lane)
        length = abs(y - a.y) + abs(y - b.y)
        cost = ca + cb + ch + 0.08 * length
        if cost < best[0]:
            best = (cost, pa + pb[::-1])
    pts = _simplify(best[1])
    if record:
        for p, q in zip(pts, pts[1:]):
            if abs(p[1] - q[1]) < 1e-9:
                obs.add_hline(p[1], p[0], q[0])
            elif abs(p[0] - q[0]) < 1e-9:
                obs.add_vline(p[0], p[1], q[1])
    return pts


def _simplify(pts: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-9 and abs(out[-1][1] - p[1]) < 1e-9:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            if (abs(a[0] - b[0]) < 1e-9 and abs(b[0] - p[0]) < 1e-9) or (abs(a[1] - b[1]) < 1e-9 and abs(b[1] - p[1]) < 1e-9):
                out[-1] = p
                continue
        out.append(p)
    return out


def text_box(x: float, y: float, w: float, size: float, anchor: str = "start") -> Box:
    """Box of a single-line text drawn at (x, y) on the alphabetic baseline."""
    x0 = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
    return (x0, y - size * 0.8, x0 + w, y + size * 0.2)


def place_label(obs: Obstacles, pts: list[Point], w: float, size: float, from_end: bool = True,
                record: bool = True) -> tuple[float, float, str]:
    """Free position (x, y, anchor) for a label along the route ``pts``, near its end (or its start)."""
    segs = list(zip(pts, pts[1:]))
    if from_end:
        segs = [(q, p) for p, q in reversed(segs)]
    cands: list[tuple[float, float, str]] = []
    for p, q in segs:
        horizontal = abs(p[1] - q[1]) < 1e-9
        length = abs(q[0] - p[0]) + abs(q[1] - p[1])
        k = max(1, int(length / 2.0))
        for i in range(k + 1):
            t = i / k
            x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
            if horizontal:
                cands += [(x + 0.6, y - 0.6, "start"), (x - 0.6, y - 0.6, "end"),
                          (x + 0.6, y + size + 0.3, "start"), (x - 0.6, y + size + 0.3, "end")]
            else:
                cands += [(x + 0.6, y + size * 0.4, "start"), (x - 0.6, y + size * 0.4, "end")]
    best: tuple[float, int] = (1e18, 0)
    for i, (x, y, anchor) in enumerate(cands):
        b = text_box(x, y, w, size, anchor)
        if obs.box_free(b, 0.3, wire_pad=0.1):
            best = (0.0, i)
            break
        cost = obs.overlap(b, 0.3, 0.1) + i * 1e-3
        if cost < best[0]:
            best = (cost, i)
    x, y, anchor = cands[best[1]] if cands else (pts[-1][0], pts[-1][1], "start")
    if record:
        obs.add_box(text_box(x, y, w, size, anchor))
    return x, y, anchor


def boxes_union(boxes: Iterable[Box]) -> Optional[Box]:
    bs = list(boxes)
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
