"""Loading, template application, identifier assignment and integrity checks."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union, get_args

from pydantic import BaseModel, ValidationError

from .i18n import t as _t
from .model import FORMAT_VERSION, NODE_TYPES, Document, NodeBase
from .tolerate import tolerate


class UniwireError(Exception):
    """Invalid document. ``issues`` holds the list of problems found."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


def _model_at(loc: tuple) -> type[BaseModel] | None:
    """The model of the object at ``loc`` (a pydantic error location: keys, list indexes and node type tags)."""
    model: Any = Document
    pending: Any = None  # annotation of the field being followed, until an object model is reached
    for p in loc:
        if pending is not None:
            if isinstance(p, str) and p in NODE_TYPES:
                model, pending = NODE_TYPES[p], None
                continue
            if isinstance(p, int):
                continue
            models = _models_in(pending)
            if len(models) != 1:
                return None
            model, pending = models[0], None
        if isinstance(p, int):
            continue
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            return None
        f = next((f for n, f in model.model_fields.items() if p in (n, f.alias)), None)
        if f is None:
            return None
        pending = f.annotation
    if pending is not None:
        models = _models_in(pending)
        return models[0] if len(models) == 1 else None
    return model


def _models_in(annotation: Any) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    value = getattr(annotation, "__value__", None)  # a type alias (the node union)
    args = get_args(value if value is not None else annotation)
    return list(dict.fromkeys(m for a in args for m in _models_in(a)))


def _fields_of(model: type[BaseModel]) -> str:
    return ", ".join(f.alias or n for n, f in model.model_fields.items() if n != "ext")


def _format_validation_error(err: ValidationError) -> list[str]:
    out = []
    for e in err.errors():
        loc = "/".join(str(p) for p in e["loc"])
        msg = e["msg"]
        if e["type"] == "extra_forbidden":
            msg = _t("validation.extra_forbidden")
            model = _model_at(e["loc"][:-1])
            if model is not None:  # the fields that can be written here, so that any misnamed one is fixed at once
                missing = [str(x["loc"][-1]) for x in err.errors()
                           if x["type"] == "missing" and x["loc"][:-1] == e["loc"][:-1]]
                msg += "; " + _t("validation.expected_fields", fields=_fields_of(model))
                if missing:
                    msg += "; " + _t("validation.missing_fields", fields=", ".join(missing))
        elif e["type"] == "union_tag_invalid":
            msg = _t("validation.unknown_node_type", type=e.get("input", {}).get("type")) if isinstance(e.get("input"), dict) else msg
        out.append(f"{loc}: {msg}")
    return out


#: Deepest nesting of JSON objects / lists accepted (about 125 levels of nodes; the bundled examples stay under 30).
#: Deeper documents are refused with a clear issue instead of exhausting the interpreter stack.
MAX_DEPTH = 256


def check_depth(data: Any, limit: int = MAX_DEPTH) -> None:
    """Raise :class:`UniwireError` when ``data`` nests objects / lists deeper than ``limit`` (iterative walk)."""
    stack = [(data, 1)]
    while stack:
        obj, depth = stack.pop()
        if depth > limit:
            raise UniwireError([_t("validation.too_deep", max=limit)])
        if isinstance(obj, dict):
            stack.extend((v, depth + 1) for v in obj.values() if isinstance(v, (dict, list)))
        elif isinstance(obj, list):
            stack.extend((v, depth + 1) for v in obj if isinstance(v, (dict, list)))


def _newer_minor(declared: Any) -> bool:
    """True when ``declared`` is a ``1.y.z`` format version with a minor version newer than this library's.

    Any ``1.y.z`` document is accepted: minor versions only add optional fields, types and enumeration values,
    so a document from a newer minor version loads as long as it does not use them.
    """
    m = re.fullmatch(r"1\.(\d+)\.\d+", declared) if isinstance(declared, str) else None
    return bool(m) and int(m.group(1)) > int(FORMAT_VERSION.split(".")[1])


def _container(data: Any, loc: tuple) -> tuple[Any, list[str]] | None:
    """The object of ``data`` at the error location ``loc`` and its path, skipping the node type tags."""
    obj, path = data, []
    for p in loc:
        if isinstance(obj, list) and isinstance(p, int) and 0 <= p < len(obj):
            obj = obj[p]
        elif isinstance(obj, dict) and p in obj:
            obj = obj[p]
        elif isinstance(obj, dict) and p == obj.get("type"):
            continue
        else:
            return None
        path.append(str(p))
    return obj, path


def _repair(data: dict[str, Any], err: ValidationError) -> tuple[dict[str, Any], list[str]]:
    """A copy of ``data`` with the unambiguous mistakes behind ``err`` fixed, and one note per fix: a number written
    for a text, a text too long for a field that only shows a few characters (its initials, else its beginning),
    and in an object, a single unknown field beside a single missing required one (a misnamed field)."""
    out, notes = copy.deepcopy(data), []
    errors = err.errors()
    for e in errors:
        v = e.get("input")
        if e["type"] == "string_type" and isinstance(v, (int, float)) and not isinstance(v, bool):
            new = f"{v:g}" if isinstance(v, float) else str(v)
        elif e["type"] == "string_too_long" and isinstance(v, str) and (e.get("ctx") or {}).get("max_length"):
            new = _short_form(v, int(e["ctx"]["max_length"]))
        else:
            continue
        found = _container(out, e["loc"][:-1])
        key = e["loc"][-1]
        if found and isinstance(found[0], dict) and found[0].get(key) == v:
            found[0][key] = new
            notes.append(_t("core.normalized", where=_where(found), field=key, old=v, new=new))
    by_object: dict[tuple, tuple[list, list]] = {}
    for e in errors:
        if e["type"] in ("extra_forbidden", "missing"):
            extra, missing = by_object.setdefault(e["loc"][:-1], ([], []))
            (extra if e["type"] == "extra_forbidden" else missing).append(e["loc"][-1])
    for at, (extra, missing) in by_object.items():
        found = _container(out, at)
        if len(extra) == 1 and len(missing) == 1 and found and isinstance(found[0], dict) and extra[0] in found[0]:
            found[0][missing[0]] = found[0].pop(extra[0])
            notes.append(_t("core.normalized_field", where=_where(found), old=extra[0], new=missing[0]))
    return out, notes


def _short_form(text: str, limit: int) -> str:
    """A text written where only ``limit`` characters fit: the initials of its words ('Air conditioner': 'AC') when
    it has several and they fit, else its beginning."""
    words = re.findall(r"[^\W_]+", text)
    initials = "".join(w[0] for w in words).upper()
    return initials if 1 < len(words) and len(initials) <= limit else text.strip()[:limit].strip()


def _where(found: tuple[Any, list[str]]) -> str:
    obj, path = found
    return str(obj.get("id") or "/".join(path)) if isinstance(obj, dict) else "/".join(path)


def _validate(data: dict[str, Any], notes: list[str] | None = None) -> tuple[Document, dict[str, Any]]:
    """The document and the data it was read from: ``data``, or a repaired copy when the repairs make it valid (each
    repair is added to ``notes``)."""
    try:
        return Document.model_validate(data), data
    except ValidationError as err:
        if notes is not None:
            fixed, fixes = _repair(data, err)
            if fixes:
                try:
                    doc = Document.model_validate(fixed)
                except ValidationError:
                    pass  # the original problems are reported, as written
                else:
                    notes.extend(fixes)
                    return doc, fixed
        if any(e["type"] == "recursion_loop" for e in err.errors()):
            # pydantic-core's own nesting guard (lower on some platforms, e.g. Windows): not a cyclic reference
            raise UniwireError([_t("validation.too_deep_validator")]) from None
        issues = _format_validation_error(err)
        declared = data.get("uniwire")
        if _newer_minor(declared) and any(e["type"] == "extra_forbidden" for e in err.errors()):
            issues.append(_t("validation.newer_minor", declared=declared, supported=FORMAT_VERSION))
        raise UniwireError(issues) from None


def _apply_templates(node: dict[str, Any], templates: dict[str, dict[str, Any]], path: str, issues: list[str]) -> dict:
    name = node.get("use")
    if name is not None:
        tpl = templates.get(name)
        if tpl is None:
            issues.append(f"{path}: " + _t("validation.unknown_template", name=name))
        else:
            ttype = tpl.get("type")
            if ttype is not None and ttype != node.get("type"):
                issues.append(f"{path}: " + _t("validation.template_type_mismatch", name=name, ttype=ttype,
                                                ntype=node.get("type")))
            merged = {k: v for k, v in tpl.items() if k not in ("type", "children", "id")}
            merged.update(node)
            node = merged
    node["children"] = [
        _apply_templates(c, templates, f"{path}/children/{i}", issues) for i, c in enumerate(node.get("children", []))
    ]
    return node


_ID_CLEAN = re.compile(r"[^A-Za-z0-9_.\-]")


def iter_nodes(doc: Document) -> Iterator[tuple[NodeBase, NodeBase | None, int]]:
    """Pre-order traversal yielding (node, parent, depth). Includes the devices carried by links."""

    def walk(n: NodeBase, parent: NodeBase | None, depth: int):
        yield n, parent, depth
        for c in n.children:
            yield from walk(c, n, depth + 1)

    for root in doc.sources:
        yield from walk(root, None, 0)
    for dev in doc.devices:
        yield from walk(dev, None, 0)
    for link in doc.links:
        if link.device is not None:
            yield from walk(link.device, None, 0)


@dataclass
class Index:
    """Lookup tables of a resolved document: node by id, parent id and depth in the tree."""

    nodes: dict[str, NodeBase] = field(default_factory=dict)
    parent: dict[str, str | None] = field(default_factory=dict)
    depth: dict[str, int] = field(default_factory=dict)

    def ancestors(self, node_id: str) -> list[NodeBase]:
        """Nodes above ``node_id``, nearest first (its parent, then the parent's parent, up to the source)."""
        out, cur = [], self.parent.get(node_id)
        while cur is not None:
            out.append(self.nodes[cur])
            cur = self.parent.get(cur)
        return out


def build_index(doc: Document) -> Index:
    """Index every node of ``doc`` (tree nodes, ``devices`` and link devices); ids must be assigned."""
    idx = Index()
    for n, p, d in iter_nodes(doc):
        assert n.id is not None
        idx.nodes[n.id] = n
        idx.parent[n.id] = p.id if p is not None else None
        idx.depth[n.id] = d
    return idx


def _assign_ids(doc: Document) -> list[str]:
    issues: list[str] = []
    seen: dict[str, int] = {}
    nodes = [n for n, _, _ in iter_nodes(doc)]
    for n in nodes:
        if n.id is not None:
            if n.id in seen:
                issues.append(_t("validation.duplicate_id", id=n.id))
            seen[n.id] = 1
    counters: dict[str, int] = {}
    for n in nodes:
        if n.id is None:
            base = _ID_CLEAN.sub("", (n.ref or "").lstrip("-=+")) or n.type  # type: ignore[attr-defined]
            if not re.match(r"^[A-Za-z_]", base):
                base = f"n{base}"
            cand = base
            while cand in seen:
                counters[base] = counters.get(base, 1) + 1
                cand = f"{base}_{counters[base]}"
            n.id = cand
            seen[cand] = 1
    for link in doc.links:
        for end in (link.from_, link.to):
            if end not in seen:
                issues.append(_t("validation.link_unknown_id", kind=link.kind, id=end))
    enc_ids = set()
    for enc in doc.enclosures:
        if enc.id in seen or enc.id in enc_ids:
            issues.append(_t("validation.enclosure_id_used", id=enc.id))
        enc_ids.add(enc.id)
        for nid in enc.nodes:
            if nid not in seen:
                issues.append(_t("validation.enclosure_unknown_node", id=enc.id, node=nid))
    for enc in doc.enclosures:
        if enc.parent is not None and enc.parent not in enc_ids:
            issues.append(_t("validation.enclosure_unknown_parent", id=enc.id, parent=enc.parent))
    return issues


def resolve(data: dict[str, Any]) -> Document:
    """Validate a raw document, apply templates and assign identifiers."""
    check_depth(data)
    data, normalized = tolerate(data)  # unambiguous near-miss values in canonical form, each one noted
    _doc, data = _validate(data, normalized)  # 1st pass: strict structure of the file as written
    issues: list[str] = []
    templates = data.get("templates", {})
    for name, tpl in templates.items():
        t = tpl.get("type")
        if t is not None and t not in NODE_TYPES:
            issues.append(_t("validation.template_unknown_type", name=name, type=t))
    data = dict(data)
    data["sources"] = [_apply_templates(dict(s), templates, f"sources/{i}", issues) for i, s in enumerate(data["sources"])]
    data["devices"] = [_apply_templates(dict(d), templates, f"devices/{i}", issues)
                       for i, d in enumerate(data.get("devices", []))]
    data["links"] = [
        {**l, "device": _apply_templates(dict(l["device"]), templates, f"links/{i}/device", issues)}
        if l.get("device") else l
        for i, l in enumerate(data.get("links", []))
    ]
    if issues:
        raise UniwireError(issues)
    doc, _data = _validate(data, normalized)  # 2nd pass: inherited attributes validated against the node type
    issues = _assign_ids(doc)
    if issues:
        raise UniwireError(issues)
    doc._normalized = normalized
    return doc


def load(src: Union[str, Path, dict[str, Any]]) -> Document:
    """Load a uniwire document from a file path or a dict: validate it, apply templates, assign ids.

    Raises :class:`UniwireError` (with the list of ``issues``) for invalid JSON or an invalid document.
    """
    if isinstance(src, dict):
        return resolve(src)
    text = Path(src).read_text("utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise UniwireError([_t("validation.invalid_json", error=e)]) from None
    except RecursionError:
        raise UniwireError([_t("validation.too_deep", max=MAX_DEPTH)]) from None
    return resolve(data)


def dump(doc: Document, *, indent: int = 2) -> str:
    """Serialise a document to canonical JSON text (templates applied, ids present, ``None`` fields left out)."""
    return json.dumps(doc.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=False),
                      ensure_ascii=False, indent=indent)
