"""Semantic metadata of the drawing: the groups behind the SVG structure contract (docs/api.md, "SVG structure").

The layout engines wrap what they draw in groups carrying a class and ``data-uw-*`` attributes (node symbols,
tree edges, busbars, out-of-tree links, conductors, cross-sheet references, feeder-table columns). The SVG
writer emits them as attributes, the PDF writer turns the references into internal links and the colour
modes (``render.colors``) use them to know what each stroke belongs to.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from .scene import Group, Item, Line, Polyline, Style

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
