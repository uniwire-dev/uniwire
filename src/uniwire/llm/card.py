"""Reference card of the uniwire format for LLM assistants.

Everything that describes the format (document fields, node types and their fields, enumerations,
link kinds, interlock semantics, views, rule profiles) is read from the pydantic model, the type
registry and the rules engine, so the card follows the format as it evolves. Only the short prose
(principles, pitfalls) is written here, in English and French.
"""

from __future__ import annotations

import json
import types
import typing
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel

from ..i18n import normalize_lang
from ..model import FORMAT_VERSION, NODE_TYPES, SCHEMA_ID, Cable, Document, Installation, Interlock, Link, Meta, View
from ..model import base as _base
from ..model import document as _document
from ..model import nodes as _nodes
from ..registry import registry

Level = Literal["compact", "full"]

CATEGORY_ORDER = ["source", "measure", "protection", "switching", "control", "converter", "conductor", "container",
                  "connector", "load"]

#: Named enumerations of the model, shown once and referenced by name in field lists.
NAMED_ENUMS: dict[str, Any] = {
    "Poles": _base.Poles, "Curve": _base.Curve, "RcdType": _base.RcdType, "Phase": _base.Phase,
    "Status": _base.Status, "Earthing": _base.Earthing, "System": _base.System, "Material": _base.Material,
    "LinkKind": _document.LinkKind, "ModuleKind": _nodes.ModuleKind,
}

_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "title": "uniwire {version} reference card",
        "intro": "uniwire is an open JSON format for electrical installations, drawn as single-line and multi-line diagrams (files `*.uniwire.json`). "
                 "A document describes the installation as a power TREE (sources -> devices -> loads) plus "
                 "LINKS for everything that is not a parent/child feed. Layout is automatic: never give coordinates.",
        "skeleton": "Document skeleton",
        "principles": "Principles",
        "p_tree": "Each node is fed by its parent and feeds its `children` (list). Roots go in `sources`. "
                  "A node with several children is drawn as a busbar; a `board` frames its whole subtree.",
        "p_links": "Anything outside the tree (2nd source on a transfer switch, bus tie, control/trip/measure wiring, "
                   "data bus, earth bonding, key interlock) is a `links` entry `{kind, from, to}` using node ids.",
        "p_ids": "`id` = stable machine identifier (pattern `^[A-Za-z_][A-Za-z0-9_.-]*$`, unique, generated from "
                 "`ref` or type when missing); links, enclosures, `view.root` and `frames` reference ids. "
                 "`ref` = displayed tag (`-Q1`, `KM1`), may repeat across boards.",
        "p_units": "Quantities are plain numbers in the unit given by the field-name suffix: `in_A: 16`, "
                   "`idn_mA: 30`, `section_mm2: 2.5`, `p_kW: 3.6`, `un_V: 400`, `length_m: 25`.",
        "p_cable": "`cable` on a node = the cable run from its parent to this node "
                   "(`{cores: \"3G\", section_mm2: 2.5, material, length_m, designation, install}`).",
        "p_templates": "`templates` holds named attribute sets; a node with `use: \"C16\"` inherits them "
                       "(its own fields win; the template `type` must match).",
        "p_strict": "Unknown fields are rejected (typos fail). Put vendor data in `ext: {vendor: {...}}`.",
        "common": "Fields common to every node",
        "protective": "Extra fields common to switching/protective devices (marked *)",
        "loadcommon": "Extra fields common to loads (marked +)",
        "types": "Node types by category (`type` label: specific fields)",
        "enums": "Enumerations",
        "links": "Links",
        "interlocks": "Interlocks and locks",
        "i_locks": "A node or link lists the keys it engages in `locks: [\"K1\"]`; `interlocks: [{key, keys, kind}]` "
                   "declares how many members sharing a key may be closed at once (default 1 = mutually exclusive). "
                   "`normal_state` (nodes) / `normally_open` (links) give the normal position.",
        "views": "Views (optional; rendering preferences)",
        "profiles": "Rule profiles (`profiles`; `core` always applies)",
        "nfc_note": "French installations (NF C 15-100); set `installation.premises`: the rules of dwellings (part 7-771) "
                    "apply only to `dwelling` or when it is absent",
        "enedis_note": "connection to the French public network (Enedis, NF C 14-100): connection power, service "
                       "main breaker (AGCP) setting, PV injection limits; combine with `nfc15100`",
        "pitfalls": "Common pitfalls",
        "pit": "\n".join([
            "- `children` is always a list of node objects; never put ids there. Links use ids, not refs.",
            "- Never write units in values (`\"16 A\"`): use the suffixed field (`in_A: 16`); "
            "RCD sensitivity is `idn_mA` (30, not 0.03).",
            "- `curve` belongs to breaker/rcbo, `rcd_type` to rcd/rcbo/main_breaker, `idn_mA` to residual-current "
            "devices; `poles` uses the Poles enum (\"1P+N\", not \"2 poles\").",
            "- Single-phase circuits on a three-phase network: set `phase` (L1/L2/L3).",
            "- Cable cross-section goes in `cable.section_mm2`, cores in `cable.cores` without the section "
            "(\"3G\", \"5G\", \"4x\").",
            "- A transfer switch receives its 2nd source through a link `{kind: \"transfer\", from: <source id>, "
            "to: <transfer_switch id>}`; the 2nd source is another root of `sources`.",
            "- Give an explicit `id` to every node you will reference (links, patches). Keep ids stable when editing.",
            "- Auxiliary devices outside the power tree (relays, CTs, IMDs) go in `devices` and connect through links.",
        ]),
        "examples": "Examples",
        "ex1": "Minimal dwelling board",
        "ex2": "Normal/standby supply with transfer switch",
        "fields": "fields",
        "desc_doc": "Top-level keys (only `sources` is required):",
        "k_links": "links outside the tree (see Links)",
        "k_views": "rendering preferences (see Views)",
        "other": "Other objects",
    },
    "fr": {
        "title": "Fiche de référence uniwire {version}",
        "intro": "uniwire est un format JSON ouvert pour les installations électriques, dessinées en schémas unifilaires et multifilaires (fichiers "
                 "`*.uniwire.json`). Un document décrit l'installation comme un ARBRE de puissance (sources -> "
                 "appareils -> récepteurs) plus des LIENS (`links`) pour tout ce qui n'est pas une alimentation "
                 "parent/enfant. La mise en page est automatique : ne jamais donner de coordonnées.",
        "skeleton": "Squelette du document",
        "principles": "Principes",
        "p_tree": "Chaque nœud est alimenté par son parent et alimente ses `children` (liste). Les racines vont "
                  "dans `sources`. Un nœud à plusieurs enfants est dessiné en jeu de barres ; un `board` (tableau) "
                  "encadre tout son sous-arbre.",
        "p_links": "Ce qui sort de l'arbre (2e source sur un inverseur, couplage, filerie de commande/déclenchement/"
                   "mesure, bus de données, liaison de terre, verrouillage à clé) est une entrée `links` "
                   "`{kind, from, to}` utilisant les ids des nœuds.",
        "p_ids": "`id` = identifiant machine stable (motif `^[A-Za-z_][A-Za-z0-9_.-]*$`, unique, généré depuis `ref` "
                 "ou le type s'il manque) ; liens, enveloppes, `view.root` et `frames` référencent des ids. "
                 "`ref` = repère affiché (`-Q1`, `KM1`), peut se répéter d'un tableau à l'autre.",
        "p_units": "Les grandeurs sont des nombres dans l'unité donnée par le suffixe du nom de champ : `in_A: 16`, "
                   "`idn_mA: 30`, `section_mm2: 2.5`, `p_kW: 3.6`, `un_V: 400`, `length_m: 25`.",
        "p_cable": "`cable` sur un nœud = la canalisation entre son parent et ce nœud "
                   "(`{cores: \"3G\", section_mm2: 2.5, material, length_m, designation, install}`).",
        "p_templates": "`templates` contient des jeux d'attributs nommés ; un nœud avec `use: \"C16\"` en hérite "
                       "(ses propres champs priment ; le `type` du modèle doit correspondre).",
        "p_strict": "Les champs inconnus sont refusés (les fautes de frappe échouent). Données propriétaires dans "
                    "`ext: {fournisseur: {...}}`.",
        "common": "Champs communs à tous les nœuds",
        "protective": "Champs supplémentaires communs à l'appareillage (marqué *)",
        "loadcommon": "Champs supplémentaires communs aux récepteurs (marqué +)",
        "types": "Types de nœuds par catégorie (`type` libellé : champs propres)",
        "enums": "Énumérations",
        "links": "Liens",
        "interlocks": "Verrouillages (interlocks et locks)",
        "i_locks": "Un nœud ou un lien liste les clés qu'il engage dans `locks: [\"K1\"]` ; `interlocks: "
                   "[{key, keys, kind}]` déclare combien de membres partageant une clé peuvent être fermés en même "
                   "temps (1 par défaut = exclusion mutuelle). `normal_state` (nœuds) / `normally_open` (liens) "
                   "donnent la position normale.",
        "views": "Vues (facultatives ; préférences de rendu)",
        "profiles": "Profils de règles (`profiles` ; `core` s'applique toujours)",
        "nfc_note": "installations françaises (NF C 15-100) ; préciser `installation.premises` : les règles du logement "
                    "(partie 7-771) ne s'appliquent qu'à `dwelling` ou en son absence",
        "enedis_note": "raccordement au réseau public français (Enedis, NF C 14-100) : puissance de raccordement, "
                       "réglage du disjoncteur de branchement (AGCP), limites d'injection photovoltaïque ; à combiner "
                       "avec `nfc15100`",
        "pitfalls": "Pièges courants",
        "pit": "\n".join([
            "- `children` est toujours une liste d'objets nœuds ; jamais d'ids. Les liens utilisent les ids, pas "
            "les repères.",
            "- Jamais d'unité dans les valeurs (`\"16 A\"`) : utiliser le champ suffixé (`in_A: 16`) ; la "
            "sensibilité différentielle est `idn_mA` (30, pas 0.03).",
            "- `curve` concerne breaker/rcbo, `rcd_type` rcd/rcbo/main_breaker, `idn_mA` les dispositifs "
            "différentiels ; `poles` suit l'énumération Poles (\"1P+N\", pas \"bipolaire\").",
            "- Circuits monophasés sur réseau triphasé : renseigner `phase` (L1/L2/L3).",
            "- La section va dans `cable.section_mm2`, la composition dans `cable.cores` sans la section "
            "(\"3G\", \"5G\", \"4x\").",
            "- Un inverseur de sources reçoit sa 2e source par un lien `{kind: \"transfer\", from: <id source>, "
            "to: <id transfer_switch>}` ; la 2e source est une autre racine de `sources`.",
            "- Donner un `id` explicite à tout nœud référencé (liens, patchs). Garder les ids stables en édition.",
            "- Les appareils annexes hors arbre de puissance (relais, TC, CPI) vont dans `devices` et se "
            "raccordent par des liens.",
        ]),
        "examples": "Exemples",
        "ex1": "Tableau de logement minimal",
        "ex2": "Alimentation normal/secours avec inverseur",
        "fields": "champs",
        "desc_doc": "Clés de premier niveau (seule `sources` est obligatoire) :",
        "k_links": "liens hors arbre (voir Liens)",
        "k_views": "préférences de rendu (voir Vues)",
        "other": "Autres objets",
    },
}

# ------------------------------------------------------------------ introspection helpers


def _unwrap(ann: Any) -> Any:
    """Strip Optional / Annotated wrappers."""
    while True:
        origin = get_origin(ann)
        if origin is typing.Annotated:
            ann = get_args(ann)[0]
        elif origin in (typing.Union, types.UnionType):
            args = [a for a in get_args(ann) if a is not type(None)]
            if len(args) != 1:
                return ann
            ann = args[0]
        elif hasattr(ann, "__value__") and type(ann).__name__ == "TypeAliasType":
            ann = ann.__value__
        else:
            return ann


def _enum_name(values: tuple) -> str | None:
    for name, lit in NAMED_ENUMS.items():
        if tuple(get_args(lit)) == tuple(values):
            return name
    return None


def field_spec(name: str, field: Any, *, inline_max: int = 7) -> str:
    """Compact field notation: ``curve(B|C|D)``, ``poles(Poles)``, ``aux[]``, ``selective:bool``, ``in_A``."""
    ann = _unwrap(field.annotation)
    origin = get_origin(ann)
    is_list = origin is list
    if is_list:
        ann = _unwrap(get_args(ann)[0])
        origin = get_origin(ann)
    if origin is Literal:
        values = get_args(ann)
        named = _enum_name(values)
        inner = named if named else "|".join(str(v) for v in values) if len(values) <= inline_max else \
            "|".join(str(v) for v in values[:inline_max]) + "|…"
        return f"{name}{'[]' if is_list else ''}({inner})"
    if is_list:
        return f"{name}[]"
    if ann is bool:
        return f"{name}:bool"
    if ann is int:
        return f"{name}:int"
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return f"{name}{{}}"
    return name


def own_fields(cls: type[BaseModel], parent: type[BaseModel]) -> dict[str, Any]:
    """Fields that ``cls`` adds to ``parent`` (``type`` excluded)."""
    return {k: f for k, f in cls.model_fields.items() if k not in parent.model_fields and k != "type"}


def _group_base(cls: type) -> tuple[type, str]:
    if issubclass(cls, _nodes._Protective):
        return _nodes._Protective, "*"
    if issubclass(cls, _nodes._Load):
        return _nodes._Load, "+"
    return _nodes.NodeBase, ""


def _alias(name: str, field: Any) -> str:
    return field.alias or name


def _fields_line(cls: type[BaseModel], parent: type[BaseModel] | None = None, skip: tuple[str, ...] = ("ext",)) -> str:
    fields = cls.model_fields.items() if parent is None else own_fields(cls, parent).items()
    return ", ".join(field_spec(_alias(k, f), f) for k, f in fields if k not in skip)


def _inner_description(ann: Any) -> str | None:
    """Description carried by a ``Field`` nested in the annotation (``Optional[Q("A", "...")]``)."""
    from pydantic.fields import FieldInfo

    if get_origin(ann) is typing.Annotated:
        for meta in get_args(ann)[1:]:
            if isinstance(meta, FieldInfo) and meta.description:
                return meta.description
        return _inner_description(get_args(ann)[0])
    if get_origin(ann) in (typing.Union, types.UnionType):
        for a in get_args(ann):
            d = _inner_description(a)
            if d:
                return d
    return None


def field_description(field: Any) -> str:
    """Description of a model field, also found in a ``Field`` nested in its annotation."""
    d = field.description or _inner_description(field.annotation) or ""
    return "" if d.startswith("in ") and len(d.split()) == 2 else d  # Q()'s default "in A" adds nothing


def _desc(field: Any) -> str:
    return field_description(field).replace("\n", " ")


def _doc(cls: type) -> str:
    return " ".join((cls.__doc__ or "").split())


def types_by_category() -> dict[str, list[str]]:
    """Node type names grouped by registry category, in the card's category order."""
    reg = registry()["types"]
    out: dict[str, list[str]] = {}
    for t in NODE_TYPES:
        out.setdefault(reg.get(t, {}).get("category", "other"), []).append(t)
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    return dict(sorted(out.items(), key=lambda kv: order.get(kv[0], 99)))


def type_label(type_: str, lang: str) -> str:
    """Label of a node type in ``lang`` (registry), falling back to English, then to the type name."""
    labels = registry()["types"].get(type_, {}).get("label", {})
    return labels.get(lang) or labels.get("en") or type_


def type_info(type_: str, lang: str = "en") -> dict[str, Any]:
    """Machine-readable description of a node type: category, label, docstring, fields (with enums)."""
    if type_ not in NODE_TYPES:
        raise KeyError(type_)
    cls = NODE_TYPES[type_]
    reg = registry()["types"].get(type_, {})
    fields: dict[str, Any] = {}
    for k, f in cls.model_fields.items():
        if k in ("type", "children", "ext"):
            continue
        ann = _unwrap(f.annotation)
        item: dict[str, Any] = {"spec": field_spec(_alias(k, f), f, inline_max=99)}
        if field_description(f):
            item["description"] = field_description(f)
        if get_origin(ann) is Literal:
            item["enum"] = list(get_args(ann))
        base, _ = _group_base(cls)
        item["group"] = ("specific" if k not in base.model_fields else
                         "common" if k in _nodes.NodeBase.model_fields else
                         "protective" if base is _nodes._Protective else "load")
        fields[_alias(k, f)] = item
    return {"type": type_, "category": reg.get("category"), "label": type_label(type_, lang),
            "iec81346_letter": reg.get("iec81346"), "description": _doc(cls), "fields": fields}


def list_types(category: str | None = None, lang: str = "en") -> list[dict[str, str]]:
    """``[{type, category, label}]`` for every node type, or those of ``category``."""
    out = []
    for cat, names in types_by_category().items():
        if category and cat != category:
            continue
        out.extend({"type": t, "category": cat, "label": type_label(t, lang)} for t in names)
    return out


# ------------------------------------------------------------------ examples

EXAMPLE_HOUSE: dict[str, Any] = {
    "uniwire": FORMAT_VERSION,
    "profiles": ["nfc15100"],
    "meta": {"title": "Small flat", "lang": "en"},
    "installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
    "templates": {"C16": {"type": "breaker", "in_A": 16, "curve": "C", "poles": "1P+N"}},
    "sources": [{"type": "grid", "id": "grid", "children": [
        {"type": "main_breaker", "id": "Q0", "ref": "-Q0", "in_A": 45, "idn_mA": 500, "selective": True,
         "children": [{"type": "board", "id": "TD", "ref": "TD", "children": [
             {"type": "rcd", "id": "F1", "ref": "-F1", "in_A": 40, "idn_mA": 30, "rcd_type": "A", "children": [
                 {"type": "breaker", "id": "Q11", "ref": "-Q11", "use": "C16",
                  "cable": {"cores": "3G", "section_mm2": 1.5},
                  "children": [{"type": "lighting", "id": "L1", "label": "Lighting", "points": 6}]},
                 {"type": "breaker", "id": "Q12", "ref": "-Q12", "in_A": 20, "curve": "C", "poles": "1P+N",
                  "cable": {"cores": "3G", "section_mm2": 2.5},
                  "children": [{"type": "socket", "id": "S1", "label": "Sockets", "points": 8}]}]}]}]}]}],
}

EXAMPLE_STANDBY: dict[str, Any] = {
    "uniwire": FORMAT_VERSION,
    "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
    "sources": [
        {"type": "grid", "id": "grid", "children": [
            {"type": "transfer_switch", "id": "ATS", "ref": "-QA1", "in_A": 125, "poles": "4P", "mode": "automatic",
             "children": [{"type": "board", "id": "DB", "ref": "DB1", "children": [
                 {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 32, "curve": "C", "poles": "4P",
                  "cable": {"cores": "5G", "section_mm2": 6, "length_m": 30},
                  "children": [{"type": "motor", "id": "M1", "label": "Pump", "p_kW": 11}]},
                 {"type": "breaker", "id": "Q2", "ref": "-Q2", "in_A": 16, "curve": "C", "poles": "1P+N",
                  "phase": "L2", "children": [{"type": "lighting", "id": "L1", "label": "Lighting"}]}]}]}]},
        {"type": "generator", "id": "G1", "ref": "G1", "sn_kVA": 60}],
    "links": [{"kind": "transfer", "from": "G1", "to": "ATS"}],
}


def _json_compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------ card


def card(lang: str = "en", level: Level = "compact") -> str:
    """Reference card of the format (Markdown), generated from the model, the registry and the rules.

    ``level="compact"`` (~3k tokens) lists every type with its field names; ``"full"`` adds field
    descriptions, docstrings and enumerations in full.
    """
    from ..rules import PROFILES, RULE_INFO

    lang = normalize_lang(lang)
    T = _TEXT.get(lang, _TEXT["en"])
    full = level == "full"
    L: list[str] = []
    add = L.append

    add(f"# {T['title'].format(version=FORMAT_VERSION)}")
    add("")
    add(T["intro"])
    add("")

    # --- skeleton
    add(f"## {T['skeleton']}")
    add(T["desc_doc"])
    for k, f in Document.model_fields.items():
        if k == "ext":
            continue
        name = _alias(k, f)
        if name == "meta":
            add(f"- `meta`: {_fields_line(Meta)}")
        elif name == "installation":
            add(f"- `installation`: {_fields_line(Installation)}")
        elif name == "uniwire":
            add(f"- `uniwire`: \"{FORMAT_VERSION}\"")
        elif name == "$schema":
            add(f"- `$schema`: \"{SCHEMA_ID}\"")
        else:
            add(f"- `{name}`: " + (_desc(f) or T.get("k_" + name, "")))
    add("")

    # --- principles
    add(f"## {T['principles']}")
    for key in ("p_tree", "p_links", "p_ids", "p_units", "p_cable", "p_templates", "p_strict"):
        add(f"- {T[key]}")
    add(f"- `cable` {T['fields']}: {_fields_line(Cable)}")
    add("")

    # --- node fields
    add(f"## {T['common']}")
    add(_fields_line(_nodes.NodeBase, skip=("ext", "children")) + ", children[]")
    add("")
    add(f"{T['protective']}: {_fields_line(_nodes._Protective, _nodes.NodeBase)}")
    add(f"{T['loadcommon']}: {_fields_line(_nodes._Load, _nodes.NodeBase)}")
    add("")

    add(f"## {T['types']}")
    for cat, names in types_by_category().items():
        add(f"### {cat}")
        for t in names:
            cls = NODE_TYPES[t]
            parent, mark = _group_base(cls)
            own = own_fields(cls, parent)
            if full:
                doc = _doc(cls)
                head = f"- `{t}`{mark}: {type_label(t, lang)}" + (f". {doc}" if doc else "")
                add(head)
                for k, f in own.items():
                    d = _desc(f)
                    add(f"  - {field_spec(_alias(k, f), f, inline_max=99)}" + (f": {d}" if d else ""))
            else:
                fl = ", ".join(field_spec(_alias(k, f), f) for k, f in own.items())
                add(f"- `{t}`{mark} {type_label(t, lang)}" + (f": {fl}" if fl else ""))
    add("")

    # --- other objects
    add(f"## {T['other']}")
    add(f"- `product{{}}` (node): {_fields_line(_base.Product)}")
    add(f"- `plc.modules[]` / `plc.onboard[]`: {_fields_line(_nodes.PLCModule)}")
    add(f"- `enclosures[]`: {_fields_line(_document.Enclosure)}")
    if full:
        add(f"  {_doc(_document.Enclosure)}")
        add(f"- `views[].frames[]`: {_fields_line(_document.Frame)}")
        add(f"  {_doc(_document.Frame)}")
    add("")

    # --- enums
    add(f"## {T['enums']}")
    for name, lit in NAMED_ENUMS.items():
        add(f"- {name}: {' | '.join(str(v) for v in get_args(lit))}")
    add("")

    # --- links
    add(f"## {T['links']}")
    if full:
        add(_doc(Link))
    else:
        add("`kind` (LinkKind): transfer = 2nd source -> transfer_switch; tie = bus coupling (`device`); "
            "bypass/parallel/infeed = extra power path; control/interlock/trip/measure = dashed control wiring; "
            "data = bus (`protocol`); earth = PE/bonding; key = key interlock (`key`).")
    add(f"{T['fields']}: {_fields_line(Link)}")
    add("")

    # --- interlocks
    add(f"## {T['interlocks']}")
    add(T["i_locks"])
    add(f"`interlocks[]` {T['fields']}: {_fields_line(Interlock)}")
    if full:
        add(_doc(Interlock))
    add("")

    # --- views
    add(f"## {T['views']}")
    view_fields = View.model_fields if full else {k: View.model_fields[k] for k in (
        "id", "kind", "title", "root", "paper", "orientation", "cartouche")}
    add(", ".join(field_spec(k, f, inline_max=99 if k != "cartouche" else 7) for k, f in view_fields.items()
                  if k != "ext"))
    if full:
        cart = get_args(_unwrap(View.model_fields["cartouche"].annotation))
        add("cartouche values: " + ", ".join(str(v) for v in get_args(_unwrap(cart[0]))))
    add("")

    # --- profiles
    add(f"## {T['profiles']}")
    for p, rules in PROFILES.items():
        names = sorted({n for n in RULE_INFO if n.split(".")[0] == p})
        line = f"- `{p}`: {len(rules)} rule(s)"
        if p == "nfc15100":
            line += f"; {T['nfc_note']}"
        elif p == "enedis":
            line += f"; {T['enedis_note']}"
        if full and names:
            line += " (" + ", ".join(names) + ")"
        add(line)
    add("")

    # --- pitfalls
    add(f"## {T['pitfalls']}")
    add(T["pit"])
    add("")

    # --- examples
    add(f"## {T['examples']}")
    add(f"{T['ex1']}:")
    add("```json")
    add(_json_compact(EXAMPLE_HOUSE))
    add("```")
    add(f"{T['ex2']}:")
    add("```json")
    add(_json_compact(EXAMPLE_STANDBY))
    add("```")
    return "\n".join(L) + "\n"


def approx_tokens(text: str) -> int:
    """Rough token count (about 4 characters per token)."""
    return (len(text) + 3) // 4
