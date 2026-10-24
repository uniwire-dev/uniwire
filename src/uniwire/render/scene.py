"""Neutral vector scene (units: mm, y axis pointing down).

The SVG and PDF writers only know these primitives.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from typing import Literal, Optional, Union

Point = tuple[float, float]

THIN = 0.25
NORMAL = 0.35
THICK = 0.7
BUS = 1.2


@dataclass
class Style:
    width: float = NORMAL
    dash: Optional[tuple[float, ...]] = None
    color: str = "#000000"
    fill: Optional[str] = None


@dataclass
class Line:
    a: Point
    b: Point
    style: Style = field(default_factory=Style)


@dataclass
class Polyline:
    points: list[Point]
    style: Style = field(default_factory=Style)
    closed: bool = False


@dataclass
class Circle:
    c: Point
    r: float
    style: Style = field(default_factory=Style)


@dataclass
class Ellipse:
    c: Point
    rx: float
    ry: float
    style: Style = field(default_factory=Style)


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    style: Style = field(default_factory=Style)


@dataclass
class Text:
    p: Point
    text: str
    size: float = 2.0
    anchor: Literal["start", "middle", "end"] = "start"
    baseline: Literal["alphabetic", "middle", "hanging"] = "alphabetic"
    rotate: float = 0.0  # degrees, counter-clockwise (90 = text reading upwards)
    bold: bool = False
    color: str = "#000000"


@dataclass
class Group:
    items: list[Item] = field(default_factory=list)
    id: Optional[str] = None  # uniwire node id (traceability)
    cls: Optional[str] = None
    attrs: dict[str, str] = field(default_factory=dict)  # semantic metadata (SVG ``data-uw-*`` attributes)

    def add(self, *items: Item) -> Group:
        self.items.extend(items)
        return self


Item = Union[Line, Polyline, Circle, Ellipse, Rect, Text, Group]


@dataclass
class Page:
    width: float
    height: float
    root: Group = field(default_factory=Group)
    title: str = ""
    attrs: dict[str, str] = field(default_factory=dict)  # metadata of the sheet (root ``<svg>`` attributes)


def text_width(text: str, size: float) -> float:
    """Width estimate (Helvetica/Arial) for layout."""
    narrow = sum(1 for ch in text if ch in "il.,:;'|! ()-/fjtrI")  # digits are all one width in Arial
    wide = sum(1 for ch in text if ch in "mwMWQGOD@%→←↔")
    full = sum(1 for ch in text if unicodedata.east_asian_width(ch) in "WF")  # CJK: one em each
    upper = sum(1 for ch in text if ch.isupper() and ch not in "IJMWQGOD")  # capitals, Latin or Cyrillic
    return size * (0.55 * (len(text) - narrow - wide - full - upper) + 0.3 * narrow + 0.8 * wide + 1.0 * full
                   + 0.68 * upper)


def arc_points(c: Point, r: float, a0: float, a1: float, n: int = 16) -> list[Point]:
    """Approximated arc (angles in degrees, screen frame: 0 = right, 90 = down)."""
    pts = []
    for i in range(n + 1):
        t = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((c[0] + r * math.cos(t), c[1] + r * math.sin(t)))
    return pts


def transform(item: Item, dx: float = 0.0, dy: float = 0.0, rot: int = 0, scale: float = 1.0) -> Item:
    """Transformed copy: rotation (0/90/180/270, clockwise on screen) about the origin,
    then scaling, then translation."""

    def tp(p: Point) -> Point:
        x, y = p[0] * scale, p[1] * scale
        if rot == 90:
            x, y = -y, x
        elif rot == 180:
            x, y = -x, -y
        elif rot == 270:
            x, y = y, -x
        return (x + dx, y + dy)

    def ts(s: Style) -> Style:
        return Style(s.width, tuple(d * scale for d in s.dash) if s.dash else None, s.color, s.fill)

    if isinstance(item, Line):
        return Line(tp(item.a), tp(item.b), ts(item.style))
    if isinstance(item, Polyline):
        return Polyline([tp(p) for p in item.points], ts(item.style), item.closed)
    if isinstance(item, Circle):
        return Circle(tp(item.c), item.r * scale, ts(item.style))
    if isinstance(item, Ellipse):
        rx, ry = (item.ry, item.rx) if rot in (90, 270) else (item.rx, item.ry)
        return Ellipse(tp(item.c), rx * scale, ry * scale, ts(item.style))
    if isinstance(item, Rect):
        a = tp((item.x, item.y))
        b = tp((item.x + item.w, item.y + item.h))
        return Rect(min(a[0], b[0]), min(a[1], b[1]), abs(b[0] - a[0]), abs(b[1] - a[1]), ts(item.style))
    if isinstance(item, Text):
        return Text(tp(item.p), item.text, item.size * scale, item.anchor, item.baseline,
                    item.rotate, item.bold, item.color)
    if isinstance(item, Group):
        return Group([transform(i, dx, dy, rot, scale) for i in item.items], item.id, item.cls, dict(item.attrs))
    raise TypeError(item)


def bbox(item: Item) -> tuple[float, float, float, float] | None:
    """Bounding box (x0, y0, x1, y1), with estimated text extents."""
    if isinstance(item, Line):
        xs, ys = (item.a[0], item.b[0]), (item.a[1], item.b[1])
    elif isinstance(item, Polyline):
        xs, ys = [p[0] for p in item.points], [p[1] for p in item.points]
    elif isinstance(item, Circle):
        return (item.c[0] - item.r, item.c[1] - item.r, item.c[0] + item.r, item.c[1] + item.r)
    elif isinstance(item, Ellipse):
        return (item.c[0] - item.rx, item.c[1] - item.ry, item.c[0] + item.rx, item.c[1] + item.ry)
    elif isinstance(item, Rect):
        return (item.x, item.y, item.x + item.w, item.y + item.h)
    elif isinstance(item, Text):
        w = text_width(item.text, item.size)
        h = item.size
        x0 = item.p[0] - (w if item.anchor == "end" else w / 2 if item.anchor == "middle" else 0)
        y0 = item.p[1] - (h * 0.8 if item.baseline == "alphabetic" else h / 2 if item.baseline == "middle" else 0)
        if item.rotate in (90, -270):
            # upward text: its length extends upwards from p
            l0 = item.p[1] - (w if item.anchor == "start" else w / 2 if item.anchor == "middle" else 0)
            return (item.p[0] - h * 0.8, l0, item.p[0] + h * 0.2, l0 + w)
        return (x0, y0, x0 + w, y0 + h)
    elif isinstance(item, Group):
        boxes = [b for b in (bbox(i) for i in item.items) if b]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    else:
        return None
    return (min(xs), min(ys), max(xs), max(ys))
