"""Sheet generation (neutral scene -> SVG / PDF)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..i18n import normalize_lang
from ..i18n import t as _t
from ..layout.engine import layout_sheet, plan_sheets, sheet_node_ids
from ..model import Document, View
from ..resolve import build_index
from .colors import colorize
from .frame import compose_page
from .scene import Page
from .svg import page_to_svg


def default_view(doc: Document, view_id: Optional[str] = None, kind: Optional[str] = None) -> View:
    """View ``view_id``, else the first view of ``kind`` (any kind when ``None``), else a default view.

    When ``kind`` is given and the document declares no view of that kind, the first view (paper, title
    block...) is reused with that kind, so ``kind="multi-line"`` always gives a multi-line view."""
    if view_id:
        for v in doc.views:
            if v.id == view_id:
                return v if kind is None or v.kind == kind else v.model_copy(update={"kind": kind, "title": None})
        raise KeyError(_t("render.unknown_view", id=view_id))
    if kind is None:
        return doc.views[0] if doc.views else View()
    for v in doc.views:
        if v.kind == kind:
            return v
    base = doc.views[0] if doc.views else View()
    return base.model_copy(update={"kind": kind, "title": None, "id": "ml" if kind == "multi-line" else base.id})


def render_pages(doc: Document, view: Optional[View] = None) -> list[Page]:
    """Plan the sheets, lay them out and compose each page."""
    view = view or default_view(doc)
    lang = normalize_lang(doc.meta.lang)
    from ..i18n import RENDER_LANG
    token = RENDER_LANG.set(lang)
    try:
        pages = _render_pages(doc, view, lang)
    finally:
        RENDER_LANG.reset(token)
    for i, page in enumerate(pages, 1):
        page.attrs.update({"data-uw-sheet": str(i), "data-uw-view-kind": view.kind})
    return pages


def _render_pages(doc: Document, view: View, lang: str) -> list[Page]:
    if view.kind == "multi-line":
        return _render_multiline(doc, view, lang)
    index = build_index(doc)
    specs = plan_sheets(doc, view, index)
    folio_by_root: dict[str, int] = {}
    for i, s in enumerate(specs, 1):
        if s.roots and not s.continuation and i > 1:
            folio_by_root[s.roots[0].id or ""] = i
    folio_of_node: dict[str, int] = {}
    for i, s in enumerate(specs, 1):
        for nid in sheet_node_ids(doc, s, index):
            folio_of_node.setdefault(nid, i)
    pages = []
    total = len(specs)
    number = {id(s): i for i, s in enumerate(specs, 1)}
    for i, spec in enumerate(specs, 1):
        prev_f = number.get(id(spec.prev)) if spec.prev is not None else None
        next_f = number.get(id(spec.next)) if spec.next is not None else None
        incoming = None
        incoming_ref: tuple[Optional[int], Optional[str]] = (None, None)
        if i > 1 and spec.roots and not spec.continuation:
            rid = spec.roots[0].id
            src = next((j for j, s in enumerate(specs, 1) if rid in s.detached and j != i), None)
            incoming_ref = (src, index.parent.get(rid or ""))
            feeder = next((a for a in index.ancestors(rid or "") if a.ref), None)
            what = _t("render.incoming_from", lang, ref=feeder.ref) if feeder is not None else _t("render.incoming", lang)
            incoming = _t("render.incoming_folio", lang, what=what, folio=src) if src else what
        lay = layout_sheet(doc, view, spec, index, folio_of=folio_by_root.get, continuation_folios=(prev_f, next_f),
                           incoming=incoming, node_folio=folio_of_node.get, incoming_ref=incoming_ref)
        title = spec.name or view.title or _t("render.default_title", lang)
        legend = colorize(lay.group, doc, view, index)
        pages.append(compose_page(doc, view, lay, i, total, title, legend))
    return pages


def _render_multiline(doc: Document, view: View, lang: str) -> list[Page]:
    from ..layout.multiline import multiline_layouts

    index = build_index(doc)
    lays = multiline_layouts(doc, view, index)
    pages = []
    for i, lay in enumerate(lays, 1):
        title = lay.spec.name or view.title or _t("render.multiline_title", lang)
        if lay.spec.name:
            title = f"{_t('render.multiline_title', lang)} · {lay.spec.name}"
        legend = colorize(lay.group, doc, view, index, multiline=True)
        pages.append(compose_page(doc, view, lay, i, len(lays), title, legend))
    return pages


def render_svg(doc: Document, out_dir: str | Path, stem: str = "sld", view: Optional[View] = None) -> list[Path]:
    """Render the sheets of ``view`` (default: :func:`default_view`) as SVG files in ``out_dir``.

    One sheet is written as ``<stem>.svg``, several as ``<stem>-f1.svg``, ``<stem>-f2.svg``... Returns the paths.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = render_pages(doc, view)
    paths = []
    for i, page in enumerate(pages, 1):
        p = out_dir / (f"{stem}.svg" if len(pages) == 1 else f"{stem}-f{i}.svg")
        p.write_text(page_to_svg(page), "utf-8")
        paths.append(p)
    return paths


def render_pdf(doc: Document, path: str | Path, view: Optional[View] = None) -> Path:
    """Render the sheets of ``view`` into one PDF at ``path`` (one page per sheet, bookmarks and clickable
    cross-sheet references). Needs the ``pdf`` extra (reportlab). Returns the path."""
    from .pdf import write_pdf

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_pdf(render_pages(doc, view), path, normalize_lang(doc.meta.lang), doc.meta.title)
    return path
