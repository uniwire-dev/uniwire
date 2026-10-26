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
BOX_CROSS = 250.0  # a route through a text or a symbol: worse than any detour on the sheet
LANE = 1.2  # spacing between parallel link channels
RUN_ALONG = 150.0  # a route on a conductor or another channel reads as one line: worse than crossing a box
BUS_CLEAR, BUS_RUN = 5.0, 20.0  # minimum spacing between a link channel and a busbar it runs along for long
BUS_PAD = 1.0  # a label keeps this far from a busbar (a thick line)
BUS_CLEAR_THIN = 4.0  # a thin link keeps this far from a busbar it runs along
FRAME_CLEAR, FRAME_RUN = 2.5, 6.0  # a link keeps this far from a dashed frame it runs along for longer
FRAME_ALONG = 60.0  # ... unless the way out runs on another line, which is worse
BUS_CROSS, FRAME_CROSS, WIRE_CROSS = 80.0, 60.0, 5.0  # crossings: a busbar reads like a tap, fewer is clearer
NEAR_RUN = 20.0  # per mm run within ``Obstacles.near_wire`` of a conductor (multi-line)


def _hit(a: Box, b: Box, pad: float = 0.0) -> bool:
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


@dataclass
class Obstacles:
    boxes: list[Box] = field(default_factory=list)  # texts and symbols: nothing may cross them
    vwires: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y0, y1) vertical conductors
    hlines: list[tuple[float, float, float]] = field(default_factory=list)  # (y, x0, x1) busbars, link channels
    buses: list[tuple[float, float, float]] = field(default_factory=list)  # (y, x0, x1) the busbars alone
    frames: list[Box] = field(default_factory=list)  # dashed outlines of boards, enclosures, view frames
    near_wire: float = 0.0  # a route keeps this far from the ``conductors`` it runs along (multi-line bundles)
    conductors: list[tuple[str, float, float, float]] = field(default_factory=list)  # ('v', x, y0, y1) / ('h', y, x0, x1)
    box_cross: float = BOX_CROSS  # cost of a route through a text or a symbol
    frame_clear: float = FRAME_CLEAR  # spacing kept from a dashed frame run along (larger on a reduced sheet)
    frame_along: float = FRAME_ALONG  # cost of running along a frame closer than that
    min_lane: float = 0.0  # spacing of parallel link channels, at least (a reduced sheet needs more)
    label_pad: float = 0.3  # a link label keeps this far from other texts and symbols
    run_along: float = RUN_ALONG  # cost of a route running on another line
    label_channel: bool = False  # link labels on the long horizontal runs rather than near the far end
    grid: bool = False  # links routed by ``route_grid`` (any number of corners)

    def add_box(self, b: Optional[Box]) -> None:
        if b is not None:
            self.boxes.append(b)

    def add_vline(self, x: float, y0: float, y1: float) -> None:
        self.vwires.append((x, min(y0, y1), max(y0, y1)))

    def add_hline(self, y: float, x0: float, x1: float, bus: bool = False) -> None:
        self.hlines.append((y, min(x0, x1), max(x0, x1)))
        if bus:
            self.buses.append((y, min(x0, x1), max(x0, x1)))

    def add_frame(self, b: Box) -> None:
        """A dashed outline: its sides are crossed freely but not run along (a dashed link beside it reads
        as one more frame line)."""
        x0, y0, x1, y1 = b
        self.add_hline(y0, x0, x1)
        self.add_hline(y1, x0, x1)
        self.add_vline(x0, y0, y1)
        self.add_vline(x1, y0, y1)
        self.frames.append(b)

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
        n = 10.0 * sum(1 for o in self.boxes if _hit(b, o, pad))  # a text on a text is the worst
        n += sum(1 for x, y0, y1 in self.vwires if b[0] - wire_pad < x < b[2] + wire_pad and y0 < b[3] and b[1] < y1)
        n += sum(1 for y, x0, x1 in self.hlines if b[1] - wire_pad < y < b[3] + wire_pad and x0 < b[2] and b[0] < x1)
        return n

    def window(self, w: Box) -> Obstacles:
        """Subset of the obstacles intersecting the window ``w`` (speeds up the searches)."""
        return Obstacles([b for b in self.boxes if _hit(b, w)],
                         [v for v in self.vwires if w[0] <= v[0] <= w[2] and v[1] < w[3] and w[1] < v[2]],
                         [h for h in self.hlines if w[1] <= h[0] <= w[3] and h[1] < w[2] and w[0] < h[2]],
                         [h for h in self.buses if w[1] <= h[0] <= w[3] and h[1] < w[2] and w[0] < h[2]],
                         [f for f in self.frames if _hit(f, w, self.frame_clear)], self.near_wire,
                         [c for c in self.conductors if (c[0] == "v" and w[0] <= c[1] <= w[2] and c[2] < w[3] and w[1] < c[3])
                          or (c[0] == "h" and w[1] <= c[1] <= w[3] and c[2] < w[2] and w[0] < c[3])], self.box_cross,
                         self.frame_clear, self.frame_along, self.min_lane, self.label_pad, self.run_along,
                         self.label_channel, self.grid)


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
    """Link end. ``side``: 'left' / 'right' (stub to that side, then vertical) or 'down' (vertical from the
    terminal)."""

    x: float
    y: float
    side: str = "left"
    stubs: tuple[float, ...] = (1.5, 2.5, 3.5, 5.0, 6.5, 8.0, 9.5, 11.0)  # longer: past a frame, a symbol, links


def _along(length: float, weight: float = RUN_ALONG) -> float:
    """Cost of running ``length`` mm on another line: a short common stub at a shared terminal is cheap."""
    return weight * min(1.0, max(length, 0.3) / 3.0)


def _seg_cost(obs: Obstacles, a: Point, b: Point, lane: float = LANE, solid: bool = False) -> float:
    """Cost of a straight route segment; ``solid``: a power link, which along a busbar would read as one."""
    (x0, y0), (x1, y1) = a, b
    if abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9:
        return 0.0
    seg = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    cost = sum(obs.box_cross for o in obs.boxes if _hit(seg, o, CLEAR))
    if abs(x0 - x1) < 1e-9:  # vertical: crosses busbars (reads like a tap) and frames at a price
        cost += sum(BUS_CROSS for y, h0, h1 in obs.buses if seg[1] < y < seg[3] and h0 < x0 < h1)
        cost += sum(FRAME_CROSS for f in obs.frames for y in (f[1], f[3]) if seg[1] < y < seg[3] and f[0] < x0 < f[2])
    else:
        cost += sum(FRAME_CROSS for f in obs.frames for x in (f[0], f[2]) if seg[0] < x < seg[2] and f[1] < y0 < f[3])
        cost += sum(WIRE_CROSS for x, v0, v1 in obs.vwires if seg[0] < x < seg[2] and v0 < y0 < v1)
    if abs(x0 - x1) < 1e-9:  # vertical: must not run along a conductor
        cost += sum(_along(min(v1, seg[3]) - max(v0, seg[1]), obs.run_along) for x, v0, v1 in obs.vwires
                    if abs(x - x0) < lane / 2 and v0 < seg[3] and seg[1] < v1)
        if obs.near_wire:  # beside a conductor: reads as one more conductor of its bundle
            cost += sum(NEAR_RUN * (min(v1, seg[3]) - max(v0, seg[1])) for k, x, v0, v1 in obs.conductors
                        if k == "v" and lane / 2 <= abs(x - x0) < obs.near_wire and v0 < seg[3] and seg[1] < v1)
        cost += sum(obs.frame_along if abs(x - x0) >= lane / 2 else BOX_CROSS for f in obs.frames for x in (f[0], f[2])
                    if abs(x - x0) < obs.frame_clear and min(f[3], seg[3]) - max(f[1], seg[1]) > FRAME_RUN)
    else:  # horizontal: must not run along a busbar or another channel
        cost += sum(_along(min(h1, seg[2]) - max(h0, seg[0]), obs.run_along) for y, h0, h1 in obs.hlines
                    if abs(y - y0) < lane * 0.9 and h0 < seg[2] and seg[0] < h1)
        if obs.near_wire:
            cost += sum(NEAR_RUN * (min(h1, seg[2]) - max(h0, seg[0])) for k, y, h0, h1 in obs.conductors
                        if k == "h" and lane * 0.9 <= abs(y - y0) < obs.near_wire and h0 < seg[2] and seg[0] < h1)
        cost += sum(obs.frame_along if abs(y - y0) >= lane * 0.9 else BOX_CROSS for f in obs.frames for y in (f[1], f[3])
                    if abs(y - y0) < obs.frame_clear and min(f[2], seg[2]) - max(f[0], seg[0]) > FRAME_RUN)
        if solid:  # a long run along a busbar, close enough to read as part of it or as a second busbar
            cost += sum(300.0 for y, h0, h1 in obs.buses
                        if abs(y - y0) < BUS_CLEAR and min(h1, seg[2]) - max(h0, seg[0]) > BUS_RUN)
        else:  # a thin link hugging a busbar (a thick line) is lost in it, and runs over the feeders' texts
            cost += sum(RUN_ALONG for y, h0, h1 in obs.buses
                        if lane * 0.9 <= abs(y - y0) < BUS_CLEAR_THIN and min(h1, seg[2]) - max(h0, seg[0]) > FRAME_RUN)
    return cost


def _leg(obs: Obstacles, e: End, y: float, lane: float = LANE) -> tuple[float, list[Point]]:
    """Cheapest way from the end ``e`` to the channel height ``y``: (cost, points from e to the channel)."""
    if e.side == "down":
        if y < e.y + 1.0:
            return 1e9, []
        return _seg_cost(obs, (e.x, e.y), (e.x, y), lane), [(e.x, e.y), (e.x, y)]
    best: tuple[float, list[Point]] = (1e9, [])
    for s in e.stubs:
        xs = e.x + s if e.side == "right" else e.x - s
        pts = [(e.x, e.y), (xs, e.y), (xs, y)]
        c = _seg_cost(obs, pts[0], pts[1], lane) + _seg_cost(obs, pts[1], pts[2], lane) + 0.15 * s
        if c < best[0]:
            best = (c, pts)
    return best


def route(obs: Obstacles, a: End, b: End, y_min: Optional[float] = None, y_max: Optional[float] = None,
          step: float = 0.5, record: bool = True, lane: float = LANE, solid: bool = False,
          cost_out: Optional[list[float]] = None) -> list[Point]:
    """Orthogonal route from ``a`` to ``b`` through a horizontal channel that avoids texts and symbols.
    ``lane``: minimum spacing from parallel conductors (wider for a link that will carry a device symbol);
    ``solid``: a power link drawn as a plain line, kept off the busbars it would run along;
    ``cost_out``: receives the cost of the route found (to compare the ends a link could use)."""
    lo = min(a.y, b.y) - 30.0 if y_min is None else y_min
    hi = max(a.y, b.y) + 30.0 if y_max is None else y_max
    sub = obs.window((min(a.x, b.x) - 12.0, lo - 2.0, max(a.x, b.x) + 12.0, hi + 2.0))
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
        ch = _seg_cost(sub, pa[-1], pb[-1], lane, solid)
        length = abs(y - a.y) + abs(y - b.y)
        cost = ca + cb + ch + 0.08 * length
        if cost < best[0]:
            best = (cost, pa + pb[::-1])
    pts = _simplify(best[1])
    if cost_out is not None:
        cost_out.append(best[0])
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


SHARE_GAP = 1.2  # multi-line: a label this close to another line than its own is ambiguous


def place_label(obs: Obstacles, pts: list[Point], w: float, size: float, from_end: bool = True,
                record: bool = True, optional: bool = False) -> Optional[tuple[float, float, str]]:
    """Free position (x, y, anchor) for a label along the route ``pts``, near its end (or its start).
    ``optional``: None rather than a position on a text, a symbol or a line."""
    segs = list(zip(pts, pts[1:]))
    if from_end:
        segs = [(q, p) for p, q in reversed(segs)]
    if obs.label_channel:  # on the long horizontal runs first, from their middle: away from the device texts
        segs.sort(key=lambda s: (abs(s[0][1] - s[1][1]) > 1e-9, -abs(s[0][0] - s[1][0])))
        segs = [h for p, q in segs for m in [((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)] for h in ((m, q), (m, p))]
    cands: list[tuple[float, float, str]] = []
    owns: list[tuple[str, float]] = []  # the line each candidate is written along
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
                owns += [("h", y)] * 4
            else:
                cands += [(x + 0.6, y + size * 0.4, "start"), (x - 0.6, y + size * 0.4, "end")]
                owns += [("v", x)] * 2

    def between(b: Box, own: tuple[str, float]) -> bool:
        """Another line runs along the far side of the label: it could belong to either (multi-line)."""
        g = SHARE_GAP
        if own[0] == "h":
            lines = obs.hlines + [(c[1], c[2], c[3]) for c in obs.conductors if c[0] == "h"]
            return any(abs(y - own[1]) > 1e-6 and b[1] - g < y < b[3] + g and x0 < b[2] and b[0] < x1
                       for y, x0, x1 in lines)
        lines = obs.vwires + [(c[1], c[2], c[3]) for c in obs.conductors if c[0] == "v"]
        return any(abs(x - own[1]) > 1e-6 and b[0] - g < x < b[2] + g and y0 < b[3] and b[1] < y1
                   for x, y0, y1 in lines)

    best: tuple[float, int] = (1e18, 0)
    clean = False
    for i, (x, y, anchor) in enumerate(cands):
        b = text_box(x, y, w, size, anchor)
        on_bus = sum(1 for by, x0, x1 in obs.buses if b[1] - BUS_PAD < by < b[3] + BUS_PAD and x0 < b[2] and b[0] < x1)
        shared = obs.label_channel and between(b, owns[i])
        if not on_bus and not shared and obs.box_free(b, obs.label_pad, wire_pad=0.1):
            best = (0.0, i)
            break
        # clear of the texts at the usual distance at least, if not at the wider one asked
        hit = obs.overlap(b, CLEAR / 2, 0.1)
        clean = clean or hit == 0
        cost = hit * 10.0 + obs.overlap(b, obs.label_pad, 0.1) + on_bus + i * 1e-3
        if obs.label_channel:  # multi-line: on a text is worse than beside another line
            cost += 5.0 * (hit > 0) + 0.5 * shared
        if cost < best[0]:
            best = (cost, i)
    if optional and not (best[0] == 0.0 or clean):
        return None
    x, y, anchor = cands[best[1]] if cands else (pts[-1][0], pts[-1][1], "start")
    if record:
        obs.add_box(text_box(x, y, w, size, anchor))
    return x, y, anchor


def boxes_union(boxes: Iterable[Box]) -> Optional[Box]:
    bs = list(boxes)
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


# ------------------------------------------------------------ grid router
BEND = 4.0  # cost of a corner of a grid route
GRID_LENGTH = 0.1  # cost per mm of a grid route
_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))  # +x, -x, +y (down), -y
_LEAVE = {"left": 1, "right": 0, "down": 2, "up": 3}  # first move from an end
_ARRIVE = {"left": 0, "right": 1, "down": 3, "up": 2}  # last move into an end ('up': a terminal on top)
_PROBE: list[list[Point]] = []  # debugging aid, see route_grid


def route_grid(obs: Obstacles, starts: list[End], goals: list[End], window: Box, lane: float = LANE,
               step: float = 1.0, record: bool = True,
               cost_out: Optional[list[float]] = None) -> tuple[list[Point], int, int]:
    """Cheapest orthogonal route, with as many corners as needed, from one of ``starts`` to one of ``goals``
    (the ends a link may use on each device): Dijkstra on a grid of ``step`` mm laid over ``window``, through
    the coordinates of the ends. Same costs as ``route`` (texts and symbols, lines run along or crossed,
    frames), plus a cost per corner. Returns the points and the indexes of the ends used (no route: [])."""
    import heapq
    from bisect import bisect_left, bisect_right

    # a link leaving a terminal downwards (PLC port) goes 3 mm straight down before it may turn
    starts_in = starts
    starts = [End(e.x, e.y + 3.0, e.side) if e.side == "down" else e for e in starts]
    goals_in = goals
    goals = [End(e.x, e.y + 3.0, e.side) if e.side == "down" else e for e in goals]
    wx0, wy0, wx1, wy1 = window
    sub = obs.window((wx0 - 6.0, wy0 - 6.0, wx1 + 6.0, wy1 + 6.0))
    xs = sorted({round(wx0 + k * step, 6) for k in range(int((wx1 - wx0) / step) + 1)} | {e.x for e in starts + goals})
    ys = sorted({round(wy0 + k * step, 6) for k in range(int((wy1 - wy0) / step) + 1)} | {e.y for e in starts + goals})
    nx, ny = len(xs), len(ys)

    def rng(vals: list[float], lo: float, hi: float) -> range:  # indexes of the values strictly inside (lo, hi)
        return range(bisect_right(vals, lo), bisect_left(vals, hi))

    blocked: set[tuple[int, int]] = set()
    for b in sub.boxes:
        for i in rng(xs, b[0] - CLEAR, b[2] + CLEAR):
            for j in rng(ys, b[1] - CLEAR, b[3] + CLEAR):
                blocked.add((i, j))
    for e in starts + goals:  # an end is against its device: the first 1.5 mm out of it are free
        i, j = xs.index(e.x), ys.index(e.y)
        if e.side == "down":
            blocked -= {(i, k) for k in range(j, len(ys)) if ys[k] <= e.y + 1.5}
        elif e.side == "up":
            blocked -= {(i, k) for k in range(len(ys)) if e.y - 1.5 <= ys[k] <= e.y}
        else:
            free = 1.5 + 2 * CLEAR  # an end inside its symbol (an earth terminal) gets out of its clearance
            lo, hi = (e.x - free, e.x) if e.side == "left" else (e.x, e.x + free)
            blocked -= {(k, j) for k in range(len(xs)) if lo <= xs[k] <= hi}
    near = obs.near_wire
    fx = sorted((x, f[1], f[3]) for f in sub.frames for x in (f[0], f[2]))  # vertical frame sides
    fy = sorted((y, f[0], f[2]) for f in sub.frames for y in (f[1], f[3]))
    frame_lines = set(fy) | set(fx)
    buses = sorted(set(sub.buses))
    vw = sorted(v for v in sub.vwires if v not in frame_lines)
    hl = sorted(h for h in sub.hlines if h not in frame_lines and h not in set(buses))
    cond_v = sorted(c[1:] for c in sub.conductors if c[0] == "v")
    cond_h = sorted(c[1:] for c in sub.conductors if c[0] == "h")
    reach = max(near, obs.frame_clear, BUS_CLEAR_THIN, lane) + 0.01

    def around(lines: list, pos: float, r: float) -> list:  # lines whose coordinate is within r of pos
        return lines[bisect_left(lines, (pos - r,)):bisect_right(lines, (pos + r, 1e18, 1e18))]

    def between(lines: list, lo: float, hi: float) -> list:  # lines whose coordinate is in (lo, hi]
        return lines[bisect_right(lines, (lo, 1e18, 1e18)):bisect_right(lines, (hi, 1e18, 1e18))]

    col: dict[int, tuple] = {}
    row: dict[int, tuple] = {}

    def lines_at(i: int, vertical: bool) -> tuple:
        memo, pos = (col, xs[i]) if vertical else (row, ys[i])
        if i not in memo:
            if vertical:
                memo[i] = (around(vw, pos, reach), around(cond_v, pos, reach), around(fx, pos, reach), [])
            else:
                memo[i] = (around(hl, pos, reach) + around(buses, pos, reach), around(cond_h, pos, reach),
                           around(fy, pos, reach), around(buses, pos, reach))
        return memo[i]

    def run_cost(pos: float, a: float, b: float, along: list, near_l: list, frames: list, bus: list) -> float:
        """Running from a to b at ``pos`` (x of a vertical, y of a horizontal move)."""
        c = 0.0
        for p, v0, v1 in along:
            ov = min(v1, b) - max(v0, a)
            if ov > 0 and abs(p - pos) < lane / 2:
                c += obs.run_along * ov / 3.0
        if near:
            for p, v0, v1 in near_l:
                ov = min(v1, b) - max(v0, a)
                if ov > 0 and lane / 2 <= abs(p - pos) < near:
                    c += NEAR_RUN * ov
        for p, v0, v1 in frames:  # the closer to a frame side run along, the worse
            ov = min(v1, b) - max(v0, a)
            if ov > 0 and abs(p - pos) < obs.frame_clear:
                k = obs.frame_along * (1.0 - abs(p - pos) / obs.frame_clear) if abs(p - pos) >= lane / 2 else obs.box_cross
                c += k * ov / FRAME_RUN
        for p, v0, v1 in bus:
            ov = min(v1, b) - max(v0, a)
            if ov > 0 and lane * 0.9 <= abs(p - pos) < BUS_CLEAR_THIN:
                c += RUN_ALONG * ov / FRAME_RUN
        return c

    cache: dict[tuple[int, int, int], float] = {}

    def edge(i: int, j: int, d: int) -> float:
        key = (min(i, i + _DIRS[d][0]), min(j, j + _DIRS[d][1]), d >> 1)  # same cost both ways
        if key in cache:
            return cache[key]
        di, dj = _DIRS[d]
        i2, j2 = i + di, j + dj
        c = sub.box_cross if (i, j) in blocked or (i2, j2) in blocked else 0.0
        if dj == 0:  # horizontal, at y = ys[j]
            y, a, b = ys[j], min(xs[i], xs[i2]), max(xs[i], xs[i2])
            c += GRID_LENGTH * (b - a) + run_cost(y, a, b, *lines_at(j, False))
            c += sum(WIRE_CROSS for x, v0, v1 in between(vw, a, b) if v0 < y < v1)
            c += sum(FRAME_CROSS for x, v0, v1 in between(fx, a, b) if v0 < y < v1)
        else:  # vertical, at x = xs[i]
            x, a, b = xs[i], min(ys[j], ys[j2]), max(ys[j], ys[j2])
            c += GRID_LENGTH * (b - a) + run_cost(x, a, b, *lines_at(i, True))
            c += sum(BUS_CROSS for y, h0, h1 in between(buses, a, b) if h0 < x < h1)
            c += sum(FRAME_CROSS for y, h0, h1 in between(fy, a, b) if h0 < x < h1)
            c += sum(WIRE_CROSS for y, h0, h1 in between(hl, a, b) if h0 < x < h1)
        cache[key] = c
        return c

    if _PROBE:  # debugging: cost of each step of a given path (grid points)
        pts = _PROBE.pop()
        idx = [(min(range(nx), key=lambda k: abs(xs[k] - x)), min(range(ny), key=lambda k: abs(ys[k] - y))) for x, y in pts]
        for (i, j), (i2, j2) in zip(idx, idx[1:]):
            while (i, j) != (i2, j2):
                d = 0 if i2 > i else 1 if i2 < i else 2 if j2 > j else 3
                c = edge(i, j, d)
                if c > 1:
                    print("  step", round(xs[i], 1), round(ys[j], 1), "dir", d, "cost", round(c, 1))
                i, j = i + _DIRS[d][0], j + _DIRS[d][1]
    goal_at = {(xs.index(e.x), ys.index(e.y), _ARRIVE[e.side]): k for k, e in enumerate(goals)}
    heap: list[tuple[float, int, int, int, int]] = []
    origin: dict[tuple[int, int, int], int] = {}
    prev: dict[tuple[int, int, int], Optional[tuple[int, int, int]]] = {}
    dist: dict[tuple[int, int, int], float] = {}
    for k, e in enumerate(starts):
        st = (xs.index(e.x), ys.index(e.y), _LEAVE[e.side])
        dist[st], prev[st], origin[st] = 0.0, None, k
        heapq.heappush(heap, (0.0, *st, 1))
    found = None
    while heap:
        cost, i, j, d, fresh = heapq.heappop(heap)
        st = (i, j, d)
        if cost > dist.get(st, 1e18):
            continue
        if not fresh and st in goal_at:
            found = st
            break
        for d2 in ((d,) if fresh else range(4)):
            if not fresh and d2 == (d ^ 1):  # no turning back
                continue
            di, dj = _DIRS[d2]
            i2, j2 = i + di, j + dj
            if not (0 <= i2 < nx and 0 <= j2 < ny):
                continue
            c = cost + edge(i, j, d2) + (BEND if d2 != d else 0.0)
            s2 = (i2, j2, d2)
            if c < dist.get(s2, 1e18):
                dist[s2], prev[s2], origin[s2] = c, st, origin[st]
                heapq.heappush(heap, (c, i2, j2, d2, 0))
    if found is None:
        return [], 0, 0
    if cost_out is not None:
        cost_out.append(dist[found])
    path = []
    s: Optional[tuple[int, int, int]] = found
    while s is not None:
        path.append((xs[s[0]], ys[s[1]]))
        if prev[s] is None:
            first = s
        s = prev[s]
    path.reverse()
    a, b = starts_in[origin[first]], goals_in[goal_at[found]]
    pts = _simplify(([(a.x, a.y)] if a.side == "down" else []) + path + ([(b.x, b.y)] if b.side == "down" else []))
    if record:
        for p, q in zip(pts, pts[1:]):
            if abs(p[1] - q[1]) < 1e-9:
                obs.add_hline(p[1], p[0], q[0])
            elif abs(p[0] - q[0]) < 1e-9:
                obs.add_vline(p[0], p[1], q[1])
    return pts, origin[found], goal_at[found]
