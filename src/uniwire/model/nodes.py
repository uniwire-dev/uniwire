"""Nodes of the power tree (union discriminated by ``type``).

Each node is fed by its parent and feeds its ``children``.
A node with several children is drawn as a busbar (jeu de barres).
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import Field
from typing_extensions import TypeAliasType

from ..units import Q
from .base import ID_PATTERN, Cable, Curve, Earthing, Phase, Poles, Product, RcdType, Status, System, UWModel


class NodeBase(UWModel):
    id: Optional[str] = Field(
        None, pattern=ID_PATTERN, description="Stable identifier, unique within the document (generated if missing)"
    )
    ref: Optional[str] = Field(None, description="Displayed IEC 81346 reference designation: '-Q3', 'KM1', 'TD1'...")
    label: Optional[str] = Field(None, description="Description (function, room): 'Living room sockets'")
    use: Optional[str] = Field(None, description="Name of a 'templates' entry to inherit attributes from")
    status: Optional[Status] = None
    phase: Optional[Phase] = Field(None, description="Connected phase(s) for a single-phase circuit on a three-phase network")
    location: Optional[str] = Field(None, description="Room / location (IEC 81346 '+' aspect)")
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    product: Optional[Product] = Field(None, description="Structured product reference; takes precedence over "
                                       "manufacturer / part_number")
    note: Optional[str] = None
    external: Optional[bool] = Field(
        None, description="Equipment outside the drawn scope (supplied by others, another trade package): drawn dashed"
    )
    # --- data common to every node
    count: Optional[int] = Field(None, ge=1, description="Number of identical items represented by this node (\"x 20\")")
    circuit: Optional[str] = Field(None, description="Circuit / feeder number or code (C1, 15B, A...), distinct from the reference designation")
    un_V: Optional[Q("V", "Operating voltage of the node (phase-to-phase)")] = None
    uln_V: Optional[Q("V", "Phase-to-neutral voltage, e.g. 230 in 230/400 V")] = None
    ib_A: Optional[Q("A", "Design current Ib")] = None
    p_kW: Optional[Q("kW", "Active power (installed or absorbed) of the node or feeder")] = None
    q_kvar: Optional[Q("var", "Reactive power")] = None
    cos_phi: Optional[float] = Field(None, ge=0, le=1)
    priority: Optional[Literal["essential", "non_essential", "safety", "standby"]] = Field(
        None, description="Service class (backed-up, safety, sheddable...)")
    normal_state: Optional[Literal["open", "closed"]] = Field(None, description="Normal state (ring open point, NO/NC)")
    locks: list[str] = Field(default_factory=list, description="Interlock keys engaged by the node (key identifiers): see 'interlocks'")
    notes: list[str] = Field(default_factory=list, description="References to sheet notes (note numbers)")
    point_no: Optional[int] = Field(None, ge=0, description="Sequence number of the point on the circuit (Belgian RGIE diagrams)")
    cable: Optional[Cable] = Field(None, description="Cable run between the parent and this node")
    children: list[Node] = Field(default_factory=list)


class _Protective(NodeBase):
    """Switching / protective devices (appareillage): common attributes."""

    in_A: Optional[Q("A", "Rated current")] = None
    poles: Optional[Poles] = None
    frame_A: Optional[Q("A", "Frame rating / AF (e.g. 250 for a DPX 250, 225AF)")] = None
    range: Optional[str] = Field(None, description="Product range / commercial reference: 'DNX3', 'iC60N', 'NSX250F'...")
    ue_V: Optional[Q("V", "Rated operational voltage")] = None
    icn_kA: Optional[Q("kA", "Rated short-circuit capacity (Icn, IEC 60898)")] = None
    icu_kA: Optional[Q("kA", "Ultimate breaking capacity (Icu, IEC 60947-2) / kAIC")] = None
    icw_kA: Optional[Q("kA", "Rated short-time withstand current (Icw)")] = None
    aux: list[str] = Field(default_factory=list, description="Auxiliaries: 'MX', 'MN', 'OF', 'SD', 'IOF', 'pilot wire'...")
    mounting: Optional[Literal["fixed", "plug_in", "withdrawable"]] = None
    lockable: Optional[bool] = Field(None, description="Padlockable / lockout-capable")


# --------------------------------------------------------------------- sources
class Grid(NodeBase):
    """Public distribution network / point of supply (point de livraison)."""

    type: Literal["grid"]
    supply: Optional[str] = Field(None, description="'Tarif Bleu', 'Tarif Jaune', 'HTA 20 kV', 'Enedis C5'...")
    ik_kA: Optional[Q("kA", "Maximum Ik at the point of supply")] = None
    scc_MVA: Optional[Q("VA", "Short-circuit power of the upstream network, in MVA")] = None
    system: Optional[System] = None


class Transformer(NodeBase):
    type: Literal["transformer"]
    sn_kVA: Optional[Q("kVA", "Rated power")] = None
    u1_V: Optional[Q("V", "Primary voltage")] = None
    u2_V: Optional[Q("V", "No-load secondary voltage")] = None
    ucc_pct: Optional[Q("%", "Short-circuit (impedance) voltage")] = None
    coupling: Optional[str] = Field(None, description="Vector group: 'Dyn11', 'Yzn11'...")
    insulation: Optional[Literal["oil", "dry"]] = None
    kind: Optional[Literal["power", "auto", "earthing", "isolation", "bank"]] = None
    u1_alt_V: Optional[Q("V", "Second primary voltage (dual-voltage 15/20 kV)")] = None


class Generator(NodeBase):
    type: Literal["generator"]
    sn_kVA: Optional[Q("kVA")] = None
    fuel: Optional[str] = None
    prime_mover: Optional[str] = Field(None, description="'diesel', 'turbine', 'wind', 'hydro'...")


class UPS(NodeBase):
    """Uninterruptible power supply (UPS, ASI / onduleur)."""

    type: Literal["ups"]
    sn_kVA: Optional[Q("kVA")] = None
    autonomy_min: Optional[Q("min")] = None
    bypass: Optional[bool] = Field(None, description="Static / maintenance bypass present")


class PVArray(NodeBase):
    """Photovoltaic array (champ photovoltaïque)."""

    type: Literal["pv_array"]
    modules: Optional[int] = Field(None, ge=1)
    module_W: Optional[Q("W", "Peak power of one module (Wp)")] = None
    strings: Optional[int] = Field(None, ge=1)
    p_kW: Optional[Q("kW", "Total peak power (kWp)")] = None
    voc_V: Optional[Q("V")] = None
    isc_A: Optional[Q("A")] = None


class Battery(NodeBase):
    type: Literal["battery"]
    capacity_kWh: Optional[Q("kWh")] = None
    technology: Optional[str] = None


class Inverter(NodeBase):
    """PV inverter / micro-inverter / hybrid inverter / charger."""

    type: Literal["inverter"]
    kind: Optional[Literal["string", "central", "micro", "hybrid", "battery", "charger"]] = None
    p_kVA: Optional[Q("kVA", "Apparent power per unit")] = None
    mppt: Optional[int] = Field(None, ge=1)
    protection: Optional[str] = Field(None, description="Built-in interface (decoupling) protection (DIN VDE 0126, RI...)")


class Meter(NodeBase):
    """Meter / metering (compteur)."""

    type: Literal["meter"]
    kind: Optional[str] = Field(None, description="'Linky', 'electronic', 'CT', 'sub-metering'...")
    in_A: Optional[Q("A")] = None
    bidirectional: Optional[bool] = None


# ------------------------------------------------------------ switchgear
class Breaker(_Protective):
    """Circuit breaker: modular, moulded-case or air circuit breaker."""

    type: Literal["breaker"]
    curve: Optional[Curve] = None
    trip_unit: Optional[str] = Field(None, description="Trip unit: 'Micrologic 2.2', 'TM-D', 'LSIG'...")
    ir_A: Optional[Q("A", "Long-time / thermal setting")] = None
    isd_A: Optional[Q("A", "Short-time / magnetic setting")] = None
    ii_A: Optional[Q("A", "Instantaneous setting")] = None
    tsd_s: Optional[Q("s", "Short-time delay")] = None
    gf_A: Optional[Q("A", "Ground-fault protection threshold (GF)")] = None
    selective: Optional[bool] = Field(None, description="Selective circuit breaker (SLS)")


class RCD(_Protective):
    """Residual-current device or standalone residual-current unit."""

    type: Literal["rcd"]
    idn_mA: Optional[Q("mA", "Sensitivity IΔn")] = None
    idn_range_mA: Optional[str] = Field(None, description="IΔn setting range, in mA: '30-3000'")
    rcd_type: Optional[RcdType] = None
    delay: Optional[str] = Field(None, description="'S' (selective), 'inst', 'retardable' (adjustable delay), or delay in ms")


class RCBO(_Protective):
    """RCBO: overcurrent + residual-current protection."""

    type: Literal["rcbo"]
    curve: Optional[Curve] = None
    idn_mA: Optional[Q("mA")] = None
    idn_range_mA: Optional[str] = Field(None, description="IΔn setting range, in mA: '30-3000'")
    rcd_type: Optional[RcdType] = None
    delay: Optional[str] = None
    rcd_in_A: Optional[Q("A", "Rating of the associated residual-current add-on block (Vigi), if different")] = None


class MainBreaker(_Protective):
    """Service main breaker (incoming device of a dwelling, e.g. the French AGCP)."""

    type: Literal["main_breaker"]
    range_A: Optional[str] = Field(None, description="Setting range: '15-45', '30-60'")
    idn_mA: Optional[Q("mA")] = None
    idn_range_mA: Optional[str] = Field(None, description="IΔn setting range, in mA")
    rcd_type: Optional[RcdType] = None
    selective: Optional[bool] = Field(None, description="Selective residual-current device (type S)")
    subscribed_kVA: Optional[Q("kVA", "Associated subscribed / setting power (e.g. 9 kVA)")] = None


class Fuse(_Protective):
    type: Literal["fuse"]
    fuse_class: Optional[str] = Field(None, description="'gG', 'aM', 'gPV'...")
    size: Optional[str] = Field(None, description="Size: '10x38', '22x58', 'NH00'...")


class FuseSwitch(_Protective):
    """Fuse switch-disconnector / fuse-carrier disconnector."""

    type: Literal["fuse_switch"]
    fuse_A: Optional[Q("A", "Fuse rating")] = None
    fuse_class: Optional[str] = None
    size: Optional[str] = None


class SwitchDisconnector(_Protective):
    """Switch-disconnector."""

    type: Literal["switch_disconnector"]
    dc: Optional[bool] = Field(None, description="Device for direct current")


class Disconnector(_Protective):
    """Disconnector, without on-load breaking capacity."""

    type: Literal["disconnector"]


class Contactor(_Protective):
    type: Literal["contactor"]
    function: Optional[Literal["HC", "power", "lighting", "load_shedding", "grid_relay", "interface", "other"]] = None
    coil_V: Optional[Q("V")] = None
    manual: Optional[bool] = Field(None, description="Manual override 0/1/Auto")


class ImpulseRelay(_Protective):
    """Impulse relay."""

    type: Literal["impulse_relay"]
    coil_V: Optional[Q("V")] = None


class ThermalRelay(NodeBase):
    """Thermal overload relay for motor protection (relais thermique)."""

    type: Literal["thermal_relay"]
    range_A: Optional[str] = Field(None, description="Setting range: '4-6'")
    setting_A: Optional[Q("A")] = None


class MotorStarter(_Protective):
    """Integrated motor starter (motor circuit breaker, starter, variable-speed drive)."""

    type: Literal["motor_starter"]
    method: Optional[Literal["dol", "reversing", "star_delta", "soft_starter", "vfd"]] = None
    p_kW: Optional[Q("kW")] = None


class TransferSwitch(_Protective):
    """Transfer switch (normal / standby source). The 2nd source arrives through a 'transfer' link."""

    type: Literal["transfer_switch"]
    mode: Optional[Literal["manual", "automatic"]] = None
    technology: Optional[Literal["electromechanical", "static"]] = Field(None, description="'static' = STS")
    interlock: Optional[Literal["mechanical", "electrical", "both"]] = None


class SPD(NodeBase):
    """Surge protective device (parafoudre)."""

    type: Literal["spd"]
    spd_type: Optional[Literal["1", "2", "1+2", "3"]] = None
    imax_kA: Optional[Q("kA")] = None
    in_kA: Optional[Q("kA")] = None
    up_kV: Optional[Q("kV")] = None
    uc_V: Optional[Q("V", "Maximum continuous operating voltage Uc")] = None
    poles: Optional[Literal["1P", "1P+N", "2P", "3P", "3P+N", "4P"]] = None
    dc: Optional[bool] = None


class Controller(NodeBase):
    """Control device drawn as a labelled box: load shedder,
    pilot-wire controller, time switch, day/night relay, energy manager..."""

    type: Literal["controller"]
    function: Optional[str] = Field(None, description="'load shedder', 'pilot wire', 'time switch', 'EMS'...")
    symbol_text: Optional[str] = Field(None, max_length=6, description="Short text inside the box")
    in_A: Optional[Q("A", "Contact rating / rated current")] = None
    poles: Optional[Poles] = None


# --------------------------------------------------------------- connections
class Busbar(NodeBase):
    """Explicit busbar (otherwise implicit as soon as a node has several children)."""

    type: Literal["busbar"]
    in_A: Optional[Q("A")] = None
    ik_kA: Optional[Q("kA")] = None
    dimensions: Optional[str] = Field(None, description="'28x10', 'comb 63 A'...")
    kind: Optional[Literal["busbar", "busway", "comb"]] = Field(None, description="'busway' = prefabricated busbar trunking")
    material: Optional[Literal["Cu", "Al"]] = None
    system: Optional[System] = None
    earthing: Optional[Earthing] = None


class Board(NodeBase):
    """Distribution board / cabinet / enclosure: container drawn as a dashed frame."""

    type: Literal["board"]
    kind: Optional[Literal["main", "distribution", "sub", "ac_box", "dc_box", "mcc", "switchboard", "enclosure",
                           "panelboard", "pdu", "substation"]] = None
    in_A: Optional[Q("A", "Rated current of the board / busbar")] = None
    ik_kA: Optional[Q("kA", "Maximum Ik at the busbar")] = None
    ik1_kA: Optional[Q("kA", "Minimum Ik (Ik1) at the busbar")] = None
    system: Optional[System] = None
    earthing: Optional[Earthing] = Field(None, description="Earthing system specific to the board (downstream of a transformer, local IT...)")
    ways: Optional[int] = Field(None, ge=1, description="Number of outgoing ways / modules")
    ip: Optional[str] = Field(None, description="Ingress protection rating: 'IP30', 'IP65 IK08'")
    form: Optional[str] = Field(None, description="Form of internal separation: '2b', '4a'")
    own_sheet: Optional[bool] = Field(None, description="Force rendering on a dedicated sheet")
    pen_split: Optional[bool] = Field(
        None, description="TN-C-S: the PEN conductor is split into PE + N at this board (by default, the first "
                          "board of a TN-C-S installation)")


class Earth(NodeBase):
    type: Literal["earth"]
    resistance_ohm: Optional[Q("Ohm")] = None


# ------------------------------------------------------------ loads
class _Load(NodeBase):
    p_max_kW: Optional[Q("kW", "Maximum power permitted on the circuit (e.g. 'max 4500 W')")] = None
    room: Optional[str] = Field(None, description="Room / area served")


class Lighting(_Load):
    type: Literal["lighting"]
    points: Optional[int] = Field(None, ge=0, description="Number of lighting points")


class Socket(_Load):
    type: Literal["socket"]
    points: Optional[int] = Field(None, ge=0, description="Number of socket outlets")
    poles: Optional[Literal["2P", "2P+T", "3P", "3P+T", "3P+N", "3P+N+T"]] = Field(
        None, description="Socket polarity (T = earth contact)")
    in_A: Optional[Q("A", "Socket rated current (16 A, 32 A)")] = None
    socket_type: Optional[str] = Field(None, description="'2P+E 16 A', '3P+N+E 32 A', 'dedicated'...")


class Heating(_Load):
    type: Literal["heating"]
    pilot_wire: Optional[bool] = None


class WaterHeater(_Load):
    type: Literal["water_heater"]
    volume_L: Optional[float] = Field(None, ge=0)


class Cooking(_Load):
    type: Literal["cooking"]
    kind: Optional[Literal["hob", "oven", "range", "other"]] = None


class Appliance(_Load):
    type: Literal["appliance"]
    kind: Optional[Literal["washing_machine", "dishwasher", "dryer", "freezer", "fridge", "other"]] = None


class Motor(_Load):
    type: Literal["motor"]
    in_A: Optional[Q("A")] = None
    rpm: Optional[float] = Field(None, ge=0)
    phases: Optional[Literal[1, 3]] = None


class EVCharger(_Load):
    """Electric vehicle charging equipment (EVSE)."""

    type: Literal["ev_charger"]
    mode: Optional[Literal["2", "3", "4"]] = None


class Ventilation(_Load):
    type: Literal["ventilation"]


class Shutter(_Load):
    type: Literal["shutter"]


class Load(_Load):
    """Generic load."""

    type: Literal["load"]
    symbol_text: Optional[str] = Field(None, max_length=6)


class OffPage(NodeBase):
    """Off-page reference to / from another sheet or document (drawn as a cross-reference arrow)."""

    type: Literal["offpage"]
    target: Optional[str] = Field(None, description="Destination: 'sheet 2', 'DB Hall', 'doc. ELEC-04'...")


# ------------------------------------------------------- PLCs
ModuleKind = Literal["cpu", "coupler", "power_feed", "power_supply", "di", "do", "ai", "ao", "relay_out", "mixed_io",
                     "counter", "temperature", "power_measurement", "comm", "safety", "motor", "end", "other"]


class PLCModule(UWModel):
    """PLC module, in mounting order on the rail / local bus."""

    slot: int = Field(ge=0, description="Position on the local bus (1 = first module after the head unit)")
    kind: ModuleKind
    part_number: Optional[str] = None
    product: Optional[Product] = None
    label: Optional[str] = None
    channels: Optional[int] = Field(None, ge=0, description="Number of channels")
    un_V: Optional[Q("V", "Channel voltage (24 V DC, 230 V AC)")] = None
    rating_A: Optional[Q("A", "Permissible current per channel (outputs)")] = None
    signal: Optional[str] = Field(None, description="Signal: '0-10 V', '4-20 mA', 'PT100', 'digital' (TOR)...")
    protocol: Optional[str] = Field(None, description="For a communication module: 'RS485', 'KNX', 'DALI', 'M-Bus'")
    channel_labels: dict[str, str] = Field(default_factory=dict, description="Label per channel: {'1': 'Pump 1'}")


class PLC(NodeBase):
    """Modular programmable logic controller (WAGO 750/PFC, Siemens S7-1200/ET 200SP/LOGO!, Schneider M241/TM3...).
    Modules are ordered sub-components; channels are addressed through link ports
    (``from_port`` / ``to_port`` = 'slot.channel', e.g. '3.1')."""

    type: Literal["plc"]
    role: Optional[Literal["controller", "coupler", "expansion", "hmi"]] = Field(
        None, description="'coupler' = remote I/O head on a fieldbus")
    family: Optional[str] = Field(None, description="'PFC200', 'S7-1200', 'LOGO! 8', 'M241'")
    protocols: list[str] = Field(default_factory=list, description="'Modbus TCP', 'PROFINET', 'EtherNet/IP', 'KNX'...")
    onboard: list[PLCModule] = Field(default_factory=list, description="I/O built into the head unit (slot 0)")
    modules: list[PLCModule] = Field(default_factory=list, description="Expansion modules, in slot order")
    ip_address: Optional[str] = None


class PowerSupply(NodeBase):
    """Power supply (switch-mode AC/DC, control transformer): 230 V AC -> 24 V DC."""

    type: Literal["power_supply"]
    u1_V: Optional[Q("V", "Input voltage")] = None
    u2_V: Optional[Q("V", "Output voltage")] = None
    output: Optional[Literal["DC", "AC"]] = "DC"
    in_A: Optional[Q("A", "Rated output current")] = None
    p_W: Optional[Q("W", "Rated power")] = None
    redundant: Optional[bool] = None


class Spare(NodeBase):
    """Spare / free way (possibly pre-equipped: rating, poles)."""

    type: Literal["spare"]
    in_A: Optional[Q("A")] = None
    poles: Optional[Poles] = None
    frame_A: Optional[Q("A")] = None


# ------------------------------------------------------- instrument transformers, MV equipment, auxiliaries
class InstrumentTransformer(NodeBase):
    """Instrument transformer: CT, VT, toroid. In series in the tree or as an auxiliary device (``devices``)."""

    type: Literal["instrument_transformer"]
    kind: Optional[Literal["ct", "vt", "toroid", "combined"]] = None
    ratio: Optional[str] = Field(None, description="'600/5 A', '20000/100 V'")
    accuracy: Optional[str] = Field(None, description="Accuracy class: '0.5', '5P10', 'C100'")
    burden_VA: Optional[Q("VA")] = None


class ProtectionRelay(NodeBase):
    """Protection relay (ANSI 50/51, 27/59, Vigirex residual-current relay, RI interface protection...)."""

    type: Literal["protection_relay"]
    functions: list[str] = Field(default_factory=list, description="Functions: '50/51', '51N', 'I>', 'RI'...")
    settings: Optional[str] = Field(None, description="Printed settings: 'I> 0,6 s ; I>> 0,1 s'")
    idn_mA: Optional[Q("mA", "Residual-current threshold (Vigirex relay)")] = None


class EarthingSwitch(NodeBase):
    """Earthing switch."""

    type: Literal["earthing_switch"]
    icw_kA: Optional[Q("kA")] = None
    ue_V: Optional[Q("V")] = None


class VoltageIndicator(NodeBase):
    """Voltage presence indicator (VPIS / capacitive dividers)."""

    type: Literal["voltage_indicator"]


class InsulationMonitor(NodeBase):
    """Insulation monitoring device (IMD) of an IT system."""

    type: Literal["insulation_monitor"]
    range: Optional[str] = None


class SurgeLimiter(NodeBase):
    """Surge limiter (Cardew) between neutral (or phase) and earth in IT systems."""

    type: Literal["surge_limiter"]
    un_rating_V: Optional[Q("V")] = None


class NeutralImpedance(NodeBase):
    """Neutral earthing impedance (impedance-earthed IT, neutral-point coil)."""

    type: Literal["neutral_impedance"]
    impedance_ohm: Optional[Q("Ohm")] = None


class TerminalBlock(NodeBase):
    """Terminal block / distribution block / connection point."""

    type: Literal["terminal_block"]
    terminals: Optional[str] = Field(None, description="Terminal numbers: 'X1.1-X1.12'")


class JunctionBox(NodeBase):
    """Junction / tap / pull box, cable joint, manhole."""

    type: Literal["junction_box"]
    kind: Optional[Literal["junction", "pull", "tap", "manhole", "vault", "service_end"]] = None


class Connector(NodeBase):
    """Pluggable connector (MC4, connection plug / socket, cable connector)."""

    type: Literal["connector"]
    kind: Optional[str] = Field(None, description="'MC4', 'Wieland', 'plug 3P+N+T 32 A'...")
    in_A: Optional[Q("A")] = None


class DCConverter(NodeBase):
    """DC converter: PV optimizer, MPPT controller, DC/DC, solar charge controller."""

    type: Literal["dc_converter"]
    kind: Optional[Literal["optimizer", "mppt", "dcdc", "charge_controller"]] = None
    p_kVA: Optional[Q("kVA")] = None
    in_A: Optional[Q("A")] = None


class EarthBar(NodeBase):
    """Main earthing terminal / bar, PE bar or equipotential bar."""

    type: Literal["earth_bar"]
    kind: Optional[Literal["main_earth", "pe_bar", "equipotential", "neutral_bar"]] = None


NODE_CLASSES = (
    Grid, Transformer, Generator, UPS, PVArray, Battery, Inverter, Meter,
    Breaker, RCD, RCBO, MainBreaker, Fuse, FuseSwitch, SwitchDisconnector, Disconnector,
    Contactor, ImpulseRelay, ThermalRelay, MotorStarter, TransferSwitch, SPD, Controller,
    Busbar, Board, Earth,
    Lighting, Socket, Heating, WaterHeater, Cooking, Appliance, Motor, EVCharger,
    Ventilation, Shutter, Load, Spare, OffPage,
    InstrumentTransformer, ProtectionRelay, EarthingSwitch, VoltageIndicator, InsulationMonitor, SurgeLimiter,
    NeutralImpedance, TerminalBlock, JunctionBox, Connector, DCConverter, EarthBar,
    PLC, PowerSupply,
)

Node = TypeAliasType("Node", Annotated[Union[NODE_CLASSES], Field(discriminator="type")])  # type: ignore[valid-type]

NODE_TYPES: dict[str, type[NodeBase]] = {
    cls.model_fields["type"].annotation.__args__[0]: cls for cls in NODE_CLASSES  # type: ignore[union-attr]
}

NodeBase.model_rebuild()  # each node class completes its own schema when first used
