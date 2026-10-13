# UEP-0001: Terminals, terminal strips and wires

| | |
|---|---|
| **UEP** | 0001 |
| **Title** | Terminals, terminal strips and wires |
| **Status** | **Draft**. The part that the current format can carry, for tree cables (`wire_marking`, `wire_marks`, `cable.marks`, exports `wires` / `markers` / `cables`, `marks --write`) is implemented in the reference library |
| **Target** | uniwire format 2.0 |
| **Type** | Format change (additive) |
| **Created** | 2026-10-12 |
| **Discussion** | GitHub issue with the `uep` label |

The key words **MUST**, **MUST NOT**, **SHOULD** and **MAY** are to be interpreted as described in RFC 2119.
Section references of the form "SPEC §n" point to the [uniwire specification](../SPEC.md) (format 1.0).

---

## Abstract

This proposal adds wiring information to uniwire without changing what a 1.x document means. It adds:

1. **named ports** on every node (the terminals of the equipment: `1`, `2`, `A1`, `A2`, `13`, `14`, `U1`,
   `PE`…), with defaults taken from the type registry, overrides on the node, and a reference syntax
   `<node id>#<port>`;
2. **terminal strips** (`terminal_strips[]`), whose terminals are addressable like ports (`X1#3`, shown
   as `-X1:3`);
3. **wires** (`wires[]`) and **cables** (`cables[]`) as first-class objects;
4. **potentials** (equipotential nets): derived from the power tree and the wires, and optionally named
   (`potentials[]`);
5. **wire marking rules** in views, and exports of the wire marker list, the terminal plan and the cable
   schedule;
6. a sketch (not normative) of a future `"control"` view kind that would draw control schematics from the
   same data;
7. consistency rules, and mappings to IEC 81346, IEC 61082, IEC 60445, CIM, IFC and IEC 61850 SCL.

Layout stays automatic. A document still contains no coordinates. The single-line diagram stays the main use
case: everything added here is optional.

## 1. Motivation

### 1.1 Use cases

A single-line diagram is rarely the only electrical document of a project. The same installation is also
described by:

* **control schematics**: coils, auxiliary contacts, push buttons, pilot lights, PLC inputs and outputs,
  self-hold circuits, interlocks, arranged in current paths with cross-references from each coil to its contacts;
* **panel wiring**: point-to-point connection lists used to build a cabinet, often with one row per wire
  (from terminal, to terminal, cross-section, colour, mark);
* **terminal plans**: for each terminal strip, what lands on each terminal on the cabinet side and on the field
  side, the bridges, and the cable cores;
* **wire marking and ferrule lists**: the marks printed on sleeves at both ends of each wire;
* **cable schedules**: each cable with its type, its cores, its length, the enclosures it connects and the use
  of each core;
* **commissioning**: loop checks and point-to-point tests, done terminal by terminal;
* **maintenance**: finding where a wire goes, which terminals are on a potential, which contacts a coil drives.

Electrical CAD tools hold this information in proprietary databases. No open, compact, text-based format covers
it with the same principles as uniwire: describe the installation, not the drawing.

### 1.2 What uniwire 1.x cannot express

The 1.x format describes power topology (a tree plus links) and stops at the level of a device:

* `terminal_block.terminals` is **free text** (`"X1.1-X1.12"`). Individual terminals cannot be referenced,
  so a terminal plan cannot be generated or checked.
* `links[].from_port` / `to_port` are **free strings**. Only the PLC form `slot.channel` is checked (rule
  `plc.port`). A link `{"kind": "control", "from": "A1", "from_port": "2.1", "to": "KM1"}` says that a PLC
  output controls a contactor; it does not say that the output lands on terminal `A1` of the coil through
  terminal 10 of strip `-X1`.
* Auxiliary equipment is a list of names (`aux: ["MX", "OF"]`). An auxiliary contact or a release cannot be
  wired, and its relation to its parent cannot be shown in a cross-reference.
* A cable belongs to exactly one tree edge (`node.cable`). A control cable that carries several circuits
  between a cabinet and a push-button station has nowhere to go, and its cores cannot be listed.
* The multi-line view already derives one conductor per phase and draws the poles of each device. The
  conductors have no identity in the file, so they cannot be marked or exported.
* The specification already lists "named ports (`Q1#MX`, `T1#N`)" and "cable as a first-class edge"
  among the items planned for 2.0 (SPEC §3a, "Out of scope").

## 2. Goals and non-goals

### 2.1 Goals

* G1. Any terminal of any device, and any terminal of a terminal strip, can be referenced by a short,
  stable string.
* G2. A wire can be described with the attributes used in practice: ends, mark, cross-section, colour, cable
  and core, conductor function, potential.
* G3. A terminal plan, a wire list, a wire marker list and a cable schedule can be **generated** from a document
  and **checked** by rules.
* G4. Power conductors already derived by the multi-line view get an identity (ports and potentials) with no
  extra data, so they can be marked and exported.
* G5. A future control-schematic view needs no other data than what this proposal adds.
* G6. Every 1.x document stays valid and keeps its meaning. A 2.0 document that uses none of the new sections
  reads exactly like a 1.x document.

### 2.2 Non-goals

* N1. **Not a full electrical CAD model.** No sheets, symbols, coordinates, wire routing, ducts, rail layout
  or 3D panel layout. The file still describes the installation, and the drawing is computed.
* N2. **Geometry stays automatic.** Views may carry preferences (marking scheme, order of current paths); they
  never carry topology.
* N3. **The single-line diagram stays the main use case.** Ports, wires and terminal strips are optional. A
  single-line diagram never needs them, and no rule of the `core` profile requires them.
* N4. Not a product database. Port defaults follow common marking conventions. Products that differ declare
  their own ports (on the node, in a template, or through the product).
* N5. No PLC programming, no signal lists beyond what wiring needs (channel, label).

## 3. Proposal

### 3.1 Named ports

#### 3.1.1 Port model

A **port** is a terminal of a node: a point where a conductor can be connected. Each node has a set of ports.
The set comes from the type registry (§3.1.3), optionally merged with a `ports` list on the node (§3.1.4).

| Field | Type | Description |
|---|---|---|
| `id` | string, **required** | Port identifier, unique within the node. Pattern `^[A-Za-z0-9+-][A-Za-z0-9_.:/+-]*$`. Examples: `1`, `2`, `A1`, `13`, `U1`, `PE`, `2N`, `L+`, `3.1` (PLC slot 3, channel 1), `X1:3` (pin 3 of the device's own connector `X1`). Case-sensitive |
| `marking` | string | Terminal marking printed on the device, when it differs from `id` or repeats (`N` on both sides of a neutral pole). Default: `id` |
| `aliases` | string[] | Other accepted names in references (`L1` for `1`, `T1` for `2`, `N` for `2N`, `U` for `U1`) |
| `function` | enum | `pole_in`, `pole_out`, `power_in`, `power_out`, `neutral`, `earth`, `shield`, `coil`, `contact_no`, `contact_nc`, `contact_co`, `signal_in`, `signal_out`, `supply`, `comm`, `other` |
| `pole` | integer ≥ 1 | Rank of the pole or winding. Used to assign a conductor by position (§3.4.2) |
| `conductor` | enum | Fixed conductor of the port when it does not depend on the circuit: `N`, `PE`, `PEN`, `L+`, `L-`… |
| `pair` | string | The other terminal of the same pole, contact, coil or winding (`2` for `1`, `A2` for `A1`, `14` for `13`) |
| `label` | text | Description (`Start`, `Run feedback`) |
| `mandatory` | boolean | The port must be connected when the node is wired (§3.7). Registry default: `true` for coils and for power poles of wired nodes, `false` otherwise |
| `capacity` | integer ≥ 1 | Maximum number of conductors on the terminal. Registry default: 2; PLC channels: 1 |
| `section_max_mm2` | number | Largest conductor the terminal accepts |
| `ext` | object | Extensions |

Port functions:

| `function` | Meaning | Examples |
|---|---|---|
| `pole_in` / `pole_out` | Line side / load side of a power pole of a switching or protective device | breaker `1` / `2`, contactor `1/L1` / `2/T1` |
| `power_in` / `power_out` | Power terminal of a load, or the input / output of a source or converter | motor `U1`, power supply `L` / `L+`, transformer `1U` / `2U` |
| `neutral`, `earth`, `shield` | Neutral, protective or functional earth, cable screen | `N`, `PE`, screen clamp |
| `coil` | Operating coil or release | `A1`, `A2`; shunt release `C1`, `C2`; undervoltage release `D1`, `D2` |
| `contact_no` / `contact_nc` / `contact_co` | Auxiliary contact: normally open, normally closed, common of a changeover | `13`-`14`, `21`-`22`, `11` (common) with `12` / `14` |
| `signal_in` / `signal_out` | Input / output of a controller or a sensor | PLC `1.1`, `2.1` |
| `supply` | Auxiliary supply of an electronic device | PLC `L+`, `M` |
| `comm` | Communication port | RJ45, RS485 terminals |

#### 3.1.2 Port references

A port is referenced by `<node id>#<port>`:

```text
KM1#A1      coil terminal A1 of contactor KM1
Q1#2        load-side terminal of pole 1 of breaker Q1
A1#2.1      PLC A1, slot 2, channel 1
X1#3        terminal 3 of terminal strip X1 (§3.2)
T1#N        neutral of transformer T1 (alias of port 2N)
Q1#MX       the shunt-release auxiliary of Q1, as a whole (§3.1.5)
Q1.MX#C1    terminal C1 of that auxiliary
```

* The node part matches the identifier pattern of SPEC §3 (`^[A-Za-z_][A-Za-z0-9_.-]*$`), which excludes
  `#`. A reference is split at its first `#`.
* Only nodes with an explicit `id` can be referenced. Generated identifiers are not stable, so a reference
  to a generated identifier is an error.
* The port part is matched against `id` first, then against `aliases`. An alias that matches two ports of the
  same node is an error. `uniwire normalize` rewrites aliases to the canonical `id`.
* Identifiers of nodes, terminal strips, cables, wires and potentials share **one namespace** (unique within
  the document), so `X1#3` is never ambiguous. Enclosure identifiers keep their own namespace, as in 1.x.
* **Display**: a port is displayed as `<ref>:<marking>`, for example `-KM1:A1` or `-X1:3`. The colon is the
  terminal prefix of IEC 81346 reference designations. When the node has no `ref`, its `id` is used. Views and
  exports MAY prefix the location (`+FS3-S1:11`) when the two ends of a wire are in different enclosures.

**Links.** The fields `links[].from_port` / `to_port` keep their place. In 2.0 their value is the port
part of a port reference: `{"from": "A1", "from_port": "2.1"}` designates `A1#2.1` and is checked like
one. As a shorthand, `from` / `to` MAY carry a full port reference (`"from": "A1#2.1"`). A link that carries
both forms MUST be consistent. Links remain the single-line abstraction ("A1 controls KM1"). Wires (§3.3)
describe the physical connections behind them.

#### 3.1.3 Registry defaults

Each type of the registry ([`core.json`](https://github.com/uniwire-dev/uniwire/blob/main/src/uniwire/registry/core.json))
gains an optional `ports` entry. Defaults may depend on a field of the node, usually `poles` or `contacts`. The
registry stores **port sets** selected by that field, or a generator for ports that depend on the node's
content (PLC channels, contact lists, conductors of a load).

```json
"breaker": {
  "ports": {
    "by": "poles",
    "sets": {
      "1P":   [{"id": "1", "function": "pole_in", "pole": 1, "pair": "2"},
               {"id": "2", "function": "pole_out", "pole": 1, "pair": "1"}],
      "3P+N": ["… 1-2, 3-4, 5-6 …",
               {"id": "N1", "marking": "N", "function": "neutral", "pair": "N2"},
               {"id": "N2", "marking": "N", "function": "neutral", "pair": "N1"}]
    },
    "default": "3P"
  }
}
```

The defaults below follow common practice for low-voltage equipment (IEC 60445 for equipment terminals and
conductors, and the terminal marking conventions used for control devices in the IEC 60947 series). Products
that differ declare their own ports.

| Type | Default ports |
|---|---|
| `breaker`, `fuse`, `fuse_switch`, `switch_disconnector`, `disconnector`, `main_breaker` | One pair per pole: `1`-`2`, `3`-`4`, `5`-`6` (`1P`: `1`-`2`; `2P`: `1`-`2`, `3`-`4`; `4P`: + `7`-`8`). Unprotected neutral pole of `1P+N` / `3P+N`: `N1`-`N2`, both marked `N`. Odd = line side (`pole_in`), even = load side (`pole_out`) |
| `rcd`, `rcbo` | Same as the breaker. A 2-pole RCD is `1`-`2` and `N1`-`N2` |
| `contactor` | Main poles `1`-`2`, `3`-`4`, `5`-`6` (+ `7`-`8` for `4P`), aliases `L1`/`T1`, `L2`/`T2`, `L3`/`T3`. Coil `A1`-`A2`. Built-in auxiliary contacts from the new optional field `contacts` (below) |
| `impulse_relay` | Poles as the contactor, coil `A1`-`A2` |
| `thermal_relay` | `1`-`2`, `3`-`4`, `5`-`6` (aliases `L1`/`T1`…), auxiliary contacts `95`-`96` (NC) and `97`-`98` (NO) |
| `motor_starter` | Poles `1`-`2`, `3`-`4`, `5`-`6`. Other terminals (drive control terminals) are product-specific: declare them, for instance `X1:3` |
| `motor` | `U1`, `V1`, `W1` (aliases `U`, `V`, `W`), `PE`. Single-phase (`phases: 1`): `U1`, `U2`, `PE`. Six-terminal motors (star-delta) add `U2`, `V2`, `W2` through `ports` or a template |
| `transformer` | `1U`, `1V`, `1W` (primary), `2U`, `2V`, `2W` (secondary), `2N` (alias `N`) when the vector group has a neutral (`Dyn11`), `PE` |
| `power_supply` | `L`, `N`, `PE` (input), `L+`, `L-` (output, aliases `+`, `-`). AC output: `L`, `N` of the secondary as `2L`, `2N` |
| `plc` | Head unit supply `L+`, `M`, `PE`. One port per channel, generated from `onboard[]` and `modules[]`: `<slot>.<channel>` (`0.3` = built-in channel 3), `signal_in` for `di` / `ai` / `counter` / `temperature` modules, `signal_out` for `do` / `ao` / `relay_out`. Capacity 1. Commons and module supply terminals are declared in `ports` |
| `spd` | One terminal per protected conductor (`L1`, `L2`, `L3`, `N`), and `PE` |
| `grid`, `generator`, `ups`, `offpage`, `busbar` | One port per conductor of the derived system: `L1`, `L2`, `L3`, `N`, `PEN`, `PE` (`L+`, `L-` in DC) |
| `board` | `PE` (protective conductor terminal of the enclosure); `N` when the board carries a neutral |
| `earth_bar` | `PE` with a capacity of 0 (unlimited). Further terminals are declared |
| Loads (`socket`, `lighting`, `heating`, `load`…) | One port per derived conductor: `L` (or `L1`, `L2`, `L3`), `N`, `PE` |
| Control devices (§3.1.6) | From `contacts`: see below |

**Contact lists.** Types that carry auxiliary contacts (`contactor`, `control_relay`, `push_button`,
`selector_switch`, `auxiliary`) accept an optional field `contacts`, an ordered list of `NO`, `NC` and `CO`
(changeover). Default ports follow the two-digit convention: the first digit is the position of the contact in
the list (1, 2, 3…), the second digit is its function (`1`-`2` normally closed, `3`-`4` normally open, `1`
common with `2` / `4` for a changeover). So `["NO", "NC"]` gives `13`-`14` and `21`-`22`, a stop button
`["NC"]` gives `11`-`12`, and a start button `["NO"]` gives `13`-`14`.

#### 3.1.4 Overrides on the node

Every node gains two optional fields:

| Field | Description |
|---|---|
| `ports` | List of ports (§3.1.1). Merged **by `id`** with the registry defaults: an entry with an existing `id` replaces the default, a new `id` adds a port |
| `port_defaults` | `false` drops the registry defaults, so only `ports` applies. Default `true` |

`ports` is an ordinary attribute, so it can come from a template (`use`, SPEC §3.3). A template is the natural
place for the terminal layout of a product range. Overriding the marking of a contactor whose built-in contact
is a normally closed contact marked `21`-`22`:

```json
{"id": "KM2", "type": "contactor", "ref": "-KM2", "poles": "3P", "coil_V": 230, "contacts": ["NC"],
 "ports": [{"id": "21", "function": "contact_nc", "pair": "22"},
           {"id": "22", "function": "contact_nc", "pair": "21"}]}
```

With `contacts: ["NC"]` alone, the default would be `11`-`12`. The two override entries add `21`-`22`, but
`11`-`12` are still generated. To replace them, set `port_defaults: false` and declare every port, or use a
template that does so.

#### 3.1.5 Auxiliary blocks as sub-components

Add-on auxiliary contact blocks, shunt releases (MX), undervoltage releases (MN), signalling contacts (OF, SD)
and similar parts have terminals of their own, and they act on, or report, the state of their parent device.
They become nodes of a new type **`auxiliary`**, placed in `devices[]` (SPEC §3a), with a `parent` relation:

| Field | Description |
|---|---|
| `type` | `auxiliary` |
| `parent` | **Required.** `id` of the device the block is mounted on (switching or protective device, relay) |
| `kind` | `aux_contact`, `alarm_contact`, `shunt_release`, `undervoltage_release`, `motor_operator`, `other` |
| `name` | Short name used in references and in the 1.x `aux[]` list: `MX`, `MN`, `OF`, `SD` |
| `contacts` | For contact blocks: list of `NO` / `NC` / `CO` (§3.1.3) |
| `coil_V` | For releases and motor operators |
| `ref` | Usually the parent's reference designation (`-Q1`). Auxiliaries are exempt from the duplicate reference rule |

Default ports: `shunt_release` `C1`-`C2`, `undervoltage_release` `D1`-`D2` (function `coil`). Contact blocks
number their contacts after the parent's own contacts: the first digit continues from the parent's last
contact. Products differ a lot here, so declaring `ports` is recommended.

**Compatibility with `aux[]`.** Each name of a 1.x `aux` list implicitly creates an auxiliary with id
`<parent id>.<name>` (`Q1.MX`), `name` = the entry and `kind` deduced from the name (`MX` → `shunt_release`,
`MN` → `undervoltage_release`, `OF` → `aux_contact` with `["CO"]`, `SD` → `alarm_contact` with `["CO"]`, any
other name → `other`). An explicit `auxiliary` with the same parent and name replaces the implicit one.

**Resolution of `Q1#MX`.** When a node has no port `MX` (by id or alias) but has an auxiliary with
`name: "MX"`, the reference `Q1#MX` designates that auxiliary **as a whole**. Such a reference is valid as a
link end (`{"kind": "trip", "from": "F10", "to": "Q1#MX"}`) but not as a wire end: a wire always ends on a
terminal (`Q1.MX#C1`).

**Cross-references.** The **contact set** of a device is its own contact ports plus the contact ports of all
auxiliaries whose `parent` is that device. This is what a control view prints under a coil (§3.6). The
relation also gives the bill of materials the accessories of a device.

#### 3.1.6 Control device types

Control schematics need a few devices that the 1.x registry does not have. They are added as types allowed in
`devices[]` (they do not carry power, SPEC §3a):

| Type | Specific fields | Default ports | IEC 81346 letter |
|---|---|---|---|
| `push_button` | `contacts`, `kind` (`momentary`, `maintained`, `mushroom`, `emergency_stop`, `key`), `color` | From `contacts` | S |
| `selector_switch` | `contacts`, `positions` (`["0", "1", "2"]` or labels) | From `contacts` | S |
| `pilot_light` | `color`, `un_V` | `X1`, `X2` | P |
| `control_relay` | `contacts`, `coil_V`, `kind` (`monostable`, `latching`, `timer`, `safety`) | `A1`, `A2` + `contacts` | K |
| `auxiliary` | §3.1.5 | §3.1.5 | as the parent |

Colours use the IEC 60757 two-letter codes (`RD`, `GN`, `YE`, `BU`, `WH`, `BK`…), like wire colours (§3.3).
The IEC 81346-2 class codes are left to the optional data package, as for existing types.

### 3.2 Terminal strips

#### 3.2.1 Decision: a top-level section, not a node

Terminal strips are declared in a new top-level section `terminal_strips[]`, **not** as nodes of the tree.
The reasons:

* **A strip is not on a power path.** It is crossed by many circuits, power and control, from different
  feeders. Placing it in the tree would give it one parent. Placing one copy per circuit would split one
  physical object.
* **Its terminals are many independent potentials.** A node has one input and one output (SPEC §8). A strip
  has dozens of unrelated pass-through points.
* **The single-line diagram stays as it is.** Most single-line diagrams do not show control terminals. Power
  terminals that a single-line diagram does show keep using the 1.x `terminal_block` node, which can now point
  at a strip (§3.2.3).
* **It matches how terminal plans are produced and read**: one table per strip, terminals in mounting order.

Like `enclosures[]` (SPEC §3a), the section is a flat list of addressable objects, linked to the rest by
identifiers.

#### 3.2.2 Model

```json
"terminal_strips": [
  {"id": "X1", "ref": "-X1", "enclosure": "MCC1", "label": "Conveyor 3 field terminals",
   "product": {"part_number": "…", "description": "Feed-through terminal 4 mm²"},
   "terminals": [
     {"no": "1", "kind": "feed_through", "label": "M1 U1", "section_max_mm2": 4},
     {"no": "4", "kind": "earth", "label": "M1 PE"},
     {"no": "20", "kind": "feed_through", "bridge_group": "B0V", "label": "0 V"},
     {"no": "21", "kind": "feed_through", "bridge_group": "B0V", "label": "0 V"},
     {"no": "30", "kind": "fuse", "fuse_A": 2, "label": "Sensor supply"}
   ]}
]
```

Strip fields:

| Field | Description |
|---|---|
| `id` | **Required.** Identifier, in the shared namespace (§3.1.2) |
| `ref` | Reference designation (`-X1`) |
| `label` | Description |
| `enclosure` | `id` of the enclosure: an entry of `enclosures[]`, or a `board` node. When both exist with the same identifier, the enclosure wins |
| `location` | Free text (IEC 81346 `+` aspect), when no enclosure is described |
| `product` | Default product of the terminals (SPEC §3b) |
| `terminals` | Ordered list, in mounting order on the rail |
| `status`, `note`, `ext` | As on nodes |

Terminal fields:

| Field | Description |
|---|---|
| `no` | **Required.** Terminal number, unique within the strip, used as the port id: `"1"`, `"PE"`, `"10a"`. Same pattern as port ids |
| `kind` | `feed_through` (default), `disconnect`, `fuse`, `earth`, `neutral`, `spare`. Enumeration values use `snake_case`, like the rest of the format |
| `bridge_group` | Terminals that share a value are bridged together (plug-in or screw bridge). Bridges never leave the strip |
| `label` | Description, or the function of the terminal |
| `section_max_mm2` | Largest conductor accepted |
| `points` | Clamping points per side. Default 1 (so 2 conductors per terminal: one on each side) |
| `fuse_A` | Fuse rating of a `fuse` terminal |
| `potential` | Expected potential (§3.4), checked |
| `product` | Product, when it differs from the strip default |
| `status`, `ext` | As on nodes |

A terminal is a port with two sides. A feed-through, earth or neutral terminal connects everything that lands on
it into one net. A `disconnect` terminal is one net in its normal (closed) state. A `fuse` terminal behaves like a
fuse: two nets, one on each side, the field side being the protected one. Exports distinguish the two sides of a
terminal (cabinet side, field side) by following the wires: a wire whose other end is in the same enclosure lands
on the cabinet side; a wire that belongs to a cable leaving the enclosure lands on the field side.

#### 3.2.3 Addressing and display

* Reference: `X1#3`. A strip has no registry ports: its ports are its terminals.
* Display: `-X1:3` (`<ref>:<no>`), as for device ports.
* The 1.x `terminal_block` node gains an optional field `strip` (id of a terminal strip). The single-line diagram
  can then show a power terminal block in the tree and the terminal plan can list its terminals. The 1.x field
  `terminal_block.terminals` (free text) is kept and deprecated (§5.3).

### 3.3 Wires and cables

#### 3.3.1 Wires

A wire is a conductor with two ends, each on a port or a strip terminal. Wires are listed in a new top-level
section `wires[]`.

```json
"wires": [
  {"id": "w25", "from": "X1#11", "to": "KM1#13", "mark": "102", "section_mm2": 0.75, "color": "BU"},
  {"id": "w21", "from": "X1#10", "to": "S1#11", "mark": "101", "cable": "W12", "core": "1"},
  {"id": "w8",  "from": "X1#1",  "to": "M1#U1", "cable": "M1.cable", "core": "BN", "conductor": "L1"}
]
```

| Field | Description |
|---|---|
| `id` | Identifier (shared namespace). Optional: generated when absent, but then not stable. An explicit `id` is recommended once marks are frozen |
| `from`, `to` | **Required.** Port references (§3.1.2). They MUST designate terminals, not auxiliaries as a whole |
| `mark` | Wire mark (ferrule text). When absent, computed by the view's marking rules (§3.5) |
| `section_mm2` | Cross-section. For a cable core, defaults to the cable's `section_mm2` (or `pe_section_mm2` for a PE core) |
| `size_awg` | Size as printed in AWG, as on cables |
| `color` | IEC 60757 code: `BK`, `BN`, `RD`, `OG`, `YE`, `GN`, `BU`, `VT`, `GY`, `WH`, `PK`, `GD`, `TQ`, `SR`, and `GNYE` (green-and-yellow) |
| `designation` | Conductor type (single-core flexible wire type designation…) |
| `material` | `Cu` / `Al` |
| `cable` | `id` of the cable this wire is a core of (§3.3.2) |
| `core` | Core identification within the cable: number (`"1"`) or colour (`"BN"`, `"GNYE"`) |
| `conductor` | Conductor function: `L1`, `L2`, `L3`, `N`, `PE`, `PEN`, `L+`, `L-`. Absent for control and signal wires |
| `potential` | `id` of a potential (§3.4), or a port reference (the net containing that port) |
| `length_m` | Length |
| `kind` | `wire` (default) or `bridge` (a bridge between device terminals, when it is not a strip `bridge_group`) |
| `label`, `status`, `note`, `ext` | As on nodes |

Wires are undirected. `from` and `to` only fix the order in exports. A port may carry several wires up to its
`capacity`.

Wires are **optional and partial**. A document may describe the wiring of one starter and leave the rest of the
installation as a single-line description. Tree connections that no wire describes stay implicit (§3.4.2).

#### 3.3.2 Cables

A cable groups cores between two places. Cables become first-class objects in a new section `cables[]`:

```json
"cables": [
  {"id": "W12", "ref": "W12", "designation": "control cable, screened", "cores": "4x", "section_mm2": 1.5,
   "length_m": 30, "from_enclosure": "MCC1", "to_enclosure": "FS3"}
]
```

A cable object has **every field of the 1.x cable** (SPEC §3.2 and §3a: `designation`, `cores`, `section_mm2`,
`pe_section_mm2`, `material`, `length_m`, `install`, `insulation`, `ref`, `kind`, `conductors`, `cpr_class`,
`raceway`, `status`…), plus:

| Field | Description |
|---|---|
| `id` | **Required.** Identifier (shared namespace) |
| `from_enclosure`, `to_enclosure` | Enclosures (or `board` nodes) at the two ends |
| `from`, `to` | Optional end devices or strips, when the cable lands on one object at each end (`"from": "X1"`, `"to": "M1"`) |
| `core_ids` | Optional explicit list of core identifications (`["1", "2", "3", "4"]`, `["BN", "BK", "GY", "GNYE"]`) when the composition does not make it obvious |
| `screen` | Description of the screen, which may be wired as a core named `SH` |

**Link with the 1.x `node.cable`.** Compatibility is kept both ways:

* An **inline** 1.x cable stays valid and keeps its meaning (the cable feeding the node from its parent). It is
  also addressable by wires with the implicit id `<node id>.cable` (`M1.cable`), and on a link with the implicit
  id `<link id>.cable`. The tree does not have to change for wires to use an existing cable.
* In 2.0, `node.cable` and `links[].cable` MAY instead be a **string**: the id of an entry of `cables[]`
  (`"cable": "W11"`). A cable shared by several feeders, or one that is not a tree edge (a control cable), is
  declared once in `cables[]`.
* Rendering and rules that read `node.cable` (circuit schedule, voltage drop, `iec60364.iz`) resolve the string
  to the cable object.

### 3.4 Potentials

#### 3.4.1 Nets and potentials

A **net** is a set of ports connected together by conductors with no device in between: wires, bridges,
feed-through terminals, busbars, and the implicit connections of the tree. A **potential** is the
identity of a net. All its wires have the same voltage, and with potential-based numbering they carry the
same mark (§3.5).

* A device separates potentials. Each pole of a switch, each contact and each coil has a different net on each
  side.
* A conductor that passes through a device without being switched (an uncut neutral, the PE) keeps its net.
* A strip terminal does not separate potentials, except a `fuse` terminal.

Nets are **derived**. The optional section `potentials[]` names some of them and gives them attributes:

```json
"potentials": [
  {"id": "P24", "name": "24V", "kind": "control", "un_V": 24, "dc": true, "mark": "24V", "ports": ["F2#2"]},
  {"id": "P0V", "name": "0V",  "kind": "control", "un_V": 0,  "dc": true, "mark": "0V",  "ports": ["PS#L-"]}
]
```

| Field | Description |
|---|---|
| `id` | **Required.** Identifier (shared namespace) |
| `name` | Displayed name (`24V`, `0V`, `L1`) |
| `kind` | `power`, `control`, `signal`, `earth`, `neutral` |
| `un_V`, `dc` | Voltage, and whether it is DC |
| `mark` | Fixed mark for every wire of the potential. It overrides the marking scheme |
| `color` | Default wire colour |
| `section_mm2` | Default cross-section of its wires |
| `ports` | Port references that belong to the potential. They anchor it to the derived nets with no wire needed |

A wire's `potential` field, a terminal's `potential` field and a potential's `ports` are **assertions**,
checked by rule `wire.potential` (§3.7). Two declared potentials MUST NOT end up in the same net.

#### 3.4.2 Power conductors: mapping the multi-line derivation to potentials

The multi-line view already derives the conductors of every node of the power tree with no extra data
(SPEC §7.1; implementation in
[`layout/multiline.py`](https://github.com/uniwire-dev/uniwire/blob/main/src/uniwire/layout/multiline.py)).
For each node it computes:

* `inp`: the conductors at its input (for example `L1, L2, L3, PE`);
* `out`: the conductors at its output (different from `inp` for a transformer, a converter, or the board that
  splits a PEN);
* `src`: for each input conductor, the conductor of the parent's output it comes from (`None` when the conductor
  starts here, such as the PE at the main earthing terminal of a TT installation, or `PEN` for the `N` and the
  `PE` after a PEN split).

The conductors come, in order of precedence, from the `phase` of a single-phase circuit, the `poles` of a device,
the cable `cores`, the motor `phases`, the `system` of a board or busbar, the usual connection of the load type,
and otherwise from upstream. The supply follows `installation.system` and the earthing system, and transformers
start a new system. For a switching device, the derivation also tells which conductors are **switched** (the
poles) and which pass through (`1P` / `3P` leave the neutral uncut, `1P+N` / `3P+N` add an unprotected neutral
pole, a PEN is never switched).

This proposal gives these conductors an identity, with these rules:

1. **Conductor of a port.** A port with a fixed `conductor` has that conductor. Otherwise, a port with a `pole`
   rank takes the rank-th switched conductor of the node, in the order `L1, L2, L3, L+, L-, N`. A `1P` breaker on
   a circuit with `phase: "L2"` has ports `1`, `2` on `L2`. A `3P+N` breaker has `1`-`2` on `L1`, …, and `N1`-`N2`
   on `N`. Loads and sources whose ports are named after conductors are matched by name.
2. **Implicit connections.** For each tree edge (parent *P*, child *C*) and each conductor *c* of `C.inp`, the
   output port of *P* for `src[c]` is connected to the input port of *C* for *c*. When a node has no port for a
   conductor (a board, a busbar, an uncut neutral, a PE through a breaker), it is transparent for that conductor:
   the connection goes on to the next port up or down the tree.
3. **Nets.** Union of the implicit connections, the wires, the strip terminals and the bridges. A busbar or a
   board with several children gives one net per conductor shared by all its outgoing feeders. Each pole of a
   device ends a net and starts another.
4. **Explicit wiring replaces implicit connections.** When an end of an implicit connection carries at least one
   wire, that implicit connection is dropped. The wires must then connect the same ports, possibly through strip
   terminals. In the example (§4), `KM1#2 → X1#1 → M1#U1` replaces the implicit `KM1#2 → M1#U1`. Rule `wire.tree`
   reports wiring that contradicts the tree (a phase landing on the wrong motor terminal).
5. **Default names.** A derived power net is named after its conductor and the device or circuit it leaves:
   `L1` on the supply side, then for instance `-Q1:2` or circuit `C3 L1`. These names are for display only. They
   are not identifiers. A wire refers to a derived net through any of its ports (`"potential": "Q1#2"`).
6. **PEN split.** At the board that splits a PEN, the PEN net continues as the PE net. The N gets a new net,
   bonded to it at the split point. In exports the bond appears as a bridge on the board's `PE` / `N` terminals.

So a document without any wire already has a complete, deterministic set of power nets and ports. That is
enough to mark the conductors of a multi-line diagram (§3.5) and to export them.

### 3.5 Wire marking, exports and display

#### 3.5.1 Marking rules in views

A view gains an optional `wire_marking` object, and a boolean `wire_marks` that shows or hides marks
(default `true` when `wire_marking` is present):

```json
"views": [{"id": "ml", "kind": "multi-line",
           "wire_marking": {"scheme": "potential", "start": 100, "step": 1, "power": "conductor",
                            "keep_manual": true}}]
```

| Field | Default | Description |
|---|---|---|
| `scheme` | `manual` | `manual`: only `wires[].mark` is shown. `potential`: one number per net, shared by all its wires. `sequential`: one number per wire. `pattern`: marks built from `pattern` |
| `pattern` | - | Template for `pattern`: tokens `{circuit}`, `{conductor}`, `{ref}` (reference designation of the `from` node), `{from}`, `{to}` (display form of the ends), `{from_port}`, `{to_port}`, `{potential}` (potential name), `{strip}`, `{terminal}`, `{cable}` (cable tag, else cable id), `{n}` (sequence number). Example `"{circuit}-{conductor}"` → `C3-L1` |
| `start`, `step` | 1, 1 | First number and increment for `potential` and `sequential` |
| `prefix`, `suffix` | `""` | Added around generated numbers |
| `per` | `document` | Numbering restarts per `document`, `sheet` or `enclosure` |
| `power` | `conductor` | Power nets: `conductor` marks them with their conductor (`L1`, `N`, `PE`), `number` numbers them like the other nets, `none` leaves them unmarked |
| `keep_manual` | `true` | A wire with an explicit `mark`, and a potential with a fixed `mark`, keep it. Generated numbers skip the values already used |
| `order` | `layout` | Numbering order: `layout` (order of appearance in the view: sheet, then column, then top to bottom), or `document` (order of `wires[]`, then of the tree) |

Rules:

* Marking is **deterministic**: the same document and the same view always produce the same marks.
* Generated marks depend on the document and on the view. Before manufacturing, the marks SHOULD be **frozen**.
  `uniwire marks FILE --view ID --write` writes the generated marks into `wires[].mark` (creating `wires[]`
  entries for implicit power connections when asked). The marking is then `manual` from that point on, and later
  edits do not renumber printed ferrules.
* A view never carries topology. Removing `wire_marking` changes the displayed marks, not the meaning of the
  document.

#### 3.5.2 Exports

The reference implementation adds four CSV exports (UTF-8, comma separated, one header line). Column names are
stable English `snake_case` tokens, so that other tools can read them. Optional localized headers follow
`--lang`. Display values (`-KM1:A1`) follow the document's `ref` fields and are not translated.

**Wire list** (`uniwire wires FILE [--view ID]`), one row per wire, implicit power connections included when
`--all` is given:

`wire_id, mark, from, from_display, from_enclosure, to, to_display, to_enclosure, potential, conductor,
section_mm2, color, cable, core, length_m, status`

**Wire marker list** (ferrules / sleeves, `uniwire markers FILE`), one row per wire end:

`mark, wire_id, end (from|to), terminal_display, section_mm2, color, enclosure, quantity`

Identical rows are merged and their `quantity` is summed, so the list can be sent to a marker printer.

**Terminal plan** (`uniwire terminals FILE [--strip X1]`), one row per terminal, in mounting order:

`strip, terminal, kind, bridge_group, label, potential, mark, inside_targets, inside_sections_mm2,
outside_targets, outside_cable, outside_cores, fuse_A, product`

`inside_targets` lists the cabinet-side ends (`-KM1:13; -KM1:14`), `outside_targets` the field-side ends with
their cable and core.

**Cable schedule** (`uniwire cables FILE`), one row per cable (from `cables[]` and inline cables):

`cable_id, ref, designation, cores, section_mm2, length_m, from_enclosure, to_enclosure, from, to,
cores_used, cores_spare, status`

A PDF form of the terminal plan (one table per strip) belongs to phase 2 (§6).

#### 3.5.3 Display

* **Multi-line view.** When `wire_marks` is on, each conductor segment between two ports carries its mark, written
  along the line next to each port. Strip terminals referenced by power wires are drawn on the conductor as a
  small terminal symbol with `-X1:1`. The layout stays automatic.
* **Single-line view.** Unchanged. A `terminal_block` node with a `strip` MAY show the terminal range
  (`-X1:1…4`).
* **Control view.** See §3.6.

### 3.6 Control schematic view (sketch, not normative)

This section is **future work**. It only shows that the data of §3.1-3.5 is enough to draw a control
schematic automatically. The normative definition will be a separate UEP.

A view of kind `"control"` would draw the control circuits as **current paths** between two supply potentials:

```json
{"id": "ctl", "kind": "control", "supply": ["P24", "P0V"], "paper": "A3", "columns": 10}
```

* **Rails.** The upper supply potential (`P24`, or a PLC output) at the top, the lower one (`P0V`) at the bottom.
* **Current paths.** Each path from the upper rail to the lower rail through two-terminal elements (a contact
  `13`-`14`, a coil `A1`-`A2`, a pilot light `X1`-`X2`, a PLC channel and its common) becomes one column. The order
  follows the order of the coils in the document, and a view MAY override it with a list of coil ids.
  Parallel branches (the self-hold contact across the start button) are drawn side by side, joined at the nets
  they share. Coils sit at the bottom of their path, as is usual.
* **Columns and sheets.** Columns are numbered on each sheet. A position is written `sheet.column` (`3.4`).
* **Terminals.** Strip terminals on a path are drawn where the wire crosses them (`-X1:10`). The field devices
  of an enclosure are framed with its `ref` (`+FS3`).
* **Cross-references.** Under each coil, a table lists the contact set of the device (§3.1.5): main poles, own
  contacts and the contacts of its auxiliaries, with the position where each contact is used, in NO / NC
  columns. Next to each contact, its parent's position is written (`-KM1 / 3.4`). PLC channels show the channel
  label and the position of the module.
* **Marks.** From `wire_marking`, as in the multi-line view.

All of these come from ports (functions and pairs), wires, nets, auxiliaries (`parent`) and terminal strips.
Nothing has to be added to the document.

### 3.7 Rules

New rules in the `core` profile. They apply only to documents that use the new sections. A document without
`wires[]`, `terminal_strips[]` or explicit `ports` gets no new findings, except `port.unknown` on links that use
ports.

| Rule | Check | Level |
|---|---|---|
| `port.unknown` | A port reference (wire, link `from_port` / `to_port`, potential `ports`) names no node, no port, no alias and no auxiliary; or uses a generated identifier; or an alias matches two ports | error |
| `port.unconnected` | A `mandatory` port of a node that has at least one wire is not connected (a wired contactor with an unwired coil terminal) | warning (error for `coil`) |
| `port.capacity` | More conductors on a port than its `capacity`; a PLC channel shared by two wires that are not on the same net | error |
| `port.conductor` | A wire's `conductor` differs from the conductor of a port it lands on; a `PE` conductor on a port that is not `earth`; a `GNYE` colour on a conductor other than PE / PEN (the green-and-yellow combination is reserved for protective conductors by IEC 60445) | error |
| `wire.endpoints` | `from` = `to`; an end on an auxiliary as a whole (`Q1#MX`) | error |
| `wire.section` | The cross-section is too small for the protective device that supplies the net: the device found by walking up the nets to the first protective `pole_out`, and its rating (`ir_A`, `fuse_A`, `in_A`, as in `iec60364.iz`). The data table is a registry file whose source is given in the finding | warning |
| `wire.cable` | Unknown `cable`; a `core` used twice; more cores used than the composition gives; a core's section different from the cable's; a wire of a cable whose ends are not in the cable's enclosures | error (warning for enclosures) |
| `wire.potential` | Two declared potentials in one net; a wire, terminal or potential assertion that disagrees with the derived net; a fixed `mark` given to two potentials | error |
| `wire.mark` | The same mark on wires of different nets (manual or frozen marks); with the `potential` scheme, two different explicit marks within one net | error / warning |
| `wire.tree` | Explicit wiring that contradicts an implicit tree connection: the wires of a tree edge reach a port of another conductor (crossed phases), or do not reach the child at all | warning |
| `strip.terminal` | Duplicate terminal number in a strip; unknown `enclosure` | error |
| `strip.capacity` | A wire larger than `section_max_mm2`; more conductors than `points` on one side | error |
| `strip.bridge` | A `bridge_group` with a single terminal (warning); a bridge between an `earth` terminal and another kind, or between terminals asserted on different potentials (error) | warning / error |
| `strip.earth` | A PE conductor on a terminal that is not `earth`; an `earth` terminal on a net that is not PE / PEN | warning |
| `aux.parent` | An `auxiliary` with an unknown `parent`, a parent that is not a switching, protective or relay device, or an auxiliary placed in the tree instead of `devices[]` | error |

Every finding carries the identifiers involved (wire, port, strip, terminal), so that editors and the LLM tools
(`describe`, `patch`) can point to it.

### 3.8 Mappings to standards and data models

Claims are kept general where the mapping depends on the profile or on the edition of a standard.

| uniwire | IEC 81346 | IEC 61082 / IEC 60445 | CIM (IEC 61970/61968) | IFC 4.x | IEC 61850 SCL |
|---|---|---|---|---|---|
| Port `KM1#A1`, displayed `-KM1:A1` | Terminal designation: product designation followed by the terminal prefix `:` | IEC 60445: alphanumeric identification of equipment terminals (`U1`, `V1`, `W1`, `L1`, `N`, `PE`…). Coil and contact markings follow the conventions of the IEC 60947 series | `Terminal` of a `ConductingEquipment` (`sequenceNumber` from the port order) | `IfcDistributionPort` nested in the element (`IfcRelNests`), with flow direction and electrical system type | `Terminal` of a `ConductingEquipment` (primary equipment only) |
| Terminal strip and terminals `X1#3` | Product `-X1`, terminals `-X1:3` | IEC 61082: terminal and connection tables | `Junction` / `Connector`, or not modelled (secondary wiring is mostly outside CIM's scope) | No dedicated entity; a terminal-strip element with one port per terminal (see open question 6) | Not modelled |
| Net / potential | - | Conductor identification by potential (IEC 60445 for power conductors) | `ConnectivityNode` | Set of ports joined by `IfcRelConnectsPorts` | `ConnectivityNode` (primary) |
| Wire | - | IEC 61082: connection diagrams and tables; IEC 60445: conductor colours and alphanumeric marks | No direct class for panel wiring | `IfcCableSegment` (conductor type), joined to ports by `IfcRelConnectsPorts` | Not modelled |
| Cable `cables[]` | Product `-W12` | Cable schedules (IEC 61082 documentation rules) | `ACLineSegment` for power cables in network models | `IfcCableSegment` (cable type), carried in `IfcCableCarrierSegment` | Not modelled |
| Auxiliary with `parent` | Sub-product of the parent | - | - | Element nested in the parent (`IfcRelNests`) | Logical nodes cover functions, not wiring |

* **IEC 81346.** `ref` already holds the product designation (`-KM1`). The terminal aspect is appended with `:`.
  Location (`+FS3`) and function (`=`) prefixes can be put in front for display and exports.
* **IEC 60445 / IEC 61082.** The default port sets (§3.1.3) and the `conductor` and `color` values follow these
  identification conventions. The wire list and the terminal plan are tables in the sense of the documentation
  rules of IEC 61082.
* **CIM.** `uniwire graph` (SPEC §8) already produces terminals and connectivity nodes for the tree with aggregated
  terminals (`in`, `out`, `in2`). With ports it emits one `Terminal` per port that carries a conductor, and the
  power nets of §3.4.2 become `ConnectivityNode`s. Control wiring is not exported to CIM.
* **IFC.** Each port becomes an `IfcDistributionPort`, each wire or cable an `IfcCableSegment` connected by
  `IfcRelConnectsPorts`. The exact predefined types are left to the exporter.
* **IEC 61850 SCL.** Only the primary (power) part maps: `Terminal` and `ConnectivityNode` in the substation
  section. Secondary wiring stays out of SCL.

## 4. Complete example: a DOL motor starter

A conveyor motor `-M1` (4 kW) is started direct-on-line by contactor `-KM1`, protected by motor circuit breaker
`-Q1`. The 24 V DC control circuit is fed by an output of PLC `-A1` (enable). It goes out to a push-button station
`+FS3` through terminal strip `-X1` and cable `W12`: stop button `-S1` (NC), start button `-S2` (NO). The
contactor holds itself in through its auxiliary contact `13`-`14`. An add-on auxiliary block on `-KM1` reports
"running" to a PLC input. The motor cable `W11` lands on `-X1:1…4`.

```json
{
  "$schema": "https://uniwire.sh/schema/v2/uniwire.schema.json",
  "uniwire": "2.0.0",
  "meta": {"title": "Conveyor 3: DOL starter with hardwired self-hold", "lang": "en"},
  "installation": {"earthing": "TN-S", "system": "3P", "un_V": 400, "f_Hz": 50},

  "sources": [
    {"id": "IN", "type": "offpage", "label": "From main switchboard", "children": [
      {"id": "MCC1", "type": "board", "ref": "MCC-1", "kind": "mcc", "children": [
        {"id": "Q1", "type": "breaker", "ref": "-Q1", "label": "Conveyor 3", "in_A": 10, "ir_A": 8.5,
         "poles": "3P", "icu_kA": 50, "children": [
          {"id": "KM1", "type": "contactor", "ref": "-KM1", "in_A": 9, "poles": "3P", "coil_V": 24,
           "contacts": ["NO"], "children": [
            {"id": "M1", "type": "motor", "ref": "-M1", "label": "Conveyor 3", "p_kW": 4, "in_A": 8.2,
             "phases": 3,
             "cable": {"ref": "W11", "designation": "U1000R2V", "cores": "4G", "section_mm2": 2.5,
                       "length_m": 35, "material": "Cu"}}]}]},
        {"id": "Q2", "type": "breaker", "ref": "-Q2", "label": "Control supply", "in_A": 4, "curve": "C",
         "poles": "2P", "children": [
          {"id": "PS", "type": "power_supply", "ref": "-T1", "u1_V": 400, "u2_V": 24, "in_A": 5, "children": [
            {"id": "F2", "type": "breaker", "ref": "-F2", "label": "24 V control", "in_A": 2, "curve": "C",
             "poles": "1P"},
            {"id": "A1", "type": "plc", "ref": "-A1", "role": "controller", "un_V": 24,
             "modules": [
               {"slot": 1, "kind": "di", "channels": 8, "un_V": 24, "channel_labels": {"1": "KM1 running"}},
               {"slot": 2, "kind": "do", "channels": 8, "un_V": 24, "rating_A": 0.5,
                "channel_labels": {"1": "Conveyor 3 enable"}}]}]}]}]}]}
  ],

  "devices": [
    {"id": "KM1_B", "type": "auxiliary", "parent": "KM1", "ref": "-KM1", "kind": "aux_contact",
     "contacts": ["NO", "NC"], "port_defaults": false,
     "ports": [{"id": "53", "function": "contact_no", "pair": "54"},
               {"id": "54", "function": "contact_no", "pair": "53"},
               {"id": "61", "function": "contact_nc", "pair": "62"},
               {"id": "62", "function": "contact_nc", "pair": "61"}]},
    {"id": "S1", "type": "push_button", "ref": "-S1", "label": "Stop", "contacts": ["NC"], "color": "RD"},
    {"id": "S2", "type": "push_button", "ref": "-S2", "label": "Start", "contacts": ["NO"], "color": "GN"}
  ],

  "enclosures": [
    {"id": "FS3", "kind": "box", "ref": "+FS3", "label": "Push-button station, conveyor 3",
     "nodes": ["S1", "S2"]}
  ],

  "terminal_strips": [
    {"id": "X1", "ref": "-X1", "enclosure": "MCC1", "label": "Conveyor 3 field terminals",
     "terminals": [
       {"no": "1",  "kind": "feed_through", "label": "M1 U1", "section_max_mm2": 4},
       {"no": "2",  "kind": "feed_through", "label": "M1 V1", "section_max_mm2": 4},
       {"no": "3",  "kind": "feed_through", "label": "M1 W1", "section_max_mm2": 4},
       {"no": "4",  "kind": "earth",        "label": "M1 PE", "section_max_mm2": 4},
       {"no": "10", "kind": "feed_through", "label": "Stop",      "section_max_mm2": 2.5},
       {"no": "11", "kind": "feed_through", "label": "Start",     "section_max_mm2": 2.5},
       {"no": "12", "kind": "feed_through", "label": "Self-hold", "section_max_mm2": 2.5},
       {"no": "20", "kind": "feed_through", "label": "0 V", "bridge_group": "B0V", "section_max_mm2": 2.5},
       {"no": "21", "kind": "feed_through", "label": "0 V", "bridge_group": "B0V", "section_max_mm2": 2.5}
     ]}
  ],

  "cables": [
    {"id": "W12", "ref": "W12", "designation": "control cable, screened", "cores": "4x", "section_mm2": 1.5,
     "length_m": 30, "from_enclosure": "MCC1", "to_enclosure": "FS3"}
  ],

  "potentials": [
    {"id": "P24", "name": "24V", "kind": "control", "un_V": 24, "dc": true, "mark": "24V", "ports": ["F2#2"]},
    {"id": "P0V", "name": "0V",  "kind": "control", "un_V": 0,  "dc": true, "mark": "0V",  "ports": ["PS#L-"]}
  ],

  "wires": [
    {"id": "w4",  "from": "KM1#2",   "to": "X1#1", "conductor": "L1", "section_mm2": 2.5, "color": "BK"},
    {"id": "w5",  "from": "KM1#4",   "to": "X1#2", "conductor": "L2", "section_mm2": 2.5, "color": "BK"},
    {"id": "w6",  "from": "KM1#6",   "to": "X1#3", "conductor": "L3", "section_mm2": 2.5, "color": "BK"},
    {"id": "w7",  "from": "MCC1#PE", "to": "X1#4", "conductor": "PE", "section_mm2": 2.5, "color": "GNYE"},
    {"id": "w8",  "from": "X1#1", "to": "M1#U1", "cable": "M1.cable", "core": "BN",   "conductor": "L1"},
    {"id": "w9",  "from": "X1#2", "to": "M1#V1", "cable": "M1.cable", "core": "BK",   "conductor": "L2"},
    {"id": "w10", "from": "X1#3", "to": "M1#W1", "cable": "M1.cable", "core": "GY",   "conductor": "L3"},
    {"id": "w11", "from": "X1#4", "to": "M1#PE", "cable": "M1.cable", "core": "GNYE", "conductor": "PE"},

    {"id": "w20", "from": "A1#2.1",   "to": "X1#10",    "mark": "101", "section_mm2": 0.75, "color": "BU"},
    {"id": "w21", "from": "X1#10",    "to": "S1#11",    "mark": "101", "cable": "W12", "core": "1"},
    {"id": "w22", "from": "S1#12",    "to": "X1#11",    "mark": "102", "cable": "W12", "core": "2"},
    {"id": "w23", "from": "S1#12",    "to": "S2#13",    "mark": "102", "section_mm2": 0.75, "color": "BU"},
    {"id": "w24", "from": "S2#14",    "to": "X1#12",    "mark": "103", "cable": "W12", "core": "3"},
    {"id": "w25", "from": "X1#11",    "to": "KM1#13",   "mark": "102", "section_mm2": 0.75, "color": "BU"},
    {"id": "w26", "from": "X1#12",    "to": "KM1#14",   "mark": "103", "section_mm2": 0.75, "color": "BU"},
    {"id": "w27", "from": "KM1#14",   "to": "KM1#A1",   "mark": "103", "section_mm2": 0.75, "color": "BU"},
    {"id": "w28", "from": "KM1#A2",   "to": "X1#20",    "potential": "P0V", "section_mm2": 0.75, "color": "BU"},
    {"id": "w29", "from": "PS#L-",    "to": "X1#21",    "potential": "P0V", "section_mm2": 1.5,  "color": "BU"},
    {"id": "w30", "from": "F2#2",     "to": "KM1_B#53", "potential": "P24", "section_mm2": 0.75, "color": "BU"},
    {"id": "w31", "from": "KM1_B#54", "to": "A1#1.1",   "mark": "104", "section_mm2": 0.75, "color": "BU"}
  ],

  "links": [
    {"kind": "control", "from": "A1", "from_port": "2.1", "to": "KM1", "label": "enable"}
  ],

  "views": [
    {"id": "sld", "paper": "A3"},
    {"id": "ml", "kind": "multi-line", "paper": "A3",
     "wire_marking": {"scheme": "potential", "start": 100, "power": "conductor", "keep_manual": true}}
  ]
}
```

What the example shows:

* **The single-line data does not change.** `sources`, the `control` link and the `sld` view are 1.x
  content. The only addition to the tree is the optional field `contacts: ["NO"]` on `KM1`, which declares its
  built-in contact `13`-`14`. The single-line diagram rendered from this document is identical to the one
  rendered from the same document without the new sections.
* **Ports come from the registry.** `Q1#2`, `KM1#A1`, `KM1#13`, `M1#U1`, `A1#2.1`, `PS#L-`, `S1#11` and
  `MCC1#PE` are defaults. Only the add-on block `KM1_B` declares its ports, because its markings depend on the
  product.
* **Implicit connections fill the gaps.** `Q1 → KM1` has no wires: its three connections (`Q1#2` to `KM1#1`…) are
  derived from the tree, and the `potential` scheme marks them `L1`, `L2`, `L3` (`power: "conductor"`). The
  edge `KM1 → M1` is described by wires through `-X1:1…4`, which replace the implicit connection. Rule `wire.tree`
  checks that `KM1#2` still reaches `M1#U1`.
* **Inline cable reused.** The motor cable stays inline on `M1` (1.x form) and its cores are referenced as
  `M1.cable`. The control cable `W12`, which belongs to no tree edge, is declared in `cables[]`. Its core 4 is
  reported as spare by the cable schedule.
* **Nets and marks.** Net `101` = {`A1#2.1`, `X1#10`, `S1#11`}. Net `102` = {`S1#12`, `S2#13`, `X1#11`,
  `KM1#13`}. Net `103` = {`S2#14`, `X1#12`, `KM1#14`, `KM1#A1`}. The self-hold contact `KM1:13-14` lies in
  parallel with `S2:13-14`, between nets `102` and `103`. `P0V` takes in `KM1#A2`, `X1#20`, `X1#21` (bridge `B0V`)
  and `PS#L-`, and all its wires get the fixed mark `0V`. Net `104` carries the feedback to input `1.1`.
* **Terminal plan of `-X1`** (abridged):

  | terminal | kind | bridge | inside | outside |
  |---|---|---|---|---|
  | 1 | feed_through | | `-KM1:2` (L1, 2.5 mm²) | `W11` BN → `-M1:U1` |
  | 4 | earth | | `MCC-1:PE` | `W11` GNYE → `-M1:PE` |
  | 10 | feed_through | | `-A1:2.1` (101) | `W12` 1 → `+FS3-S1:11` |
  | 11 | feed_through | | `-KM1:13` (102) | `W12` 2 → `+FS3-S1:12` |
  | 12 | feed_through | | `-KM1:14` (103) | `W12` 3 → `+FS3-S2:14` |
  | 20 | feed_through | B0V | `-KM1:A2` (0V) | |
  | 21 | feed_through | B0V | `-T1:L-` (0V) | |

* **Cross-reference under the coil of `-KM1`** (control view, §3.6): main poles `1-2`, `3-4`, `5-6`; NO `13-14`
  (self-hold, path of the coil); NO `53-54` (feedback to `-A1:1.1`); NC `61-62` (unused).
* **Rules.** The 2 A breaker `-F2` protects the `P24` net and `wire.section` accepts 0.75 mm². `A1#2.1`
  protection is the PLC output itself (`plc.coil` already checks the 24 V coil). `port.unconnected` would warn if
  `KM1#A2` were not wired.

## 5. Compatibility and migration

### 5.1 Everything is additive

* Every 1.x document is a valid 2.0 document with the same meaning. None of the new fields is required.
* New top-level sections: `terminal_strips`, `wires`, `cables`, `potentials`. New node fields: `ports`,
  `port_defaults`, `contacts` (contactor and control types), `strip` (terminal block). New types: `auxiliary`,
  `push_button`, `selector_switch`, `pilot_light`, `control_relay`. New view fields: `wire_marking`,
  `wire_marks`. New view kind: `control` (reserved until its own UEP).
* The only widening of an existing field: `node.cable` and `links[].cable` accept a string (the id of a
  `cables[]` entry) in addition to the 1.x object.
* 1.x readers reject unknown top-level keys (`additionalProperties: false`, SPEC §9). A document that uses
  the new sections therefore declares `"uniwire": "2.0.0"` and the `/v2/` schema. A 2.0 document that uses none
  of them can be written as 1.x by changing the version string.

### 5.2 `from_port` / `to_port` become port references

* Current values `slot.channel` (`"2.1"`) are already valid port ids of the generated PLC ports. Existing documents
  keep working, and the check that rule `plc.port` did for PLCs is now done by `port.unknown` for every type.
* Other free strings (`"MX"`, `"N"`) resolve through ports, aliases and auxiliaries (§3.1.5). Unresolvable
  values produce `plc.port` only for PLCs in the current format. In 2.0 they raise `port.unknown` as a **warning** for documents
  that declare `uniwire` 1.x, and as an **error** for 2.0 documents.

### 5.3 `terminal_block.terminals` → terminal strips

`uniwire migrate` (the migration function required by SPEC §9 for a major version) converts what it can:

* `"X1.1-X1.12"`, `"X1:1-12"`, `"1-12"`: a strip `X1` (or `<block id>` when no prefix is given) with terminals
  `1`…`12` of kind `feed_through`, and the node gets `strip: "X1"`. The original text is kept in `note`.
* Lists such as `"X1.1, X1.2, X1.PE"`: one terminal per entry, `PE` as `earth`.
* Anything else is left as it is, with an info finding. The field stays valid and is only deprecated.

The function is idempotent and never deletes data.

### 5.4 Other migrations

* `aux[]` names stay valid. They create implicit auxiliaries (§3.1.5). `migrate --explicit-aux` writes them out as
  `devices[]` entries.
* Inline cables stay valid. `migrate --hoist-cables` moves them to `cables[]` and replaces them with their id
  (optional; useful when wires reference them).

## 6. Implementation plan

**Phase 1, 2.0-alpha: model, rules, exports**

* Pydantic models: `Port`, `TerminalStrip`, `Terminal`, `Wire`, `CableObject`, `Potential`, the new node types
  and fields. Regenerated `/v2/` schema. Registry `ports` entries for every existing type.
* Port resolution (ids, aliases, auxiliaries, implicit `<id>.cable` and `<id>.<aux>`), net derivation (union-find
  over implicit connections, wires, strips and bridges) reusing the conductor derivation of the multi-line layout.
* Rules of §3.7. CLI exports `wires`, `markers`, `terminals`, `cables` (CSV). `uniwire marks --write`.
* `uniwire migrate` for §5. `uniwire graph` with one terminal per port.
* LLM tools: the reference card, `describe` (ports and wires of a node) and `patch` operations for wires and
  terminals.
* Specification updated in English and French. This example added as `examples/` and covered by tests.

**Phase 2, 2.0-beta: drawings**

* Wire marks in the multi-line view. Strip terminals drawn on power conductors.
* Terminal plan as PDF/SVG (one table per strip). Cable schedule sheet.
* Viewer: show the ports and nets of a selected node.

**Phase 3, later: control view**

* A separate UEP for the `"control"` view kind (§3.6): current paths, columns, cross-reference tables, sheet
  numbering. Then its rendering in the reference implementation.

## 7. Open questions

1. **Where do marking rules live?** This proposal puts `wire_marking` in views and relies on freezing
   (`marks --write`) for stable ferrules. Should there also be a document-level default, so that exports do not
   depend on choosing a view?
2. **Should implicit power connections be materialised?** Should `normalize` write them as `wires[]` entries,
   or leave them derived, as proposed?
3. **Multi-level terminals**: should they be written with numbers such as `"5.1"`, `"5.2"`, or with a separate
   `level` field and a reference syntax `X1#5/2`?
4. **Port id case and aliases**: ids are case-sensitive, as proposed. Should `U` vs `U1` (old and current motor
   markings) be an alias in the registry, or a profile choice?
5. **Version number**: everything is additive. Should this ship as a 1.x minor version (with `cable` as a string deferred), rather
   than wait for 2.0 and the graph-first changes planned there?
6. **IFC representation of terminal strips**: is there an entity better suited than a generic element with
   ports, and should each terminal be an element or a port?
7. **Data source for `wire.section`**: panel wiring needs a current-capacity table for small sections in
   enclosures. Which openly licensed source can the registry cite?
8. **Coil ↔ contact positions in files**: should a document be able to store a frozen cross-reference
   (`sheet.column`) for contacts, the way marks are frozen, so that printed schematics keep their references
   when the layout changes?

## 8. References

* [uniwire specification](../SPEC.md): SPEC §3 (nodes), §3a (common fields, `devices[]`, `enclosures[]`,
  `terminal_block`), §3b (PLC ports), §7.1 (multi-line view), §8 (derived graph form), §9 (versions).
* [Contributing: UEP process](../contributing.md).
* IEC 81346-1 and -2: structuring principles and reference designations.
* IEC 61082-1: preparation of documents used in electrotechnology.
* IEC 60445: identification of equipment terminals, conductor terminations and conductors.
* IEC 60757: code for designation of colours.
* IEC 60947 series: low-voltage switchgear and controlgear (terminal marking conventions of control devices).
* IEC 61970 / 61968 (CIM): `Terminal`, `ConnectivityNode`. ISO 16739 (IFC): `IfcDistributionPort`,
  `IfcRelConnectsPorts`, `IfcCableSegment`. IEC 61850-6 (SCL): `Terminal`, `ConnectivityNode`.
