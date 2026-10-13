"""Scoring of candidate documents against machine-checkable task expectations (LLM evaluations).

A task is a JSON object::

    {"id": "fr_house_tt_hc", "request": "natural-language brief…", "base": "01_studio_apartment" (edit tasks),
     "expect": [ {"check": "...", ...}, ... ]}

Checks (each worth one point; document validity is always the first point and gates the others):

* ``profile`` (``{"value": "nfc15100"}``): the profile is listed in ``profiles``;
* ``installation`` (``{"fields": {...}}``): installation fields match (see *patterns*);
* ``count``: ``{"match": {...}, "min": n, "max": m, "scope": "nodes"|"links"|"views"|"interlocks"|"enclosures"}``;
* ``distinct`` (``{"match": {...}, "field": "phase", "min": 3}``): distinct values among matching nodes;
* ``under`` (``{"ancestor": {...}, "descendant": {...}, "min": 1}``): matching descendants fed through
  a matching ancestor (``"or_self": true`` also accepts the descendant itself);
* ``link`` (``{"match": {...}, "from": {...}, "to": {...}, "min": 1}``): links whose endpoint nodes
  (or one of their ancestors) match the patterns;
* ``no_errors``: no ``error`` finding (rule profiles of the document);
* ``max_findings``: ``{"level": "warning", "max": n}``;
* ``renders``: the default view (and ``{"kind": "multi-line"}`` if given) renders without exception;
* ``keeps_ids``: every node id of the ``base`` document is still present (edit tasks).

Patterns: ``{"field": value}`` (equality), a list (any of), ``{"min": x, "max": y}`` (numeric range),
``{"exists": true|false}``; dotted keys reach sub-objects (``"cable.section_mm2"``).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..resolve import UniwireError, build_index, iter_nodes, load

_MISSING = object()


def _get(obj: dict[str, Any], key: str) -> Any:
    cur: Any = obj
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _match_value(val: Any, pat: Any) -> bool:
    if isinstance(pat, dict) and set(pat) <= {"min", "max", "exists"}:
        if "exists" in pat:
            present = val is not _MISSING and val not in (None, [], {})
            if present != bool(pat["exists"]):
                return False
            if set(pat) == {"exists"}:
                return True
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return False
        return ("min" not in pat or val >= pat["min"]) and ("max" not in pat or val <= pat["max"])
    if val is _MISSING:
        return False
    if isinstance(pat, list):
        return any(_match_value(val, p) for p in pat)
    if isinstance(val, list) and not isinstance(pat, list):
        return pat in val
    return val == pat


def matches(obj: dict[str, Any], pattern: dict[str, Any] | None) -> bool:
    """True when every ``key: value`` of ``pattern`` matches ``obj``: dotted keys, a list pattern accepts any of its
    values, ``{"min", "max", "exists"}`` test numbers and presence."""
    return all(_match_value(_get(obj, k), v) for k, v in (pattern or {}).items())


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def _bound(n: int, spec: dict[str, Any]) -> bool:
    lo = spec.get("min", 1 if "max" not in spec else 0)
    return n >= lo and ("max" not in spec or n <= spec["max"])


def _run_check(c: dict[str, Any], raw: dict[str, Any], doc: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
    kind = c.get("check")
    nodes: list[dict[str, Any]] = ctx["nodes"]
    if kind == "profile":
        return c["value"] in doc.profiles, f"profiles={doc.profiles}"
    if kind == "installation":
        inst = _dump(doc.installation)
        return matches(inst, c.get("fields")), f"installation={ {k: inst.get(k) for k in c.get('fields', {})} }"
    if kind == "count":
        scope = c.get("scope", "nodes")
        pool = nodes if scope == "nodes" else [_dump(x) for x in getattr(doc, scope)]
        n = sum(1 for x in pool if matches(x, c.get("match")))
        return _bound(n, c), f"{n} matching {scope}"
    if kind == "distinct":
        vals = {json.dumps(_get(x, c["field"]), sort_keys=True) for x in nodes
                if matches(x, c.get("match")) and _get(x, c["field"]) is not _MISSING}
        return _bound(len(vals), c), f"{len(vals)} distinct {c['field']}"
    if kind == "under":
        idx = ctx["index"]
        by_id = ctx["by_id"]
        n = 0
        for x in nodes:
            if not matches(x, c.get("descendant")):
                continue
            chain = ([x] if c.get("or_self") else []) + [by_id[a.id] for a in idx.ancestors(x["id"])]
            if any(matches(a, c.get("ancestor")) for a in chain):
                n += 1
        return _bound(n, c), f"{n} matching descendant(s)"
    if kind == "link":
        idx = ctx["index"]
        by_id = ctx["by_id"]

        def end_ok(node_id: str, pat: dict | None) -> bool:
            if not pat:
                return True
            chain = [node_id] + [a.id for a in idx.ancestors(node_id)]
            return any(i in by_id and matches(by_id[i], pat) for i in chain)

        n = sum(1 for l in doc.links if matches(_dump(l), c.get("match"))
                and end_ok(l.from_, c.get("from")) and end_ok(l.to, c.get("to")))
        return _bound(n, c), f"{n} matching link(s)"
    if kind == "no_errors":
        errs = [f for f in ctx["findings"] if f.level == "error"]
        return not errs, "; ".join(str(f) for f in errs[:3]) or "no errors"
    if kind == "max_findings":
        level = c.get("level", "warning")
        n = sum(1 for f in ctx["findings"] if f.level == level)
        return n <= c.get("max", 0), f"{n} {level}(s)"
    if kind == "renders":
        from ..render import default_view, render_pages

        render_pages(doc, default_view(doc, None, c.get("kind")))
        return True, "rendered"
    if kind == "keeps_ids":
        base = ctx.get("base")
        if base is None:
            return False, "task has no base document"
        from .patch import materialize_ids

        base_ids = {n["id"] for n in _flat_ids(materialize_ids(base))}
        missing = sorted(base_ids - set(ctx["by_id"]))
        return not missing, f"missing ids: {', '.join(missing[:10])}" if missing else "all base ids kept"
    raise ValueError(f"unknown check {kind!r}")


def _flat_ids(data: dict[str, Any]) -> list[dict[str, Any]]:
    from .patch import _raw_nodes

    return [n for n, _, _ in _raw_nodes(data)]


def load_base(task: dict[str, Any]) -> dict[str, Any] | None:
    """Base document of an edit task (``base`` = example name or inline document)."""
    base = task.get("base")
    if base is None:
        return None
    if isinstance(base, dict):
        return base
    from .tools import get_example

    return get_example(base)


def score(candidate: Any, task: dict[str, Any]) -> dict[str, Any]:
    """Score one candidate document (dict, JSON text or path) against ``task``.

    Returns ``{"task", "valid", "passed", "total", "score", "results": [{"check", "ok", "detail"}]}``.
    """
    from ..rules import check as run_rules
    from .patch import as_dict

    expects = task.get("expect", [])
    total = 1 + len(expects)
    results: list[dict[str, Any]] = []
    try:
        raw = as_dict(candidate) if candidate is not None else None
        if raw is None:
            raise UniwireError(["no candidate document"])
        doc = load(copy.deepcopy(raw))
    except (UniwireError, ValueError, OSError) as e:
        issues = e.issues if isinstance(e, UniwireError) else [str(e)]
        results.append({"check": "valid", "ok": False, "detail": "; ".join(issues[:5])})
        results += [{"check": c.get("check"), "ok": False, "detail": "skipped (invalid document)"} for c in expects]
        return {"task": task.get("id"), "valid": False, "passed": 0, "total": total, "score": 0.0, "results": results}
    results.append({"check": "valid", "ok": True, "detail": "valid"})
    nodes = [_dump(n) for n, _, _ in iter_nodes(doc)]
    for n in nodes:
        n.pop("children", None)
    ctx = {"nodes": nodes, "by_id": {n["id"]: n for n in nodes}, "index": build_index(doc),
           "findings": run_rules(doc), "base": load_base(task)}
    for c in expects:
        try:
            ok, detail = _run_check(c, raw, doc, ctx)
        except Exception as e:  # a failing render or a malformed check counts as a failed point
            ok, detail = False, f"{type(e).__name__}: {e}"
        label = c.get("check") + (f" {c['match']}" if "match" in c else "")
        results.append({"check": label, "ok": bool(ok), "detail": detail})
    passed = sum(1 for r in results if r["ok"])
    return {"task": task.get("id"), "valid": True, "passed": passed, "total": total,
            "score": round(passed / total, 4), "results": results}


def load_tasks(folder: str | Path) -> list[dict[str, Any]]:
    """Task specifications (``*.json``) of ``folder``, sorted by file name."""
    return [json.loads(p.read_text("utf-8")) for p in sorted(Path(folder).glob("*.json"))]


def find_candidate(folder: str | Path, task_id: str) -> Path | None:
    """Answer file of a task in ``folder`` (``<id>.uniwire.json`` or ``<id>.json``), or None."""
    for name in (f"{task_id}.uniwire.json", f"{task_id}.json"):
        p = Path(folder) / name
        if p.is_file():
            return p
    return None


def task_prompt(task: dict[str, Any], *, lang: str = "en", level: str = "compact") -> str:
    """Self-contained prompt for a model without tools: reference card + request (+ base document)."""
    from .card import card

    parts = [card(lang, level), "---", "Task:", task["request"]]
    base = load_base(task)
    if base is not None:
        from .patch import materialize_ids

        base = materialize_ids(base)  # explicit ids, so that the model can keep them
        parts += ["", "Starting document:", "```json", json.dumps(base, ensure_ascii=False, indent=1), "```",
                  "Return the complete modified document."]
    parts += ["", "Answer with a single uniwire JSON document only (no prose, no code fence)."]
    return "\n".join(parts) + "\n"
