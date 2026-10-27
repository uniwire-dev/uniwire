"""Common building blocks of the uniwire model."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..units import Q

ID_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.\-]*$"


class UWModel(BaseModel):
    """Base: unknown fields are forbidden (typos fail), except inside ``ext``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=False)

    ext: Optional[dict[str, Any]] = Field(
        None,
        description="Free-form extensions, namespaced by vendor prefix (e.g. {'acme': {...}}). "
        "Tools must preserve what they do not understand.",
    )


Poles = Literal["1P", "1P+N", "2P", "3P", "3P+N", "4P"]
Curve = Literal["B", "C", "D", "K", "Z", "MA"]
RcdType = Literal["AC", "A", "F", "B", "A-SI", "Hpi", "G"]
Phase = Literal["L1", "L2", "L3", "L1L2", "L2L3", "L1L3", "L1L2L3"]
Status = Literal["new", "existing", "spare", "future", "removed"]
Earthing = Literal["TT", "TN", "TN-C", "TN-S", "TN-C-S", "IT"]
System = Literal["1P+N", "2P", "3P", "3P+N", "DC", "split-phase"]
Material = Literal["Cu", "Al"]
ConductorName = Literal["L1", "L2", "L3", "N", "PE", "PEN", "L+", "L-"]


class Cable(UWModel):
    """Cable run (canalisation) feeding the node from its parent."""

    designation: Optional[str] = Field(None, description="Cable type: U1000R2V, H07V-U, AR2V, XVB...")
    cores: Optional[str] = Field(
        None, description="Core composition: '3G', '5G', '4x', '4x(2x1x240)'... (without the cross-section)"
    )
    section_mm2: Optional[Q("mm2", "Cross-section of the live conductors")] = None
    pe_section_mm2: Optional[Q("mm2", "PE cross-section, if different")] = None
    neutral_section_mm2: Optional[Q("mm2", "Neutral cross-section, if different")] = None
    parallel: Optional[int] = Field(None, ge=1, description="Number of parallel cables per phase")
    material: Optional[Material] = None
    length_m: Optional[Q("m", "Length")] = None
    install: Optional[str] = Field(None, description="Installation method, IEC 60364-5-52 reference: A1, B, C, E, F...")
    insulation: Optional[Literal["PVC", "PR", "EPR", "XLPE"]] = None
    du_pct: Optional[Q("%", "Calculated voltage drop at the cable end")] = None
    # --- 1.2
    ref: Optional[str] = Field(None, description="Cable tag / label: C1, W12, schedule tag 15B")
    kind: Optional[Literal["cable", "busway", "overhead", "bar", "trunk"]] = None
    conductors: Optional[str] = Field(None, description="Conductor functions: 'L1, L2, L3, N, PE'")
    pen: Optional[bool] = Field(None, description="PEN conductor (TN-C)")
    cpr_class: Optional[str] = Field(None, description="CPR reaction-to-fire class: 'Cca-s1,d1,a1', 'Eca'")
    size_awg: Optional[str] = Field(None, description="Size in AWG/kcmil as printed: '#4/0', '500 kcmil'")
    raceway: Optional[str] = Field(None, description="Conduit / raceway: '2\" EMT', 'tube IRL 20'")
    ambient_C: Optional[float] = Field(None, description="Ambient temperature used for calculation (°C)")
    status: Optional[Literal["new", "existing", "spare", "future", "removed"]] = None
    marks: Optional[dict[ConductorName, str]] = Field(
        None, description="Wire marks (ferrule texts) of the conductors of this cable, by conductor: "
        "{'L1': '101', 'L2': '102', 'L3': '103', 'PE': 'PE'}. Kept by every marking scheme (keep_manual); "
        "written by 'uniwire marks --write' (freezing)")


PORT_ID_PATTERN = r"^[A-Za-z0-9+-][A-Za-z0-9_.:/+-]*$"
PortFunction = Literal["pole_in", "pole_out", "power_in", "power_out", "neutral", "earth", "shield", "coil",
                       "contact_no", "contact_nc", "contact_co", "signal_in", "signal_out", "supply", "comm", "other"]
#: IEC 60757 colour codes, and GNYE (green-and-yellow, reserved for protective conductors by IEC 60445)
WireColor = Literal["BK", "BN", "RD", "OG", "YE", "GN", "BU", "VT", "GY", "WH", "PK", "GD", "TQ", "SR", "GNYE"]
#: who makes a connection: in the workshop with the equipment, or on site by the installer (format 1.1)
Wiring = Literal["factory", "site"]


class Port(UWModel):
    """A terminal of a node (format 1.1, UEP-0001 §3.1): a point where a conductor can be connected, referenced as
    ``<node id>#<port id>`` and displayed ``<ref>:<marking>`` (``-KM1:A1``)."""

    id: str = Field(pattern=PORT_ID_PATTERN, description="Port identifier, unique within the node: '1', 'A1', '13', "
                    "'U1', 'PE', '2.1' (PLC slot 2, channel 1). Case-sensitive")
    marking: Optional[str] = Field(None, description="Marking printed on the device, when it differs from 'id'")
    aliases: list[str] = Field(default_factory=list, description="Other accepted names: 'L1' for '1', 'T1' for '2'")
    function: Optional[PortFunction] = None
    pole: Optional[int] = Field(None, ge=1, description="Rank of the pole or winding")
    conductor: Optional[ConductorName] = Field(None, description="Fixed conductor of the port: N, PE...")
    pair: Optional[str] = Field(None, description="The other terminal of the same pole, contact or coil: '2' for '1'")
    label: Optional[str] = Field(None, description="Description: 'Start', 'Run feedback'")
    mandatory: Optional[bool] = Field(None, description="Must be connected when the node is wired (coils)")
    capacity: Optional[int] = Field(None, ge=1, description="Maximum number of conductors on the terminal (default 2; "
                                    "PLC channels 1)")
    section_max_mm2: Optional[Q("mm2", "Largest conductor the terminal accepts")] = None
    wiring: Optional[Wiring] = Field(None, description="'site': the installer connects this terminal on site")


class Product(UWModel):
    """Product reference: identifies the commercial product actually installed or specified."""

    manufacturer: Optional[str] = Field(None, description="Manufacturer: 'Schneider Electric', 'WAGO', 'Siemens'...")
    part_number: Optional[str] = Field(None, description="Catalog part number: 'A9F04616', '750-8212', '6ED1052-1FB08-0BA1'")
    range: Optional[str] = Field(None, description="Product range: 'Acti9 iC60N', 'PFC200', 'LOGO! 8'")
    description: Optional[str] = Field(None, description="Commercial description")
    ean: Optional[str] = Field(None, description="EAN / GTIN code")
    quantity: Optional[int] = Field(None, ge=1, description="Quantity, if different from 'count' (e.g. accessories)")
    url: Optional[str] = Field(None, description="Product datasheet / documentation")
    accessories: list[Product] = Field(default_factory=list, description="Fitted accessories (Vigi add-on block, MX shunt trip, OF auxiliary contact...)")


class Revision(UWModel):
    index: str
    date: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None


class Meta(UWModel):
    title: Optional[str] = None
    project: Optional[str] = Field(None, description="Project name or job number")
    client: Optional[str] = None
    site: Optional[str] = None
    company: Optional[str] = None
    author: Optional[str] = None
    checked_by: Optional[str] = None
    date: Optional[str] = Field(None, description="ISO 8601 date")
    revisions: list[Revision] = Field(default_factory=list)
    lang: Optional[str] = Field("en", description="Language of labels and rendered texts (BCP 47)")
    drawing_number: Optional[str] = Field(None, description="Drawing number / sheet number within the drawing set")
    scale: Optional[str] = None
    contributors: list[str] = Field(default_factory=list, description="Contributors (design office, installer...)")
    notes: list[str] = Field(default_factory=list)


class Installation(UWModel):
    """General characteristics of the installation (title block + rules)."""

    earthing: Optional[Earthing] = Field(None, description="Earthing system")
    system: Optional[System] = Field(None, description="Supply system")
    un_V: Optional[Q("V", "Nominal voltage (phase-to-phase in three-phase)")] = None
    f_Hz: Optional[Q("Hz")] = 50
    supply: Optional[str] = Field(None, description="Utility connection type: 'Tarif Bleu', 'Tarif Jaune', 'HTA', 'C5', 'C4'...")
    subscribed_kVA: Optional[Q("kVA", "Subscribed power (puissance souscrite)")] = None
    planned_kVA: Optional[Q("kVA", "Planned / estimated power")] = None
    ik3_kA: Optional[Q("kA", "Maximum short-circuit current at the point of supply")] = None
    ik1_kA: Optional[Q("kA", "Minimum short-circuit current (Ik1)")] = None
    uln_V: Optional[Q("V", "Phase-to-neutral voltage")] = None
    du_max_pct: Optional[Q("%", "Maximum permitted voltage drop")] = None
    earth_resistance_ohm: Optional[Q("Ohm", "Earth electrode resistance")] = None
    surface_m2: Optional[Q("m2", "Floor area of the dwelling / premises (rules on minimum number of circuits)")] = None
    standard: Optional[str] = Field(None, description="Reference standard: 'NF C 15-100', 'IEC 60364', 'RGIE'...")
    premises: Optional[Literal["dwelling", "commercial", "office", "industrial", "public", "agricultural", "other"]] = Field(
        None, description="Kind of premises: dwelling rules (e.g. nfc15100.rcd-count) apply only to 'dwelling', or when "
        "this is not given")


Product.model_rebuild()
