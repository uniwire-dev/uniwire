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

import os
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from math import floor
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
# a dashed link across a busbar: drawn with a gap there, a crossing like that of a few feeders (not the price of a
# tap: a dashed link kept off a board's busbars runs across every feeder below them instead)
DASHED_BUS_CROSS = 4 * WIRE_CROSS
NEAR_RUN = 20.0  # per mm run within ``Obstacles.near_wire`` of a conductor (multi-line)
SOLID_CROSS = 30.0  # a solid power link across a conductor: reads as a connection there (a dashed link does not)
WRAP = 50.0  # a turn taking a route round what it passes on three sides (with its ends, it reads as a frame)


def bus_cross(solid: bool) -> float:
    """Cost of a link crossing a busbar: a solid line there reads like a tap, a dashed one is drawn with a gap."""
    return BUS_CROSS if solid else DASHED_BUS_CROSS


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
        x0, y0, x1, y1 = b
        if any(x0 < o[2] + pad and o[0] < x1 + pad and y0 < o[3] + pad and o[1] < y1 + pad for o in self.boxes):
            return False  # (_hit written out: the hottest test of the layout)
        wp = pad if wire_pad is None else wire_pad
        if any(b[0] - wp < x < b[2] + wp and y0 < b[3] and b[1] < y1 for x, y0, y1 in self.vwires):
            return False
        if any(b[1] - wp < y < b[3] + wp and x0 < b[2] and b[0] < x1 for y, x0, x1 in self.hlines):
            return False
        return True

    def overlap(self, b: Box, pad: float = 0.0, wire_pad: float = 0.0) -> float:
        """How badly ``b`` collides: overlapped boxes weigh more than crossed conductors."""
        x0, y0, x1, y1 = b
        n = 10.0 * sum(1 for o in self.boxes  # a text on a text is the worst
                       if x0 < o[2] + pad and o[0] < x1 + pad and y0 < o[3] + pad and o[1] < y1 + pad)
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


class _Lines:
    """Lines (position, start, end) sorted by their position: the ones strictly between two positions in one slice."""

    def __init__(self, lines: Iterable[tuple[float, float, float]]):
        self.lines = sorted(lines)
        self.keys = [ln[0] for ln in self.lines]

    def inside(self, lo: float, hi: float) -> list[tuple[float, float, float]]:
        """The lines whose position p is such that lo < p < hi (the same test, the same floats)."""
        return self.lines[bisect_right(self.keys, lo):bisect_left(self.keys, hi)]


class _Index:
    """The obstacles of a window that does not change while ``place_label`` searches it, indexed for the box tests:
    texts and symbols in the cells of a uniform grid, lines sorted by their position. The counts of
    ``Obstacles.box_free`` / ``overlap`` (a yes / no, or a count: the order the obstacles are met in does not change
    them), testing only the obstacles near the box rather than all of them."""

    CELL = 10.0  # mm
    BIG = 64  # a box over more cells than this is tested for every box
    EPS = 1e-3  # the cells looked at reach this much further: whatever the rounding of the tests

    def __init__(self, obs: Obstacles):
        c = self.CELL
        self.boxes = obs.boxes
        cells: dict[int, list[int]] = {}
        self.big: list[int] = []
        for k, o in enumerate(obs.boxes):
            i0, i1, j0, j1 = floor(o[0] / c), floor(o[2] / c), floor(o[1] / c), floor(o[3] / c)
            if (i1 - i0 + 1) * (j1 - j0 + 1) > self.BIG:
                self.big.append(k)
                continue
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    cells.setdefault(i * 65536 + j, []).append(k)
        self.cells = cells
        self.seen: dict[tuple[int, int, int, int], list[Box]] = {}
        self.vwires, self.hlines = _Lines(obs.vwires), _Lines(obs.hlines)

    def near(self, b: Box, pad: float) -> list[Box]:
        """The boxes that may come within ``pad`` of ``b``: every one that does, as many times as it is in the
        obstacles."""
        c, e = self.CELL, self.EPS
        key = (floor((b[0] - pad - e) / c), floor((b[2] + pad + e) / c), floor((b[1] - pad - e) / c),
               floor((b[3] + pad + e) / c))
        got = self.seen.get(key)  # (the boxes searched one after the other are often in the same cells)
        if got is None:
            got = self.seen[key] = self._near(*key)
        return got

    def _near(self, i0: int, i1: int, j0: int, j1: int) -> list[Box]:
        """The boxes in the cells i0..i1 x j0..j1, each as many times as it is in the obstacles."""
        boxes, cells = self.boxes, self.cells
        if i0 == i1 and j0 == j1 and not self.big:  # in one cell: each box once
            return [boxes[k] for k in cells.get(i0 * 65536 + j0, ())]
        ks: set[int] = set(self.big)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                got = cells.get(i * 65536 + j)
                if got:
                    ks.update(got)
        return [boxes[k] for k in ks]

    def hits(self, b: Box, pad: float, near: list[Box]) -> int:
        """How many boxes come within ``pad`` of ``b``; ``near``: ``self.near(b, p)`` with p >= ``pad``."""
        x0, y0, x1, y1 = b
        return sum(1 for o in near if x0 < o[2] + pad and o[0] < x1 + pad and y0 < o[3] + pad and o[1] < y1 + pad)

    def crossed(self, b: Box, wire_pad: float) -> tuple[int, int]:
        """How many vertical, and horizontal, lines cross ``b`` grown by ``wire_pad`` (as ``Obstacles.overlap``)."""
        nv = sum(1 for x, y0, y1 in self.vwires.inside(b[0] - wire_pad, b[2] + wire_pad) if y0 < b[3] and b[1] < y1)
        nh = sum(1 for y, x0, x1 in self.hlines.inside(b[1] - wire_pad, b[3] + wire_pad) if x0 < b[2] and b[0] < x1)
        return nv, nh


@lru_cache(maxsize=32, typed=True)
def _offsets(step: float, reach: float, dx_weight: float, dy_weight: float) -> tuple[tuple[float, float, int], ...]:
    """The moves ``place_box`` tries, by increasing (weighted) distance: (dx, dy, number of the lattice point, row
    by row)."""
    cands = []
    n = int(reach / step)
    for i in range(-n, n + 1):
        for j in range(-n // 2, n // 2 + 1):
            dx, dy = i * step, j * step
            cands.append((abs(dx) * dx_weight + abs(dy) * dy_weight, dx, dy, (j - (-n // 2)) * (2 * n + 1) + i + n))
    cands.sort()
    return tuple((dx, dy, k) for _, dx, dy, k in cands)


def _edge(cond: Callable[[int], bool], lo: int, hi: int, guess: float, rising: bool) -> int:
    """For ``cond`` false then true over lo..hi (``rising``): its first true (hi + 1: none); otherwise, true then false:
    its last true (lo - 1: none). Looked for from ``guess``, a near estimate."""
    g = lo if guess != guess else min(max(floor(max(lo - 1.0, min(hi + 1.0, guess))), lo), hi)
    if cond(g):
        if rising:
            while g > lo and cond(g - 1):
                g -= 1
        else:
            while g < hi and cond(g + 1):
                g += 1
        return g
    if rising:
        while g < hi:
            g += 1
            if cond(g):
                return g
        return hi + 1
    while g > lo:
        g -= 1
        if cond(g):
            return g
    return lo - 1


def _blocked(obs: Obstacles, w: float, h: float, px: float, py: float, step: float, n: int, pad: float) -> bytearray:
    """The lattice of ``place_box``: for each of its points (dx, dy) = (i * step, j * step), i in -n..n, j in
    -n // 2..n // 2, row by row, whether the box there is not ``obs.box_free(b, pad)``. Each test of ``box_free`` is
    monotonic along a row or a column (a box further right is further right, after rounding too), so each obstacle
    blocks a rectangle of points, found by testing its edges with the same floating-point operations."""
    i0, i1, j0, j1 = -n, n, -n // 2, n // 2
    width = i1 - i0 + 1
    grid = bytearray(width * (j1 - j0 + 1))
    ones = b"\x01" * width

    def mark(ia: int, ib: int, ja: int, jb: int) -> None:
        if ia <= ib:
            for j in range(ja, jb + 1):
                r = (j - j0) * width - i0
                grid[r + ia:r + ib + 1] = ones[:ib - ia + 1]

    def cols(lo_ok: Callable[[int], bool], lo_at: float, hi_ok: Callable[[int], bool], hi_at: float) -> tuple[int, int]:
        """The i (columns) where both ``lo_ok`` (false, then true) and ``hi_ok`` (true, then false) hold."""
        return _edge(lo_ok, i0, i1, lo_at, True), _edge(hi_ok, i0, i1, hi_at, False)

    def rows(lo_ok: Callable[[int], bool], lo_at: float, hi_ok: Callable[[int], bool], hi_at: float) -> tuple[int, int]:
        return _edge(lo_ok, j0, j1, lo_at, True), _edge(hi_ok, j0, j1, hi_at, False)

    for o in obs.boxes:  # x0 < o[2] + pad and o[0] < x1 + pad and y0 < o[3] + pad and o[1] < y1 + pad
        ox0, oy0, ox1, oy1 = o
        ia, ib = cols(lambda i, a=ox0: a < px + i * step + w + pad, (ox0 - pad - w - px) / step,
                      lambda i, a=ox1: px + i * step < a + pad, (ox1 + pad - px) / step)
        if ia <= ib:
            mark(ia, ib, *rows(lambda j, a=oy0: a < py + j * step + h + pad, (oy0 - pad - h - py) / step,
                               lambda j, a=oy1: py + j * step < a + pad, (oy1 + pad - py) / step))
    for x, y0, y1 in obs.vwires:  # b[0] - pad < x < b[2] + pad and y0 < b[3] and b[1] < y1
        ia, ib = cols(lambda i, a=x: a < px + i * step + w + pad, (x - pad - w - px) / step,
                      lambda i, a=x: px + i * step - pad < a, (x + pad - px) / step)
        if ia <= ib:
            mark(ia, ib, *rows(lambda j, a=y0: a < py + j * step + h, (y0 - h - py) / step,
                               lambda j, a=y1: py + j * step < a, (y1 - py) / step))
    for y, x0, x1 in obs.hlines:  # b[1] - pad < y < b[3] + pad and x0 < b[2] and b[0] < x1
        ja, jb = rows(lambda j, a=y: a < py + j * step + h + pad, (y - pad - h - py) / step,
                      lambda j, a=y: py + j * step - pad < a, (y + pad - py) / step)
        if ja <= jb:
            mark(*cols(lambda i, a=x0: a < px + i * step + w, (x0 - w - px) / step,
                       lambda i, a=x1: px + i * step < a, (x1 - px) / step), ja, jb)
    return grid


def place_box(obs: Obstacles, w: float, h: float, pref: Point, step: float = 1.25, reach: float = 120.0,
              pad: float = 1.0, dx_weight: float = 1.0, dy_weight: float = 2.0,
              within: Optional[Box] = None) -> Optional[Point]:
    """Top-left corner of the free ``w`` x ``h`` box closest to ``pref``.

    Positions are tried by increasing (weighted) distance; when nothing is free within ``reach``, the box
    goes to the right of every obstacle, at the preferred height. ``within``: only inside that box, None when no
    place there is free.
    """
    px, py = pref
    sub = obs.window((px - reach - w, py - reach / 2 - h, px + reach + w, py + reach / 2 + h))
    blocked = _blocked(sub, w, h, px, py, step, int(reach / step), pad)  # (``sub.box_free``, at every point at once)
    for dx, dy, k in _offsets(step, reach, dx_weight, dy_weight):
        if blocked[k]:
            continue
        b = (px + dx, py + dy, px + dx + w, py + dy + h)
        if within is not None and not (within[0] <= b[0] and b[2] <= within[2] and within[1] <= b[1] and b[3] <= within[3]):
            continue
        return px + dx, py + dy
    if within is not None:
        return None
    right = max([b[2] for b in obs.boxes] + [px])
    return right + 4.0, py


@dataclass
class End:
    """Link end. ``side``: 'left' / 'right' (stub to that side, then vertical), 'down' (vertical from the
    terminal) or 'up' (vertical from above: a tap on top of a busbar)."""

    x: float
    y: float
    side: str = "left"
    stubs: tuple[float, ...] = (1.5, 2.5, 3.5, 5.0, 6.5, 8.0, 9.5, 11.0)  # longer: past a frame, a symbol, links


def _along(length: float, weight: float = RUN_ALONG) -> float:
    """Cost of running ``length`` mm on another line: a short common stub at a shared terminal is cheap."""
    return weight * min(1.0, max(length, 0.3) / 3.0)


def _seg_cost(obs: Obstacles, a: Point, b: Point, lane: float = LANE, solid: bool = False) -> float:
    """Cost of a straight route segment; ``solid``: a power link, which along a busbar would read as one."""
    # (each term summed by ``sum`` over the same obstacles in the same order as ever, list comprehensions rather than
    # generators, an empty kind of obstacle skipped: the hottest function of the channel router)
    (x0, y0), (x1, y1) = a, b
    if abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9:
        return 0.0
    seg = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    sx0, sy0, sx1, sy1 = seg
    boxes, frames, vwires = obs.boxes, obs.frames, obs.vwires
    cost = sum([obs.box_cross for o in boxes  # _hit(seg, o, CLEAR), written out
                if sx0 < o[2] + CLEAR and o[0] < sx1 + CLEAR and sy0 < o[3] + CLEAR and o[1] < sy1 + CLEAR]) if boxes else 0
    if abs(x0 - x1) < 1e-9:  # vertical: crosses busbars (reads like a tap) and frames at a price
        if obs.buses:
            bus = bus_cross(solid)
            cost += sum([bus for y, h0, h1 in obs.buses if sy0 < y < sy1 and h0 < x0 < h1])
        if frames:
            cost += sum([FRAME_CROSS for f in frames for y in (f[1], f[3]) if sy0 < y < sy1 and f[0] < x0 < f[2]])
    else:
        if frames:
            cost += sum([FRAME_CROSS for f in frames for x in (f[0], f[2]) if sx0 < x < sx1 and f[1] < y0 < f[3]])
        if vwires:
            cost += sum([SOLID_CROSS if solid else WIRE_CROSS for x, v0, v1 in vwires if sx0 < x < sx1 and v0 < y0 < v1])
    if abs(x0 - x1) < 1e-9:  # vertical: must not run along a conductor
        if vwires:
            half = lane / 2
            cost += sum([_along(min(v1, sy1) - max(v0, sy0), obs.run_along) for x, v0, v1 in vwires
                         if abs(x - x0) < half and v0 < sy1 and sy0 < v1])
        if obs.near_wire and obs.conductors:  # beside a conductor: reads as one more conductor of its bundle
            cost += sum([NEAR_RUN * (min(v1, sy1) - max(v0, sy0)) for k, x, v0, v1 in obs.conductors
                         if k == "v" and lane / 2 <= abs(x - x0) < obs.near_wire and v0 < sy1 and sy0 < v1])
        if frames:
            cost += sum([obs.frame_along if abs(x - x0) >= lane / 2 else BOX_CROSS for f in frames for x in (f[0], f[2])
                         if abs(x - x0) < obs.frame_clear and min(f[3], sy1) - max(f[1], sy0) > FRAME_RUN])
    else:  # horizontal: must not run along a busbar or another channel
        if obs.hlines:
            cost += sum([_along(min(h1, sx1) - max(h0, sx0), obs.run_along) for y, h0, h1 in obs.hlines
                         if abs(y - y0) < lane * 0.9 and h0 < sx1 and sx0 < h1])
        if obs.near_wire and obs.conductors:
            cost += sum([NEAR_RUN * (min(h1, sx1) - max(h0, sx0)) for k, y, h0, h1 in obs.conductors
                         if k == "h" and lane * 0.9 <= abs(y - y0) < obs.near_wire and h0 < sx1 and sx0 < h1])
        if frames:
            cost += sum([obs.frame_along if abs(y - y0) >= lane * 0.9 else BOX_CROSS for f in frames for y in (f[1], f[3])
                         if abs(y - y0) < obs.frame_clear and min(f[2], sx1) - max(f[0], sx0) > FRAME_RUN])
        if obs.buses:
            if solid:  # a long run along a busbar, close enough to read as part of it or as a second busbar
                cost += sum([300.0 for y, h0, h1 in obs.buses
                             if abs(y - y0) < BUS_CLEAR and min(h1, sx1) - max(h0, sx0) > BUS_RUN])
            else:  # a thin link on or hugging a busbar (a thick line) is lost in it, and runs over the feeders' texts
                cost += sum([RUN_ALONG for y, h0, h1 in obs.buses
                             if abs(y - y0) < BUS_CLEAR_THIN and min(h1, sx1) - max(h0, sx0) > FRAME_RUN])
    return cost


def _narrow(obs: Obstacles, x0: float, x1: float, lane: float) -> Obstacles:
    """The obstacles that can count in ``_seg_cost`` for a segment between x0 and x1 (a superset, in the same
    order: the sums, hence the costs, are exactly the same, over far fewer obstacles)."""
    m = max(CLEAR, lane, obs.near_wire, obs.frame_clear) + 0.01
    lo, hi = x0 - m, x1 + m
    return Obstacles([b for b in obs.boxes if b[0] < hi and lo < b[2]],
                     [v for v in obs.vwires if lo < v[0] < hi],
                     [h for h in obs.hlines if h[1] < hi and lo < h[2]],
                     [h for h in obs.buses if h[1] < hi and lo < h[2]],
                     obs.frames, obs.near_wire,
                     [c for c in obs.conductors if (c[0] == "v" and lo < c[1] < hi) or (c[0] == "h" and c[2] < hi and lo < c[3])],
                     obs.box_cross, obs.frame_clear, obs.frame_along, obs.min_lane, obs.label_pad, obs.run_along,
                     obs.label_channel, obs.grid)


def _narrow_line(obs: Obstacles, vertical: bool, pos: float, lane: float) -> Obstacles:
    """The obstacles that can count in ``_seg_cost`` for a vertical segment at x = ``pos`` or a horizontal one at
    y = ``pos``, whatever its length (a superset, in the same order: the sums, hence the costs, are exactly the same)."""
    e = 0.01  # a little more than each test: a segment "vertical" within 1e-9 may not be exactly at pos
    lo, hi = pos - e, pos + e
    fc = obs.frame_clear + e
    if vertical:  # its boxes, the busbars and frames it crosses, the conductors and frame sides it runs along
        return Obstacles([b for b in obs.boxes if b[0] < hi + CLEAR and lo - CLEAR < b[2]],
                         [v for v in obs.vwires if abs(v[0] - pos) < lane / 2 + e], [],
                         [h for h in obs.buses if h[1] < hi and lo < h[2]],
                         [f for f in obs.frames if (f[0] < hi and lo < f[2]) or abs(f[0] - pos) < fc or abs(f[2] - pos) < fc],
                         obs.near_wire,
                         [c for c in obs.conductors if c[0] == "v" and abs(c[1] - pos) < max(obs.near_wire, lane) + e],
                         obs.box_cross, obs.frame_clear, obs.frame_along, obs.min_lane, obs.label_pad, obs.run_along,
                         obs.label_channel, obs.grid)
    return Obstacles([b for b in obs.boxes if b[1] < hi + CLEAR and lo - CLEAR < b[3]],
                     [v for v in obs.vwires if v[1] < hi and lo < v[2]],
                     [h for h in obs.hlines if abs(h[0] - pos) < lane * 0.9 + e],
                     [h for h in obs.buses if abs(h[0] - pos) < max(BUS_CLEAR, BUS_CLEAR_THIN) + e],
                     [f for f in obs.frames if (f[1] < hi and lo < f[3]) or abs(f[1] - pos) < fc or abs(f[3] - pos) < fc],
                     obs.near_wire,
                     [c for c in obs.conductors if c[0] == "h" and abs(c[1] - pos) < max(obs.near_wire, lane) + e],
                     obs.box_cross, obs.frame_clear, obs.frame_along, obs.min_lane, obs.label_pad, obs.run_along,
                     obs.label_channel, obs.grid)


class _Costs:
    """``_seg_cost`` over one set of obstacles that does not change, for the many segments ``route`` tries: each
    segment on the obstacles near its line (``_narrow_line``), and a segment met again (a stub, a leg) costed once."""

    def __init__(self, obs: Obstacles, lane: float):
        self.obs, self.lane = obs, lane
        self.near: dict[tuple, Obstacles] = {}
        self.done: dict[tuple, float] = {}

    def __call__(self, a: Point, b: Point, solid: bool = False) -> float:
        key = (a, b, solid)
        if key not in self.done:
            if abs(a[0] - b[0]) < 1e-9:
                line: tuple = ("v", a[0])
            elif abs(a[1] - b[1]) < 1e-9:
                line = ("h", a[1])
            else:  # oblique (not drawn by the routers): on the obstacles of its x span
                line = ("s", min(a[0], b[0]), max(a[0], b[0]))
            near = self.near.get(line)
            if near is None:
                near = self.near[line] = (_narrow(self.obs, line[1], line[2], self.lane) if line[0] == "s"
                                          else _narrow_line(self.obs, line[0] == "v", line[1], self.lane))
            self.done[key] = _seg_cost(near, a, b, self.lane, solid)
        return self.done[key]


def _leg(obs: Obstacles, e: End, y: float, lane: float = LANE,
         seg: Optional[_Costs] = None) -> tuple[float, list[Point]]:
    """Cheapest way from the end ``e`` to the channel height ``y``: (cost, points from e to the channel)."""
    cost = seg or (lambda a, b: _seg_cost(obs, a, b, lane))
    if e.side == "down":
        if y < e.y + 1.0:
            return 1e9, []
        return cost((e.x, e.y), (e.x, y)), [(e.x, e.y), (e.x, y)]
    if e.side == "up":  # high enough above the busbar not to read as its extension
        if y > e.y - 4.0:
            return 1e9, []
        return cost((e.x, y), (e.x, e.y)), [(e.x, e.y), (e.x, y)]
    best: tuple[float, list[Point]] = (1e9, [])
    for s in e.stubs:
        xs = e.x + s if e.side == "right" else e.x - s
        pts = [(e.x, e.y), (xs, e.y), (xs, y)]
        c = cost(pts[0], pts[1]) + cost(pts[1], pts[2]) + 0.15 * s
        if c < best[0]:
            best = (c, pts)
    return best


class _VLine:
    """``_seg_cost`` of the vertical segments at x = ``x``, for the many legs ``route`` tries on one line: the tests
    that depend on x alone done once, the others on the obstacles that pass them. The same terms, in the same order,
    summed the same way: the same costs."""

    def __init__(self, obs: Obstacles, x: float, lane: float, solid: bool = False):
        half = lane / 2
        self.bus = bus_cross(solid)
        self.box_cross, self.run_along = obs.box_cross, obs.run_along
        self.boxes = [(o[1], o[3] + CLEAR) for o in obs.boxes if x < o[2] + CLEAR and o[0] < x + CLEAR]
        self.buses = [y for y, h0, h1 in obs.buses if h0 < x < h1]
        self.sides = [y for f in obs.frames for y in (f[1], f[3]) if f[0] < x < f[2]]  # frame sides crossed
        self.along = [(v0, v1) for v, v0, v1 in obs.vwires if abs(v - x) < half]
        self.near = [(v0, v1) for k, v, v0, v1 in obs.conductors
                     if k == "v" and half <= abs(v - x) < obs.near_wire] if obs.near_wire else []
        self.frames = [(obs.frame_along if abs(v - x) >= half else BOX_CROSS, f[1], f[3])
                       for f in obs.frames for v in (f[0], f[2]) if abs(v - x) < obs.frame_clear]
        self.empty = not (self.boxes or self.buses or self.sides or self.along or self.near or self.frames)

    def leg(self, ye: float) -> Callable[[float], float]:
        """``cost(ye, y)`` as a function of y, for the legs from one end: the tests and bounds that depend on ``ye`` alone
        done once for each way (y above or below ``ye``), the boxes, busbars and frame sides crossed counted by
        bisection (a sum of equal terms: the same sum)."""
        w, bc, bus = self.run_along, self.box_cross, self.bus
        # y > ye: lo = ye, hi = y
        up_boxes = sorted(y0 for y0, y1c in self.boxes if ye < y1c)
        up_bars = sorted(y for y in self.buses if ye < y)
        up_sides = sorted(y for y in self.sides if ye < y)
        up_along = [(v0, v1, max(v0, ye)) for v0, v1 in self.along if ye < v1]
        up_near = [(v0, v1, max(v0, ye)) for v0, v1 in self.near if ye < v1]
        up_frames = [(k, f3, max(f1, ye)) for k, f1, f3 in self.frames]
        # y < ye: lo = y, hi = ye
        yc = ye + CLEAR
        down_boxes = sorted(y1c for y0, y1c in self.boxes if y0 < yc)
        down_bars = sorted(y for y in self.buses if y < ye)
        down_sides = sorted(y for y in self.sides if y < ye)
        down_along = [(v0, v1, min(v1, ye)) for v0, v1 in self.along if v0 < ye]
        down_near = [(v0, v1, min(v1, ye)) for v0, v1 in self.near if v0 < ye]
        down_frames = [(k, f1, min(f3, ye)) for k, f1, f3 in self.frames]

        def cost(y: float) -> float:
            if abs(ye - y) < 1e-9:
                return 0.0
            if ye < y:
                c = sum([bc] * bisect_left(up_boxes, y + CLEAR)) if up_boxes else 0
                if up_bars:
                    c += sum([bus] * bisect_left(up_bars, y))
                if up_sides:
                    c += sum([FRAME_CROSS] * bisect_left(up_sides, y))
                if up_along:  # (``_along`` written out)
                    c += sum([w * min(1.0, max(min(v1, y) - m0, 0.3) / 3.0) for v0, v1, m0 in up_along if v0 < y])
                if up_near:
                    c += sum([NEAR_RUN * (min(v1, y) - m0) for v0, v1, m0 in up_near if v0 < y])
                if up_frames:
                    c += sum([k for k, f3, m1 in up_frames if min(f3, y) - m1 > FRAME_RUN])
                return c
            c = sum([bc] * (len(down_boxes) - bisect_right(down_boxes, y))) if down_boxes else 0
            if down_bars:
                c += sum([bus] * (len(down_bars) - bisect_right(down_bars, y)))
            if down_sides:
                c += sum([FRAME_CROSS] * (len(down_sides) - bisect_right(down_sides, y)))
            if down_along:
                c += sum([w * min(1.0, max(m1 - max(v0, y), 0.3) / 3.0) for v0, v1, m1 in down_along if y < v1])
            if down_near:
                c += sum([NEAR_RUN * (m1 - max(v0, y)) for v0, v1, m1 in down_near if y < v1])
            if down_frames:
                c += sum([k for k, f1, m3 in down_frames if m3 - max(f1, y) > FRAME_RUN])
            return c

        return cost

    def cost(self, ya: float, yb: float) -> float:
        """``_seg_cost`` from (x, ya) to (x, yb)."""
        if abs(ya - yb) < 1e-9:
            return 0.0
        if self.empty:
            return 0
        lo, hi = min(ya, yb), max(ya, yb)
        if self.boxes:
            hc = hi + CLEAR
            cost = sum([self.box_cross for y0, y1c in self.boxes if lo < y1c and y0 < hc])
        else:
            cost = 0
        if self.buses:
            cost += sum([self.bus for y in self.buses if lo < y < hi])
        if self.sides:
            cost += sum([FRAME_CROSS for y in self.sides if lo < y < hi])
        if self.along:  # (``_along`` written out)
            w = self.run_along
            cost += sum([w * min(1.0, max(min(v1, hi) - max(v0, lo), 0.3) / 3.0) for v0, v1 in self.along
                         if v0 < hi and lo < v1])
        if self.near:
            cost += sum([NEAR_RUN * (min(v1, hi) - max(v0, lo)) for v0, v1 in self.near if v0 < hi and lo < v1])
        if self.frames:
            cost += sum([k for k, f1, f3 in self.frames if min(f3, hi) - max(f1, lo) > FRAME_RUN])
        return cost


class _Legs:
    """The ways ``_leg`` tries from the end ``e`` to a channel, for ``route``: each stub with its horizontal cost and the
    line of its vertical, costed once."""

    def __init__(self, obs: Obstacles, e: End, lane: float, seg: _Costs, solid: bool = False):
        self.e = e
        lines: dict[float, _VLine] = {}
        if e.side in ("down", "up"):
            self.line = _VLine(obs, e.x, lane, solid).leg(e.y)  # (``cost(y, e.y)`` is ``cost(e.y, y)``)
            return
        self.stubs = []
        for s in e.stubs:
            xs = e.x + s if e.side == "right" else e.x - s
            h, t = seg((e.x, e.y), (xs, e.y)), 0.15 * s
            line = lines.get(xs)
            if line is None:
                line = lines[xs] = _VLine(obs, xs, lane, solid)
            self.stubs.append((xs, h, t, h + t, line.leg(e.y)))

    def within(self, y: float, ca: Optional[float], extra: float, bound: float) -> tuple[float, list[Point]]:
        """``_leg`` to the channel at ``y``, leaving out the stubs that cannot give a route cheaper than ``bound``: the
        route costs at least (``ca`` + this leg) + ``extra`` (``ca`` None: this leg + ``extra``). The leg returned is
        ``_leg``'s whenever its route is cheaper than ``bound`` (1e9: none is)."""
        e = self.e
        if e.side == "down":
            if y < e.y + 1.0:
                return 1e9, []
            return self.line(y), [(e.x, e.y), (e.x, y)]
        if e.side == "up":  # high enough above the busbar not to read as its extension
            if y > e.y - 4.0:
                return 1e9, []
            return self.line(y), [(e.x, e.y), (e.x, y)]
        best: tuple[float, list[Point]] = (1e9, [])
        for xs, h, t, low, vertical in self.stubs:  # the leg costs h + v + t >= low
            if low >= best[0] or (low + extra if ca is None else (ca + low) + extra) >= bound:
                continue
            c = h + vertical(y) + t
            if c < best[0]:
                best = (c, [(e.x, e.y), (xs, e.y), (xs, y)])
        return best


def route(obs: Obstacles, a: End, b: End, y_min: Optional[float] = None, y_max: Optional[float] = None,
          step: float = 0.5, record: bool = True, lane: float = LANE, solid: bool = False,
          cost_out: Optional[list[float]] = None, deeper: bool = False, wrap: float = 0.0) -> list[Point]:
    """Orthogonal route from ``a`` to ``b`` through a horizontal channel that avoids texts and symbols.
    ``lane``: minimum spacing from parallel conductors (wider for a link that will carry a device symbol);
    ``solid``: a power link drawn as a plain line, kept off the busbars it would run along;
    ``cost_out``: receives the cost of the route found (to compare the ends a link could use);
    ``deeper``: when the best channel runs on another line, a channel of its own lower down, under everything drawn
    between the ends if need be (room is made there: what is drawn under the routes moves down); ``wrap``: the cost
    of each turn that closes the route round something (see ``wraps``)."""
    lo = min(a.y, b.y) - 30.0 if y_min is None else y_min
    hi = max(a.y, b.y) + 30.0 if y_max is None else y_max
    sub = obs.window((min(a.x, b.x) - 12.0, lo - 2.0, max(a.x, b.x) + 12.0, hi + 2.0))
    best = _channel(sub, a, b, lo, hi, step, lane, solid, wrap=wrap)
    if deeper and best[1] and _shared(sub, best[3], lane):
        x0, x1 = min(a.x, b.x) - 12.0, max(a.x, b.x) + 12.0
        floor = max([o[3] for o in obs.boxes if o[0] < x1 and x0 < o[2]]
                    + [y for y, h0, h1 in obs.hlines if h0 < x1 and x0 < h1] + [hi]) + 2.0 * lane
        low = obs.window((x0, lo - 2.0, x1, floor + 2.0))
        alt = _channel(low, a, b, best[2], floor, step, lane, solid, unshared=True, wrap=wrap)
        if alt[1]:
            best = alt
    pts = _simplify(best[1])
    if cost_out is not None:
        cost_out.append(best[0])
    if record:
        record_route(obs, pts)
    return pts


def _dir(p: Point, q: Point) -> Optional[int]:
    """Index in ``_DIRS`` of the move from p to q (None: no move, or not along an axis)."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    if abs(dy) < 1e-9 and abs(dx) > 1e-9:
        return 0 if dx > 0 else 1
    if abs(dx) < 1e-9 and abs(dy) > 1e-9:
        return 2 if dy > 0 else 3
    return None


def _hand(d: int, d2: int) -> int:
    """+1 / -1: the way a turn from the move ``d`` to ``d2`` goes (0: no turn)."""
    (ax, ay), (bx, by) = _DIRS[d], _DIRS[d2]
    return ax * by - ay * bx


def _wind(w: int, d: int, d2: int) -> tuple[int, int]:
    """The turns of a route so far, ``w`` = 4 * a + b: ``a`` quarter turns one way since its most the other way, ``b``
    the other way since its least (each kept at three at most), after a move ``d`` then ``d2``; and whether that turn
    takes it past two quarter turns between its two extremes (round on three sides)."""
    h = _hand(d, d2)
    if h == 0:
        return w, 0
    a, b = divmod(w, 4)
    a2, b2 = (a + 1, max(b - 1, 0)) if h > 0 else (max(a - 1, 0), b + 1)
    k = int(a2 + b2 > max(2, a + b))
    return min(a2, 3) * 4 + min(b2, 3), k


def wraps(pts: list[Point], then: Optional[int] = None) -> int:
    """The turns of a route that take it past two quarter turns the same way between its extremes (jogs between them
    or not): with them it goes round what it passes on three sides and, with the line it leaves or reaches, closes a
    rectangle that reads as a frame. ``then``: the move the line goes on with after the route's end (a trunk)."""
    ds = [d for p, q in zip(pts, pts[1:]) if (d := _dir(p, q)) is not None]
    if then is not None:
        ds.append(then)
    n, w = 0, 0
    for d, d2 in zip(ds, ds[1:]):
        w, k = _wind(w, d, d2)
        n += k
    return n


def _channel(obs: Obstacles, a: End, b: End, lo: float, hi: float, step: float, lane: float, solid: bool,
             unshared: bool = False, wrap: float = 0.0) -> tuple[float, list[Point], float, list[Point]]:
    """Cheapest route through one channel between the heights ``lo`` and ``hi``: (cost, points, height of the
    channel, the channel); ``unshared``: only channels running on no other line; ``wrap``: see ``route``."""
    seg = _Costs(obs, lane)
    legs_a, legs_b = _Legs(obs, a, lane, seg, solid), _Legs(obs, b, lane, seg, solid)
    best: tuple[float, list[Point], float, list[Point]] = (1e18, [], lo, [])
    n = int((hi - lo) / step)
    # Every cost is >= 0 and a rounded sum never decreases when a term grows: a channel, or a stub, whose cost so far
    # already reaches the best route found cannot beat it (``<``) and is not costed further. Same route, same cost.
    for i in range(n + 1):
        y = lo + i * step
        length = abs(y - a.y) + abs(y - b.y)
        extra = 0.08 * length
        if extra >= best[0]:
            continue
        ca, pa = legs_a.within(y, None, extra, best[0])
        if ca >= 1e9:
            continue
        if ca + extra >= best[0]:
            continue
        cb, pb = legs_b.within(y, ca, extra, best[0])
        if cb >= 1e9:
            continue
        if (ca + cb) + extra >= best[0]:
            continue
        ch = seg(pa[-1], pb[-1], solid)
        cost = ca + cb + ch + extra
        if wrap and cost < best[0]:  # (a wrap adds to the cost: the bounds above stay valid)
            cost += wrap * wraps(pa + pb[::-1])
        if cost < best[0] and not (unshared and _shared(obs, [pa[-1], pb[-1]], lane)):
            best = (cost, pa + pb[::-1], y, [pa[-1], pb[-1]])
    return best


SHARED_RUN = 3.0  # mm: two lines running on one another longer than this read as one


def _shared(obs: Obstacles, pts: list[Point], lane: float) -> bool:
    """Whether the horizontal stretches of a route run on another line (the channel of a link already routed, a
    busbar, the side of a frame) for longer than ``SHARED_RUN``."""
    for p, q in zip(pts, pts[1:]):
        if abs(p[1] - q[1]) < 1e-9:
            x0, x1 = min(p[0], q[0]), max(p[0], q[0])
            if any(abs(y - p[1]) < lane * 0.9 and min(h1, x1) - max(h0, x0) > SHARED_RUN for y, h0, h1 in obs.hlines):
                return True
    return False


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

    rec = obs
    if cands:  # every test below on the obstacles near the candidates only: the same answers, far fewer to scan
        tb = [text_box(x, y, w, size, anchor) for x, y, anchor in cands]
        m = max(obs.label_pad, CLEAR, BUS_PAD, SHARE_GAP) + 1.0
        obs = obs.window((min(b[0] for b in tb) - m, min(b[1] for b in tb) - m,
                          max(b[2] for b in tb) + m, max(b[3] for b in tb) + m))
    index = _Index(obs) if cands else None
    if obs.label_channel:
        h_lines = _Lines(obs.hlines + [(c[1], c[2], c[3]) for c in obs.conductors if c[0] == "h"])
        v_lines = _Lines(obs.vwires + [(c[1], c[2], c[3]) for c in obs.conductors if c[0] == "v"])

    best: tuple[float, int] = (1e18, 0)
    clean = False
    pad, channel, buses, g = obs.label_pad, obs.label_channel, obs.buses, SHARE_GAP
    small, large = min(pad, CLEAR / 2), max(pad, CLEAR / 2)
    if index is not None:
        vk, vl, hk, hl = index.vwires.keys, index.vwires.lines, index.hlines.keys, index.hlines.lines
    for i, b in enumerate(tb if cands else ()):  # (each ``text_box`` of ``cands``)
        x0, y0, x1, y1 = b
        on_bus = sum([1 for by, h0, h1 in buses if y0 - BUS_PAD < by < y1 + BUS_PAD and h0 < x1 and x0 < h1]) if buses else 0
        shared = False  # another line runs along the far side of the label: it could belong to either (multi-line)
        if channel:
            kind, at = owns[i]
            if kind == "h":
                for y, h0, h1 in h_lines.lines[bisect_right(h_lines.keys, y0 - g):bisect_left(h_lines.keys, y1 + g)]:
                    if h0 < x1 and x0 < h1 and abs(y - at) > 1e-6:
                        shared = True
                        break
            else:
                for x, v0, v1 in v_lines.lines[bisect_right(v_lines.keys, x0 - g):bisect_left(v_lines.keys, x1 + g)]:
                    if v0 < y1 and y0 < v1 and abs(x - at) > 1e-6:
                        shared = True
                        break
        # ``obs.box_free(b, pad, 0.1)`` and ``obs.overlap(b, pad, 0.1)`` and ``obs.overlap(b, CLEAR / 2, 0.1)`` from the
        # same counts: the boxes within ``large``, those of them within ``small`` (a box within the smaller pad is within
        # the larger one, after rounding too), and the lines crossed (as ``_Index.hits``, ``_Index.crossed``)
        near = index.near(b, large)
        if near:
            hits = [o for o in near if x0 < o[2] + large and o[0] < x1 + large and y0 < o[3] + large and o[1] < y1 + large]
            k_large = len(hits)
            k_small = len([o for o in hits if x0 < o[2] + small and o[0] < x1 + small and y0 < o[3] + small
                           and o[1] < y1 + small]) if hits else 0
        else:
            k_large = k_small = 0
        k = k_large if pad == large else k_small
        nv = sum([1 for v, v0, v1 in vl[bisect_right(vk, x0 - 0.1):bisect_left(vk, x1 + 0.1)] if v0 < y1 and y0 < v1])
        nh = sum([1 for h, h0, h1 in hl[bisect_right(hk, y0 - 0.1):bisect_left(hk, y1 + 0.1)] if h0 < x1 and x0 < h1])
        if not on_bus and not shared and not k and not nv and not nh:
            best = (0.0, i)
            break
        # clear of the texts at the usual distance at least, if not at the wider one asked
        hit = 10.0 * (k_large if CLEAR / 2 == large else k_small) + nv + nh
        clean = clean or hit == 0
        cost = hit * 10.0 + (10.0 * k + nv + nh) + on_bus + i * 1e-3
        if channel:  # multi-line: on a text is worse than beside another line
            cost += 5.0 * (hit > 0) + 0.5 * shared
        if cost < best[0]:
            best = (cost, i)
    if optional and not (best[0] == 0.0 or clean):
        return None
    x, y, anchor = cands[best[1]] if cands else (pts[-1][0], pts[-1][1], "start")
    if record:
        rec.add_box(text_box(x, y, w, size, anchor))
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


def _load_native():
    """The compiled search of ``route_grid`` (the optional package ``uniwire-native``), or None: not installed, not
    loadable here, of another interface, or turned off with the environment variable ``UNIWIRE_NATIVE=0``. Both
    searches find the same routes (same costs, same floating-point operations, same tie order); the compiled one is
    many times faster. It is also built for the browser editor (Pyodide), where it is loaded when it can be."""
    if os.environ.get("UNIWIRE_NATIVE", "").strip() == "0":
        return None
    try:
        import uniwire_native
    except Exception:  # noqa: BLE001  (not installed, or a build that cannot be loaded here: draw in pure Python)
        return None
    if getattr(uniwire_native, "GRID_API", None) != 1:  # built for another version of this search
        return None
    return uniwire_native.grid_search


_grid_search = _load_native()
# ``_wind`` as two tables by turns * 16 + d * 4 + d2 (for the compiled search): the turns after, a wrap made or not
_WIND = [_wind(t, d, d2) for t in range(16) for d in range(4) for d2 in range(4)]
_WIND_TURNS, _WIND_WRAP = bytes(w for w, _ in _WIND), bytes(k for _, k in _WIND)
_PROBE: list[list[Point]] = []  # debugging aid, see route_grid


def _ragged(lists: list[tuple], width: int = 4) -> tuple[list[int], list[float]]:
    """Lists of tuples of ``width`` floats as (offsets, flat values), for the compiled search."""
    off, vals = [0], []
    for items in lists:
        for item in items:
            vals.extend(item[-width:])
        off.append(len(vals) // width)
    return off, vals


def _gaps(vals: list[float], kinds: list[list]) -> list[tuple[list[int], list[float]]]:
    """For each kind of line (position, start, end), the lines between each grid line and the next (the ones a move
    between them crosses, as ``between``), as ``_ragged`` (start, end) lists, for the compiled search."""
    from bisect import bisect_right

    out = []
    for lines in kinds:
        keys = [bisect_right(lines, (v, 1e18, 1e18)) for v in vals]
        out.append(_ragged([lines[keys[n]:keys[n + 1]] if n + 1 < len(vals) else [] for n in range(len(vals))], 2))
    return out


def _grid_dijkstra(nx: int, ny: int, start_at: list[tuple[int, int]], goal_at: dict[int, int], wrap: float,
                   then: Optional[list[Optional[int]]], bend: float, cache: list[Optional[float]],
                   edge_cost: Callable[[int], float]) -> tuple[list[int], int, float]:
    """The search of ``route_grid`` (pure Python): the states from the goal reached back to the start used ([]: no
    route), the index of that start and the cost of the route."""
    import heapq

    # states (column, row, direction of the last move) numbered (i * ny + j) * 4 + d: flat arrays, not dictionaries;
    # with ``wrap``, the turns made on the cheapest way to each state kept with it (see ``_wind``: not a state of its
    # own, many times more states to search, for a cost that the cheapest way gets right but in rare cases).
    # The heap holds (cost, state << 6 | kind << 4 | turns[, state before]), kind 1: the first move from an end, 2: a
    # goal reached (wrap): the same order as (cost, i, j, d, kind, turns[, before]), with less to compare.
    heap: list[tuple] = []
    size = nx * ny * 4
    origin = [0] * size
    prev = [-1] * size
    dist = [1e18] * size
    turns = [0] * size
    for st, k in start_at:
        dist[st], prev[st], origin[st] = 0.0, -1, k
        heapq.heappush(heap, (0.0, st << 6 | 16))
    # the moves from a state: (direction, step of the cell number, step of the edge key from cell * 2)
    px, mx, py, my = (0, ny, 0), (1, -ny, -2 * ny), (2, 1, 1), (3, -1, -1)
    moves = [(px, py, my), (mx, py, my), (px, mx, py), (px, mx, my)]  # no turning back
    straight = [(px,), (mx,), (py,), (my,)]  # the first move from an end
    last_i, last_j = nx - 1, ny - 1
    pop, push = heapq.heappop, heapq.heappush
    found = -1
    last = -1  # wrap: the state before the goal reached (a goal is reached by its own heap entry)
    while heap:
        item = pop(heap)
        cost, code = item[0], item[1]
        st = code >> 6
        fresh = (code >> 4) & 3
        if fresh == 2:  # wrap: a goal reached, the turn into the line it joins counted
            found, last = st, item[2]
            break
        if cost > dist[st]:
            continue
        t = code & 15
        if wrap:
            if t != turns[st]:
                continue
        elif not fresh and st in goal_at:
            found = st
            break
        d = st & 3
        cell = st >> 2
        i, j = divmod(cell, ny)
        for d2, dc, dk in (straight[d] if fresh else moves[d]):
            if d2 == 0:
                if i == last_i:
                    continue
            elif d2 == 1:
                if i == 0:
                    continue
            elif d2 == 2:
                if j == last_j:
                    continue
            elif j == 0:
                continue
            key = cell * 2 + dk
            e = cache[key]
            if e is None:
                e = edge_cost(key)
            c = cost + e + (bend if d2 != d else 0.0)
            s2 = (cell + dc) * 4 + d2
            if wrap:
                t2 = t
                if not fresh and d2 != d:
                    t2, k = _wind(t, d, d2)
                    c += wrap * k
                if s2 in goal_at:
                    nxt = then[goal_at[s2]] if then is not None else None
                    k = _wind(t2, d2, nxt)[1] if nxt is not None else 0
                    push(heap, (c + wrap * k, s2 << 6 | 32 | t2, st))
                if c < dist[s2]:
                    dist[s2], prev[s2], origin[s2], turns[s2] = c, st, origin[st], t2
                    push(heap, (c, s2 << 6 | t2))
            elif c < dist[s2]:
                dist[s2], prev[s2], origin[s2] = c, st, origin[st]
                push(heap, (c, s2 << 6))
    if found < 0:
        return [], 0, 0.0
    chain = [found] if wrap else []  # wrap: the way the goal was reached by (its own state may be reached cheaper)
    s = last if wrap else found
    while s >= 0:
        chain.append(s)
        s = prev[s]
    return chain, origin[chain[-1]], cost if wrap else dist[found]


def route_grid(obs: Obstacles, starts: list[End], goals: list[End], window: Box, lane: float = LANE,
               step: float = 1.0, record: bool = True,
               cost_out: Optional[list[float]] = None, bend: float = 0.0,
               length: float = GRID_LENGTH, wrap: float = 0.0,
               then: Optional[list[Optional[int]]] = None, solid: bool = False) -> tuple[list[Point], int, int]:
    """Cheapest orthogonal route, with as many corners as needed, from one of ``starts`` to one of ``goals``
    (the ends a link may use on each device): Dijkstra on a grid of ``step`` mm laid over ``window``, through
    the coordinates of the ends. Same costs as ``route`` (texts and symbols, lines run along or crossed,
    frames), plus a cost per corner (``bend``, ``BEND`` if not given) and per mm (``length``). ``wrap``: the cost of a
    turn closing the route round what it passes (see ``wraps``); ``then``: for each goal, the move the line goes on
    with from there (a trunk), or None; ``solid``: a power link drawn as a plain line (a busbar crossed costs a tap,
    see ``bus_cross``). Returns the points and the indexes of the ends used (no route: [])."""
    from bisect import bisect_left, bisect_right

    bus = bus_cross(solid)

    bend = bend or BEND

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

    blocked_at = bytearray(nx * ny)  # grid points too close to a text or a symbol, by cell number i * ny + j
    for b in sub.boxes:
        rows = rng(ys, b[1] - CLEAR, b[3] + CLEAR)
        if rows:
            ones = b"\x01" * len(rows)
            for i in rng(xs, b[0] - CLEAR, b[2] + CLEAR):
                blocked_at[i * ny + rows.start:i * ny + rows.stop] = ones
    for e in starts + goals:  # an end is against its device: the first 1.5 mm out of it are free
        i, j = xs.index(e.x), ys.index(e.y)
        if e.side == "down":
            for k in range(j, len(ys)):
                if ys[k] <= e.y + 1.5:
                    blocked_at[i * ny + k] = 0
        elif e.side == "up":
            for k in range(len(ys)):
                if e.y - 1.5 <= ys[k] <= e.y:
                    blocked_at[i * ny + k] = 0
        else:
            free = 1.5 + 2 * CLEAR  # an end inside its symbol (an earth terminal) gets out of its clearance
            lo, hi = (e.x - free, e.x) if e.side == "left" else (e.x, e.x + free)
            for k in range(len(xs)):
                if lo <= xs[k] <= hi:
                    blocked_at[k * ny + j] = 0
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

    half = lane / 2

    def terms(pos: float, vertical: bool) -> tuple:
        """The lines that count when running at ``pos`` (x of a vertical, y of a horizontal move), each as
        (weight, divisor, start, end), in the order their costs are added: the distance tests, which depend on the
        line and ``pos`` only, done once per grid line rather than once per move."""
        if vertical:
            along, near_l, frames, bus = around(vw, pos, reach), around(cond_v, pos, reach), around(fx, pos, reach), []
        else:
            along = around(hl, pos, reach) + around(buses, pos, reach)
            near_l, frames, bus = around(cond_h, pos, reach), around(fy, pos, reach), around(buses, pos, reach)
        out = [(obs.run_along, 3.0, v0, v1) for p, v0, v1 in along if abs(p - pos) < half]
        if near:  # beside a conductor: reads as one more conductor of its bundle
            out += [(NEAR_RUN, 1.0, v0, v1) for p, v0, v1 in near_l if half <= abs(p - pos) < near]
        for p, v0, v1 in frames:  # the closer to a frame side run along, the worse
            if abs(p - pos) < obs.frame_clear:
                k = obs.frame_along * (1.0 - abs(p - pos) / obs.frame_clear) if abs(p - pos) >= half else obs.box_cross
                out.append((k, FRAME_RUN, v0, v1))
        out += [(RUN_ALONG, FRAME_RUN, v0, v1) for p, v0, v1 in bus if abs(p - pos) < BUS_CLEAR_THIN]  # on a busbar
        return tuple(out)

    def run_cost(a: float, b: float, lines: tuple) -> float:
        """Running from a to b along a grid line whose ``terms`` are ``lines``."""
        c = 0.0
        for w, k, v0, v1 in lines:
            if v0 < b and a < v1:
                c += w * (min(v1, b) - max(v0, a)) / k  # x / 1.0 is exactly x
        return c

    col: list[Optional[tuple]] = [None] * nx
    row: list[Optional[tuple]] = [None] * ny
    cache: list[Optional[float]] = [None] * (nx * ny * 2)  # edge costs, by (lower end, axis): same both ways
    gap_x: list[Optional[tuple]] = [None] * nx  # the lines crossed between two grid columns, the same on every row
    gap_y: list[Optional[tuple]] = [None] * ny
    box_cross = sub.box_cross

    def edge(i: int, j: int, d: int) -> float:
        di, dj = _DIRS[d]
        key = ((i + di if di < 0 else i) * ny + (j + dj if dj < 0 else j)) * 2 + (d >> 1)
        c = cache[key]
        return edge_cost(key) if c is None else c

    def edge_cost(key: int) -> float:
        """Cost of the move numbered ``key``: (lower end i * ny + j) * 2 + axis (1: vertical)."""
        cell = key >> 1
        i, j = divmod(cell, ny)
        if key & 1:  # vertical, at x = xs[i]
            c = box_cross if blocked_at[cell] or blocked_at[cell + 1] else 0.0
            x, a, b = xs[i], ys[j], ys[j + 1]
            lines = col[i]
            if lines is None:
                lines = col[i] = terms(x, True)
            c += length * (b - a) + (run_cost(a, b, lines) if lines else 0.0)
            g = gap_y[j]
            if g is None:
                g = gap_y[j] = (between(buses, a, b), between(fy, a, b), between(hl, a, b))
            bars, sides, wires = g
            if bars:
                c += sum(bus for y, h0, h1 in bars if h0 < x < h1)
            if sides:
                c += sum(FRAME_CROSS for y, h0, h1 in sides if h0 < x < h1)
            if wires:
                c += sum(WIRE_CROSS for y, h0, h1 in wires if h0 < x < h1)
        else:  # horizontal, at y = ys[j]
            c = box_cross if blocked_at[cell] or blocked_at[cell + ny] else 0.0
            y, a, b = ys[j], xs[i], xs[i + 1]
            lines = row[j]
            if lines is None:
                lines = row[j] = terms(y, False)
            c += length * (b - a) + (run_cost(a, b, lines) if lines else 0.0)
            h = gap_x[i]
            if h is None:
                h = gap_x[i] = (between(vw, a, b), between(fx, a, b))
            wires, sides = h
            if wires:
                c += sum(WIRE_CROSS for x, v0, v1 in wires if v0 < y < v1)
            if sides:
                c += sum(FRAME_CROSS for x, v0, v1 in sides if v0 < y < v1)
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
    # states (column, row, direction of the last move) numbered (i * ny + j) * 4 + d: flat arrays, not dictionaries;
    # with ``wrap``, the turns made on the cheapest way to each state kept with it (see ``_wind``: not a state of its
    # own, many times more states to search, for a cost that the cheapest way gets right but in rare cases).
    # The heap holds (cost, state << 6 | kind << 4 | turns[, state before]), kind 1: the first move from an end, 2: a
    # goal reached (wrap): the same order as (cost, i, j, d, kind, turns[, before]), with less to compare.
    goal_at = {(xs.index(e.x) * ny + ys.index(e.y)) * 4 + _ARRIVE[e.side]: k for k, e in enumerate(goals)}
    start_at = [((xs.index(e.x) * ny + ys.index(e.y)) * 4 + _LEAVE[e.side], k) for k, e in enumerate(starts)]
    if _grid_search is not None:  # the same search, compiled: on every grid line's costs, built here
        res = _grid_search(nx, ny, xs, ys, bytes(blocked_at),
                             _ragged([terms(x, True) for x in xs]), _ragged([terms(y, False) for y in ys]),
                             *_gaps(ys, [buses, fy, hl]), *_gaps(xs, [vw, fx]),
                             box_cross, length, bend, wrap, bus, FRAME_CROSS, WIRE_CROSS, start_at,
                             [(st, k, -1 if then is None or then[k] is None else then[k]) for st, k in goal_at.items()],
                             _WIND_TURNS, _WIND_WRAP)
        if res is None:
            return [], 0, 0
        chain, used, reported = res
    else:
        chain, used, reported = _grid_dijkstra(nx, ny, start_at, goal_at, wrap, then, bend, cache, edge_cost)
        if not chain:
            return [], 0, 0
    if cost_out is not None:
        cost_out.append(reported)
    found = chain[0]
    path = [(xs[s // 4 // ny], ys[s // 4 % ny]) for s in reversed(chain)]
    a, b = starts_in[used], goals_in[goal_at[found]]
    pts = _simplify(([(a.x, a.y)] if a.side == "down" else []) + path + ([(b.x, b.y)] if b.side == "down" else []))
    if record:
        record_route(obs, pts)
    return pts, used, goal_at[found]


DETOUR_BEND = 15.0  # a single-line route rerouted on the grid: few corners (a jog round a mark reads as a fault)


def record_route(obs: Obstacles, pts: list[Point]) -> None:
    """Record a route in the obstacles: later links fan out instead of running on it."""
    for p, q in zip(pts, pts[1:]):
        if abs(p[1] - q[1]) < 1e-9:
            obs.add_hline(p[1], p[0], q[0])
        elif abs(p[0] - q[0]) < 1e-9:
            obs.add_vline(p[0], p[1], q[1])


def path_cost(obs: Obstacles, pts: list[Point], lane: float = LANE, solid: bool = False) -> float:
    """Cost of a whole route with the costs of ``route``: what it crosses or runs along, its length, its corners."""
    c = sum(_seg_cost(obs, p, q, lane, solid) + 0.08 * (abs(p[0] - q[0]) + abs(p[1] - q[1]))
            for p, q in zip(pts, pts[1:]))
    return c + BEND * max(len(pts) - 2, 0)


def _length(pts: list[Point]) -> float:
    return sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(pts, pts[1:]))


GRAZE = 0.4  # a route this far inside the box of a text only grazes it (the box has a margin round the letters)


def _crosses_box(obs: Obstacles, pts: list[Point], free: float = 1.5) -> bool:
    """Whether a route passes through a text or a symbol, leaving out its first and last ``free`` mm and the boxes
    of the devices it joins."""
    total = _length(pts)
    done = 0.0
    own = [o for o in obs.boxes if any(_hit((x, y, x, y), o, 0.8) for x, y in (pts[0], pts[-1]))]  # joined devices
    boxes = [(o[0] + GRAZE, o[1] + GRAZE, o[2] - GRAZE, o[3] - GRAZE) for o in obs.boxes if o not in own]
    for p, q in zip(pts, pts[1:]):
        seg = _length([p, q])
        a, b = max(free - done, 0.0), min(total - free - done, seg)
        done += seg
        if b <= a or seg <= 0:
            continue
        ux, uy = (q[0] - p[0]) / seg, (q[1] - p[1]) / seg
        s0 = (p[0] + ux * a, p[1] + uy * a)
        s1 = (p[0] + ux * b, p[1] + uy * b)
        box = (min(s0[0], s1[0]), min(s0[1], s1[1]), max(s0[0], s1[0]), max(s0[1], s1[1]))
        if any(_hit(box, o) for o in boxes):
            return True
    return False


def along_bus(obs: Obstacles, pts: list[Point]) -> bool:
    """Whether a route runs along a busbar, close enough and long enough to read as part of it."""
    return any(abs(p[1] - q[1]) < 1e-9 and abs(y - p[1]) < BUS_CLEAR and min(h1, max(p[0], q[0])) - max(h0, min(p[0], q[0])) > BUS_RUN
               for p, q in zip(pts, pts[1:]) for y, h0, h1 in obs.buses)


def runs_along(obs: Obstacles, pts: list[Point], gap: float = 0.3, run: float = 3.0) -> bool:
    """Whether a route runs on another line (a conductor, another link) for more than ``run`` mm: drawn on one another,
    the two read as one."""
    for p, q in zip(pts, pts[1:]):
        if abs(p[1] - q[1]) < 1e-9:
            lo, hi = sorted((p[0], q[0]))
            if any(abs(y - p[1]) < gap and min(h1, hi) - max(h0, lo) > run for y, h0, h1 in obs.hlines):
                return True
        elif abs(p[0] - q[0]) < 1e-9:
            lo, hi = sorted((p[1], q[1]))
            if any(abs(x - p[0]) < gap and min(v1, hi) - max(v0, lo) > run for x, v0, v1 in obs.vwires):
                return True
    return False


def improve_route(obs: Obstacles, a: End, b: End, pts: list[Point], lane: float = LANE, solid: bool = False,
                  min_run: float = 0.0, starts: Optional[list[End]] = None, goals: Optional[list[End]] = None,
                  far_round: bool = True, on_lines: bool = False) -> list[Point]:
    """A route through one channel that passes through a text or a symbol, runs along a busbar (or on another line), or
    goes far round (``far_round``): the route with as many corners as needed (``route_grid``) when that one is clearly
    better.
    ``min_run``: its longest straight stretch at least this long (a link carrying a device symbol); ``starts``,
    ``goals``: the other ends the link may use on each device (``a``, ``b`` are the ones chosen); ``on_lines``: a route
    on another line (a thin link on another link) improved too."""
    if len(pts) < 2:
        return pts
    direct = abs(a.x - b.x) + abs(a.y - b.y)
    through = _crosses_box(obs, pts)
    crossing = through or along_bus(obs, pts) or (on_lines and runs_along(obs, pts))
    if not crossing and (not far_round or _length(pts) - direct <= max(30.0, 0.4 * direct)):
        return pts
    starts, goals = starts or [a], goals or [b]
    xs, ys = [e.x for e in starts + goals], [e.y for e in starts + goals]
    window = (min(xs) - 25.0, min(ys) - 25.0, max(xs) + 25.0, max(ys) + 25.0)
    alt, _ka, _kb = route_grid(obs, starts, goals, window, lane, record=False, bend=DETOUR_BEND, solid=solid)
    if len(alt) < 2 or max((_length([p, q]) for p, q in zip(alt, alt[1:])), default=0.0) < min_run:
        return pts
    if not crossing and _length(alt) > 0.8 * _length(pts):  # far round only: worth it when clearly shorter
        return pts
    if not through and _crosses_box(obs, alt):  # (off another line, but through a text or a symbol: no better)
        return pts
    if path_cost(obs, alt, lane, solid) < path_cost(obs, pts, lane, solid) - 1.0:
        return alt
    return pts
