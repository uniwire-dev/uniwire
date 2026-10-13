"""Tool functions behind the MCP server, usable directly from Python (no MCP dependency).

Every ``document`` argument accepts a JSON object (dict), a JSON string or a path to a
``*.uniwire.json`` file. Results are JSON-serialisable.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import sys
import tempfile
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ..model import Document
from ..resolve import UniwireError, check_depth, iter_nodes, load
from . import card as _card_fn  # noqa: F401  (ensures the submodule is loaded)
from .describe import describe as _describe
from .link import MAX_LINK_CHARS
from .link import viewer_link as _viewer_link
from .patch import PatchError, as_dict, explain_issue, patch

_card = sys.modules["uniwire.llm.card"]  # the package re-exports the card() function under the same name


class ToolError(ValueError):
    """Error reported to the caller (MCP clients see it as a failed tool call)."""


#: Public (hosted) mode: no file system access, bounded inputs and outputs. Set by ``uniwire-mcp --public``.
#: The limits below apply only in public mode (docs/llm.md, "Public server"); local use is unlimited.
PUBLIC = os.environ.get("UNIWIRE_MCP_PUBLIC") == "1"
MAX_DOCUMENT_CHARS = 2_000_000  # document (and patched document) as JSON text
MAX_NODES = 1500  # nodes after template resolution, auxiliary and link devices included
MAX_SHEETS = 40  # sheets of one rendering
MAX_OUTPUT_BYTES = 20_000_000  # SVG characters (all sheets) or PDF bytes of one rendering
MAX_PATCH_OPS = 500  # operations of one apply_patch call

#: What a rule check covers, returned with every check result so that assistants report it with the findings.
CHECK_SCOPE = ("Automatic checks of the rules of the listed profiles, on the data in the document only. Not a "
               "conformity certificate: a qualified electrician must verify the installation (design, installation "
               "conditions, earthing, short-circuit currents, equipment data) before it is built.")


def _scope(doc: Document, profiles: list[str]) -> str:
    """What the checks covered: :data:`CHECK_SCOPE`, plus which NF C 15-100 rules apply to the premises."""
    if "nfc15100" not in profiles:
        return CHECK_SCOPE
    premises = doc.installation.premises
    if premises in (None, "dwelling"):
        extra = ("NF C 15-100: the rules of dwellings (part 7-771) were applied"
                 + (" (installation.premises not set: set it for other premises)." if premises is None else "."))
    else:
        extra = (f"NF C 15-100, premises '{premises}': only the general rules were applied (30 mA protection of "
                 "socket-outlets, EV charging, selectivity, cable table as a reminder); the rules of dwellings (part "
                 "7-771) do not apply. Not checked: fire safety of premises open to the public (ERP), safety "
                 "lighting, workplace rules.")
    return f"{CHECK_SCOPE} {extra}"


def _count_raw_nodes(raw: dict[str, Any]) -> int:
    """Nodes of a raw document (templates add no children, so this is also the resolved count)."""
    stack: list[Any] = [*(raw.get("sources") or []), *(raw.get("devices") or []),
                        *(lk.get("device") for lk in (raw.get("links") or []) if isinstance(lk, dict))]
    n = 0
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            n += 1
            children = node.get("children")
            if isinstance(children, list):
                stack.extend(children)
    return n


def _check_size(n_nodes: int) -> None:
    if PUBLIC and n_nodes > MAX_NODES:
        raise ToolError(f"document too large for this server: {n_nodes} nodes (at most {MAX_NODES})")


def _raw(document: Any) -> dict[str, Any]:
    if PUBLIC:
        if isinstance(document, (str, bytes)) and not str(document).lstrip().startswith("{"):
            raise ToolError("file paths are disabled on this server: pass the document itself (JSON object or text)")
        if not isinstance(document, (str, bytes, dict)):
            raise ToolError("pass the document as a JSON object or JSON text")
        if len(document if isinstance(document, (str, bytes)) else json.dumps(document)) > MAX_DOCUMENT_CHARS:
            raise ToolError("document too large for this server")
    try:
        raw = as_dict(document)
    except FileNotFoundError as e:
        raise ToolError(f"file not found: {e.filename}") from None
    except json.JSONDecodeError as e:
        raise ToolError(f"invalid JSON: {e}") from None
    except RecursionError:
        raise ToolError("invalid document: nested too deeply") from None
    except TypeError as e:
        raise ToolError(str(e)) from None
    if not isinstance(raw, dict):
        raise ToolError("the document must be a JSON object")
    try:
        check_depth(raw)
    except UniwireError as e:
        raise ToolError("invalid document: " + "; ".join(e.issues)) from None
    if PUBLIC:
        _check_size(_count_raw_nodes(raw))
    return raw


def _load(raw: dict[str, Any]) -> Document:
    """Resolved document; in public mode, refused beyond :data:`MAX_NODES` nodes."""
    doc = load(copy.deepcopy(raw))
    if PUBLIC:
        _check_size(sum(1 for _ in iter_nodes(doc)))
    return doc


def _issues(raw: dict[str, Any], err: UniwireError) -> list[str]:
    return [explain_issue(raw, i) for i in err.issues]


def _doc(document: Any) -> Document:
    if isinstance(document, Document):
        return document
    raw = _raw(document)
    try:
        return _load(raw)
    except UniwireError as e:
        raise ToolError("invalid document:\n" + "\n".join(f"- {i}" for i in _issues(raw, e))) from None


def _link(raw: dict[str, Any]) -> dict[str, str]:
    """``{"viewer_url", "pdf_url"}`` for a raw document, empty when the links would be too long to pass around.
    ``pdf_url`` opens the same editor page and downloads the PDF drawn by the library (on the hosted server, a
    plain PDF link instead: see :func:`uniwire.mcp_server._shorten`)."""
    url = _viewer_link(raw)
    return {"viewer_url": url, "pdf_url": url + "&download=pdf"} if len(url) <= MAX_LINK_CHARS else {}


def viewer_link(document: Any) -> dict[str, Any]:
    """Links that open the document in the web editor: ``{viewer_url, pdf_url}`` (or ``{error}`` when too long)."""
    links = _link(_raw(document))
    return links or {"error": f"document too large for a link (at most {MAX_LINK_CHARS} characters)"}


# ------------------------------------------------------------------ reference


def get_reference_card(level: str = "compact", lang: str = "en") -> str:
    """The reference card of the format (``level`` ``compact`` or ``full``) in ``lang``."""
    if level not in ("compact", "full"):
        raise ToolError("level must be 'compact' or 'full'")
    return _card.card(lang, level)  # type: ignore[arg-type]


def list_types(category: Optional[str] = None, lang: str = "en") -> list[dict[str, str]]:
    """Node types with their category and label, optionally limited to one ``category``."""
    out = _card.list_types(category, lang)
    if category and not out:
        raise ToolError(f"unknown category {category!r}; known: {', '.join(_card.types_by_category())}")
    return out


def type_info(type: str, lang: str = "en") -> dict[str, Any]:  # noqa: A002 (MCP argument name)
    """Fields, enumerations and description of one node type (see :func:`uniwire.llm.card.type_info`)."""
    try:
        return _card.type_info(type, lang)
    except KeyError:
        raise ToolError(f"unknown node type {type!r}; see list_types") from None


def schema() -> dict[str, Any]:
    """The JSON Schema of the format."""
    from ..schema import json_schema

    return json_schema()


# ------------------------------------------------------------------ checking


def validate(document: Any) -> dict[str, Any]:
    """Validate a document (dict, JSON text or, outside public mode, a path): ``{valid, issues, nodes}``."""
    raw = _raw(document)
    try:
        doc = _load(raw)
    except UniwireError as e:
        return {"valid": False, "issues": _issues(raw, e), **_link(raw)}
    return {"valid": True, "issues": [], "nodes": sum(1 for _ in iter_nodes(doc)), **_link(raw)}


def check(document: Any, profiles: Optional[list[str]] = None) -> dict[str, Any]:
    """Validate then run the rules: ``{valid, profiles, summary, findings}`` (findings as dicts)."""
    from ..rules import check as _check

    raw = _raw(document)
    try:
        doc = _load(raw)
    except UniwireError as e:
        return {"valid": False, "issues": _issues(raw, e), "findings": [], "summary": {}, **_link(raw)}
    findings = _check(doc, profiles)
    summary = {lv: sum(1 for f in findings if f.level == lv) for lv in ("error", "warning", "info")}
    return {
        "valid": True,
        "profiles": ["core", *(profiles if profiles is not None else doc.profiles)],
        "scope": _scope(doc, profiles if profiles is not None else doc.profiles),
        "summary": summary,
        "findings": [{"level": f.level, "rule": f.rule, "node": f.node, "message": f.message, "source": f.source}
                     for f in findings],
        **_link(raw),
    }


def describe(document: Any, lang: str = "en") -> str:
    """Text outline of a document with stable ids (see :func:`uniwire.llm.describe`)."""
    return _describe(_doc(document), lang)


def normalize(document: Any) -> dict[str, Any]:
    """The resolved document as JSON data (templates applied, ids assigned)."""
    return _doc(document).model_dump(mode="json", by_alias=True, exclude_none=True)


def apply_patch(document: Any, ops: Any, validate: bool = True) -> dict[str, Any]:  # noqa: A002
    """Apply id-based edit operations: ``{ok: True, document}`` or ``{ok: False, errors}``."""
    raw = _raw(document)
    if isinstance(ops, str):
        try:
            ops = json.loads(ops)
        except json.JSONDecodeError as e:
            raise ToolError(f"ops: invalid JSON: {e}") from None
        except RecursionError:
            raise ToolError("ops: nested too deeply") from None
    try:
        check_depth(ops)
    except UniwireError as e:
        raise ToolError("ops: " + "; ".join(e.issues)) from None
    if PUBLIC:
        listed = (ops.get("ops", [ops]) if "op" not in ops else [ops]) if isinstance(ops, dict) else ops  # as patch()
        n_ops = len(listed) if isinstance(listed, list) else 1
        if n_ops > MAX_PATCH_OPS:
            raise ToolError(f"too many operations for this server: {n_ops} (at most {MAX_PATCH_OPS} per call)")
    try:
        out = patch(raw, ops, validate=validate)
    except PatchError as e:
        return {"ok": False, "errors": e.errors}
    if PUBLIC:
        if len(json.dumps(out, ensure_ascii=False)) > MAX_DOCUMENT_CHARS:
            raise ToolError(f"patched document too large for this server (at most {MAX_DOCUMENT_CHARS} characters)")
        _check_size(_count_raw_nodes(out))
    return {"ok": True, "document": out, **_link(out)}


def bom(document: Any) -> list[dict[str, Any]]:
    """Bill of materials rows of a document (see :func:`uniwire.bom.bom`)."""
    from ..bom import bom as _bom

    return _bom(_doc(document))


# ------------------------------------------------------------------ rendering


def _with_colors(v: Any, color: Optional[str], conductor_colors: Optional[str]) -> Any:
    """``v`` with the colour options overridden (validated by the View model)."""
    if color is None and conductor_colors is None:
        return v
    from pydantic import ValidationError

    data = v.model_dump(by_alias=True, exclude_none=True)
    if color is not None:
        data["color"] = color
    if conductor_colors is not None:
        data["conductor_colors"] = conductor_colors
    try:
        return type(v).model_validate(data)
    except ValidationError as e:
        raise ToolError("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from None


def render(document: Any, kind: str = "single-line", format: str = "svg",  # noqa: A002
           sheet: Optional[int] = None, view: Optional[str] = None, path: Optional[str] = None,
           color: Optional[str] = None, conductor_colors: Optional[str] = None) -> dict[str, Any]:
    """Render the sheets. ``svg``: SVG texts (all sheets, or ``sheet`` numbered from 1).
    ``pdf``: written to ``path`` when given, else returned as base64; in public mode, ``pdf_url`` only (no files,
    and chat apps cannot hand base64 to the user). ``color`` / ``conductor_colors`` override the view's colour
    mode. Every result also carries ``viewer_url`` and ``pdf_url`` (see :func:`viewer_link`)."""
    from ..render import default_view, render_pages
    from ..render.svg import page_to_svg

    if kind not in ("single-line", "multi-line"):
        raise ToolError("kind must be 'single-line' or 'multi-line'")
    if isinstance(document, Document):
        doc, link = document, {}
    else:
        raw = _raw(document)
        try:
            doc = _load(raw)
        except UniwireError as e:
            raise ToolError("invalid document:\n" + "\n".join(f"- {i}" for i in _issues(raw, e))) from None
        link = _link(raw)
    try:
        v = default_view(doc, view, kind)
    except KeyError as e:
        raise ToolError(str(e.args[0])) from None
    v = _with_colors(v, color, conductor_colors)
    if format not in ("svg", "pdf"):
        raise ToolError("format must be 'svg' or 'pdf'")
    if format == "pdf" and PUBLIC:
        # no files on this server, and chat apps cannot hand base64 to the user: the PDF comes from the link
        if not link:
            raise ToolError(f"document too large for a link (at most {MAX_LINK_CHARS} characters)")
        return {**link, "note": "Give the user pdf_url as a clickable link: it opens the PDF drawn by uniwire "
                                "(viewer_url opens the drawing in the uniwire web editor)."}
    pages = render_pages(doc, v)
    if PUBLIC and len(pages) > MAX_SHEETS:
        raise ToolError(f"too many sheets for this server: {len(pages)} (at most {MAX_SHEETS})")
    too_big = f"output too large for this server (at most {MAX_OUTPUT_BYTES} bytes per rendering)"
    if format == "svg":
        if sheet is not None:
            if not 1 <= sheet <= len(pages):
                raise ToolError(f"sheet must be between 1 and {len(pages)}")
            svg = page_to_svg(pages[sheet - 1])
            if PUBLIC and len(svg) > MAX_OUTPUT_BYTES:
                raise ToolError(too_big)
            return {"sheets": len(pages), "sheet": sheet, "svg": svg, **link}
        svgs = []
        for p in pages:
            svgs.append(page_to_svg(p))
            if PUBLIC and sum(map(len, svgs)) > MAX_OUTPUT_BYTES:
                raise ToolError(too_big)
        return {"sheets": len(pages), "svg": svgs, **link}
    if path:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_pdf_bytes(doc, pages))
        return {"path": str(target), **link}
    data = _pdf_bytes(doc, pages)
    if PUBLIC and len(data) > MAX_OUTPUT_BYTES:
        raise ToolError(too_big)
    return {"pdf_base64": base64.b64encode(data).decode("ascii"), **link}


def _pdf_bytes(doc: Document, pages: list) -> bytes:
    from ..i18n import normalize_lang

    try:
        from ..render.pdf import write_pdf

        with tempfile.TemporaryDirectory() as tmp:
            write_pdf(pages, Path(tmp) / "sld.pdf", normalize_lang(doc.meta.lang), doc.meta.title)
            return (Path(tmp) / "sld.pdf").read_bytes()
    except ImportError as e:
        raise ToolError(f"PDF output needs the 'uniwire[pdf]' extra (reportlab): {e}") from None
    except RuntimeError as e:
        if isinstance(e.__cause__, ImportError):  # reportlab missing (write_pdf)
            raise ToolError(f"PDF output needs the 'uniwire[pdf]' extra (reportlab): {e}") from None
        raise


def pdf_filename(title: Optional[str]) -> str:
    """File name for the PDF of a document titled ``title`` ("Small bakery, 400 V" -> "small-bakery-400-v.pdf")."""
    ascii_ = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:80].strip("-")
    return f"{slug or 'uniwire'}.pdf"


def pdf_file(document: Any, kind: str = "single-line") -> dict[str, Any]:
    """The PDF of a document (all sheets of the default ``kind`` view) and its file name: ``{pdf_base64,
    filename}``. Not an assistant tool: the hosted server serves it at ``GET /pdf/<id>`` (the ``pdf_url`` links)."""
    from ..render import default_view, render_pages

    raw = _raw(document)
    try:
        doc = _load(raw)
    except UniwireError as e:
        raise ToolError("invalid document:\n" + "\n".join(f"- {i}" for i in _issues(raw, e))) from None
    pages = render_pages(doc, default_view(doc, None, kind))
    if PUBLIC and len(pages) > MAX_SHEETS:
        raise ToolError(f"too many sheets for this server: {len(pages)} (at most {MAX_SHEETS})")
    data = _pdf_bytes(doc, pages)
    if PUBLIC and len(data) > MAX_OUTPUT_BYTES:
        raise ToolError(f"output too large for this server (at most {MAX_OUTPUT_BYTES} bytes per rendering)")
    return {"pdf_base64": base64.b64encode(data).decode("ascii"), "filename": pdf_filename(doc.meta.title)}


def wiring(document: Any, what: str = "markers", view: Optional[str] = None) -> dict[str, Any]:
    """Wiring exports as rows: ``markers`` (one row per wire end, for label printers), ``wires`` (wire list)
    or ``cables`` (cable schedule). Marks follow the ``wire_marking`` rules of ``view`` (id; default: the first
    view that declares marking rules, else manual marks only)."""
    from .. import exports
    from ..marks import marked_wires

    doc = _doc(document)
    if what == "cables":
        return {"columns": exports.CABLE_COLUMNS, "rows": exports.cable_rows(doc)}
    if what not in ("markers", "wires"):
        raise ToolError("what must be 'markers', 'wires' or 'cables'")
    if view is not None:
        v = next((x for x in doc.views if x.id == view), None)
        if v is None:
            raise ToolError(f"unknown view {view!r}; views: {[x.id for x in doc.views]}")
    else:
        v = next((x for x in doc.views if x.wire_marking is not None), None)
    wires = marked_wires(doc, v)
    if what == "wires":
        return {"view": v.id if v else None, "columns": exports.WIRE_COLUMNS, "rows": exports.wire_rows(wires)}
    return {"view": v.id if v else None, "columns": exports.MARKER_COLUMNS, "rows": exports.marker_rows(wires)}


# ------------------------------------------------------------------ examples


def examples_dir() -> Optional[Path]:
    """Folder of the bundled examples: ``$UNIWIRE_EXAMPLES``, the wheel copy, or the source checkout."""
    env = os.environ.get("UNIWIRE_EXAMPLES")
    here = Path(__file__).resolve().parent.parent
    for cand in ([Path(env)] if env else []) + [here / "_examples", here.parent.parent / "examples"]:
        if cand.is_dir() and any(cand.glob("*.uniwire.json")):
            return cand
    return None


@lru_cache(maxsize=4)
def _example_index(folder: str) -> dict[str, Path]:
    return {p.name.removesuffix(".uniwire.json"): p for p in sorted(Path(folder).glob("*.uniwire.json"))}


def list_examples() -> list[dict[str, Any]]:
    """The bundled examples: name, title, language, profiles, earthing and system of each."""
    folder = examples_dir()
    if folder is None:
        return []
    out = []
    for name, p in _example_index(str(folder)).items():
        data = json.loads(p.read_text("utf-8"))
        inst = data.get("installation", {})
        out.append({"name": name, "title": data.get("meta", {}).get("title"), "lang": data.get("meta", {}).get("lang"),
                    "profiles": data.get("profiles", []), "earthing": inst.get("earthing"),
                    "system": inst.get("system")})
    return out


def get_example(name: str) -> dict[str, Any]:
    """One bundled example as JSON data, by full name, number (``"03"``) or name without number."""
    folder = examples_dir()
    if folder is None:
        raise ToolError("examples are not available in this installation")
    index = _example_index(str(folder))
    key = name.removesuffix(".json").removesuffix(".uniwire")
    p = index.get(key) or next((v for k, v in index.items() if k.startswith(f"{key}_") or k.split("_", 1)[-1] == key),
                               None)
    if p is None:
        raise ToolError(f"unknown example {name!r}; see list_examples")
    return json.loads(p.read_text("utf-8"))
