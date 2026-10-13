"""Glue between the web viewer (worker.js) and the uniwire library, executed inside Pyodide.

Every public function takes and returns JSON strings so that no Python proxy crosses the
worker boundary.
"""

from __future__ import annotations

import json
import os
import re
import typing

import uniwire
from uniwire.bom import bom_csv
from uniwire.render import default_view, render_pages
from uniwire.render.svg import page_to_svg
from uniwire.resolve import UniwireError, dump, iter_nodes, resolve
from uniwire.rules import RULE_INFO, check

_last: dict = {"text": None, "doc": None, "data": None}

#: View fields the viewer may override (colour mode, palettes): only those the library defines are used.
_OPTION_FIELD = re.compile(r"colou?rs?|palette", re.I)


def _set_lang(lang: str) -> None:
    os.environ["UNIWIRE_LANG"] = "fr" if str(lang).lower().startswith("fr") else "en"


def _split_issue(issue: str) -> dict:
    """``"sources/0/children/2: message"`` -> path + message (paths never contain spaces)."""
    head, sep, tail = issue.partition(": ")
    if sep and " " not in head and ("/" in head or head.isidentifier()):
        return {"path": head, "message": tail}
    return {"path": "", "message": issue}


def _node_paths(data: dict) -> list[str]:
    """JSON paths of the nodes, in the traversal order of :func:`uniwire.resolve.iter_nodes`."""
    out: list[str] = []

    def walk(node, path: str) -> None:
        out.append(path)
        for i, c in enumerate(node.get("children", []) or []):
            if isinstance(c, dict):
                walk(c, f"{path}/children/{i}")

    for i, s in enumerate(data.get("sources", []) or []):
        walk(s, f"sources/{i}")
    for i, d in enumerate(data.get("devices", []) or []):
        walk(d, f"devices/{i}")
    for i, link in enumerate(data.get("links", []) or []):
        if isinstance(link, dict) and isinstance(link.get("device"), dict):
            walk(link["device"], f"links/{i}/device")
    return out


def _choices(annotation) -> list | None:
    """Values of a ``Literal`` (possibly wrapped in ``Optional``), else ``None``."""
    if typing.get_origin(annotation) is typing.Literal:
        return [v for v in typing.get_args(annotation) if isinstance(v, (str, int, float, bool))]
    for arg in typing.get_args(annotation):
        found = _choices(arg)
        if found:
            return found
    return None


def view_options() -> dict:
    """Overridable View fields supported by the installed library: ``{name: [choices] | None}``."""
    from uniwire.model import View

    return {name: _choices(f.annotation) for name, f in View.model_fields.items() if _OPTION_FIELD.search(name)}


def _apply_options(view, options):
    """``view`` with the viewer's overrides (unknown fields and invalid values are ignored)."""
    if not isinstance(options, dict) or not options:
        return view
    supported = view_options()
    upd = {}
    for k, v in options.items():
        if k not in supported or v in (None, ""):
            continue
        if supported[k] is not None and v not in supported[k]:
            continue
        upd[k] = v
    return view.model_copy(update=upd) if upd else view


def _summary(node, lang: str) -> str:
    """Ratings shown next to the symbol (annotation lines), on one line."""
    try:
        from uniwire.labels import annotation

        lines = [ln for ln in annotation(node, lang) if ln and ln != getattr(node, "label", None)]
        return " · ".join(lines)
    except Exception:  # pragma: no cover - annotation helpers must never break the viewer
        return ""


def _cable(c) -> str:
    if c is None:
        return ""
    try:
        from uniwire.labels import cable_text

        text = cable_text(c)
    except Exception:  # pragma: no cover
        text = ""
    parts = [p for p in (c.ref, c.designation, text) if p]
    if c.length_m is not None:
        parts.append(f"{c.length_m:g} m")
    return " ".join(parts)


def _links(doc, lang: str) -> list[dict]:
    out = []
    for i, link in enumerate(doc.links):
        dev = link.device
        out.append({
            "index": i, "id": link.id or "", "kind": link.kind, "from": link.from_, "to": link.to,
            "label": link.label or "", "normally_open": bool(link.normally_open), "status": link.status or "",
            "device": ({"id": dev.id, "ref": dev.ref or "", "type": dev.type, "summary": _summary(dev, lang)}
                       if dev is not None else None),
            "cable": _cable(link.cable),
            "path": f"links/{i}",
        })
    return out


def _load(text: str):
    if _last["text"] == text and _last["doc"] is not None:
        return _last["doc"], _last["data"]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise UniwireError(["the document must be a JSON object"])
    doc = resolve(json.loads(text))  # resolve() mutates nested dicts: keep `data` pristine
    _last.update(text=text, doc=doc, data=data)
    return doc, data


def process(request: str) -> str:
    """Validate, check and render. Request: {text, view, kind, lang, options}.

    ``options`` overrides View fields listed by :func:`view_options` (colour mode, palette...)."""
    req = json.loads(request)
    _set_lang(req.get("lang", "en"))
    res: dict = {"ok": False, "version": uniwire.__version__, "errors": [], "findings": [], "pages": [],
                 "views": [], "nodes": {}, "links": [], "lang": "en",
                 "options": view_options()}
    text = req.get("text", "")
    try:
        doc, data = _load(text)
    except json.JSONDecodeError as e:
        res["stage"] = "json"
        res["errors"] = [{"path": "", "message": e.msg, "line": e.lineno, "col": e.colno, "pos": e.pos}]
        return json.dumps(res)
    except UniwireError as e:
        res["stage"] = "validation"
        res["errors"] = [_split_issue(i) for i in e.issues]
        return json.dumps(res)

    res["stage"] = "render"
    res["lang"] = doc.meta.lang or "en"
    res["title"] = doc.meta.title or ""
    paths = _node_paths(data)
    lang = res["lang"]
    for (n, parent, _), path in zip(iter_nodes(doc), paths):
        res["nodes"][n.id] = {"path": path, "type": n.type, "ref": n.ref or "", "label": getattr(n, "label", None) or "",
                              "parent": parent.id if parent is not None else None,
                              "children": [c.id for c in n.children], "summary": _summary(n, lang),
                              "cable": _cable(n.cable)}
    res["links"] = _links(doc, lang)
    res["views"] = [{"id": v.id, "title": v.title or v.id, "kind": v.kind} for v in doc.views]

    try:
        for f in check(doc):
            info = RULE_INFO.get(f.rule)
            res["findings"].append({"level": f.level, "rule": f.rule, "message": f.message, "node": f.node,
                                    "source": f.source or (info.source if info else None)})
    except Exception as e:  # a rule crash must not hide the drawing
        res["findings"].append({"level": "error", "rule": "internal", "message": f"{type(e).__name__}: {e}",
                                "node": None, "source": None})

    try:
        try:
            view = default_view(doc, req.get("view") or None, req.get("kind") or None)
        except KeyError:
            view = default_view(doc, None, req.get("kind") or None)
        view = _apply_options(view, req.get("options"))
        res["view"] = {"id": view.id, "kind": view.kind}
        pages = render_pages(doc, view)
        res["pages"] = [{"title": p.title, "svg": page_to_svg(p)} for p in pages]
    except Exception as e:
        res["errors"].append({"path": "", "message": f"render failed: {type(e).__name__}: {e}"})
        return json.dumps(res)
    res["ok"] = True
    return json.dumps(res)


def export(request: str) -> str:
    """Request: {text, what: normalized|bom}. Returns {ok, content | error}."""
    req = json.loads(request)
    _set_lang(req.get("lang", "en"))
    try:
        doc, _ = _load(req["text"])
        content = dump(doc) + "\n" if req["what"] == "normalized" else bom_csv(doc)
        return json.dumps({"ok": True, "content": content})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})


def export_pdf(request: str) -> str:
    """Write the PDF of the requested view to the in-memory file system; returns its path."""
    from uniwire.render import render_pdf

    req = json.loads(request)
    _set_lang(req.get("lang", "en"))
    doc, _ = _load(req["text"])
    try:
        view = default_view(doc, req.get("view") or None, req.get("kind") or None)
    except KeyError:
        view = default_view(doc, None, req.get("kind") or None)
    view = _apply_options(view, req.get("options"))
    path = "/tmp/uniwire-export.pdf"
    render_pdf(doc, path, view)
    return path
