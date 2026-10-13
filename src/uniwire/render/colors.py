"""Colour modes of a view (``View.color``): conductors, phase, source, status, voltage.

The layout engines draw in black; this pass recolours the strokes of a laid-out sheet from the semantic
groups of the drawing (``render.semantics``: node symbols, tree edges, busbars, links, multi-line
conductors), so the SVG and PDF writers get the same colours. Only black strokes are recoloured (frames,
greyed external equipment, earth / data links keep their own colour); texts stay black. The colours used
on a sheet are listed in a legend (:class:`Legend`) that ``frame.compose_page`` draws in a free corner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .. import registry
from ..i18n import t as _t
from ..model import Document, NodeBase, View
from ..resolve import Index
from .scene import Circle, Ellipse, Group, Item, Line, Polyline, Rect, Style, Text
from .semantics import HIT_COLOR, has_cls

BLACK = "#000000"
PE_STRIPE = "#f2c500"  # yellow of the green/yellow protective conductor (dashed over the green)

#: Conductor colours: IEC 60445 (brown / black / grey, blue neutral, green-yellow PE) and North-American
#: practice (black / red / blue at 120/208-240 V, brown / orange / yellow at 277/480 V, white neutral drawn
#: light grey, green ground). DC: L+ red, L- black (common practice, not set by IEC 60445).
CONDUCTOR_PRESETS: dict[str, dict[str, str]] = {
    "iec": {"L1": "#8b4513", "L2": "#000000", "L3": "#8c8c8c", "N": "#2b7bd0", "PE": "#2e9d2e", "PEN": "#2e9d2e",
            "L+": "#c62828", "L-": "#000000"},
    "us": {"L1": "#000000", "L2": "#d32f2f", "L3": "#1f5fbf", "N": "#a6a6a6", "PE": "#2e9d2e", "PEN": "#2e9d2e",
           "L+": "#c62828", "L-": "#000000"},
    "us480": {"L1": "#8b4513", "L2": "#ef7d00", "L3": "#d4ac00", "N": "#a6a6a6", "PE": "#2e9d2e", "PEN": "#2e9d2e",
              "L+": "#c62828", "L-": "#000000"},
}
# Colour-blind safe (Okabe-Ito) palettes
PHASE_COLORS = {"L1": "#d55e00", "L2": "#0072b2", "L3": "#009e73"}
SOURCE_COLORS = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9", "#882255", "#999933"]
STATUS_COLORS = {"new": "#000000", "existing": "#8c8c8c", "future": "#0072b2", "removed": "#c62828",
                 "temporary": "#e69f00", "spare": "#6e6e6e"}
VOLTAGE_COLORS = {"mv": "#d55e00", "lv": "#000000", "elv": "#009e73", "dc": "#0072b2"}
FUTURE_DASH = (2.0, 1.0)

COND_ORDER = ("L1", "L2", "L3", "L+", "L-", "N", "PEN", "PE")
STATUS_ORDER = ("new", "existing", "future", "temporary", "removed", "spare")
VOLTAGE_ORDER = ("mv", "lv", "elv", "dc")
POWER_LINKS = ("transfer", "tie", "bypass", "parallel", "infeed")
MULTI = "multi"  # key of the multi-phase lines (phase / single-line conductor modes): black


@dataclass
class LegendEntry:
    label: str
    color: str
    dash: Optional[tuple[float, ...]] = None
    stripe: Optional[str] = None  # second colour dashed over the first (green/yellow PE)


@dataclass
class Legend:
    title: str
    entries: list[LegendEntry] = field(default_factory=list)


def conductor_preset(doc: Document, view: View) -> str:
    """``view.conductor_colors``, else 'us' for a document following the NEC / CEC, else 'iec'."""
    if view.conductor_colors:
        return view.conductor_colors
    std = (doc.installation.standard or "").upper()
    if any(k in std for k in ("NEC", "NFPA", "CEC", "CSA")) or any(p.lower().startswith("nec") for p in doc.profiles):
        return "us"
    return "iec"


def _phases(text: Optional[str]) -> list[str]:
    return re.findall(r"L[123]", text or "")


class Colorizer:
    """Colour keys of the nodes and links of a document for one colour mode, and the recolouring pass."""

    def __init__(self, doc: Document, view: View, index: Index):
        self.doc, self.view, self.index = doc, view, index
        self.mode = view.color or "none"
        self.palette = dict(view.palette or {})
        self.lang = doc.meta.lang
        self.preset = conductor_preset(doc, view)
        self.used: dict[str, None] = {}  # colour keys met on the sheet, in order
        self.root: dict[str, str] = {}  # node id -> id of the tree root (source) feeding it
        self.sources: list[NodeBase] = []
        self.voltage: dict[str, str] = {}  # node id -> 'mv' | 'lv' | 'elv' | 'dc'
        self.volts: dict[str, Optional[float]] = {}  # node id -> nominal voltage (US 480 V conductor colours)
        self.phase: dict[str, str] = {}  # node id -> single phase of a single-phase circuit on a polyphase supply
        self.status: dict[str, str] = {}  # node id -> own status, else the status of the nearest upstream node
        for src in doc.sources:
            self.sources.append(src)
            self._walk(src, src.id or "", self._source_voltage(src), self._is_dc(src, None), [])

    # ---------------------------------------------------------------- analysis
    def _source_voltage(self, src: NodeBase) -> Optional[float]:
        v = src.un_V or getattr(src, "u2_V", None)
        if v is None and src.type in ("grid", "offpage", "meter"):  # type: ignore[attr-defined]
            v = self.doc.installation.un_V
        return v

    def _is_dc(self, node: NodeBase, parent: Optional[NodeBase]) -> bool:
        t = node.type  # type: ignore[attr-defined]
        if getattr(node, "system", None) == "DC" or getattr(node, "dc", None):
            return True
        if t in ("pv_array", "battery", "dc_converter") or getattr(node, "kind", None) == "dc_box":
            return True
        return parent is None and self.doc.installation.system == "DC"

    def _walk(self, node: NodeBase, root: str, volts: Optional[float], dc: bool, up_phases: list[int],
              ph_up: Optional[str] = None, status: Optional[str] = None) -> None:
        nid = node.id or ""
        t = node.type  # type: ignore[attr-defined]
        self.root[nid] = root
        status = node.status or status
        if status:
            self.status[nid] = status
        system = getattr(node, "system", None)
        dc = (dc or self._is_dc(node, None)) and not (system and system != "DC")
        v = node.un_V or volts
        if t == "transformer":
            v = getattr(node, "u1_V", None) or v
        self.volts[nid] = v
        self.voltage[nid] = self._klass(v, dc)
        # output side of the converting equipment
        out_v, out_dc = v, dc
        if t == "transformer":
            out_v, out_dc = getattr(node, "u2_V", None) or node.un_V or volts, False
        elif t == "power_supply":
            out_v = getattr(node, "u2_V", None) or out_v
            out_dc = (getattr(node, "output", None) or "DC") == "DC"
        elif t in ("inverter", "ups"):
            out_dc = t == "inverter" and getattr(node, "kind", None) == "charger"
        # single-phase circuit (one phase named on it or down its single-child chain) on a polyphase supply
        own = _phases(node.phase) or self._chain_phase(node)
        if len(own) == 1 and any(n >= 2 for n in up_phases):
            self.phase[nid] = own[0]
        elif not own and ph_up:  # downstream of a single-phase device
            self.phase[nid] = ph_up
        n_here = len(_phases(node.phase)) or self._system_phases(node)
        for c in node.children:
            cdc = out_dc or (t in ("inverter", "ups") and self._feeds_dc(c))
            self._walk(c, root, out_v, cdc, up_phases + ([n_here] if n_here else []),
                       self.phase.get(nid) if t not in ("board", "busbar") and len(node.children) == 1 else None,
                       status if status != "spare" else None)

    def _chain_phase(self, node: NodeBase) -> list[str]:
        n: Optional[NodeBase] = node
        while n is not None and n.type not in ("board", "busbar"):  # type: ignore[attr-defined]
            if n.phase:
                return _phases(n.phase)
            n = n.children[0] if len(n.children) == 1 else None
        return []

    def _feeds_dc(self, node: NodeBase) -> bool:
        """DC side of an inverter: the branch leads to PV arrays / batteries."""
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type in ("pv_array", "battery", "dc_converter"):  # type: ignore[attr-defined]
                return True
            stack.extend(n.children)
        return False

    def _system_phases(self, node: NodeBase) -> int:
        system = getattr(node, "system", None) or (self.doc.installation.system if node.type in ("grid",) else None)  # type: ignore[attr-defined]
        return {"1P+N": 1, "2P": 2, "split-phase": 2, "3P": 3, "3P+N": 3}.get(system or "", 0) or \
            (3 if node.type == "transformer" else 0)  # type: ignore[attr-defined]

    @staticmethod
    def _klass(v: Optional[float], dc: bool) -> str:
        if dc:
            return "dc"
        if v is not None and v > 1000:
            return "mv"
        if v is not None and v <= 50:
            return "elv"
        return "lv"

    # ---------------------------------------------------------------- keys
    def node_key(self, nid: Optional[str]) -> Optional[str]:
        if not nid:
            return None
        node = self.index.nodes.get(nid)
        if self.mode == "source":
            return self.root.get(nid)
        if self.mode == "status":
            return self.status.get(nid) or getattr(node, "status", None)
        if self.mode == "voltage":
            return self.voltage.get(nid)
        if self.mode in ("phase", "conductors"):
            if nid not in self.root:
                return None
            return self.phase.get(nid, MULTI)
        return None

    def link_key(self, key: str) -> Optional[str]:
        link = self._link(key)
        if link is None:
            return None
        if self.mode == "status":
            return link.status or getattr(link.device, "status", None)
        if link.kind not in POWER_LINKS:
            return None
        if self.mode == "source":
            return self.root.get(link.from_)
        if self.mode == "voltage":
            return self.voltage.get(link.from_)
        return None

    def _link(self, key: str) -> Any:
        for i, link in enumerate(self.doc.links):
            if (link.id or str(i)) == key:
                return link
        return None

    def color(self, key: Optional[str], nid: Optional[str] = None) -> Optional[str]:
        """Colour of a key of the current mode (``None``: left black)."""
        if key is None:
            return None
        if key in self.palette:
            return self.palette[key]
        if self.mode == "source":
            ids = [s.id for s in self.sources]
            return SOURCE_COLORS[ids.index(key) % len(SOURCE_COLORS)] if key in ids else None
        if self.mode == "status":
            return STATUS_COLORS.get(key)
        if self.mode == "voltage":
            return VOLTAGE_COLORS.get(key)
        if key == MULTI:
            return BLACK
        if self.mode == "phase":
            return PHASE_COLORS.get(key, BLACK if key in COND_ORDER else None)
        if self.mode == "conductors":
            return self._conductor_preset(nid).get(key)
        return None

    def _conductor_preset(self, nid: Optional[str]) -> dict[str, str]:
        if self.preset == "us" and nid and (self.volts.get(nid) or 0) >= 480:
            return CONDUCTOR_PRESETS["us480"]
        return CONDUCTOR_PRESETS.get(self.preset, CONDUCTOR_PRESETS["iec"])

    def stripe(self, key: Optional[str]) -> Optional[str]:
        if self.mode == "conductors" and key in ("PE", "PEN") and self.preset == "iec" and key not in self.palette:
            return PE_STRIPE
        return None

    def dash(self, key: Optional[str]) -> Optional[tuple[float, ...]]:
        return FUTURE_DASH if self.mode == "status" and key == "future" else None

    # ---------------------------------------------------------------- recolouring
    def apply(self, group: Group, multiline: bool) -> None:
        self.multiline = multiline
        self._group(group, None, None, None)

    def _group(self, g: Group, key: Optional[str], nid: Optional[str], cond: Optional[str]) -> None:
        out: list[Item] = []
        for it in g.items:
            if isinstance(it, Group):
                if has_cls(it, "uw-hit"):
                    out.append(it)
                    continue
                k, n, c = self._context(it, key, nid, cond)
                if has_cls(it, "uw-cell"):
                    self._cell(it)
                self._group(it, k, n, c)
                out.append(it)
                continue
            out.append(self._recolor(it, key, nid))
            stripe = self.stripe(key)
            if stripe and isinstance(it, (Line, Polyline)) and not getattr(it, "closed", False):
                over = Style(it.style.width, (1.0, 1.0), stripe)
                out.append(Line(it.a, it.b, over) if isinstance(it, Line) else Polyline(list(it.points), over))
        g.items = out

    def _context(self, g: Group, key: Optional[str], nid: Optional[str],
                 cond: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
        a = g.attrs
        cond_mode = self.mode == "conductors" or (self.mode == "phase" and self.multiline)
        if "data-uw-cond" in a:
            cond = a["data-uw-cond"]
            if cond_mode:
                own_id = g.id if has_cls(g, "uw-busbar") else nid
                if self.mode == "phase":
                    return (cond if cond in PHASE_COLORS else MULTI), own_id, cond
                return cond, own_id, cond
        if has_cls(g, "uw-link"):
            return (None if cond_mode else self.link_key(a.get("data-uw-link", ""))), a.get("data-uw-from"), cond
        if has_cls(g, "uw-node") and "data-uw-link" in a:
            return key, nid, cond  # device carried by a link: coloured as the link
        own: Optional[str] = None
        if has_cls(g, "uw-edge"):
            own = a.get("data-uw-edge")
        elif has_cls(g, "uw-node") or has_cls(g, "uw-busbar"):
            own = g.id
        elif has_cls(g, "uw-ref") and a.get("data-uw-target-id") in self.root:
            own = a["data-uw-target-id"]  # off-page arrow of a board: coloured as that board
        if own is None:
            return key, nid, cond
        if cond_mode and self.multiline:
            return None, own, cond
        return self.node_key(own), own, cond

    def _recolor(self, it: Item, key: Optional[str], nid: Optional[str]) -> Item:
        if key is None or isinstance(it, Text):
            return it
        color = self.color(key, nid)
        if color is None:
            return it
        if not isinstance(it, (Line, Polyline, Circle, Ellipse, Rect)):
            return it
        s = it.style
        if s.color != BLACK or s.color == HIT_COLOR:
            return it
        self.used[key] = None
        fill = color if s.fill == BLACK else s.fill
        dash = s.dash or self.dash(key)
        new = Style(s.width, dash, color, fill)
        return type(it)(**{**it.__dict__, "style": new})

    def _cell(self, col: Group) -> None:
        """Feeder table: phase cell tinted with the phase colour of its column."""
        if self.mode not in ("phase", "conductors"):
            return
        key = self.node_key(col.id)
        if key in (None, MULTI):
            return
        color = self.color(key, col.id)
        if color is None:
            return
        for cg in col.items:
            if isinstance(cg, Group) and cg.attrs.get("data-uw-field") == "phase":
                for it in cg.items:
                    if isinstance(it, Rect):
                        it.style = Style(it.style.width, it.style.dash, it.style.color, _tint(color))
                        self.used[key] = None

    # ---------------------------------------------------------------- legend
    def legend(self) -> Optional[Legend]:
        if self.mode == "none" or not self.used:
            return None
        lang = self.lang
        if self.mode == "source":
            order = [s.id for s in self.sources if s.id in self.used]
        elif self.mode == "status":
            order = [k for k in STATUS_ORDER if k in self.used]
        elif self.mode == "voltage":
            order = [k for k in VOLTAGE_ORDER if k in self.used]
        else:
            order = [k for k in COND_ORDER if k in self.used] + ([MULTI] if MULTI in self.used else [])
        title = _t(f"legend.{self.mode}", lang) if self.mode != "conductors" else \
            _t("legend.conductors", lang, standard=_t(f"legend.preset.{self.preset}", lang))
        out = Legend(title)
        nid_480 = next((n for n, v in self.volts.items() if (v or 0) >= 480), None) if self.preset == "us" else None
        for k in order:
            if k is None:
                continue
            color = self.color(k)
            if color is None:
                continue
            out.entries.append(LegendEntry(self._label(k), color, self.dash(k), self.stripe(k)))
            if nid_480 and self.mode == "conductors" and k in ("L1", "L2", "L3") and k not in self.palette:
                out.entries[-1].label += " (≤ 240 V)"
                out.entries.append(LegendEntry(f"{k} (480 V)", CONDUCTOR_PRESETS["us480"][k]))
        return out

    def _label(self, key: str) -> str:
        lang = self.lang
        if self.mode == "source":
            n = self.index.nodes.get(key)
            if n is None:
                return key
            name = " ".join(x for x in (n.ref, n.label) if x)
            return name or registry.label(n.type, lang)  # type: ignore[attr-defined]
        if self.mode in ("status", "voltage"):
            return _t(f"legend.{self.mode}.{key}", lang)
        if key == MULTI:  # multi-line phase mode: the conductors that are not phases
            return "N, PE" if getattr(self, "multiline", False) else _t("legend.multi_phase", lang)
        return key


def _tint(color: str, amount: float = 0.78) -> str:
    """Light tint of ``color`` (mixed with white)."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in (r, g, b))


def colorize(group: Group, doc: Document, view: View, index: Index, multiline: bool = False) -> Optional[Legend]:
    """Recolour a laid-out sheet (in place) for ``view.color``; returns its legend (``None``: nothing coloured)."""
    if not view.color or view.color == "none":
        return None
    c = Colorizer(doc, view, index)
    c.apply(group, multiline)
    return c.legend()
