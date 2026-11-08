"""Sheet generation (neutral scene -> SVG / PDF)."""

from __future__ import annotations

import copy
import hashlib
import re
from collections import OrderedDict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Optional

from ..i18n import normalize_lang
from ..i18n import t as _t
from ..layout.engine import PAPER, drawing_area, feeding_sheet, layout_sheet, plan_sheets, sheet_node_ids
from ..model import Document, View
from ..resolve import build_index
from ..symbols import ACTIVE_SET, known_set
from .colors import colorize
from .frame import compose_page
from .scene import Group, Item, Page, Text
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


_PAGES: OrderedDict[str, list[Page]] = OrderedDict()  # recent layouts: the same document is often drawn
_PAGES_MAX = 16                                        # several times in a row (check, render, then its PDF)


def render_pages(doc: Document, view: Optional[View] = None) -> list[Page]:
    """Plan the sheets, lay them out and compose each page."""
    view = view or default_view(doc)
    pages = _view_pages(doc, view)
    number_sheets(pages, [(view, len(pages))])
    return pages


_LANG_TAG = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*")


def _lang_tag(lang: Optional[str]) -> str:
    """``meta.lang`` as a language tag for ``lang`` / ``xml:lang`` (``en_GB`` -> ``en-GB``); text that is not a tag
    ("Français") gives the language uniwire draws in."""
    tag = (lang or "").strip().replace("_", "-")
    return tag if _LANG_TAG.fullmatch(tag) else normalize_lang(lang)


def _view_pages(doc: Document, view: View) -> list[Page]:
    """Sheets of one view, numbered 1..n in their title blocks and cross-sheet references (see number_sheets)."""
    lang = normalize_lang(doc.meta.lang)
    try:
        key: Optional[str] = hashlib.sha256((doc.model_dump_json() + "\0" + view.model_dump_json() + "\0" + lang)
                                            .encode()).hexdigest()
    except ValueError:  # text that cannot be encoded (lone surrogates): drawn, not cached
        key = None
    if key in _PAGES:
        _PAGES.move_to_end(key)
        return copy.deepcopy(_PAGES[key])
    from ..i18n import RENDER_LANG
    from ..labels import INTERLOCK_KINDS, NORTH_AMERICAN, north_american
    token, na_token = RENDER_LANG.set(lang), NORTH_AMERICAN.set(north_american(doc))
    ik_token = INTERLOCK_KINDS.set({i.key: i.kind for i in doc.interlocks if i.kind})
    set_token = ACTIVE_SET.set(known_set(doc.symbols))
    try:
        pages = _render_pages(doc, view, lang)
    finally:
        RENDER_LANG.reset(token)
        NORTH_AMERICAN.reset(na_token)
        INTERLOCK_KINDS.reset(ik_token)
        ACTIVE_SET.reset(set_token)
    tag = _lang_tag(doc.meta.lang)  # the language of the texts: a browser picks the glyph forms (Japanese, Chinese) by it
    for i, page in enumerate(pages, 1):
        page.attrs.update({"lang": tag, "xml:lang": tag, "data-uw-sheet": str(i), "data-uw-view-kind": view.kind})
    if key is not None:
        _PAGES[key] = copy.deepcopy(pages)
    while len(_PAGES) > _PAGES_MAX:
        _PAGES.popitem(last=False)
    return pages


def render_views(doc: Document, views: Optional[Iterable[View]] = None) -> list[Page]:
    """Sheets of several views, one view after the other (default: every view of the document, or the default view
    when it declares none): a drawing set such as the multi-line power diagram then the single-line diagram with the
    auxiliary devices and links. The cross-sheet references of each view keep pointing at its own sheets."""
    views = list(views) if views is not None else (list(doc.views) or [default_view(doc)])
    out: list[Page] = []
    counts: list[tuple[View, int]] = []
    for v in views:
        pages = _view_pages(doc, v)
        if out:
            for page in pages:
                _shift_refs(page.root, len(out))
        out += pages
        counts.append((v, len(pages)))
    for i, page in enumerate(out, 1):
        page.attrs["data-uw-sheet"] = str(i)
    number_sheets(out, counts)
    return out


def sheet_numbers(views: list[tuple[View, int]]) -> tuple[list[int], Optional[int]]:
    """Printed number of each sheet of one drawing set (its views in order, with their number of sheets), and the
    total to print after it. A view numbered from its ``first_folio`` (when given), else following the view
    before it (from 1 for the first). A view whose sheets would take numbers already given follows the highest one
    (two sheets with one number make every "-> sheet n" ambiguous; ``core.folio-duplicate``). The total is the
    ``total_folios`` given (the largest, never less than the last sheet: '7 / 6' would be false), else the last
    sheet when the set starts at 1, else none ('3', not '3 / 4', for a partial set)."""
    numbers = [k for nums in _view_numbers(views)[0] for k in nums]
    given = [v.total_folios for v, _ in views if v.total_folios]
    last = max(numbers, default=0)
    total = max(given + [last]) if given else (last if numbers and numbers[0] == 1 else None)
    return numbers, total


def _view_numbers(views: list[tuple[View, int]]) -> tuple[list[list[int]], list[tuple[int, int, int, int]]]:
    """Printed numbers of the sheets of each view (see :func:`sheet_numbers`), and the views renumbered because
    their sheets would take numbers already given: (view, its wanted first sheet, the earlier view holding one of
    those numbers, its first sheet as printed), views by position."""
    per_view: list[list[int]] = []
    moved: list[tuple[int, int, int, int]] = []
    numbers: list[int] = []
    for i, (v, n) in enumerate(views):
        start = v.first_folio if "first_folio" in v.model_fields_set or not numbers else numbers[-1] + 1
        wanted = set(range(start, start + n))
        if wanted & set(numbers):
            other = next(j for j, nums in enumerate(per_view) if wanted & set(nums))
            moved.append((i, start, other, max(numbers) + 1))
            start = max(numbers) + 1
        per_view.append(list(range(start, start + n)))
        numbers += per_view[-1]
    return per_view, moved


def renumbered_views(doc: Document) -> list[tuple[int, int, int, int]]:
    """Views of ``doc`` whose sheets would take numbers already given to the views before them, so are numbered
    after them (``core.folio-overlap``): (view, wanted first sheet, earlier view, printed first sheet), views by
    their position in ``doc.views``. It needs the number of sheets of each view, so lays them out (kept for the
    drawing that usually follows); only done when a view after the first gives its own ``first_folio``, the one
    case where numbers can clash."""
    views = list(doc.views)
    if not any("first_folio" in v.model_fields_set for v in views[1:]):
        return []
    counts = [(v, len(_view_pages(doc, v))) for v in views]
    return _view_numbers(counts)[1]


def number_sheets(pages: list[Page], views: list[tuple[View, int]]) -> None:
    """Write the printed sheet numbers (:func:`sheet_numbers`) in the title blocks and in the text of the
    cross-sheet references, which until then give the position of the sheet; the links keep the position."""
    numbers, total = sheet_numbers(views)
    for page, number in zip(pages, numbers):
        page.attrs["data-uw-folio"] = str(number)
        _renumber(page.root, number, total)
        _print_refs(page.root, numbers)


def _renumber(item: Item, folio: int, total: Optional[int]) -> None:
    """Write ``folio / total`` in the sheet cell of a title block (the last text of its ``tb-sheet`` group)."""
    if isinstance(item, Group):
        if item.cls == "tb-sheet":
            texts = [t for t in item.items if isinstance(t, Text)]
            if texts:
                texts[-1].text = f"{folio} / {total}" if total else str(folio)
            return
        for c in item.items:
            _renumber(c, folio, total)


def _last_number(text: str, old: int, new: int) -> str:
    """``text`` with its last occurrence of the number ``old`` replaced by ``new``."""
    return re.sub(rf"(?<!\d){old}(?!\d)(?!.*(?<!\d){old}(?!\d))", str(new), text)


def _ref_text(group: Group, change: Callable[[str], str]) -> None:
    """Change the text of a cross-sheet reference that carries the sheet number: its last text (a link's label,
    written before it, keeps its own figures)."""
    texts = [t for t in group.items if isinstance(t, Text)]
    if texts:
        texts[-1].text = change(texts[-1].text)


def _print_refs(item: Item, numbers: list[int]) -> None:
    if isinstance(item, Group):
        target = item.attrs.get("data-uw-target-sheet", "")
        if target.isdigit() and 1 <= int(target) <= len(numbers) and numbers[int(target) - 1] != int(target):
            _ref_text(item, lambda s: _last_number(s, int(target), numbers[int(target) - 1]))
        for c in item.items:
            _print_refs(c, numbers)


def _shift_refs(item: Item, offset: int) -> None:
    """Add ``offset`` to the target sheet of the cross-sheet references under ``item``, in their link and in the
    sheet number written in their text ('=RA → sheet 2', 'from -P3 (sheet 1)')."""
    if isinstance(item, Group):
        target = item.attrs.get("data-uw-target-sheet", "")
        if target.isdigit():
            item.attrs["data-uw-target-sheet"] = str(int(target) + offset)
            _ref_text(item, lambda s: _last_number(s, int(target), int(target) + offset))
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
        if i > 1 and spec.roots and not spec.continuation and index.parent.get(spec.roots[0].id or ""):
            rid = spec.roots[0].id  # a board drawn on its own sheet (not a group of trees): fed from another one
            src = feeding_sheet(specs, i, rid, index, folio_of_node)
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


def render_pdf(doc: Document, path: str | Path, view: Optional[View] = None, all_views: bool = False,
               about: Optional[Any] = None) -> Path:
    """Render the sheets of ``view`` into one PDF at ``path`` (one page per sheet, bookmarks and clickable
    cross-sheet references); with ``all_views``, the sheets of every view of the document (:func:`render_views`).
    ``about`` (:class:`~uniwire.render.about.About`): add the page "About this document" after the sheets.
    Needs the ``pdf`` extra (reportlab). Returns the path."""
    from .pdf import write_pdf

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pages = render_views(doc) if all_views else render_pages(doc, view)
    if about is not None:
        pages = with_about(doc, pages, about)
    write_pdf(pages, path, normalize_lang(doc.meta.lang), doc.meta.title)
    return path


def with_about(doc: Document, pages: list[Page], about: Any) -> list[Page]:
    """``pages`` followed by the page "About this document", at the size of the first sheet."""
    from .about import about_page

    w, h = (pages[0].width, pages[0].height) if pages else PAPER["A4"]
    return [*pages, about_page(doc, w, h, [p.title for p in pages], about)]
