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
        for f in _RANGE_FIELDS:
            v = n.get(f)
            if isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                           for x in v):
                new = f"{v[0]:g}-{v[1]:g}"
                self.note(where, f, v, new)
                n[f] = new
        cable = n.get("cable")
        if isinstance(cable, dict):
            self.cable(cable, where)
        children = n.get("children")
        if isinstance(children, list):
            for i, c in enumerate(children):
                self.node(c, f"{path}/children/{i}")

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


def _meta_fields() -> set[str]:
    from .model.base import Meta

    return set(Meta.model_fields)


def tolerate(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """A copy of ``data`` with unambiguous near-miss values in canonical form, and one note per change."""
    if not isinstance(data, dict):
        return data, []
    out = copy.deepcopy(data)
    tol = _Tolerance()
    tol.document(out)
    return out, tol.notes
