"""Sheet generation (neutral scene -> SVG / PDF)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

from ..i18n import normalize_lang
from ..i18n import t as _t
from ..layout.engine import drawing_area, layout_sheet, plan_sheets, sheet_node_ids
from ..model import Document, View
from ..resolve import build_index
from .colors import colorize
from .frame import compose_page
from .scene import Group, Item, Page
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


def render_views(doc: Document, views: Optional[Iterable[View]] = None) -> list[Page]:
    """Sheets of several views, one view after the other (default: every view of the document, or the default view
    when it declares none): a drawing set such as the multi-line power diagram then the single-line diagram with the
    auxiliary devices and links. The cross-sheet references of each view keep pointing at its own sheets."""
    views = list(views) if views is not None else (list(doc.views) or [default_view(doc)])
    out: list[Page] = []
    for v in views:
        pages = render_pages(doc, v)
        if out:
            for page in pages:
                _shift_refs(page.root, len(out))
        out += pages
    return out


def _shift_refs(item: Item, offset: int) -> None:
    """Add ``offset`` to the target sheet of the cross-sheet references under ``item``."""
    if isinstance(item, Group):
        target = item.attrs.get("data-uw-target-sheet", "")
        if target.isdigit():
            item.attrs["data-uw-target-sheet"] = str(int(target) + offset)
        for c in item.items:
            _shift_refs(c, offset)


#: Largest enlargement of a drawing that leaves most of its sheet empty (annotations 2 mm -> 2.5 mm).
MAX_ENLARGE = 1.25
#: Largest enlargement of a multi-line diagram (its symbols are smaller).
ML_MAX_ENLARGE = 1.4


def _room(lay: Any, view: View) -> float:
    """How much the drawing could grow on its sheet (>1: room left, <1: it must be reduced)."""
    _, _, aw, ah = drawing_area(view)
    return min(aw / max(lay.width, 1e-6), ah / max(lay.height, 1e-6))


def _enlargement(lays: list[Any], view: View, cap: float) -> Optional[float]:
    """One enlargement for all the sheets of a view (the text keeps the same size from sheet to sheet), when every
    sheet has room for it; None otherwise (each sheet is then reduced as needed, never enlarged)."""
    rooms = [_room(lay, view) for lay in lays]
    k = min(rooms, default=1.0)
    return min(cap, k) if k > 1.0 else None


def _render_pages(doc: Document, view: View, lang: str) -> list[Page]:
    if view.kind == "multi-line":
        return _render_multiline(doc, view, lang)
    if "paper" not in view.model_fields_set:
        # no paper in the document: the smallest sheet that holds the drawing at full size (A4 landscape), else A3
        small = view.model_copy(update={"paper": "A4"})
        index = build_index(doc)
        if len(plan_sheets(doc, small, index)) == len(plan_sheets(doc, view, index)):
            pages, lays = _render_sheets(doc, small, lang)
            if all(_room(lay, small) >= 0.999 for lay in lays):
                return pages
    return _render_sheets(doc, view, lang)[0]


def _render_sheets(doc: Document, view: View, lang: str) -> tuple[list[Page], list[Any]]:
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
    built = []
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
        built.append((lay, title, legend))
    grow = _enlargement([b[0] for b in built], view, MAX_ENLARGE)
    pages = [compose_page(doc, view, lay, i, total, title, legend, scale=grow)
             for i, (lay, title, legend) in enumerate(built, 1)]
    return pages, [b[0] for b in built]


def _render_multiline(doc: Document, view: View, lang: str) -> list[Page]:
    from ..layout.multiline import multiline_layouts

    index = build_index(doc)
    lays = multiline_layouts(doc, view, index)
    pages = []
    grow = _enlargement(lays, view, ML_MAX_ENLARGE)
    for i, lay in enumerate(lays, 1):
        title = lay.spec.name or view.title or _t("render.multiline_title", lang)
        if lay.spec.name:
            title = f"{_t('render.multiline_title', lang)} · {lay.spec.name}"
        legend = colorize(lay.group, doc, view, index, multiline=True)
        pages.append(compose_page(doc, view, lay, i, len(lays), title, legend, scale=grow))
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


def render_pdf(doc: Document, path: str | Path, view: Optional[View] = None, all_views: bool = False) -> Path:
    """Render the sheets of ``view`` into one PDF at ``path`` (one page per sheet, bookmarks and clickable
    cross-sheet references); with ``all_views``, the sheets of every view of the document (:func:`render_views`).
    Needs the ``pdf`` extra (reportlab). Returns the path."""
    from .pdf import write_pdf

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pages = render_views(doc) if all_views else render_pages(doc, view)
    write_pdf(pages, path, normalize_lang(doc.meta.lang), doc.meta.title)
    return path
