"""SVG writer (plain XML, no dependencies). Units: mm."""

from __future__ import annotations

import re
from xml.sax import saxutils

from .scene import Circle, Ellipse, Group, Item, Line, Page, Path, Polyline, Rect, Style, Text

FONT = "Arial, Helvetica, 'Liberation Sans', sans-serif"

_SHAPES = ("line", "polyline", "polygon", "circle", "ellipse", "rect")
_HOVER = ", ".join(
    [f"{sel} {shape}" for sel in (".uw-node:hover", ".uw-edge:hover", ".uw-busbar:hover") for shape in _SHAPES]
    + [f".uw-link:hover > {shape}, .uw-link:hover > :not(.uw-hit) {shape}" for shape in _SHAPES])
# Hover highlight when the SVG is opened on its own (screen only: printing is unchanged); the web viewer
# adds its own interactions on top of the same classes (docs/api.md, "SVG structure").
STYLE = ("@media screen { " + _HOVER + " { stroke: #e8590c; } "
         ".uw-hit { pointer-events: stroke; } .uw-node, .uw-edge, .uw-busbar, .uw-link, .uw-ref { cursor: default; } }")


# Characters that XML 1.0 forbids (C0 controls other than tab / newline / carriage return, lone surrogates,
# U+FFFE / U+FFFF): replaced by U+FFFD so that any document text gives a well-formed SVG.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def xml_safe(text: str) -> str:
    """``text`` with the characters XML (and UTF-8 output) cannot carry replaced by U+FFFD."""
    return _XML_ILLEGAL.sub("\ufffd", text)


def escape(text: str) -> str:
    return saxutils.escape(xml_safe(text))


def quoteattr(text: str) -> str:
    return saxutils.quoteattr(xml_safe(str(text)))


def _n(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def _style(s: Style, fill_default: str = "none") -> str:
    out = f'stroke={quoteattr(s.color)} stroke-width="{_n(s.width)}" fill={quoteattr(s.fill or fill_default)}'
    if s.dash:
        out += f' stroke-dasharray="{" ".join(_n(d) for d in s.dash)}"'
    return out


def _item(it: Item, out: list[str], indent: str) -> None:
    if isinstance(it, Group):
        attrs = ""
        if it.id:
            attrs += f" data-uw-id={quoteattr(it.id)}"
        if it.cls:
            attrs += f" class={quoteattr(it.cls)}"
        for k, v in it.attrs.items():
            attrs += f" {k}={quoteattr(v)}"
        href = it.attrs.get("data-uw-href") if it.cls == "uw-href" else None
        if href:
            out.append(f"{indent}<a href={quoteattr(href)}>")
        out.append(f"{indent}<g{attrs}>")
        for c in it.items:
            _item(c, out, indent + " ")
        out.append(f"{indent}</g>")
        if href:
            out.append(f"{indent}</a>")
    elif isinstance(it, Line):
        out.append(f'{indent}<line x1="{_n(it.a[0])}" y1="{_n(it.a[1])}" x2="{_n(it.b[0])}" y2="{_n(it.b[1])}" '
                   f'{_style(it.style)} stroke-linecap="round"/>')
    elif isinstance(it, Polyline):
        pts = " ".join(f"{_n(x)},{_n(y)}" for x, y in it.points)
        tag = "polygon" if it.closed else "polyline"
        out.append(f'{indent}<{tag} points="{pts}" {_style(it.style)} stroke-linejoin="round"/>')
    elif isinstance(it, Circle):
        out.append(f'{indent}<circle cx="{_n(it.c[0])}" cy="{_n(it.c[1])}" r="{_n(it.r)}" {_style(it.style)}/>')
    elif isinstance(it, Ellipse):
        out.append(f'{indent}<ellipse cx="{_n(it.c[0])}" cy="{_n(it.c[1])}" rx="{_n(it.rx)}" ry="{_n(it.ry)}" '
                   f'{_style(it.style)}/>')
    elif isinstance(it, Rect):
        out.append(f'{indent}<rect x="{_n(it.x)}" y="{_n(it.y)}" width="{_n(it.w)}" height="{_n(it.h)}" '
                   f'{_style(it.style)}/>')
    elif isinstance(it, Path):
        d = " ".join(seg[0] + " ".join(_n(v) for v in seg[1:]) for seg in it.segments)
        out.append(f'{indent}<path d="{d}" fill={quoteattr(it.fill)}/>')
    elif isinstance(it, Text):
        base = {"middle": "central", "hanging": "hanging"}.get(it.baseline, "auto")
        tr = f' transform="rotate({_n(-it.rotate)} {_n(it.p[0])} {_n(it.p[1])})"' if it.rotate else ""
        weight = ' font-weight="bold"' if it.bold else ""
        out.append(f'{indent}<text x="{_n(it.p[0])}" y="{_n(it.p[1])}" font-size="{_n(it.size)}" '
                   f'text-anchor={quoteattr(it.anchor)} dominant-baseline="{base}" fill={quoteattr(it.color)}{weight}{tr}>'
                   f"{escape(it.text)}</text>")


def page_to_svg(page: Page) -> str:
    meta = "".join(f" {k}={quoteattr(v)}" for k, v in page.attrs.items())
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(page.width)}mm" height="{_n(page.height)}mm" '
        f'viewBox="0 0 {_n(page.width)} {_n(page.height)}" font-family="{FONT}"{meta}>',
        f"<title>{escape(page.title)}</title>",
        f"<style>{STYLE}</style>",
        f'<rect x="0" y="0" width="{_n(page.width)}" height="{_n(page.height)}" fill="#ffffff"/>',
    ]
    _item(page.root, out, "")
    out.append("</svg>")
    return "\n".join(out) + "\n"
