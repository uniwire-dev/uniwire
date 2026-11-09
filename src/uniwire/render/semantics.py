"""Semantic metadata of the drawing: the groups behind the SVG structure contract (docs/api.md, "SVG structure").

The layout engines wrap what they draw in groups carrying a class and ``data-uw-*`` attributes (node symbols,
tree edges, busbars, out-of-tree links, conductors, cross-sheet references, feeder-table columns). The SVG
writer emits them as attributes, the PDF writer turns the references into internal links and the colour
modes (``render.colors``) use them to know what each stroke belongs to.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from .scene import Group, Item, Line, Point, Polyline, Style

HIT_WIDTH = 3.0  # mm: invisible stroke making a thin link easy to hover
HIT_COLOR = "transparent"  # skipped by the PDF writer, emitted as is in SVG


def has_cls(g: Group, cls: str) -> bool:
    return bool(g.cls) and cls in g.cls.split()


def add_cls(g: Group, cls: str) -> Group:
    if not has_cls(g, cls):
        g.cls = f"{g.cls} {cls}" if g.cls else cls
    return g


def node_group(g: Group) -> Group:
    """Mark a symbol group (``data-uw-id`` = node id) as a drawn node."""
    return add_cls(g, "uw-node")


def link_key(doc: Any, i: int) -> str:
    """Identifier of ``doc.links[i]`` in the drawing: its ``id``, else its index."""
    link = doc.links[i]
    return link.id or str(i)


def link_group(doc: Any, i: int) -> Group:
    link = doc.links[i]
    return Group(cls="uw-link", attrs={"data-uw-link": link_key(doc, i), "data-uw-kind": link.kind,
                                       "data-uw-from": link.from_, "data-uw-to": link.to})


def _strokes(items: Iterable[Item]) -> list[Item]:
    """Open conductor paths of a link (direct children and plain sub-groups; symbols, texts and references
    excluded)."""
    out: list[Item] = []
    for it in items:
        if isinstance(it, Line):
            out.append(Line(it.a, it.b, Style(HIT_WIDTH, None, HIT_COLOR)))
        elif isinstance(it, Polyline) and not it.closed:
            out.append(Polyline(list(it.points), Style(HIT_WIDTH, None, HIT_COLOR)))
        elif isinstance(it, Group) and not it.cls:
            out += _strokes(it.items)
    return out


def finish_link_group(g: Group) -> Group:
    """Add the invisible hit path to a link group and mark the devices it carries."""
    key = g.attrs.get("data-uw-link", "")
    for it in g.items:
        if isinstance(it, Group) and it.cls and ({"sym", "ml-sym"} & set(it.cls.split())):
            node_group(it)
            it.attrs["data-uw-link"] = key
    hits = _strokes(g.items)
    if hits:
        g.add(Group(hits, cls="uw-hit", attrs={"pointer-events": "stroke"}))
    return g


def edge_group(child: str, parent: Optional[str], items: Iterable[Item] = ()) -> Group:
    return Group(list(items), cls="uw-edge", attrs={"data-uw-edge": child, "data-uw-parent": parent or ""})


def busbar_group(owner: str, items: Iterable[Item] = (), cond: Optional[str] = None) -> Group:
    g = Group(list(items), owner, "uw-busbar")
    if cond:
        g.attrs["data-uw-cond"] = cond
    return g


def ref_group(sheet: Optional[int], target: Optional[str], items: Iterable[Item] = ()) -> Group:
    """Reference to another sheet (off-page arrow, continuation, cross-sheet link end, incoming feed)."""
    return Group(list(items), cls="uw-ref", attrs={"data-uw-target-sheet": str(sheet) if sheet else "",
                                                   "data-uw-target-id": target or ""})


def cond_group(cond: str, *items: Item) -> Group:
    """Conductor segment(s) of the multi-line diagram."""
    return Group(list(items), attrs={"data-uw-cond": cond})


CROSSING_GAP = 0.8  # mm each side: a dashed link is interrupted where it crosses a conductor (not connected to it)
MIN_PIECE = 3.0  # mm: crossings closer than this (plus the gaps) cross a bundle of conductors: left whole, a gap per
# conductor would cut the link into dots and one gap across the bundle would hide it


SIGNAL_KINDS = ("control", "interlock", "trip", "measure", "key")  # links interrupted at a crossing (not a power,
# earth or data link: a gap in those could read as a break of the conductor or of the bus)
CONDUCTING_KINDS = ("infeed", "bypass", "parallel", "transfer", "tie")  # a solid link of these kinds is a conductor


def _conductor_segments(item: Item, inside: bool = False) -> list[tuple[Point, Point]]:
    """Straight runs of the conductors drawn in ``item``: tree conductors, busbars, the conductors of the multi-line
    view (also those drawn inside a device's group) and the solid power links."""
    if isinstance(item, Group):
        power_link = has_cls(item, "uw-link") and item.attrs.get("data-uw-kind") in CONDUCTING_KINDS
        if has_cls(item, "uw-hit") or has_cls(item, "uw-link") and not power_link:
            return []
        inside = inside or power_link or has_cls(item, "uw-edge") or has_cls(item, "uw-busbar") \
            or "data-uw-cond" in item.attrs
        return [s for i in item.items for s in _conductor_segments(i, inside)]
    if not inside or getattr(item, "style", None) is not None and item.style.dash:
        return []
    if isinstance(item, Line):
        return [(item.a, item.b)]
    if isinstance(item, Polyline):
        pts = item.points + (item.points[:1] if item.closed else [])
        return list(zip(pts, pts[1:]))
    return []


def _crossings(pts: list[Point], conductors: list[tuple[Point, Point]], margin: float) -> list[float]:
    """Distances along the path ``pts`` where it crosses a conductor at right angles, the crossing inside both
    (not where the conductor ends: a link may stop on it or pass its end)."""
    out, s = [], 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        length = abs(bx - ax) + abs(by - ay)
        horizontal = abs(ay - by) < 1e-6
        if horizontal == (abs(ax - bx) < 1e-6):  # a point, or not axis-parallel
            s += length
            continue
        for (cx, cy), (dx, dy) in conductors:
            if horizontal and abs(cx - dx) < 1e-6 and min(ax, bx) < cx < max(ax, bx) \
                    and min(cy, dy) + margin < ay < max(cy, dy) - margin:
                out.append(s + abs(cx - ax))
            elif not horizontal and abs(cy - dy) < 1e-6 and min(ay, by) < cy < max(ay, by) \
                    and min(cx, dx) + margin < ax < max(cx, dx) - margin:
                out.append(s + abs(cy - ay))
        s += length
    return sorted(out)


def gapped_crossings(pts: list[Point], conductors: list[tuple[Point, Point]], gap: float = CROSSING_GAP) -> list[float]:
    """Where the link ``pts`` is interrupted (distances along it): its single crossings of a conductor, not near its
    ends (they stop on what they reach), not in a bundle (see ``MIN_PIECE``)."""
    total = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    cs: list[float] = []
    for c in _crossings(pts, conductors, 0.3):  # (several conductors drawn on one another cross it once)
        if not cs or c - cs[-1] > 1e-3:
            cs.append(c)
    return [c for i, c in enumerate(cs) if gap + 0.5 <= c <= total - gap - 0.5
            and all(abs(c - d) >= 2 * gap + MIN_PIECE for j, d in enumerate(cs) if j != i)]


def _sub_path(pts: list[Point], s0: float, s1: float) -> list[Point]:
    """The part of the path ``pts`` between the distances ``s0`` and ``s1`` along it."""
    out: list[Point] = []
    s = 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        length = abs(bx - ax) + abs(by - ay)
        if length > 0 and s + length > s0 and s < s1:
            k0, k1 = (max(s0, s) - s) / length, (min(s1, s + length) - s) / length
            a, b = (ax + k0 * (bx - ax), ay + k0 * (by - ay)), (ax + k1 * (bx - ax), ay + k1 * (by - ay))
            if not out or out[-1] != a:
                out.append(a)
            out.append(b)
        s += length
    return out


def _phase(v: float, period: float) -> float:
    """A dash offset rounded to a thousandth of a millimetre (0 for a whole period)."""
    v = round(v, 3)
    return 0.0 if v <= 0.0 or v >= round(period, 3) else v


def gap_link_crossings(root: Group, gap: float = CROSSING_GAP) -> None:
    """Interrupt every dashed signal link (``SIGNAL_KINDS``) where it crosses a conductor, so that the crossing does
    not read as a connection (the conductor stays whole). Not near a link's ends: they stop on what they reach. Each
    piece keeps the dash pattern of the whole line."""
    conductors = _conductor_segments(root)
    if conductors:
        _gap_links(root, conductors, gap)


def _gap_links(g: Group, conductors: list[tuple[Point, Point]], gap: float, kind: Optional[str] = None) -> None:
    if has_cls(g, "uw-link"):
        kind = g.attrs.get("data-uw-kind")
    items: list[Item] = []
    for it in g.items:
        if isinstance(it, Group):
            if not has_cls(it, "uw-hit"):
                _gap_links(it, conductors, gap, kind if not it.cls or has_cls(it, "uw-link") else None)
            items.append(it)
            continue
        if not (kind in SIGNAL_KINDS and isinstance(it, Polyline) and not it.closed and it.style.dash
                and len(it.points) > 1):
            items.append(it)
            continue
        total = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(it.points, it.points[1:]))
        cuts = [[c - gap, c + gap] for c in gapped_crossings(it.points, conductors, gap)]
        if not cuts:
            items.append(it)
            continue
        starts = [0.0] + [b for _a, b in cuts]
        ends = [a for a, _b in cuts] + [total]
        period = sum(it.style.dash)
        for a, b in zip(starts, ends):
            if b - a > 1e-6:
                st = Style(it.style.width, it.style.dash, it.style.color, it.style.fill,
                           _phase((it.style.dash_offset + a) % period, period) if period else 0.0)
                items.append(Polyline(_sub_path(it.points, a, b), st))
    g.items = items
