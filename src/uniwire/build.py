"""Schematics as code: a fluent, build123d-style Python API for uniwire.

    from uniwire.build import *

    with Installation("House", earthing="TT", system="1P+N", un="230 V", profiles=["nfc15100"]) as inst:
        with Grid("Utility"), MainBreaker("-Q0", "15-45 A", idn="500 mA", selective=True), Board("TD1"):
            Breaker("-F0", "C25") >> SPD(type="2")
            with RCD("-Q1", "40 A", "30 mA", type="A"):
                Breaker("-Q11", "C20", cable="3G2,5") >> Appliance("Washing machine", kind="washing_machine")
                Breaker("-Q12", "C32", cable="3G6") >> Cooking("Hob", kind="hob", p="7.2 kW")

    inst.check()
    inst.save("house.uniwire.json")
    inst.render("house.pdf")

Rules of the game
-----------------
* ``with X:`` makes X the current parent: every element created inside is fed by X.
* ``a >> b`` moves ``b`` under ``a`` (and returns ``b``, so ``a >> b >> c`` builds a chain).
* An element created outside any parent becomes a source (root of the tree).
* Values accept units as strings (``"16 A"``, ``"2,5 mm²"``, ``"30 mA"``); the document stores canonical numbers.
* Every keyword argument that is a field of the uniwire type is passed through unchanged
  (``Breaker("-Q1", "C16", icn_kA=6, aux=["MX"])``).
"""

from __future__ import annotations

import contextvars
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional, Union

from .model import FORMAT_VERSION, NODE_TYPES, SCHEMA_ID, Document
from .resolve import load

__all__ = [  # completed at the bottom with every element class
    "Installation", "Enclosure", "Module", "Port",
    "control", "data", "transfer", "tie", "infeed", "earth", "interlock", "trip", "measure", "bypass", "link",
    "Template",
]

_INSTALLATION: contextvars.ContextVar[Optional[Installation]] = contextvars.ContextVar("uw_installation", default=None)
_PARENTS: contextvars.ContextVar[tuple[Element, ...]] = contextvars.ContextVar("uw_parents", default=())
_ENCLOSURES: contextvars.ContextVar[tuple[Enclosure, ...]] = contextvars.ContextVar("uw_enclosures", default=())

# Same language as '[-=+]?[A-Z][A-Z0-9]{0,4}[\d.\-_]*[A-Za-z0-9]*' but written without overlapping unbounded
# quantifiers (the digits that could open the last part are taken by the separator part), so matching is linear.
_REF_RE = re.compile(r"[-=+]?[A-Z][A-Z0-9]{0,4}[\d.\-_]*(?:[A-Za-z][A-Za-z0-9]*)?")
_MAX_SPEC_CHARS = 128  # longest reference / rating / cable shorthand parsed by the helpers below
_ID_CLEAN = re.compile(r"[^A-Za-z0-9_.\-]")


# --------------------------------------------------------------- parsing helpers
def _looks_like_ref(s: Any) -> bool:
    return (isinstance(s, str) and len(s) <= _MAX_SPEC_CHARS and (s[:1] in "-=+" or bool(_REF_RE.fullmatch(s)))
            and " " not in s)


def _rating(spec: Any) -> dict[str, Any]:
    """'C16' -> curve C, in_A 16 ; '16 A' / 16 -> in_A 16 ; 'gG 32 A' -> fuse_class gG, in_A 32."""
    if spec is None:
        return {}
    if isinstance(spec, (int, float)):
        return {"in_A": spec}
    s = str(spec).strip()
    if len(s) > _MAX_SPEC_CHARS:
        return {"in_A": s}  # rejected with a clear message by the quantity parser
    m = re.fullmatch(r"([BCDKZ])\s*(\d+(?:[.,]\d+)?)\s*A?", s, re.I)
    if m:
        return {"curve": m.group(1).upper(), "in_A": float(m.group(2).replace(",", "."))}
    m = re.fullmatch(r"(gG|aM|gL|gPV)\s*(\d+(?:[.,]\d+)?)\s*A?", s)
    if m:
        return {"fuse_class": m.group(1), "in_A": float(m.group(2).replace(",", "."))}
    return {"in_A": s}


def _cable(spec: Any, length: Any = None) -> Optional[dict[str, Any]]:
    """'3G2,5' -> cores 3G, section 2.5 ; '5G16 25 m' adds the length ; dicts pass through."""
    if spec is None and length is None:
        return None
    if isinstance(spec, dict):
        c = dict(spec)
    else:
        c = {}
        s = str(spec or "").strip()
        if len(s) > _MAX_SPEC_CHARS:
            raise ValueError(f"cable shorthand too long ({len(s)} characters, at most {_MAX_SPEC_CHARS})")
        # (?<!\d): a number is only tried from its first digit, which keeps the search linear (a match that
        # starts inside a run of digits also matches from the start of the run)
        m = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*m\b(?!m)", s)
        if m and length is None:
            length = m.group(1)
            s = (s[: m.start()] + s[m.end():]).strip()
        parts = s.split()
        if parts and not re.match(r"^\d", parts[0]):  # leading designation: 'U1000R2V 3G2,5'
            c["designation"] = parts.pop(0)
        s = " ".join(parts)
        m = re.fullmatch(r"(\d+\s*[GgXx×])\s*(\d+(?:[.,]\d+)?)", s)
        if m:
            c["cores"], c["section_mm2"] = m.group(1).upper().replace("X", "x"), float(m.group(2).replace(",", "."))
        elif re.fullmatch(r"\d+(?:[.,]\d+)?", s):
            c["section_mm2"] = float(s.replace(",", "."))
        elif s:
            c["cores"] = s
    if length is not None:
        c["length_m"] = length
    return c


_ALIASES = {  # short keyword -> field name (only applied when the type has that field)
    "p": "p_kW", "un": "un_V", "idn": "idn_mA", "icn": "icn_kA", "icu": "icu_kA", "sn": "sn_kVA",
    "u1": "u1_V", "u2": "u2_V", "ucc": "ucc_pct", "length": None, "in_": "in_A", "rating": "in_A",
    "capacity": "capacity_kWh", "surface": "surface_m2",
}


# ------------------------------------------------------------------- elements
class Element:
    """A uniwire node under construction."""

    type: str = ""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        inst = _INSTALLATION.get()
        if inst is None:
            raise RuntimeError("uniwire elements must be created inside `with Installation(...):`")
        self.installation = inst
        self.data: dict[str, Any] = {"type": self.type}
        self.children: list[Element] = []
        self.parent: Optional[Element] = None
        fields = NODE_TYPES[self.type].model_fields
        self._positional(list(args), fields)
        cable_spec = kwargs.pop("cable", None)
        length = kwargs.pop("length", None)
        annex = kwargs.pop("annex", False)
        for k, v in kwargs.items():
            name = k
            if k == "type":  # 'type' means the RCD / SPD type, never the node type
                name = {"rcd": "rcd_type", "rcbo": "rcd_type", "main_breaker": "rcd_type", "spd": "spd_type"}.get(
                    self.type, "kind")
            elif k not in fields:
                alias = _ALIASES.get(k)
                if k == "range" and "range_A" in fields:
                    name = "range_A"
                elif alias and alias in fields:
                    name = alias
                else:
                    raise TypeError(f"{type(self).__name__}: unknown field {k!r}")
            if name == "product" and isinstance(v, str):
                v = _product_from_str(v)
            self.data[name] = v
        cab = _cable(cable_spec, length)
        if cab:
            self.data["cable"] = cab
        self.id = inst._new_id(self)
        self.data["id"] = self.id
        for enc in _ENCLOSURES.get():
            enc.nodes.append(self.id)
        if annex:
            inst._devices.append(self)
        else:
            parents = _PARENTS.get()
            if parents:
                parents[-1]._adopt(self)
            else:
                inst._sources.append(self)

    # -- positional conventions per family
    def _positional(self, args: list[Any], fields: dict[str, Any]) -> None:
        if args and _looks_like_ref(args[0]) and "ref" in fields and self.type not in _LABEL_FIRST:
            self.data["ref"] = args.pop(0)
        if self.type in _LABEL_FIRST and args and isinstance(args[0], str):
            self.data["label"] = args.pop(0)
        if self.type in ("breaker", "rcbo", "fuse", "fuse_switch", "switch_disconnector", "disconnector",
                         "contactor", "impulse_relay", "motor_starter", "transfer_switch", "rcd", "socket",
                         "connector", "spare") and args:
            self.data.update(_rating(args.pop(0)))
        if self.type == "main_breaker" and args:
            r = str(args.pop(0)).replace(" A", "").replace("A", "")
            if "-" in r or "/" in r:
                self.data["range_A"] = r.replace("/", "-")
            else:
                self.data["in_A"] = r
        if self.type in ("rcd", "rcbo", "main_breaker") and args:
            self.data["idn_mA"] = args.pop(0)
        if args and isinstance(args[0], str) and "label" in fields and "label" not in self.data:
            self.data["label"] = args.pop(0)
        if args:
            raise TypeError(f"{type(self).__name__}: unexpected positional arguments {args!r}")

    def _adopt(self, child: Element) -> None:
        if child.parent is not None:
            child.parent.children.remove(child)
        elif child in self.installation._sources:
            self.installation._sources.remove(child)
        child.parent = self
        self.children.append(child)

    # -- context manager: becomes the current parent
    def __enter__(self) -> Element:
        self._token = _PARENTS.set(_PARENTS.get() + (self,))
        return self

    def __exit__(self, *exc: Any) -> None:
        _PARENTS.reset(self._token)

    def __rshift__(self, other: Element) -> Element:
        self._adopt(other)
        return other

    def to_dict(self) -> dict[str, Any]:
        """The node as a uniwire JSON object, children included (not validated)."""
        d = dict(self.data)
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.data.get('ref') or self.data.get('label') or self.id!r})"


_LABEL_FIRST = {"grid", "lighting", "socket", "heating", "water_heater", "cooking", "appliance", "motor", "ev_charger",
                "ventilation", "shutter", "load", "pv_array", "battery", "offpage"}


def _product_from_str(s: str) -> dict[str, str]:
    """'WAGO 750-8212' -> {'manufacturer': 'WAGO', 'part_number': '750-8212'}."""
    parts = s.rsplit(" ", 1)
    return {"manufacturer": parts[0], "part_number": parts[1]} if len(parts) == 2 else {"part_number": s}


# ------------------------------------------------------------------- PLC helpers
class Port:
    """A PLC channel: ``api.port(4, 1)`` or ``api[4][1]``."""

    def __init__(self, element: Element, slot: int, channel: Optional[int] = None) -> None:
        self.element, self.slot, self.channel = element, slot, channel

    def __getitem__(self, channel: int) -> Port:
        return Port(self.element, self.slot, channel)

    @property
    def name(self) -> str:
        """Port name used in ``from_port`` / ``to_port``: ``"slot.channel"`` (``"4.1"``), or ``"slot"``."""
        return f"{self.slot}.{self.channel}" if self.channel is not None else str(self.slot)


def Module(kind: str, part_number: Optional[str] = None, **kw: Any) -> dict[str, Any]:
    """A PLC module description (slot is assigned automatically by PLC.add)."""
    d: dict[str, Any] = {"kind": kind}
    if part_number:
        d["part_number"] = part_number
    d.update(kw)
    return d


# --------------------------------------------------------------- links & frames
def _end(x: Union[Element, Port, str]) -> tuple[str, Optional[str]]:
    if isinstance(x, Port):
        return x.element.id, x.name
    if isinstance(x, Element):
        return x.id, None
    return str(x), None


def link(kind: str, a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
         **kw: Any) -> dict[str, Any]:
    """Declare a link of ``kind`` from ``a`` to ``b`` in the current installation and return it.

    ``a`` and ``b`` are elements, PLC ports (``plc[3][1]``, which set ``from_port`` / ``to_port``) or node ids.
    Extra keyword arguments are link fields: ``device`` (an element, moved onto the link), ``cable`` (shorthand
    such as ``"4G2,5 25 m"`` or a dict), ``normally_open``, ``locks``... Must be called inside
    ``with Installation(...):``.
    """
    inst = _INSTALLATION.get()
    if inst is None:
        raise RuntimeError("links must be declared inside `with Installation(...):`")
    fa, pa = _end(a)
    fb, pb = _end(b)
    d: dict[str, Any] = {"kind": kind, "from": fa, "to": fb}
    if pa:
        d["from_port"] = pa
    if pb:
        d["to_port"] = pb
    if label:
        d["label"] = label
    if "device" in kw and isinstance(kw["device"], Element):
        dev = kw.pop("device")
        inst._detach(dev)
        d["device"] = dev.to_dict()
    if "cable" in kw:
        kw["cable"] = _cable(kw["cable"])
    d.update(kw)
    inst._links.append(d)
    return d


def control(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
            **kw: Any) -> dict[str, Any]:
    """Declare a control link (drawn dashed): a controller acting on a device (see :func:`link`)."""
    return link("control", a, b, label, **kw)


def data(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
         **kw: Any) -> dict[str, Any]:
    """Declare a communication link (bus, Modbus, teleinfo); ``protocol=`` names the protocol (see :func:`link`)."""
    return link("data", a, b, label, **kw)


def transfer(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
             **kw: Any) -> dict[str, Any]:
    """Declare a transfer link: a second source arriving on a transfer switch (``b``) (see :func:`link`)."""
    return link("transfer", a, b, label, **kw)


def tie(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
        **kw: Any) -> dict[str, Any]:
    """Declare a bus-tie link between two busbars; ``device=`` is the coupling device (see :func:`link`)."""
    return link("tie", a, b, label, **kw)


def infeed(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
           **kw: Any) -> dict[str, Any]:
    """Declare a infeed link: an additional supply to ``b`` (second incomer, ring, back-feed) (see :func:`link`)."""
    return link("infeed", a, b, label, **kw)


def earth(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
          **kw: Any) -> dict[str, Any]:
    """Declare a earth link: protective conductor or equipotential bonding (see :func:`link`)."""
    return link("earth", a, b, label, **kw)


def interlock(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
              **kw: Any) -> dict[str, Any]:
    """Declare a interlock link between two devices (drawn dashed) (see :func:`link`)."""
    return link("interlock", a, b, label, **kw)


def trip(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
         **kw: Any) -> dict[str, Any]:
    """Declare a trip link: a relay or protection tripping a device (see :func:`link`)."""
    return link("trip", a, b, label, **kw)


def measure(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
            **kw: Any) -> dict[str, Any]:
    """Declare a measurement link: an instrument transformer or meter feeding a relay or device (see :func:`link`)."""
    return link("measure", a, b, label, **kw)


def bypass(a: Union[Element, Port, str], b: Union[Element, Port, str], label: Optional[str] = None,
           **kw: Any) -> dict[str, Any]:
    """Declare a bypass link: an additional power connection around a device (see :func:`link`)."""
    return link("bypass", a, b, label, **kw)


class Enclosure:
    """Addressable enclosure (cabinet, MV cell, zone...): every element created inside the block is a member.
    Unlike a Board, it does not change the electrical parent."""

    def __init__(self, label: Optional[str] = None, kind: str = "cabinet", ref: Optional[str] = None, **kw: Any):
        inst = _INSTALLATION.get()
        if inst is None:
            raise RuntimeError("Enclosure must be created inside `with Installation(...):`")
        self.id = inst._unique(_ID_CLEAN.sub("", (ref or label or kind)).strip("-") or kind)
        self.nodes: list[str] = []
        self.data = {"id": self.id, "kind": kind, **({"label": label} if label else {}), **({"ref": ref} if ref else {}),
                     **kw}
        parents = _ENCLOSURES.get()
        if parents:
            self.data["parent"] = parents[-1].id
        inst._enclosures.append(self)

    def __enter__(self) -> Enclosure:
        self._token = _ENCLOSURES.set(_ENCLOSURES.get() + (self,))
        return self

    def __exit__(self, *exc: Any) -> None:
        _ENCLOSURES.reset(self._token)

    def to_dict(self) -> dict[str, Any]:
        """The enclosure as a uniwire ``enclosures[]`` entry."""
        return {**self.data, "nodes": list(self.nodes)}


def Template(**fields: Any) -> dict[str, Any]:
    """Reusable keyword set: ``C16 = Template(curve="C", in_A=16, icn_kA=6)`` then ``Breaker("-Q1", **C16)``."""
    return dict(fields)


# ---------------------------------------------------------------- installation
class Installation:
    """Root of a uniwire document built in code."""

    def __init__(self, title: Optional[str] = None, *, earthing: Optional[str] = None, system: Optional[str] = None,
                 un: Any = None, profiles: Iterable[str] = (), lang: str = "en", **meta_or_installation: Any) -> None:
        self.meta: dict[str, Any] = {"lang": lang}
        if title:
            self.meta["title"] = title
        self.installation: dict[str, Any] = {}
        for k, v in (("earthing", earthing), ("system", system), ("un_V", un)):
            if v is not None:
                self.installation[k] = v
        from .model import Installation as _I
        from .model import Meta as _M
        for k, v in meta_or_installation.items():
            if k in _M.model_fields:
                self.meta[k] = v
            elif k in _I.model_fields or f"{k}_V" in _I.model_fields:
                self.installation[k if k in _I.model_fields else f"{k}_V"] = v
            else:
                raise TypeError(f"Installation: unknown field {k!r}")
        self.profiles = list(profiles)
        self.views: list[dict[str, Any]] = []
        self._sources: list[Element] = []
        self._devices: list[Element] = []
        self._links: list[dict[str, Any]] = []
        self._enclosures: list[Enclosure] = []
        self._interlocks: list[dict[str, Any]] = []
        self._ids: set[str] = set()
        self._counters: dict[str, int] = {}

    # -- ids
    def _unique(self, base: str) -> str:
        base = base or "n"
        if not re.match(r"^[A-Za-z_]", base):
            base = f"n{base}"
        cand, i = base, 1
        while cand in self._ids:
            i += 1
            cand = f"{base}_{i}"
        self._ids.add(cand)
        return cand

    def _new_id(self, el: Element) -> str:
        if "id" in el.data:
            return self._unique(el.data["id"])
        return self._unique(_ID_CLEAN.sub("", str(el.data.get("ref", "")).lstrip("-=+")) or el.type)

    def _detach(self, el: Element) -> None:
        if el.parent is not None:
            el.parent.children.remove(el)
            el.parent = None
        if el in self._sources:
            self._sources.remove(el)
        if el in self._devices:
            self._devices.remove(el)

    # -- context
    def __enter__(self) -> Installation:
        self._token = _INSTALLATION.set(self)
        self._ptoken = _PARENTS.set(())
        return self

    def __exit__(self, *exc: Any) -> None:
        _PARENTS.reset(self._ptoken)
        _INSTALLATION.reset(self._token)

    def view(self, **kw: Any) -> None:
        """Add a view (``views[]`` entry) with the given fields, e.g. ``inst.view(id="ml", kind="multi-line")``."""
        self.views.append({"id": kw.pop("id", f"v{len(self.views) + 1}"), **kw})

    def declare_interlock(self, key: str, keys: int = 1, label: Optional[str] = None, kind: Optional[str] = None) -> None:
        """Declare an interlock: at most ``keys`` of the members whose ``locks`` contain ``key`` are closed."""
        d: dict[str, Any] = {"key": key, "keys": keys}
        if label:
            d["label"] = label
        if kind:
            d["kind"] = kind
        self._interlocks.append(d)

    # -- output
    def to_dict(self) -> dict[str, Any]:
        """The whole installation as a uniwire JSON document (not validated: see :attr:`document`)."""
        d: dict[str, Any] = {"$schema": SCHEMA_ID, "uniwire": FORMAT_VERSION}
        if self.profiles:
            d["profiles"] = self.profiles
        d["meta"] = self.meta
        if self.installation:
            d["installation"] = self.installation
        d["sources"] = [s.to_dict() for s in self._sources]
        if self._devices:
            d["devices"] = [x.to_dict() for x in self._devices]
        if self._enclosures:
            d["enclosures"] = [e.to_dict() for e in self._enclosures]
        if self._links:
            d["links"] = self._links
        if self._interlocks:
            d["interlocks"] = self._interlocks
        if self.views:
            d["views"] = self.views
        return d

    @property
    def document(self) -> Document:
        """Validated uniwire document (raises UniwireError with explicit messages)."""
        return load(self.to_dict())

    def json(self, indent: int = 2) -> str:
        """The validated document as canonical JSON text."""
        from .resolve import dump
        return dump(self.document, indent=indent)

    def save(self, path: Union[str, Path]) -> Path:
        """Write the validated document to ``path`` (UTF-8 JSON) and return the path."""
        path = Path(path)
        path.write_text(self.json() + "\n", "utf-8")
        return path

    def check(self, profiles: Optional[Iterable[str]] = None) -> list[Any]:
        """Run the rule checks (the document's ``profiles`` unless ``profiles`` is given); return the findings."""
        from .rules import check
        return check(self.document, profiles)

    def bom(self) -> list[dict[str, Any]]:
        """Bill of materials of the document (see :func:`uniwire.bom.bom`)."""
        from .bom import bom
        return bom(self.document)

    def render(self, path: Union[str, Path]) -> Union[Path, list[Path]]:
        """``*.pdf`` -> one multi-page PDF; otherwise a directory of SVG sheets."""
        from .render import render_pdf, render_svg
        path = Path(path)
        if path.suffix.lower() == ".pdf":
            return render_pdf(self.document, path)
        return render_svg(self.document, path, path.stem or "sld")

    def _repr_svg_(self) -> str:  # Jupyter display
        from .render import render_pages
        from .render.svg import page_to_svg
        return page_to_svg(render_pages(self.document)[0])


# --------------------------------------------- one class per uniwire node type
def _class_name(t: str) -> str:
    special = {"ups": "UPS", "pv_array": "PVArray", "rcd": "RCD", "rcbo": "RCBO", "spd": "SPD", "ev_charger": "EVCharger",
               "dc_converter": "DCConverter", "plc": "PLC", "offpage": "OffPage"}
    return special.get(t, "".join(p.capitalize() for p in t.split("_")))


class _PLCMixin:
    def add(self, kind: str, part_number: Optional[str] = None, **kw: Any) -> Port:
        """Append a module on the local bus (next free slot) and return its Port."""
        mods = self.data.setdefault("modules", [])  # type: ignore[attr-defined]
        slot = kw.pop("slot", (mods[-1]["slot"] + 1) if mods else 1)
        mods.append({"slot": slot, **Module(kind, part_number, **kw)})
        return Port(self, slot)  # type: ignore[arg-type]

    def port(self, slot: int, channel: Optional[int] = None) -> Port:
        return Port(self, slot, channel)  # type: ignore[arg-type]

    def __getitem__(self, slot: int) -> Port:
        return Port(self, slot)  # type: ignore[arg-type]


for _t in NODE_TYPES:
    _bases: tuple[type, ...] = (_PLCMixin, Element) if _t == "plc" else (Element,)
    _cls = type(_class_name(_t), _bases, {"type": _t, "__doc__": f"uniwire `{_t}` node "
                                          f"(fields: see the `{_t}` definition in the JSON Schema)."})
    globals()[_cls.__name__] = _cls
    __all__.append(_cls.__name__)
