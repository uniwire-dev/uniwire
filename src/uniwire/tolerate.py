"""Tolerance for near-miss values, applied before validation.

Documents written by hand or by language models often say ``"poles": 2`` for ``"2P"`` or ``"cores": "3G2.5"``
for ``{"cores": "3G", "section_mm2": 2.5}``. When the intended value is unambiguous, :func:`tolerate` rewrites it
to the canonical form and records a note; the rule ``core.normalized`` reports each note as a warning, and
``uniwire normalize`` writes the canonical document. Anything ambiguous is left alone for validation to reject.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .i18n import t as _t

_POLES = {"1P", "1P+N", "2P", "3P", "3P+N", "4P"}
_CORES_WITH_SECTION = re.compile(r"^\s*(\d+)\s*([GgXx])\s*(\d+(?:[.,]\d+)?)\s*(?:mm2|mm²)?\s*$")
_RANGE_FIELDS = ("range_A", "idn_range_mA")
#: A voltage with its current kind in the unit ("24 V DC", "230VAC", "24 Vdc"): the number and unit are kept, the kind
#: dropped (a coil's kind is not the kind of the circuit the device is on, so it is not carried to another field)
_VOLTS_WITH_KIND = re.compile(r"^\s*(\d+(?:[.,]\d+)?\s*[kmµu]?V)\s*(?:[ ._-]?\s*)(?:DC|AC|d\.?c\.?|a\.?c\.?|=|~)\s*$",
                              re.IGNORECASE)
#: Fields whose values are a few whole numbers: lax validation reads "16" as 16 elsewhere, not for these
_INT_CHOICES = {"phases": (1, 3)}
#: Revision columns under the names of a drawing's revision table, read as the format's names
_REVISION_FIELDS = {"rev": "index", "revision": "index", "note": "description", "by": "author"}
#: PLC module kinds written in full, read as the format's short kinds
_MODULE_KINDS = {
    "digital_input": "di", "digital_inputs": "di", "digital_in": "di",
    "digital_output": "do", "digital_outputs": "do", "digital_out": "do",
    "analog_input": "ai", "analog_inputs": "ai", "analogue_input": "ai", "analogue_inputs": "ai", "analog_in": "ai",
    "analog_output": "ao", "analog_outputs": "ao", "analogue_output": "ao", "analogue_outputs": "ao",
    "analog_out": "ao",
    "relay_output": "relay_out", "relay_outputs": "relay_out",
    "mixed": "mixed_io", "mixed_input_output": "mixed_io", "digital_io": "mixed_io",
    "communication": "comm",
}


def _poles(v: Any) -> Any:
    """Canonical poles value for ``v``, or ``v`` unchanged."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and 1 <= v <= 4:
        return f"{v}P"
    if isinstance(v, str):
        s = v.strip().upper().replace(" ", "")
        if s.isdigit() and 1 <= int(s) <= 4:
            s += "P"
        if s in _POLES:
            return s
    return v


def _number(s: str) -> float | int:
    x = float(s.replace(",", "."))
    return int(x) if x.is_integer() else x


class _Tolerance:
    def __init__(self) -> None:
        self.notes: list[str] = []

    def note(self, where: str, field: str, old: Any, new: Any) -> None:
        self.notes.append(_t("core.normalized", where=where, field=field, old=old, new=new))

    def moved(self, where: str, old: str, new: str) -> None:
        self.notes.append(_t("core.normalized_field", where=where, old=old, new=new))

    def node(self, n: Any, path: str) -> None:
        if not isinstance(n, dict):
            return
        where = str(n.get("id") or path)
        if "poles" in n:
            new = _poles(n["poles"])
            if new != n["poles"]:
                self.note(where, "poles", n["poles"], new)
                n["poles"] = new
        for f, v in list(n.items()):
            if f.endswith("_V") and isinstance(v, str):
                m = _VOLTS_WITH_KIND.match(v)
                if m:
                    new = re.sub(r"\s+", " ", m.group(1))
                    self.note(where, f, v, new)
                    n[f] = new
        for f, choices in _INT_CHOICES.items():
            v = n.get(f)
            if isinstance(v, str) and re.fullmatch(r"\s*\d+\s*", v) and int(v) in choices:
                self.note(where, f, v, int(v))
                n[f] = int(v)
        for f in _RANGE_FIELDS:
            v = n.get(f)
            if isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                           for x in v):
                new = f"{v[0]:g}-{v[1]:g}"
                self.note(where, f, v, new)
                n[f] = new
        for f in ("onboard", "modules"):
            mods = n.get(f)
            if n.get("type") == "plc" and isinstance(mods, list):
                for i, m in enumerate(mods):
                    if isinstance(m, dict):
                        self.module_kind(m, f"{where}/{f}/{i}")
        cable = n.get("cable")
        if isinstance(cable, dict):
            self.cable(cable, where)
        children = n.get("children")
        if isinstance(children, list):
            for i, c in enumerate(children):
                self.node(c, f"{path}/children/{i}")

    def link_devices(self, d: dict[str, Any]) -> None:
        """A link's ``device`` written as the id or ref of a top-level ``devices`` entry: that node, moved onto the link.

        Only when the text names exactly one node of the document, that node stands alone under ``devices`` (no parent
        in the tree, so moving it changes nothing else) and no other link names it; otherwise validation explains.
        """
        links = [lk for lk in d.get("links") or [] if isinstance(lk, dict) and isinstance(lk.get("device"), str)]
        devices = d.get("devices")
        if not links or not isinstance(devices, list):
            return
        named: dict[str, list[Any]] = {}

        def walk(n: Any) -> None:
            if isinstance(n, dict):
                for key in {n.get("id"), n.get("ref")} - {None}:
                    if isinstance(key, str):
                        named.setdefault(key, []).append(n)
                for c in n.get("children") or []:
                    walk(c)

        for top in (*(d.get("sources") or []), *devices):
            walk(top)
        uses: dict[str, int] = {}
        for lk in links:
            uses[lk["device"]] = uses.get(lk["device"], 0) + 1
        for i, lk in enumerate(d.get("links") or []):
            text = lk.get("device") if isinstance(lk, dict) else None
            if not isinstance(text, str) or uses[text] != 1:
                continue
            nodes = named.get(text.strip(), [])
            if len(nodes) == 1 and any(nodes[0] is x for x in devices):
                devices[:] = [x for x in devices if x is not nodes[0]]
                lk["device"] = nodes[0]
                self.note(str(lk.get("id") or f"links/{i}"), "device", text, f"the node {text.strip()} of 'devices'")

    def module_kind(self, m: dict[str, Any], where: str) -> None:
        k = m.get("kind")
        if not isinstance(k, str):
            return
        new = re.sub(r"[\s\-/]+", "_", k.strip().lower())
        new = _MODULE_KINDS.get(new, new)
        if new != k and new in _module_kinds():
            self.note(where, "kind", k, new)
            m["kind"] = new

    def revision(self, r: dict[str, Any], where: str) -> None:
        for old, new in _REVISION_FIELDS.items():
            if old in r and new not in r and old not in _revision_fields():
                r[new] = r.pop(old)
                self.moved(where, old, new)

    def cable(self, c: dict[str, Any], where: str) -> None:
        v = c.get("cores")
        if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 61:
            new = f"{v}G"  # a cable with a count only: conductors including the protective one (French "G")
            self.note(where, "cable.cores", v, new)
            c["cores"] = new
        elif isinstance(v, str):
            m = _CORES_WITH_SECTION.match(v)
            if m:
                count, letter, section = m.groups()
                new = f"{count}{letter.upper() if letter in 'gG' else 'x'}"
                if "section_mm2" not in c:
                    c["section_mm2"] = _number(section)
                    self.note(where, "cable.cores", v, f"{new} + section_mm2 {c['section_mm2']}")
                else:
                    self.note(where, "cable.cores", v, new)
                c["cores"] = new

    def document(self, d: dict[str, Any]) -> None:
        for i, s in enumerate(d.get("sources") or []):
            self.node(s, f"sources/{i}")
        for i, s in enumerate(d.get("devices") or []):
            self.node(s, f"devices/{i}")
        self.link_devices(d)
        for i, lk in enumerate(d.get("links") or []):
            if isinstance(lk, dict):
                self.node(lk.get("device"), f"links/{i}/device")
        for name, tpl in (d.get("templates") or {}).items():
            if isinstance(tpl, dict):
                self.node(tpl, f"templates/{name}")
        meta = d.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("description"), str) and "description" not in _meta_fields():
            text = meta.pop("description")
            notes = meta.get("notes")
            meta["notes"] = ([*notes] if isinstance(notes, list) else []) + [text]
            self.moved("meta", "description", "notes")
        revisions = meta.get("revisions") if isinstance(meta, dict) else None
        for i, r in enumerate(revisions if isinstance(revisions, list) else []):
            if isinstance(r, dict):
                self.revision(r, f"meta/revisions/{i}")
        for i, v in enumerate(d.get("views") or []):
            if not isinstance(v, dict):
                continue
            where = str(v.get("id") or f"views/{i}")
            if "kind" not in v and isinstance(v.get("type"), str):
                v["kind"] = v.pop("type")
                self.moved(where, "type", "kind")
            k = v.get("kind")
            if isinstance(k, str):
                new = k.strip().lower().replace("_", "-").replace(" ", "-")
                new = {"singleline": "single-line", "multiline": "multi-line"}.get(new, new)
                if new != k and new in ("single-line", "multi-line"):
                    self.note(where, "kind", k, new)
                    v["kind"] = new
            p = v.get("pitch_mm")
            if isinstance(p, (int, float)) and not isinstance(p, bool) and 0 < p < _pitch_min():
                self.note(where, "pitch_mm", p, _pitch_min())  # narrower than a feeder column can be: the narrowest
                v["pitch_mm"] = _pitch_min()


def _meta_fields() -> set[str]:
    from .model.base import Meta

    return set(Meta.model_fields)


def _revision_fields() -> set[str]:
    from .model.base import Revision

    return set(Revision.model_fields)


def _module_kinds() -> tuple[str, ...]:
    from typing import get_args

    from .model.nodes import ModuleKind

    return get_args(ModuleKind)


def tolerate(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """A copy of ``data`` with unambiguous near-miss values in canonical form, and one note per change."""
    if not isinstance(data, dict):
        return data, []
    out = copy.deepcopy(data)
    tol = _Tolerance()
    tol.document(out)
    return out, tol.notes


def _pitch_min() -> int:
    """Narrowest feeder column of a view (``pitch_mm``): a narrower one is read as this."""
    from .model.document import View

    return int(next(m.ge for m in View.model_fields["pitch_mm"].metadata if getattr(m, "ge", None) is not None))
