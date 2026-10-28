"""Readability audit of a laid-out sheet: overlapping texts, links drawn over one another, links running on a
conductor. Used by the tests to keep these defects from coming back."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Optional

from uniwire.render.scene import Group, Line, Polyline, Rect, Text, text_width

Box = tuple[float, float, float, float]
Seg = tuple[tuple[float, float], tuple[float, float]]


@dataclass
class Finding:
    kind: str  # "text_overlap", "shared_run", "link_on_conductor", "link_along_frame"
    what: str
    where: tuple[float, float]

    def __str__(self) -> str:
        return f"{self.kind} at ({self.where[0]:.0f}, {self.where[1]:.0f}): {self.what}"


def _walk(item, link: Optional[str] = None, owner: Optional[str] = None) -> Iterator[tuple[object, Optional[str], Optional[str]]]:
    if isinstance(item, Group):
        link = item.attrs.get("data-uw-link", link)
        owner = item.id or owner
        for i in item.items:
            yield from _walk(i, link, owner)
    else:
        yield item, link, owner


def text_box(t: Text) -> Box:
    w, s = text_width(t.text, t.size), t.size
    x0 = {"start": 0.0, "middle": -w / 2, "end": -w}[t.anchor]
    y0, y1 = {"alphabetic": (-0.75 * s, 0.05 * s), "middle": (-0.4 * s, 0.4 * s), "hanging": (0.0, 0.8 * s)}[t.baseline]
    x, y = t.p
    if abs(t.rotate) % 180 == 90:  # reading upwards: the text runs along y
        return x + y0, y - (x0 + w), x + y1, y - x0
    return x + x0, y + y0, x + x0 + w, y + y1


def _segments(item: object) -> list[Seg]:
    if isinstance(item, Line):
        return [(item.a, item.b)]
    if isinstance(item, Polyline):
        return list(zip(item.points, item.points[1:]))
    return []


def _overlap(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _run(p: Seg, q: Seg, gap: float) -> float:
    """Length over which two axis-parallel segments run within ``gap`` of each other (0 if not parallel)."""
    (ax, ay), (bx, by) = p
    (cx, cy), (dx, dy) = q
    if abs(ay - by) < 1e-6 and abs(cy - dy) < 1e-6 and abs(ay - cy) <= gap:
        return min(max(ax, bx), max(cx, dx)) - max(min(ax, bx), min(cx, dx))
    if abs(ax - bx) < 1e-6 and abs(cx - dx) < 1e-6 and abs(ax - cx) <= gap:
        return min(max(ay, by), max(cy, dy)) - max(min(ay, by), min(cy, dy))
    return 0.0


def audit(root: Group) -> list[Finding]:
    texts: list[tuple[Text, Box]] = []
    links: dict[str, list[Seg]] = {}
    wires: list[Seg] = []
    frames: list[Seg] = []  # dashed outlines of boards, enclosures and view frames
    for item, link, _owner in _walk(root):
        if isinstance(item, Text) and item.text.strip():
            texts.append((item, text_box(item)))
        elif isinstance(item, Rect) and item.style.dash:
            x0, y0, x1, y1 = item.x, item.y, item.x + item.w, item.y + item.h
            frames += [((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))]
        elif link is not None:
            links.setdefault(link, []).extend(_segments(item))
        elif isinstance(item, (Line, Polyline)):
            wires.extend(_segments(item))
    out: list[Finding] = []
    for i, (t, a) in enumerate(texts):
        for u, b in texts[i + 1:]:
            ov = _overlap(a, b)
            small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if small > 0 and ov > 0.15 * small:
                out.append(Finding("text_overlap", f"{t.text!r} / {u.text!r}", t.p))
    ids = sorted(links)
    for i, la in enumerate(ids):
        for lb in ids[i + 1:]:
            run = max((_run(p, q, 0.3) for p in links[la] for q in links[lb]), default=0.0)
            if run > 3.0:
                out.append(Finding("shared_run", f"links {la} and {lb} share {run:.0f} mm", links[la][0][0]))
    for la in ids:
        run = max((_run(p, q, 1.2) for p in links[la] for q in wires), default=0.0)
        if run > 8.0:
            out.append(Finding("link_on_conductor", f"link {la} runs {run:.0f} mm on a conductor", links[la][0][0]))
        run = max((_run(p, q, 2.0) for p in links[la] for q in frames), default=0.0)
        if run > 10.0:  # a dashed link beside a dashed frame reads as one more frame line
            out.append(Finding("link_along_frame", f"link {la} runs {run:.0f} mm along a frame", links[la][0][0]))
    return out
