"""uniwire document (root of a ``*.uniwire.json`` file)."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional

from pydantic import Field, PrivateAttr, field_validator, model_validator

from ..units import Q
from .base import (
    ID_PATTERN,
    PORT_ID_PATTERN,
    Cable,
    ConductorName,
    Installation,
    Material,
    Meta,
    Product,
    UWModel,
    WireColor,
    Wiring,
)
from .nodes import Node

#: a port reference: ``<node or strip id>#<port>`` (UEP-0001 §3.1.2)
PORT_REF_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.\-]*#[A-Za-z0-9+-][A-Za-z0-9_.:/+-]*$"

FORMAT_VERSION = "1.1.0"
SCHEMA_ID = "https://uniwire.sh/schema/v1/uniwire.schema.json"

LinkKind = Literal["transfer", "tie", "bypass", "parallel", "infeed", "earth", "control", "interlock", "trip",
                   "measure", "data", "key"]

CartoucheField = Literal[
    "label", "ref", "protection", "in_A", "curve", "icn_kA", "idn_mA", "rcd_type", "poles",
    "cable", "section_mm2", "length_m", "p_kW", "phase", "room", "points",
    "circuit", "ib_A", "cos_phi", "cable_type", "cable_ref", "install", "frame_A", "count", "un_V",
]

DEFAULT_CARTOUCHE: list[str] = ["label", "ref", "protection", "idn_mA", "cable", "p_kW"]


class Link(UWModel):
    """Link outside the tree.

    * ``transfer``: 2nd source arriving on a transfer switch (``to`` = transfer_switch);
    * ``tie``: coupling between two busbars (``device`` = bus-tie device);
    * ``bypass`` / ``parallel``: additional power connection;
    * ``control`` / ``interlock`` / ``trip`` / ``measure``: control, interlocking, tripping and
      metering links (drawn dashed);
    * ``infeed`` (additional supply to a node: 2nd incomer, MV (HTA) ring, back-feed),
      ``earth`` (protective conductor / equipotential bonding), ``data`` (communication bus,
      TIC teleinfo, Modbus), ``key`` (key-lock interlocking, ``key`` = key identifier).
    """

    id: Optional[str] = Field(None, pattern=ID_PATTERN)
    kind: LinkKind
    from_: str = Field(alias="from", pattern=ID_PATTERN, description="id of the start node")
    to: str = Field(pattern=ID_PATTERN, description="id of the end node")
    label: Optional[str] = None
    device: Optional[Node] = Field(None, description="Device inserted on the link (bus coupler)")
    cable: Optional[Cable] = Field(None, description="Cable run carried by the link")
    normally_open: Optional[bool] = Field(None, description="Link open in normal operation (normally-open point)")
    locks: list[str] = Field(
        default_factory=list, description="Interlock keys engaged by the link (and its device): see 'interlocks'")
    key: Optional[str] = Field(None, description="Key identifier for kind='key'")
    from_port: Optional[str] = Field(None, description="Start terminal / channel: PLC 'slot.channel' ('3.1')")
    to_port: Optional[str] = Field(None, description="End terminal / channel")
    protocol: Optional[str] = Field(None, description="Protocol of a 'data' link: 'Modbus TCP', 'PROFINET'...")
    status: Optional[Literal["new", "existing", "future", "removed", "temporary"]] = None


class Interlock(UWModel):
    """Interlock declaration: the nodes and links whose ``locks`` contain ``key`` form one interlock.

    Trapped-key principle: with ``keys`` keys, at most ``keys`` members may be closed at the same time
    (1 = mutually exclusive positions: removable links, changeover jumpers, either/or supplies;
    2 = "2 of 3" transformer / bus-tie scheme...). A key used in ``locks`` without a declaration has one key.
    """

    key: str = Field(pattern=ID_PATTERN, description="Key identifier, as used in the 'locks' of nodes and links")
    keys: int = Field(1, ge=1, description="Number of keys: maximum number of members closed at the same time")
    label: Optional[str] = None
    kind: Optional[Literal["trapped_key", "mechanical", "removable_link", "electrical"]] = Field(
        None, description="How the interlock is achieved")


class Override(UWModel):
    label_offset: Optional[tuple[float, float]] = Field(None, description="Annotation offset (mm)")
    hide: Optional[bool] = None


class Frame(UWModel):
    """Enclosure frame drawn around a list of nodes (cabinet, box, switchgear cell)
    when it does not match a ``board`` subtree."""

    label: Optional[str] = None
    nodes: list[str] = Field(min_length=1, description="ids of the framed nodes")


class Enclosure(UWModel):
    """Addressable enclosure: cabinet, MV (HTA) cell, box, room, zone, property boundary.
    Unlike ``board``, it only contains the listed nodes."""

    id: str = Field(pattern=ID_PATTERN)
    kind: Literal["cabinet", "cell", "box", "room", "zone", "substation", "boundary", "lineup", "panel"] = "cabinet"
    ref: Optional[str] = None
    label: Optional[str] = None
    cell_type: Optional[str] = Field(None, description="MV (HTA) cell function: 'IM', 'QM', 'DM1', 'CM', 'PM', 'GBC'")
    position: Optional[int] = Field(None, ge=0, description="Position within the switchgear line-up")
    nodes: list[str] = Field(default_factory=list, description="ids of the contained nodes")
    parent: Optional[str] = Field(None, pattern=ID_PATTERN, description="Enclosing (parent) enclosure")
    un_V: Optional[float] = Field(None, ge=0)
    ip: Optional[str] = None
    form: Optional[str] = None


class Terminal(UWModel):
    """A terminal of a terminal strip (1.1, UEP-0001 §3.2): referenced ``<strip id>#<no>``, displayed ``-X1:3``."""

    no: str = Field(pattern=PORT_ID_PATTERN, description="Terminal number, unique within the strip: '1', 'PE', '10a'")
    kind: Literal["feed_through", "disconnect", "fuse", "earth", "neutral", "spare"] = "feed_through"
    bridge_group: Optional[str] = Field(None, description="Terminals sharing a value are bridged together")
    label: Optional[str] = Field(None, description="Description, or the function of the terminal")
    section_max_mm2: Optional[Q("mm2", "Largest conductor accepted")] = None
    points: Optional[int] = Field(None, ge=1, description="Clamping points per side (default 1)")
    fuse_A: Optional[Q("A", "Fuse rating of a 'fuse' terminal")] = None
    potential: Optional[str] = Field(None, description="Expected potential")
    product: Optional[Product] = None
    wiring: Optional[Wiring] = Field(None, description="'site': the field side is connected by the installer")
    status: Optional[Literal["new", "existing", "spare", "future", "removed"]] = None


class TerminalStrip(UWModel):
    """A terminal strip (1.1, UEP-0001 §3.2): not a node of the tree, since it is crossed by many circuits."""

    id: str = Field(pattern=ID_PATTERN, description="Identifier, in the namespace of the nodes and wires")
    ref: Optional[str] = Field(None, description="Reference designation: '-X1'")
    label: Optional[str] = None
    enclosure: Optional[str] = Field(None, pattern=ID_PATTERN, description="id of the enclosure or 'board' node")
    location: Optional[str] = Field(None, description="Location (IEC 81346 '+' aspect), when no enclosure is described")
    product: Optional[Product] = Field(None, description="Default product of the terminals")
    terminals: list[Terminal] = Field(default_factory=list, description="Terminals in mounting order on the rail")
    status: Optional[Literal["new", "existing", "spare", "future", "removed"]] = None
    note: Optional[str] = None


class Wire(UWModel):
    """A conductor between two terminals (1.1, UEP-0001 §3.3): device ports or strip terminals. Wires are optional
    and partial: the connections of the power tree that no wire describes stay implicit."""

    id: Optional[str] = Field(None, pattern=ID_PATTERN, description="Identifier (generated when absent, not stable)")
    from_: str = Field(alias="from", pattern=PORT_REF_PATTERN, description="Port reference: 'X1#11', 'KM1#13'")
    to: str = Field(pattern=PORT_REF_PATTERN, description="Port reference")
    mark: Optional[str] = Field(None, description="Wire mark (ferrule text)")
    section_mm2: Optional[Q("mm2", "Cross-section")] = None
    size_awg: Optional[str] = Field(None, description="Size as printed in AWG")
    color: Optional[WireColor] = Field(None, description="IEC 60757 colour code; GNYE for protective conductors")
    designation: Optional[str] = Field(None, description="Conductor type: 'H05V-K'")
    material: Optional[Material] = None
    cable: Optional[str] = Field(None, description="Cable this wire is a core of: '<node id>.cable' for a tree cable")
    core: Optional[str] = Field(None, description="Core number or colour within the cable: '1', 'BN', 'GNYE'")
    conductor: Optional[ConductorName] = Field(None, description="Conductor function; absent for control wires")
    potential: Optional[str] = Field(None, description="Potential id, or a port reference on the same net")
    length_m: Optional[Q("m", "Length")] = None
    kind: Literal["wire", "bridge"] = "wire"
    wiring: Optional[Wiring] = Field(None, description="'site': connected by the installer on site, not in the "
                                     "workshop (the dashed connections of a manufacturer's diagram)")
    label: Optional[str] = None
    status: Optional[Literal["new", "existing", "spare", "future", "removed"]] = None
    note: Optional[str] = None


PATTERN_TOKENS = ("circuit", "conductor", "ref", "from", "to", "from_port", "to_port", "potential", "strip",
                  "terminal", "n", "cable")
_TOKEN = re.compile(r"\{([^{}]*)\}")


class WireMarking(UWModel):
    """Wire marking rules of a view (UEP-0001 §3.5.1). The current format marks the conductors of the cables of the
    power tree (``node.cable``); format 2.0 extends the same rules to ``wires[]``."""

    scheme: Literal["manual", "potential", "sequential", "pattern"] = Field(
        "manual", description="'manual': only the marks written in the document (cable 'marks'); 'potential': one "
        "number per potential (net), shared by its conductors; 'sequential': one number per conductor; 'pattern': "
        "marks built from 'pattern'")
    pattern: Optional[str] = Field(
        None, description="Template of the 'pattern' scheme, e.g. '{circuit}-{conductor}'. Tokens: {circuit}, "
        "{conductor}, {ref} (tag of the 'from' device), {from}, {to} (tags of the two ends), {cable} (cable tag), "
        "{n} (sequence number); {from_port}, {to_port}, {potential}, {strip}, {terminal} are reserved for format "
        "2.0 and empty in the current format")
    start: int = Field(1, ge=0, description="First generated number")
    step: int = Field(1, ge=1, description="Increment of generated numbers")
    prefix: str = Field("", description="Text added before generated numbers")
    suffix: str = Field("", description="Text added after generated numbers")
    per: Literal["document", "sheet", "enclosure"] = Field(
        "document", description="Numbering restarts per 'document', 'sheet' or 'enclosure' (of the 'from' end)")
    power: Literal["conductor", "number", "none"] = Field(
        "conductor", description="Power conductors in the 'potential' and 'sequential' schemes: 'conductor' marks "
        "them with their conductor (L1, N, PE), 'number' numbers them, 'none' leaves them unmarked")
    keep_manual: bool = Field(True, description="Marks written in the document are kept; generated numbers skip "
                              "the values they use")
    order: Literal["layout", "document"] = Field(
        "layout", description="Numbering order: 'layout' (sheet, then column, then top to bottom) or 'document' "
        "(order of the tree)")

    @field_validator("pattern")
    @classmethod
    def _tokens(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            bad = [t for t in _TOKEN.findall(v) if t not in PATTERN_TOKENS]
            if bad:
                raise ValueError(f"unknown token(s) {', '.join('{' + t + '}' for t in bad)}; "
                                 f"expected {', '.join('{' + t + '}' for t in PATTERN_TOKENS)}")
        return v

    @model_validator(mode="after")
    def _needs_pattern(self) -> WireMarking:
        if self.scheme == "pattern" and not self.pattern:
            raise ValueError("scheme 'pattern' needs a 'pattern'")
        return self


HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class View(UWModel):
    """Rendering preferences. A document is complete without any view: layout is automatic."""

    id: str = Field("sld", pattern=ID_PATTERN)
    kind: Literal["single-line", "multi-line", "terminals"] = Field(
        "single-line", description="'single-line' diagram, or 'multi-line' power diagram (one line per conductor, "
        "derived from the same tree: phase, poles, cable cores, system and earthing), or 'terminals': the terminal "
        "plan of the terminal strips, one table per strip (1.1)")
    title: Optional[str] = None
    root: Optional[str] = Field(None, description="Only draw the subtree of this node")
    paper: Literal["A4", "A3", "A2", "A1", "A0"] = "A3"
    orientation: Literal["landscape", "portrait"] = "landscape"
    direction: Literal["down", "up", "right", "left"] = Field(
        "down", description="Direction of power flow on the source drawing (the reference renderer draws 'down')")
    pitch_mm: float = Field(20.0, ge=10, le=40, description="Width of an outgoing-circuit (feeder) column")
    cartouche: list[CartoucheField] = Field(
        default_factory=lambda: list(DEFAULT_CARTOUCHE),
        description="Rows of the feeder table, in order",
    )
    folio_split: Literal["auto", "none"] = "auto"
    min_scale: float = Field(0.7, gt=0, le=1, description="Maximum scale reduction before splitting into several sheets")
    annotations: bool = Field(True, description="Show tag + ratings next to the symbols")
    tag_field: Literal["ref", "part_number"] = Field("ref", description="Identifier shown at the top of the annotation")
    conductor_marks: bool = Field(
        True, description="Draw conductor-count marks (IEC 60617 oblique strokes; 4P vs 3P+N distinguished) on "
        "incomers and wherever a device changes the conductors, plus feeder ends; false = no marks")
    frames: list[Frame] = Field(default_factory=list, description="Additional enclosure frames")
    title_block: bool = Field(True, description="Draw the sheet border and title block")
    first_folio: int = Field(1, ge=1, description="Number of the first sheet (partial sheet set)")
    total_folios: Optional[int] = Field(None, ge=1, description="Total number of sheets in the drawing set")
    show_pe: bool = Field(True, description="Multi-line view: draw the protective conductor (PE)")
    color: Optional[Literal["none", "conductors", "phase", "source", "status", "voltage"]] = Field(
        None, description="Colour mode (1.3; omitted = 'none', black drawing): 'conductors' = conductor colours "
        "(multi-line: each conductor; single-line: single-phase feeders in their phase colour), 'phase' = "
        "single-phase feeders by phase, 'source' = what each source feeds in normal operation, 'status' = "
        "new / existing / future / removed / temporary, 'voltage' = MV / LV / ELV / DC. A legend is drawn on "
        "each sheet; texts stay black")
    palette: Optional[dict[str, HexColor]] = Field(
        None, description="Colour overrides, by key of the colour mode: 'L1'...'PE' (conductors, phase), source "
        "id (source), status value (status), 'mv' / 'lv' / 'elv' / 'dc' (voltage); values '#rrggbb'")
    conductor_colors: Optional[Literal["iec", "us"]] = Field(
        None, description="Conductor colour preset of the 'conductors' mode: 'iec' (IEC 60445: brown / black / "
        "grey, blue N, green-yellow PE) or 'us' (black / red / blue, brown / orange / yellow from 480 V, white N, "
        "green ground); omitted = 'us' when the installation standard is the NEC / CEC, else 'iec'")
    wire_marking: Optional[WireMarking] = Field(
        None, description="Wire marking rules: marks of the conductors of the cables, drawn in the multi-line view "
        "and exported by 'uniwire wires' / 'uniwire markers'")
    wire_marks: Optional[bool] = Field(
        None, description="Show the wire marks on the multi-line drawing (default: true when 'wire_marking' is set)")
    overrides: dict[str, Override] = Field(default_factory=dict)


class Document(UWModel):
    """A uniwire document: metadata, installation, power tree (``sources``), devices, enclosures, links,
    interlocks, templates and views. Build one with :func:`uniwire.load` (validation, templates, ids)."""

    #: Near-miss values rewritten on load (:mod:`uniwire.tolerate`), reported by the rule ``core.normalized``.
    _normalized: list[str] = PrivateAttr(default_factory=list)
    #: The identifiers written in the file (nodes, terminal strips, wires), set by :func:`uniwire.load`: a port
    #: reference must use one of them, a generated identifier being unstable.
    _explicit_ids: set[str] = PrivateAttr(default_factory=set)

    schema_: Optional[str] = Field(SCHEMA_ID, alias="$schema")
    uniwire: str = Field(FORMAT_VERSION, pattern=r"^1\.\d+\.\d+$", title="uniwire", description="Format version (semver)")
    profiles: list[str] = Field(default_factory=list, description="Rule profiles: 'nfc15100'...")
    meta: Meta = Field(default_factory=Meta)
    installation: Installation = Field(default_factory=Installation)
    templates: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Reusable attribute templates, referenced by 'use' in nodes",
    )
    sources: list[Node] = Field(min_length=1, description="Tree roots (power sources)")
    devices: list[Node] = Field(
        default_factory=list,
        description="Auxiliary devices outside the power tree (relays, CTs, insulation monitors (CPI), voltage presence indicators (VPIS)...), connected by links")
    enclosures: list[Enclosure] = Field(default_factory=list, description="Addressable enclosures")
    terminal_strips: list[TerminalStrip] = Field(default_factory=list, description="Terminal strips (1.1)")
    wires: list[Wire] = Field(default_factory=list, description="Wires between terminals (1.1); optional and partial")
    links: list[Link] = Field(default_factory=list)
    interlocks: list[Interlock] = Field(
        default_factory=list, description="Interlock declarations: number of keys per 'locks' identifier")
    views: list[View] = Field(default_factory=list)
