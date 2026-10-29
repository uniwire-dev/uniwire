"""Readability audit of a laid-out sheet: overlapping texts, texts written over a symbol, texts shrunk below a
readable size, links drawn over one another, links running on a conductor. Used by the tests to keep these defects
from coming back."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Optional

from uniwire.render.scene import Circle, Group, Line, Polyline, Rect, Text, text_width

Box = tuple[float, float, float, float]
Seg = tuple[tuple[float, float], tuple[float, float]]


@dataclass
class Finding:
    kind: str  # "text_overlap", "text_on_symbol", "text_crossed", "text_on_conductor", "small_text", "shared_run",
    # "link_on_conductor", "link_along_frame"
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


SHRUNK = 0.78  # a black text this much smaller than the usual text of its sheet was shrunk to fit (the sheet itself
# may be drawn reduced: sizes compared on the sheet; conductor marks, port labels and symbol texts are small by design)


SMALL_BY_DESIGN = {"conductors", "title-block", "notes", "uw-legend"}  # conductor marks, the sheet's frame
TERMINALS = {"L1", "L2", "L3", "N", "PE", "PEN", "L", "L+", "L-", "+", "-", "U", "V", "W"}  # under a source bar


def _marks(item: object, inside: bool = False) -> Iterator[Text]:
    """Texts small by design: conductor marks (strokes, phases), title block, notes and legend."""
    if isinstance(item, Group):
        inside = inside or bool(item.cls and SMALL_BY_DESIGN & set(item.cls.split()))
        for i in item.items:
            yield from _marks(i, inside)
    elif inside and isinstance(item, Text):
        yield item


def _symbol_boxes(item: object) -> Iterator[tuple[str, list[Box], Group]]:
    """Strokes of every drawn node, one box each (its own texts left out: 'CTRL', 'M' are inside it)."""
    if not isinstance(item, Group):
        return
    if item.cls and "uw-node" in item.cls.split() and item.id:
        boxes = [b for i in _own(item) if not isinstance(i, Text) and not (isinstance(i, Rect) and i.style.dash)
                 for b in _stroke_boxes(i)]  # a board's dashed frame encloses its feeders: not its symbol
        if boxes:
            yield item.id, boxes, item
    for i in item.items:
        yield from _symbol_boxes(i)


def _stroke_boxes(item: object) -> list[Box]:
    """Boxes of the strokes of a drawn item: a segment, the four sides of a rectangle, a circle."""
    segs = _segments(item)
    if isinstance(item, Polyline) and item.closed and len(item.points) > 2:
        segs.append((item.points[-1], item.points[0]))
    if isinstance(item, Rect):
        x0, y0, x1, y1 = item.x, item.y, item.x + item.w, item.y + item.h
        segs = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    if isinstance(item, Circle):
        return [(item.c[0] - item.r, item.c[1] - item.r, item.c[0] + item.r, item.c[1] + item.r)]
    return [(min(p[0], q[0]) - 0.1, min(p[1], q[1]) - 0.1, max(p[0], q[0]) + 0.1, max(p[1], q[1]) + 0.1)
            for p, q in segs]


def _own(g: Group) -> Iterator[object]:
    """Items of a node group, without the nodes, links and edges nested in it (a board holds its feeders)."""
    for i in g.items:
        if isinstance(i, Group):
            if i.id or (i.cls and {"uw-node", "uw-link", "uw-edge"} & set(i.cls.split())):
                continue
            yield from _own(i)
        else:
            yield i


def _overlap(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _crosses(b: Box, s: Seg) -> bool:
    """Whether the axis-parallel segment ``s`` passes through the box ``b``."""
    (x0, y0), (x1, y1) = s
    return min(x0, x1) < b[2] and b[0] < max(x0, x1) and min(y0, y1) < b[3] and b[1] < max(y0, y1) \
        or (abs(x0 - x1) < 1e-6 and b[0] < x0 < b[2] and min(y0, y1) < b[3] and b[1] < max(y0, y1)) \
        or (abs(y0 - y1) < 1e-6 and b[1] < y0 < b[3] and min(x0, x1) < b[2] and b[0] < max(x0, x1))


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
    texts: list[tuple[Text, Box, Optional[str]]] = []
    links: dict[str, list[Seg]] = {}
    wires: list[Seg] = []
    frames: list[Seg] = []  # dashed outlines of boards, enclosures and view frames
    for item, link, _owner in _walk(root):
        if isinstance(item, Text) and item.text.strip():
            texts.append((item, text_box(item), link))
        elif isinstance(item, Rect) and item.style.dash:
            x0, y0, x1, y1 = item.x, item.y, item.x + item.w, item.y + item.h
            frames += [((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))]
        elif link is not None:
            links.setdefault(link, []).extend(_segments(item))
        elif isinstance(item, (Line, Polyline)):
            wires.extend(_segments(item))
    out: list[Finding] = []
    for i, (t, a, _l) in enumerate(texts):
        for u, b, _m in texts[i + 1:]:
            ov = _overlap(a, b)
            small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            w = min(a[2], b[2]) - max(a[0], b[0])
            h = min(a[3], b[3]) - max(a[1], b[1])
            # a large share of the smaller text, or one line run into another over a few letters
            if small > 0 and ov > 0.15 * small or w > 1.5 and h > 0.15:
                out.append(Finding("text_overlap", f"{t.text!r} / {u.text!r}", t.p))
    symbols = list(_symbol_boxes(root))
    own = {id(i) for _n, _b, g in symbols for i in _own(g) if isinstance(i, Text)}
    marks = {id(t) for t in _marks(root)}
    sizes = Counter(round(t.size, 2) for t, _b, _l in texts if id(t) not in own and id(t) not in marks)
    usual = sizes.most_common(1)[0][0] if sizes else 0.0
    for t, a, own_link in texts:
        if id(t) in own or id(t) in marks:
            continue
        dx, dy = 0.1 * (a[2] - a[0]), 0.15 * (a[3] - a[1])  # the box of a text is approximate: its core
        core = (a[0] + dx, a[1] + dy, a[2] - dx, a[3] - dy)
        crossing = next((la for la, segs in links.items() if la != own_link and any(_crosses(core, s) for s in segs)),
                        None)
        if crossing is not None:
            out.append(Finding("text_crossed", f"{t.text!r} crossed by link {crossing}", t.p))
        elif own_link is not None and any(_crosses(core, s) for s in wires):  # a link's text across a conductor
            out.append(Finding("text_on_conductor", f"{t.text!r} written across a conductor", t.p))
        for nid, boxes, _g in symbols:
            if t.text.strip() not in TERMINALS and any(_overlap(core, b) > 0 for b in boxes):
                out.append(Finding("text_on_symbol", f"{t.text!r} on the symbol of {nid}", t.p))
                break
        if t.color == "#000000" and t.size < SHRUNK * usual - 1e-6:
            out.append(Finding("small_text", f"{t.text!r} at {t.size:.2f} mm ({usual:.2f} usually)", t.p))
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
