# Code-first API (`uniwire.build`)

`uniwire.build` lets you describe electrical installations as Python code. The code builds a regular uniwire
document: you can save it as `*.uniwire.json`, check it, render it or export its bill of materials.

```python
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
```

## Rules of the game

* **`with Installation(...) as inst:`** opens a document. Every element must be created inside it.
* **`with X:`** makes `X` the current parent: every element created inside the block is fed by `X`.
  Several context managers on one line (`with Grid(...), MainBreaker(...), Board(...):`) build a chain.
* **`a >> b`** moves `b` under `a` and returns `b`, so `a >> b >> c` builds a chain
  (feeder breaker → contactor → motor).
* An element created **outside any parent** becomes a source (a root of the tree).
* **Values accept units as strings** (`"16 A"`, `"2,5 mm²"`, `"30 mA"`, `"7.2 kW"`); the document stores
  canonical numbers in the field units (`in_A`, `section_mm2`, …).
* Every keyword argument that is a field of the uniwire type is passed through unchanged
  (`Breaker("-Q1", "C16", icn_kA=6, aux=["MX"])`). An unknown keyword raises `TypeError`.

## `Installation`

```python
Installation(title=None, *, earthing=None, system=None, un=None, profiles=(), lang="en", **fields)
```

* `earthing` (`"TT"`, `"TN-S"`, `"IT"`…), `system` (`"1P+N"`, `"3P+N"`…), `un` (`"400 V"`) fill the
  `installation` object; any other `installation` or `meta` field can be given as a keyword
  (`project="EX-10"`, `subscribed_kVA=12`, `ik3_kA=10`, `author=...`).
* `profiles` lists the rule profiles to apply; `lang` sets `meta.lang` (`"en"` or `"fr"`), which controls
  the language of the drawing.

Methods and properties:

| Member | Result |
|---|---|
| `inst.document` | the validated `Document` (raises `UniwireError` with explicit messages) |
| `inst.to_dict()` / `inst.json()` | raw dict / canonical JSON text |
| `inst.save(path)` | writes the `*.uniwire.json` file |
| `inst.check(profiles=None)` | list of rule findings |
| `inst.bom()` | bill of materials rows |
| `inst.render("x.pdf")` | one multi-page PDF; any other path renders a directory of SVG sheets |
| `inst.view(**fields)` | adds a view (`paper="A3"`, `title=...`, `root=...`, `cartouche=[...]`) |
| `inst.declare_interlock(key, keys=1, label=None, kind=None)` | declares an interlock (`interlocks[]`): at most `keys` members whose `locks` contain `key` are closed |

In Jupyter, an `Installation` displays its first sheet inline.

## Element classes

There is one class per uniwire node type (53 in format 1.0). The class name is the type in CamelCase,
with a few acronyms:

| Category | Classes |
|---|---|
| Sources | `Grid`, `Transformer`, `Generator`, `UPS`, `PVArray`, `Battery`, `Inverter`, `DCConverter` |
| Protection | `Breaker`, `RCD`, `RCBO`, `MainBreaker`, `Fuse`, `FuseSwitch`, `ThermalRelay`, `SPD`, `ProtectionRelay`, `SurgeLimiter` |
| Switching | `SwitchDisconnector`, `Disconnector`, `Contactor`, `ImpulseRelay`, `MotorStarter`, `TransferSwitch`, `EarthingSwitch` |
| Measurement | `Meter`, `InstrumentTransformer`, `VoltageIndicator`, `InsulationMonitor` |
| Control | `Controller`, `PLC`, `PowerSupply` |
| Conductors, containers | `Busbar`, `Board`, `Earth`, `EarthBar`, `NeutralImpedance`, `TerminalBlock`, `JunctionBox`, `Connector`, `OffPage` |
| Loads | `Lighting`, `Socket`, `Heating`, `WaterHeater`, `Cooking`, `Appliance`, `Motor`, `EVCharger`, `Ventilation`, `Shutter`, `Load`, `Spare` |

### Positional arguments

* **Reference designation first** when it looks like one: `Breaker("-Q11", ...)`, `Board("TD1")`.
  Loads, grids, PV arrays, batteries and off-page references take a **label** first instead:
  `Lighting("Kitchen", points=4)`, `Grid("Utility")`.
* **Rating** for switchgear (`Breaker`, `RCBO`, `Fuse`, `FuseSwitch`, `SwitchDisconnector`,
  `Disconnector`, `Contactor`, `ImpulseRelay`, `MotorStarter`, `TransferSwitch`, `RCD`, `Socket`,
  `Connector`, `Spare`):
    * `"C16"` → curve C, `in_A` 16 (curves B, C, D, K, Z);
    * `"gG 32 A"` → `fuse_class` gG, `in_A` 32 (also aM, gL, gPV);
    * `"40 A"` or `40` → `in_A` 40.
* `MainBreaker("-Q0", "15-45 A")` sets the adjustable range `range_A`; a single value sets `in_A`.
* **Sensitivity** next for residual-current devices: `RCD("-Q1", "40 A", "30 mA")`,
  `RCBO("-Q2", "C16", "30 mA")`, `MainBreaker("-Q0", "15-45 A", "500 mA")`.
* A remaining string becomes the `label`.

### Keyword shortcuts

| Keyword | Field |
|---|---|
| `type=` | `rcd_type` on RCD / RCBO / main breaker, `spd_type` on SPD, `kind` elsewhere |
| `p=` `un=` `idn=` `icn=` `icu=` `sn=` `u1=` `u2=` `ucc=` `capacity=` `surface=` | `p_kW`, `un_V`, `idn_mA`, `icn_kA`, `icu_kA`, `sn_kVA`, `u1_V`, `u2_V`, `ucc_pct`, `capacity_kWh`, `surface_m2` |
| `rating=` | `in_A` |
| `range=` | `range_A` on types that have it |
| `product="WAGO 750-8212"` | `product={"manufacturer": "WAGO", "part_number": "750-8212"}` (a dict is passed through) |
| `annex=True` | places the element in `devices[]` (outside the power tree), to be connected by links |

### Cables

`cable=` describes the cable run **between the parent and this element**:

```python
Breaker("-Q11", "C16", cable="3G1,5")                 # cores 3G, section_mm2 1.5
Breaker("-Q21", "D16", cable="4G2,5 25 m")            # + length_m 25
Breaker("-Q30", "C32", cable="U1000R2V 5G6 40 m")     # + designation U1000R2V
Breaker("-Q31", "C20", cable="3G2,5", length="18 m")  # length as a separate keyword
Breaker("-Q40", "250 A", cable={"cores": "4x", "section_mm2": 120, "material": "Al", "install": "E"})
```

## Templates

`Template(**fields)` returns a reusable keyword set; unpack it with `**`:

```python
MOT = Template(curve="D", icn_kA=10, poles="3P", product={"manufacturer": "ACME", "range": "MCB-100"})
Breaker("-Q21", "D16", **MOT)
```

(Unlike JSON `templates` / `use`, code templates are expanded when the element is created.)

## Links

Connections outside the tree are created with helper functions that take two elements (or PLC ports),
an optional label and any link field:

`control`, `data`, `transfer`, `tie`, `infeed`, `earth`, `interlock`, `trip`, `measure`, `bypass`, and the
generic `link(kind, a, b, label=None, **fields)`.

```python
transfer(q_generator, ats)                         # standby source into a transfer switch
tie(busbar_a, busbar_b, device=Breaker("-Q50", "630 A"))   # bus coupling with its device
measure(InsulationMonitor("-IM1", annex=True), busbar_a)
data(remote_io, controller, protocol="Modbus TCP")
```

## PLCs

`PLC(...)` adds `.add(kind, part_number=None, **fields)`, which appends a module on the local bus
(next free slot, or `slot=`) and returns a `Port` for that slot. Index a port with a channel to address
one I/O: `port[2]` is channel 2. `plc.port(slot, channel)` and `plc[slot][channel]` work too.

```python
api = PLC("-A1", label="Pump controller", family="PFC200", role="controller",
          protocols=["Modbus TCP"], product="WAGO 750-8212")
api.add("power_feed", "750-602", un_V=24)
di = api.add("di", "750-430", channels=8, channel_labels={"1": "High level"})
relays = api.add("relay_out", "750-512", channels=2, rating_A=2)
api.add("end", "750-600")

km = Breaker("-Q22", "D16") >> Contactor("-KM21", "18 A", coil_V=230)
control(relays[1], km, "Pump 1")      # control link with from_port "3.1" (slot 3, channel 1)
```

`Module(kind, part_number=None, **fields)` builds a module dict if you prefer to pass `modules=[...]`
directly.

## Enclosures

`with Enclosure(label, kind="cabinet", ref=None, **fields):` records every element created inside the
block as a member of an addressable enclosure (`enclosures[]`). Unlike a `Board`, it does **not** change the
electrical parent, so it can group elements from different branches (cabinet, MV cell, zone). Enclosures
can be nested.

```python
with Board("TGBT"), Breaker("-Q1", "400 A", poles="4P"):
    with Enclosure("Cabinet A", kind="cabinet"):
        Breaker("-Q11", "C16", cable="3G2,5 40 m") >> Socket("Workshop sockets", points=6)
    Breaker("-Q12", "D32", poles="3P") >> Motor("Compressor", p="15 kW")
```

## Complete example

A pumping station with a modular PLC, two motor feeders driven by relay outputs and a remote I/O
coupler linked over Modbus TCP
([`examples/code/pumping_station.py`](https://github.com/uniwire-dev/uniwire/blob/main/examples/code/pumping_station.py)):

```python
--8<-- "examples/code/pumping_station.py"
```
