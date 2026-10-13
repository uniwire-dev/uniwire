"""Sheet showing every symbol (documentation / visual check)."""

from __future__ import annotations

from .. import registry
from ..i18n import current_lang
from ..i18n import t as _t
from ..render.scene import THIN, Group, Page, Rect, Style, Text
from . import SYMBOLS


def symbol_sheet(cols: int = 8, cell_w: float = 34.0, cell_h: float = 34.0) -> Page:
    names = list(SYMBOLS)
    rows = (len(names) + cols - 1) // cols
    page = Page(cols * cell_w + 10, rows * cell_h + 18, Group(cls="symbol-sheet"), title=_t("symbols.page_title"))
    page.root.add(Text((5, 9), _t("symbols.heading"), 4.0, bold=True))
    for i, name in enumerate(names):
        r, c = divmod(i, cols)
        x0, y0 = 5 + c * cell_w, 14 + r * cell_h
        page.root.add(Rect(x0, y0, cell_w, cell_h, Style(width=THIN, color="#999999")))
        sym = SYMBOLS[name](None)
        page.root.add(sym.group(x0 + cell_w / 2, y0 + 4 + max(0.0, (cell_h - 12 - sym.height) / 2), name))
        page.root.add(Text((x0 + cell_w / 2, y0 + cell_h - 6), name, 2.2, "middle", bold=True))
        page.root.add(Text((x0 + cell_w / 2, y0 + cell_h - 2.5), registry.label(name, current_lang()), 1.8, "middle", color="#444444"))
    return page
