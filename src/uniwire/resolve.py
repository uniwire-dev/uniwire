"""Loading, template application, identifier assignment and integrity checks."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from pydantic import ValidationError

from .i18n import t as _t
from .model import FORMAT_VERSION, NODE_TYPES, Document, NodeBase
from .tolerate import tolerate


class UniwireError(Exception):
    """Invalid document. ``issues`` holds the list of problems found."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


def _format_validation_error(err: ValidationError) -> list[str]:
    out = []
    for e in err.errors():
        loc = "/".join(str(p) for p in e["loc"])
        msg = e["msg"]
        if e["type"] == "extra_forbidden":
            msg = _t("validation.extra_forbidden")
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


def _validate(data: dict[str, Any]) -> Document:
    try:
        return Document.model_validate(data)
    except ValidationError as err:
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
    _validate(data)  # 1st pass: strict structure of the file as written
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
    doc = _validate(data)  # 2nd pass: inherited attributes validated against the node type
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
