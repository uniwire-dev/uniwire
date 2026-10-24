"""Faithful, deterministic text outline of a uniwire document, meant to be read by an LLM.

Every node line starts with its stable ``id`` (usable in :func:`uniwire.llm.patch` operations),
followed by the ``[ref]``, the type, the quoted label, then the node's own fields as
``field=value`` (templates applied) and the cable run from its parent.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from ..i18n import normalize_lang
from ..model import Document, NodeBase
from ..resolve import load
from .patch import DocLike, as_dict

_TEXT = {
    "en": {"doc": "uniwire document", "installation": "Installation", "counts": "Counts", "nodes": "nodes",
           "templates": "Templates", "sources": "Sources", "tree": "Tree", "legend":
           "(id [ref] type \"label\" field=value… | cable; indentation = fed by the line above)",
           "devices": "Auxiliary devices (outside the power tree)", "links": "Links", "interlocks": "Interlocks",
           "enclosures": "Enclosures", "views": "Views", "boards": "Boards", "findings": "Findings",
           "none": "none", "more": "… {n} more", "outgoing": "outgoing", "fed_by": "fed by",
           "no_findings": "no findings", "members": "members", "keys": "key(s)", "notes": "Notes"},
    "fr": {"doc": "Document uniwire", "installation": "Installation", "counts": "Effectifs", "nodes": "nœuds",
           "templates": "Modèles", "sources": "Sources", "tree": "Arbre", "legend":
           "(id [repère] type \"libellé\" champ=valeur… | câble ; indentation = alimenté par la ligne au-dessus)",
           "devices": "Appareils annexes (hors arbre de puissance)", "links": "Liens", "interlocks": "Verrouillages",
           "enclosures": "Enveloppes", "views": "Vues", "boards": "Tableaux", "findings": "Remarques",
           "none": "aucun", "more": "… {n} de plus", "outgoing": "départs", "fed_by": "alimenté par",
           "no_findings": "aucune remarque", "members": "membres", "keys": "clé(s)", "notes": "Notes"},
}

_SKIP = {"id", "ref", "label", "type", "children", "cable", "ext", "product", "notes", "use", "manufacturer",
         "part_number"}


def _num(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:g}"
    return str(v)


def _val(v: Any) -> str:
    if isinstance(v, (int, float, bool)):
        return _num(v)
    if isinstance(v, str):
        return v if v and " " not in v and "," not in v else json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        if all(isinstance(x, (str, int, float)) for x in v):
            return "[" + ",".join(_num(x) if not isinstance(x, str) else x for x in v) + "]"
        return f"[{len(v)} item(s)]"
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def cable_text(cable: Any) -> str:
    """Compact one-line text of a cable (model or dict), e.g. ``W12 4G2.5mm2 Cu 18m method B``; ``""`` for None."""
    if cable is None:
        return ""
    c = cable.model_dump(exclude_none=True) if hasattr(cable, "model_dump") else dict(cable)
    parts = []
    if c.get("ref"):
        parts.append(c["ref"])
    if c.get("kind") and c["kind"] != "cable":
        parts.append(c["kind"])
    size = ""
    if c.get("parallel"):
        size += f"{c['parallel']}x("
    size += c.get("cores") or ""
    if c.get("section_mm2") is not None:
        size += f"{_num(c['section_mm2'])}mm2"
    if c.get("parallel"):
        size += ")"
    if size:
        parts.append(size)
    if c.get("size_awg"):
        parts.append(c["size_awg"])
    for k in ("pe_section_mm2", "neutral_section_mm2"):
        if c.get(k) is not None:
            parts.append(f"{k.split('_')[0].upper()} {_num(c[k])}mm2")
    if c.get("material"):
        parts.append(c["material"])
    if c.get("length_m") is not None:
        parts.append(f"{_num(c['length_m'])}m")
    for k in ("designation", "insulation"):
        if c.get(k):
            parts.append(str(c[k]))
    if c.get("install"):
        parts.append(f"method {c['install']}")
    if c.get("du_pct") is not None:
        parts.append(f"du {_num(c['du_pct'])}%")
    return " ".join(parts)


def node_line(n: NodeBase, raw_use: str | None = None) -> str:
    """One outline line of a node: ``id [ref] type "label" (use T) field=value... | cable`` (children excluded)."""
    # children are described on their own lines: dumping them here would serialise the whole subtree (and fail
    # on deep trees)
    d = n.model_dump(exclude_none=True, by_alias=True, exclude={"children"})
    s = f"{n.id}"
    if n.ref:
        s += f" [{n.ref}]"
    s += f" {n.type}"  # type: ignore[attr-defined]
    if n.label:
        s += f" {json.dumps(n.label, ensure_ascii=False)}"
    if n.use:
        s += f" (use {n.use})"
    fields = []
    for k, v in d.items():
        if k in _SKIP or v in ([], {}, None, ""):
            continue
        if k in ("onboard", "modules") and isinstance(v, list):
            fields.append(f"{k}={len(v)}")
            continue
        fields.append(f"{k}={_val(v)}")
    pn = (n.product.part_number if n.product is not None else None) or n.part_number
    if pn:
        fields.append(f"part_number={_val(pn)}")
    if fields:
        s += " " + " ".join(fields)
    ct = cable_text(n.cable)
    if ct:
        s += f" | cable {ct}"
    return s


def describe(doc: DocLike, lang: str = "en", *, findings: bool = True, max_findings: int = 30) -> str:
    """Text outline of ``doc`` (dict, JSON text, path or :class:`~uniwire.Document`): installation,
    templates, the full tree with ids, auxiliary devices, links, interlocks, enclosures, views, boards
    and a summary of the rule findings. Deterministic for a given document."""
    from ..rules import check

    lang = normalize_lang(lang)
    T = _TEXT.get(lang, _TEXT["en"])
    d: Document = doc if isinstance(doc, Document) else load(as_dict(doc))
    L: list[str] = []
    add = L.append

    title = d.meta.title or ""
    add(f"# {T['doc']}" + (f" \"{title}\"" if title else "") +
        f" (format {d.uniwire}, lang {d.meta.lang or 'en'}, profiles: {', '.join(d.profiles) or T['none']})")
    meta = d.meta.model_dump(exclude_none=True, exclude={"title", "lang", "notes", "revisions", "contributors", "ext"})
    if meta:
        add(" ".join(f"{k}={_val(v)}" for k, v in meta.items()))
    inst = d.installation.model_dump(exclude_none=True, exclude={"ext"})
    add(f"{T['installation']}: " + (" ".join(f"{k}={_val(v)}" for k, v in inst.items()) or T["none"]))
    if d.meta.notes:
        add(f"{T['notes']}: " + " / ".join(d.meta.notes))

    from ..resolve import iter_nodes
    all_nodes = [n for n, _, _ in iter_nodes(d)]
    counts = Counter(n.type for n in all_nodes)  # type: ignore[attr-defined]
    add(f"{T['counts']}: {len(all_nodes)} {T['nodes']} (" +
        ", ".join(f"{t} {c}" for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))) +
        f"), {len(d.links)} link(s), {len(d.interlocks)} interlock(s)")
    if d.templates:
        add(f"{T['templates']}: " + "; ".join(
            f"{name}=" + " ".join(f"{k}={_val(v)}" for k, v in tpl.items()) for name, tpl in d.templates.items()))
    add("")

    add(f"## {T['tree']} {T['legend']}")

    def walk(n: NodeBase, depth: int):
        add("  " * depth + "- " + node_line(n))
        for c in n.children:
            walk(c, depth + 1)

    for root in d.sources:
        walk(root, 0)
    if d.devices:
        add("")
        add(f"## {T['devices']}")
        for dev in d.devices:
            walk(dev, 0)

    if d.links:
        add("")
        add(f"## {T['links']}")
        for i, l in enumerate(d.links):
            s = f"- {l.id or '#' + str(i)}: {l.kind} {l.from_}"
            if l.from_port:
                s += f"[{l.from_port}]"
            s += f" -> {l.to}"
            if l.to_port:
                s += f"[{l.to_port}]"
            extra = l.model_dump(exclude_none=True, by_alias=True,
                                 exclude={"id", "kind", "from_", "to", "device", "cable", "from_port", "to_port", "ext"})
            extra = {k: v for k, v in extra.items() if v not in ([], {}, None, "")}
            if extra:
                s += " " + " ".join(f"{k}={_val(v)}" for k, v in extra.items())
            ct = cable_text(l.cable)
            if ct:
                s += f" | cable {ct}"
            add(s)
            if l.device is not None:
                walk(l.device, 1)

    locks: dict[str, list[str]] = {}
    for n in all_nodes:
        for k in n.locks:
            locks.setdefault(k, []).append(n.id or "")
    for i, l in enumerate(d.links):
        for k in l.locks:
            locks.setdefault(k, []).append(l.id or f"link#{i}")
    if d.interlocks or locks:
        add("")
        add(f"## {T['interlocks']}")
        declared = {il.key: il for il in d.interlocks}
        for key in list(declared) + sorted(k for k in locks if k not in declared):
            il = declared.get(key)
            s = f"- {key}: {il.keys if il else 1} {T['keys']}"
            if il is not None and il.kind:
                s += f" ({il.kind})"
            if il is not None and il.label:
                s += f" {json.dumps(il.label, ensure_ascii=False)}"
            s += f"; {T['members']}: {', '.join(locks.get(key, [])) or T['none']}"
            add(s)

    if d.enclosures:
        add("")
        add(f"## {T['enclosures']}")
        for e in d.enclosures:
            s = f"- {e.id} {e.kind}"
            if e.ref:
                s += f" [{e.ref}]"
            if e.label:
                s += f" {json.dumps(e.label, ensure_ascii=False)}"
            if e.parent:
                s += f" in {e.parent}"
            if e.nodes:
                s += f": {', '.join(e.nodes)}"
            add(s)

    boards = [n for n in all_nodes if n.type == "board"]  # type: ignore[attr-defined]
    if boards:
        from ..resolve import build_index
        idx = build_index(d)
        add("")
        add(f"## {T['boards']}")
        for b in boards:
            feeder = next((a for a in idx.ancestors(b.id or "") if a.type != "board"), None)  # type: ignore[attr-defined]
            outs = sum(1 for c in _feeders(b))
            s = f"- {b.id}" + (f" [{b.ref}]" if b.ref else "") + (f" {json.dumps(b.label, ensure_ascii=False)}" if b.label else "")
            s += f": {outs} {T['outgoing']}"
            if feeder is not None:
                s += f", {T['fed_by']} {feeder.id}"
            add(s)

    if d.views:
        add("")
        add(f"## {T['views']}")
        for v in d.views:
            add(f"- {v.id}: {v.kind} {v.paper} {v.orientation}" + (f" root={v.root}" if v.root else "") +
                (f" {json.dumps(v.title, ensure_ascii=False)}" if v.title else ""))

    if findings:
        res = check(d)
        add("")
        lv = Counter(f.level for f in res)
        add(f"## {T['findings']}: " + (", ".join(f"{lv[k]} {k}" for k in ("error", "warning", "info") if lv[k])
                                       or T["no_findings"]))
        order = {"error": 0, "warning": 1, "info": 2}
        shown = sorted(res, key=lambda f: order[f.level])[:max_findings]
        for f in shown:
            add(f"- {f}")
        if len(res) > len(shown):
            add(f"- {T['more'].format(n=len(res) - len(shown))}")
    return "\n".join(L) + "\n"


def _feeders(board: NodeBase):
    """Outgoing circuits of a board: its children, looking through explicit busbars."""
    for c in board.children:
        if c.type == "busbar":  # type: ignore[attr-defined]
            yield from _feeders(c)
        else:
            yield c
