"""Id-based editing of uniwire documents (raw JSON dictionaries).

Operations (applied in order on a copy; the result is validated at the end)::

    {"op": "set",    "id": "Q11", "path": "in_A", "value": 20}          # value null removes the field
    {"op": "set",    "path": "installation.earthing", "value": "TN-S"}  # no id: document root
    {"op": "add",    "parent": "F1", "node": {...}, "index": 0}         # or "at": "sources" | "devices"
    {"op": "remove", "id": "Q12"}                                       # drops links / enclosure entries to it
    {"op": "move",   "id": "Q12", "parent": "F2", "index": 1}
    {"op": "rename", "id": "Q12", "new_id": "Q21"}                      # updates links, enclosures, views
    {"op": "link",   "link": {"kind": "control", "from": "CPT", "to": "KM1"}}
    {"op": "unlink", "id": "L1"}  or  {"op": "unlink", "from": "CPT", "to": "KM1", "kind": "control"}

``id`` may also designate a link (by its ``id``) for ``set``. Node ids missing from the input are
materialized first (same ids as :func:`uniwire.load` assigns), so the ids shown by
:func:`uniwire.llm.describe` can be used directly.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Union

from ..resolve import UniwireError, check_depth, iter_nodes, load

DocLike = Union[dict, str, Path, Any]


class PatchError(Exception):
    """A patch failed. ``errors`` lists ``{"op": index or None, "error": message}`` entries."""

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__("; ".join(
            (f"op #{e['op']}: " if e.get("op") is not None else "validation: ") + e["error"] for e in errors))


# ------------------------------------------------------------------ helpers


def as_dict(doc: DocLike) -> dict[str, Any]:
    """Raw document dictionary from a dict, a JSON string, a file path or a :class:`~uniwire.Document`."""
    if isinstance(doc, dict):
        return doc
    if hasattr(doc, "model_dump"):
        return doc.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(doc, Path):
        return json.loads(doc.read_text("utf-8"))
    if isinstance(doc, str):
        s = doc.lstrip()
        if s.startswith("{"):
            return json.loads(doc)
        return json.loads(Path(doc).read_text("utf-8"))
    raise TypeError(f"unsupported document: {type(doc).__name__}")


def _raw_nodes(data: dict) -> Iterator[tuple[dict, dict | None, list]]:
    """(node, parent node, list containing the node) for every node of the raw document."""
    def walk(lst: list, parent: dict | None):
        for n in list(lst):
            if not isinstance(n, dict):
                continue
            yield n, parent, lst
            ch = n.get("children")
            if isinstance(ch, list):
                yield from walk(ch, n)

    for key in ("sources", "devices"):
        lst = data.get(key)
        if isinstance(lst, list):
            yield from walk(lst, None)
    for link in data.get("links") or []:
        if isinstance(link, dict) and isinstance(link.get("device"), dict):
            yield link["device"], None, [link["device"]]
            ch = link["device"].get("children")
            if isinstance(ch, list):
                yield from walk(ch, link["device"])


def materialize_ids(doc: DocLike) -> dict[str, Any]:
    """Copy of the raw document where every node has an explicit ``id`` (the one :func:`uniwire.load` assigns).

    Templates (``use``) and every other field are left untouched. Raises :class:`~uniwire.UniwireError`
    if the document is invalid.
    """
    raw_doc = as_dict(doc)
    check_depth(raw_doc)
    data = copy.deepcopy(raw_doc)
    resolved = load(copy.deepcopy(data))
    raw = [n for n, _, _ in _raw_nodes(data)]
    res = [n for n, _, _ in iter_nodes(resolved)]
    if len(raw) == len(res):
        for r, n in zip(raw, res):
            if r.get("id") is None:
                r["id"] = n.id
    return data


def _find_node(data: dict, node_id: str) -> tuple[dict, dict | None, list] | None:
    for n, parent, container in _raw_nodes(data):
        if n.get("id") == node_id:
            return n, parent, container
    return None


def _find_link(data: dict, link_id: str) -> dict | None:
    for l in data.get("links") or []:
        if isinstance(l, dict) and l.get("id") == link_id:
            return l
    return None


def _subtree_ids(node: dict) -> set[str]:
    out = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.get("id"):
            out.add(n["id"])
        stack.extend(c for c in n.get("children") or [] if isinstance(c, dict))
    return out


def _split_path(path: str) -> list[Union[str, int]]:
    parts: list[Union[str, int]] = []
    for p in str(path).replace("/", ".").split("."):
        if p == "":
            raise ValueError(f"empty segment in path {path!r}")
        parts.append(int(p) if p.lstrip("-").isdigit() else p)
    return parts


def _set_path(obj: Any, path: str, value: Any) -> None:
    parts = _split_path(path)
    if parts[0] in ("children",):
        raise ValueError("use 'add' / 'remove' / 'move' to change 'children'")
    if parts[0] == "id":
        raise ValueError("use 'rename' to change an id")
    cur = obj
    for i, p in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if isinstance(cur, dict):
            if p not in cur or cur[p] is None:
                if value is None:
                    return
                cur[p] = [] if isinstance(nxt, int) else {}
            cur = cur[p]
        elif isinstance(cur, list) and isinstance(p, int):
            if not -len(cur) <= p < len(cur):
                raise ValueError(f"index {p} out of range in path {path!r}")
            cur = cur[p]
        else:
            raise ValueError(f"cannot traverse {p!r} in path {path!r}")
    last = parts[-1]
    if isinstance(cur, dict):
        if value is None:
            cur.pop(last, None)
        else:
            cur[last] = value
    elif isinstance(cur, list) and isinstance(last, int):
        if last == len(cur) and value is not None:
            cur.append(value)
        elif -len(cur) <= last < len(cur):
            if value is None:
                del cur[last]
            else:
                cur[last] = value
        else:
            raise ValueError(f"index {last} out of range in path {path!r}")
    else:
        raise ValueError(f"cannot set {last!r} in path {path!r}")


def _insert(lst: list, item: Any, index: Any) -> None:
    if index is None:
        lst.append(item)
    else:
        if not isinstance(index, int):
            raise ValueError("'index' must be an integer")
        lst.insert(index, item)


def _rename_refs(data: dict, old: str, new: str) -> None:
    for l in data.get("links") or []:
        if isinstance(l, dict):
            for k in ("from", "to"):
                if l.get(k) == old:
                    l[k] = new
    for e in data.get("enclosures") or []:
        if isinstance(e, dict):
            e["nodes"] = [new if x == old else x for x in e.get("nodes") or []]
    for v in data.get("views") or []:
        if isinstance(v, dict):
            if v.get("root") == old:
                v["root"] = new
            for fr in v.get("frames") or []:
                if isinstance(fr, dict):
                    fr["nodes"] = [new if x == old else x for x in fr.get("nodes") or []]
            if isinstance(v.get("overrides"), dict) and old in v["overrides"]:
                v["overrides"][new] = v["overrides"].pop(old)


def _drop_refs(data: dict, ids: set[str]) -> None:
    if data.get("links"):
        data["links"] = [l for l in data["links"] if not (isinstance(l, dict) and (l.get("from") in ids or l.get("to") in ids))]
    for e in data.get("enclosures") or []:
        if isinstance(e, dict) and e.get("nodes"):
            e["nodes"] = [x for x in e["nodes"] if x not in ids]
    for v in data.get("views") or []:
        if isinstance(v, dict):
            if v.get("root") in ids:
                v.pop("root")
            if v.get("frames"):
                for fr in v["frames"]:
                    if isinstance(fr, dict):
                        fr["nodes"] = [x for x in fr.get("nodes") or [] if x not in ids]
                v["frames"] = [fr for fr in v["frames"] if not isinstance(fr, dict) or fr.get("nodes")]
            if isinstance(v.get("overrides"), dict):
                for i in ids:
                    v["overrides"].pop(i, None)


def _all_ids(data: dict) -> set[str]:
    return {n["id"] for n, _, _ in _raw_nodes(data) if n.get("id")}


# ------------------------------------------------------------------ operations


def _apply(data: dict, op: dict) -> None:
    if not isinstance(op, dict):
        raise ValueError("an operation must be an object")
    kind = op.get("op")
    if kind == "set":
        if "path" not in op:
            raise ValueError("'set' requires 'path'")
        if "value" not in op:
            raise ValueError("'set' requires 'value' (null removes the field)")
        target_id = op.get("id")
        if target_id is None:
            if _split_path(op["path"])[0] in ("sources", "devices"):
                raise ValueError("address nodes by 'id' (set) or use add/remove/move")
            _set_path(data, op["path"], op["value"])
            return
        found = _find_node(data, target_id)
        if found is not None:
            _set_path(found[0], op["path"], op["value"])
            return
        link = _find_link(data, target_id)
        if link is not None:
            _set_path(link, op["path"], op["value"])
            return
        raise ValueError(f"unknown id {target_id!r}")
    if kind == "add":
        node = op.get("node")
        if not isinstance(node, dict) or "type" not in node:
            raise ValueError("'add' requires 'node', an object with a 'type'")
        from ..model import NODE_TYPES
        if node["type"] not in NODE_TYPES:
            raise ValueError(f"unknown node type {node['type']!r}")
        node = copy.deepcopy(node)
        existing = _all_ids(data)
        clash = sorted(_subtree_ids(node) & existing)
        if clash:
            raise ValueError(f"id(s) already in use: {', '.join(clash)}")
        if op.get("parent") is not None:
            found = _find_node(data, op["parent"])
            if found is None:
                raise ValueError(f"unknown parent id {op['parent']!r}")
            _insert(found[0].setdefault("children", []), node, op.get("index"))
        else:
            at = op.get("at", "sources")
            if at not in ("sources", "devices"):
                raise ValueError("'at' must be 'sources' or 'devices' (or give 'parent')")
            _insert(data.setdefault(at, []), node, op.get("index"))
        return
    if kind == "remove":
        nid = op.get("id")
        found = _find_node(data, nid) if nid else None
        if found is None:
            raise ValueError(f"unknown id {nid!r}")
        node, _, container = found
        ids = _subtree_ids(node)
        container.remove(node)
        _drop_refs(data, ids)
        return
    if kind == "move":
        nid = op.get("id")
        found = _find_node(data, nid) if nid else None
        if found is None:
            raise ValueError(f"unknown id {nid!r}")
        node, _, container = found
        if op.get("parent") is not None:
            if op["parent"] in _subtree_ids(node):
                raise ValueError("cannot move a node under itself or its descendants")
            target = _find_node(data, op["parent"])
            if target is None:
                raise ValueError(f"unknown parent id {op['parent']!r}")
            container.remove(node)
            _insert(target[0].setdefault("children", []), node, op.get("index"))
        else:
            at = op.get("at")
            if at not in ("sources", "devices"):
                raise ValueError("'move' requires 'parent' (or 'at': 'sources' | 'devices')")
            container.remove(node)
            _insert(data.setdefault(at, []), node, op.get("index"))
        return
    if kind == "rename":
        nid, new = op.get("id"), op.get("new_id")
        if not new or not isinstance(new, str):
            raise ValueError("'rename' requires 'new_id'")
        found = _find_node(data, nid) if nid else None
        if found is None:
            raise ValueError(f"unknown id {nid!r}")
        if new in _all_ids(data):
            raise ValueError(f"id {new!r} already in use")
        found[0]["id"] = new
        _rename_refs(data, nid, new)
        return
    if kind == "link":
        link = op.get("link")
        if not isinstance(link, dict):
            raise ValueError("'link' requires 'link', an object {kind, from, to}")
        ids = _all_ids(data)
        missing = [link.get(k) for k in ("from", "to") if link.get(k) not in ids]
        if missing:
            raise ValueError(f"unknown node id(s) in link: {', '.join(repr(m) for m in missing)}")
        data.setdefault("links", []).append(copy.deepcopy(link))
        return
    if kind == "unlink":
        links = data.get("links") or []
        if op.get("id"):
            keep = [l for l in links if not (isinstance(l, dict) and l.get("id") == op["id"])]
        else:
            crit = {k: op[k] for k in ("from", "to", "kind") if op.get(k) is not None}
            if not crit:
                raise ValueError("'unlink' requires 'id' or at least one of 'from' / 'to' / 'kind'")
            keep = [l for l in links if not (isinstance(l, dict) and all(l.get(k) == v for k, v in crit.items()))]
        if len(keep) == len(links):
            raise ValueError("no matching link")
        data["links"] = keep
        return
    raise ValueError(f"unknown op {kind!r} (expected set, add, remove, move, rename, link, unlink)")


def patch(doc: DocLike, ops: list[dict[str, Any]] | dict[str, Any], *, validate: bool = True) -> dict[str, Any]:
    """Apply id-based operations to a raw document and return the new raw document.

    The input is never modified. On failure raises :class:`PatchError` whose ``errors`` give the index
    of the failing operation and the reason, or the validation issues of the result (``op`` = ``None``).
    """
    if isinstance(ops, dict):
        ops = ops.get("ops", [ops]) if "op" not in ops else [ops]
    if isinstance(ops, str):
        ops = json.loads(ops)
    raw_doc = as_dict(doc)
    try:
        check_depth(raw_doc)
    except UniwireError as e:
        raise PatchError([{"op": None, "error": issue} for issue in e.issues]) from None
    try:
        data = materialize_ids(raw_doc)
    except UniwireError:
        data = copy.deepcopy(raw_doc)  # invalid input: patch it anyway (it may fix it)
    for i, op in enumerate(ops):
        try:
            _apply(data, op)
        except (ValueError, TypeError, KeyError) as e:
            raise PatchError([{"op": i, "error": str(e), "operation": op}]) from None
    try:
        check_depth(data)  # before anything recursive (deepcopy, validation, serialisation) runs on the result
    except UniwireError as e:
        raise PatchError([{"op": None, "error": issue} for issue in e.issues]) from None
    if validate:
        try:
            load(copy.deepcopy(data))
        except UniwireError as e:
            raise PatchError([{"op": None, "error": explain_issue(data, issue)} for issue in e.issues]) from None
    return data


def explain_issue(data: dict, issue: str) -> str:
    """Rewrite a validation issue ``sources/0/grid/children/1/breaker/curve: msg`` as
    ``node 'Q11' (breaker), field 'curve': msg`` when the location falls inside a node."""
    loc, sep, msg = issue.partition(": ")
    if not sep or "/" not in loc:
        return issue
    cur: Any = data
    node: dict | None = None
    rest: list[str] = []
    for seg in loc.split("/"):
        if isinstance(cur, list) and seg.lstrip("-").isdigit() and -len(cur) <= int(seg) < len(cur):
            cur = cur[int(seg)]
        elif isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, dict) and cur.get("type") == seg:
            continue  # discriminator tag inserted by the validator
        else:
            rest.append(seg)
            continue
        if isinstance(cur, dict) and "type" in cur and cur.get("id"):
            node, rest = cur, []
        elif node is not None:
            rest.append(seg)
    if node is None:
        return issue
    where = f"node {node['id']!r} ({node.get('type')})"
    if rest:
        where += f", field {'.'.join(rest)!r}"
    return f"{where}: {msg} [{loc}]"


# ------------------------------------------------------------------ flat table form


def flatten(doc: DocLike) -> list[dict[str, Any]]:
    """Nodes of ``sources`` and ``devices`` as a flat list (pre-order).

    Each row holds the node fields (without ``children``) plus ``parent`` (parent id, ``None`` for roots)
    and, for roots, ``root`` (``"sources"`` or ``"devices"``). Ids are materialized.
    """
    data = materialize_ids(doc)
    rows: list[dict[str, Any]] = []

    def walk(lst: list, parent: str | None, root: str | None):
        for n in lst:
            row = {k: v for k, v in n.items() if k != "children"}
            row["parent"] = parent
            if root:
                row["root"] = root
            rows.append(row)
            walk(n.get("children") or [], n["id"], None)

    for key in ("sources", "devices"):
        walk(data.get(key) or [], None, key)
    return rows


def unflatten(rows: list[dict[str, Any]], base: DocLike | None = None) -> dict[str, Any]:
    """Inverse of :func:`flatten`: rebuild ``sources`` / ``devices`` from rows (order of rows = child order).

    With ``base``, the other top-level keys (meta, installation, links...) are copied from it.
    """
    out = copy.deepcopy(as_dict(base)) if base is not None else {}
    out["sources"], out["devices"] = [], []
    by_id: dict[str, dict] = {}
    pending: list[tuple[dict, str]] = []
    for i, r in enumerate(rows):
        node = {k: copy.deepcopy(v) for k, v in r.items() if k not in ("parent", "root")}
        nid = node.get("id")
        if not nid:
            raise PatchError([{"op": i, "error": "row without 'id'"}])
        if nid in by_id:
            raise PatchError([{"op": i, "error": f"duplicate id {nid!r}"}])
        by_id[nid] = node
        if r.get("parent"):
            pending.append((node, r["parent"]))
        else:
            root = r.get("root", "sources")
            if root not in ("sources", "devices"):
                raise PatchError([{"op": i, "error": f"invalid root {root!r}"}])
            out[root].append(node)
    for node, parent in pending:
        if parent not in by_id:
            raise PatchError([{"op": None, "error": f"node {node['id']!r}: unknown parent {parent!r}"}])
        by_id[parent].setdefault("children", []).append(node)
    if not out["devices"]:
        del out["devices"]
    return out
