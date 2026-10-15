# uniwire format specification, version 1.0

> Open exchange format for **describing electrical installations**, drawn as single-line and multi-line
> diagrams (residential, commercial and industrial LV, with an MV/LV transformer at the head, standby sources, PV, EV charging (IRVE)).
> `*.uniwire.json` files, which can be validated against the published JSON Schema
> [`schema/uniwire.schema.json`](https://github.com/uniwire-dev/uniwire/blob/main/schema/uniwire.schema.json) (draft 2020-12).

The key words **MUST**, **MUST NOT**, **SHOULD** and **MAY** are to be interpreted as described in RFC 2119.

---

## 1. Principles

1. **Describe the installation, not the drawing.** A document contains the electrical topology and the
   characteristics of the equipment. It is complete **without any coordinates**: the layout is
   computed by the rendering tool. Views (`views`) carry only optional preferences and
   overrides (the same approach as CIM *Diagram Layout* and OpenSCD).
2. **Tree + links.** Power flows down from the sources to the loads, and the vast majority of single-line
   diagrams are radial trees. A document therefore describes a **tree** (`sources` → `children`). Whatever
   falls outside the tree (source transfer switch, busbar coupling, bypass, control connections) is
   described in `links`. The "terminals / connectivity nodes graph" form (CIM, IEC 61850) is **derived**
   automatically (see §8).
3. **Explicit, closed typing.** Each node has a `type` taken from a registry (§5). Unknown fields
   are rejected (a typo such as `calibre` instead of `in_A` is an error); extensions go
   in `ext`.
4. **Numeric quantities, unit in the name.** `in_A: 16`, `idn_mA: 30`, `section_mm2: 2.5`
   (as in pandapower). No "16 A" strings in a published file.
5. **Identifier ≠ reference designation.** `id` is stable and is used for references; `ref` is the
   displayed IEC 81346 reference designation (`-Q3`), which may change when items are renumbered.
6. **Factoring.** Repeated characteristics (a C16 4.5 kA circuit breaker…) are declared once
   in `templates` and applied with `use`.

## 2. Document structure

```json
{
  "$schema": "https://uniwire.sh/schema/v1/uniwire.schema.json",
  "uniwire": "1.0.0",
  "profiles": ["nfc15100"],
  "meta": { ... },
  "installation": { ... },
  "templates": { "C16": { "type": "breaker", "in_A": 16, "curve": "C", "icn_kA": 4.5 } },
  "sources": [ { "type": "grid", "children": [ ... ] } ],
  "links": [ { "kind": "control", "from": "CPT", "to": "KM1" } ],
  "views": [ { "id": "sld", "paper": "A3" } ],
  "ext": {}
}
```

| Key | Required | Purpose |
|---|---|---|
| `$schema` | no | Schema URL (the major version appears in the path: `/v1/`) |
| `uniwire` | no (default `1.0.0`) | Format version, semver `1.x.y` |
| `profiles` | no | Business rule profiles to apply (`nfc15100`, `iec60364`, `enedis`…) |
| `meta` | no | Title, project, client, author, date, `revisions[]`, `notes[]`, `lang` |
| `installation` | no | `earthing` (TT, TN-C, TN-S, TN-C-S, IT), `system` (1P+N, 3P+N…), `un_V`, `f_Hz`, `supply`, `subscribed_kVA`, `planned_kVA`, `ik3_kA`, `earth_resistance_ohm`, `surface_m2`, `standard`, `premises` (dwelling, commercial, office, industrial, public, agricultural, other: dwelling rules apply to `dwelling` or when absent) |
| `templates` | no | Named attribute templates |
| `sources` | **yes** (≥ 1) | Roots of the tree: grid, generator set, transformer… |
| `links` | no | Connections outside the tree (§4) |
| `interlocks` | no | Interlock declarations: number of keys per `locks` identifier (§4.1) |
| `views` | no | Rendering preferences (§7) |
| `ext` | no | Free-form extensions (§9) |

## 3. Nodes

Every node has the following common fields (all optional except `type`):

| Field | Type | Description |
|---|---|---|
| `type` | enum | Component type (§5), **required** |
| `id` | `^[A-Za-z_][A-Za-z0-9_.-]*$` | Identifier, unique within the document. If absent, the tool generates one (from `ref`, otherwise from the type) |
| `ref` | text | Displayed reference designation (IEC 81346: `-Q1`, `-KM1`, `TD1`) |
| `label` | text | Designation: function, room (`Living room sockets`) |
| `use` | text | Name of a template in `templates` |
| `status` | `new`, `existing`, `spare`, `future`, `removed` | State (planned / existing / spare) |
| `phase` | `L1`, `L2`, `L3`, `L1L2`… | Connection of a single-phase circuit on a three-phase network |
| `location`, `manufacturer`, `part_number`, `note` | text | Additional information |
| `external` | boolean | Equipment outside the scope (another work package, supplied by others): drawn dashed |
| `cable` | object | Cable run **between the parent and this node** (§3.2) |
| `children` | array of nodes | Nodes supplied by this one |
| `ext` | object | Extensions |

### 3.1 Tree semantics

* A node is supplied by its parent and supplies its `children`, in order (left → right).
* A node with **several children** implicitly carries a **busbar**. The `busbar` type makes it
  possible to declare it explicitly in order to give it characteristics (In, dimensions, Ik).
* A `board` (distribution board, cabinet, enclosure) is a **container**: it has no electrical function
  of its own; it groups its descendants down to the next board. It is drawn as a dashed frame.
* Loads (category `load`), `pv_array` and `battery` are **leaves**.
* A protective device without children represents an outgoing circuit whose load is not described (drawn as an arrow).

### 3.2 Cable

| Field | Description |
|---|---|
| `designation` | Type: `U1000R2V`, `H07V-U`, `AR2V`, `H1Z2Z2-K`… |
| `cores` | Core composition without the cross-section: `3G`, `5G`, `4x`, or full composition `4x120+70` |
| `section_mm2`, `pe_section_mm2`, `neutral_section_mm2` | Cross-sections |
| `parallel` | Number of cables in parallel per phase |
| `material` | `Cu` / `Al` |
| `length_m` | Length |
| `install` | Installation method (IEC 60364-5-52 reference) |
| `insulation` | `PVC`, `PR`, `EPR`, `XLPE` |
| `du_pct` | Calculated voltage drop |
| `ref` | Cable tag (`W12`), written with the cable text on the drawings (display: §7.2) |
| `marks` | Wire marks of its conductors, by conductor: `{"L1": "101", "PE": "PE"}` (§7.2) |

### 3.3 Templates (`templates`)

A template is an object of attributes, optionally typed. During resolution:

1. the template's attributes are copied into the node, **with the node's own attributes taking precedence**;
2. if the template declares a `type`, it **MUST** be equal to the node's type;
3. `id`, `type` and `children` are never inherited;
4. the resulting node is validated against its type.

```json
"templates": { "C20": { "type": "breaker", "in_A": 20, "curve": "C", "icn_kA": 4.5, "poles": "1P+N" } },
...
{ "type": "breaker", "ref": "-F0", "use": "C20", "in_A": 25 }   // → C25 4.5 kA 1P+N
```


## 3a. Common fields, switchgear, auxiliary devices and enclosures

### Fields common to all nodes
| Field | Description |
|---|---|
| `count` | Number of identical items represented ("x 20", 8 micro-inverters) |
| `circuit` | Circuit or outgoing feeder number / code, distinct from the reference designation (C1, 15B) |
| `un_V`, `uln_V` | Rated (phase-to-phase) voltage and phase-to-neutral voltage of the node (boards, busbars, loads, inverters) |
| `ib_A`, `p_kW`, `q_kvar`, `cos_phi` | Feeder data / power balance |
| `priority` | `essential`, `non_essential`, `safety`, `standby` |
| `normal_state` | `open` / `closed`: ring open point, NO/NC device, removable link not fitted. Rendered as an `N.O.` annotation |
| `locks[]` | Interlock keys engaged by the device: the members sharing a key form one interlock (§4.1) |
| `notes[]` | References to the numbered notes on the sheet |
| `point_no` | Sequence number of a point on a circuit (RGIE diagrams, Belgian wiring regulations) |

### Switchgear (all protection / switching types)
`frame_A` (AF), `range`, `ue_V`, `icn_kA`, `icu_kA` (kAIC), `icw_kA`, `aux[]` (MX, MN, OF, SD, IOF, heating control-wire contact),
`mounting` (`fixed`, `plug_in`, `withdrawable`), `lockable`. Circuit breaker: `ii_A`, `tsd_s`, `gf_A`, `selective`.
`rcbo.rcd_in_A` (Vigi add-on block with a different rating). `spd.poles`, `spd.uc_V`. `socket.in_A`. `spare.in_A/poles/frame_A`
(prepared space). `transfer_switch.technology` (`static` = STS). `contactor.function`: `grid_relay`, `interface`.

### Boards, busbars, sources
`board`: `in_A`, `ik1_kA`, `system`, `earthing` (local earthing system, IT downstream of a transformer), `ways`, `ip`, `form`,
`kind`: `panelboard`, `pdu`, `substation`, `pen_split` (TN-C-S: PEN split into PE + N at this board; when no board
sets it, a TN-C-S installation splits at the first board). `busbar`: `kind` (`busway` = busbar trunking system), `material`,
`system`, `earthing`. `grid.scc_MVA`, `grid.system`. `transformer.kind` (`auto`, `earthing`, `isolation`, `bank`),
`transformer.u1_alt_V` (dual voltage). `generator.prime_mover`. `inverter.protection` (built-in grid decoupling protection),
`inverter.kind`: `charger`. Systems: `split-phase` (120/240 V); earthing system: `TN`. `rcd_type`: `G`.

### Further types
| Type | Use |
|---|---|
| `instrument_transformer` (`kind` ct/vt/toroid/combined, `ratio`, `accuracy`, `burden_VA`) | CTs, VTs, toroids |
| `protection_relay` (`functions[]`, `settings`, `idn_mA`) | ANSI relays, Vigirex, grid decoupling |
| `earthing_switch` | Earthing switch |
| `voltage_indicator` | VPIS / capacitive dividers |
| `insulation_monitor` | IMD (insulation monitoring device, IT system) |
| `surge_limiter` | Surge limiter (Cardew) |
| `neutral_impedance` (`impedance_ohm`) | Neutral impedance (impedance-earthed IT) |
| `terminal_block` (`terminals`) | Terminal block, connection point |
| `junction_box` (`kind` junction/pull/tap/manhole/vault/service_end) | Junction box, manhole |
| `connector` | MC4, plug-in connector |
| `dc_converter` (`kind` optimizer/mppt/dcdc/charge_controller) | PV optimizers, charge controllers |
| `earth_bar` (`kind` main_earth/pe_bar/equipotential/neutral_bar) | Main earthing terminal, PE bar, neutral bar |

### Cable
`ref` (reference designation / schedule tag), `kind` (`busway`, `trunk`...), `conductors` ("L1, L2, L3, N, PE"), `pen`,
`cpr_class`, `size_awg`, `raceway`, `ambient_C`, `status`.

### Auxiliary devices and enclosures
* `devices[]` (document root): nodes **outside the power tree** (relays, CTs on a branch, IMDs, VPIS,
  communication modules). They are connected by links (`measure`, `trip`, `control`, `data`, `earth`).
  Rule: a tree node carries power; a device that only measures, controls or signals goes in `devices`.
* `enclosures[]`: **addressable** enclosures that contain only the listed nodes (`kind`: cabinet, cell, box, room,
  zone, substation, boundary, lineup, panel; `cell_type` IM/QM/DM1…; `position` in the lineup; `parent`).
  Prefer them to `board` when the frame on the diagram does not match a subtree (MV cubicles, partial enclosure,
  property boundary).

### Links
Further `kind` values: `infeed` (additional supply to a node: 2nd incomer, MV ring, back-feed),
`earth` (PE / equipotential bonding conductor), `data` (bus, TIC (French utility meter teleinfo), Modbus), `key` (`key` = key identifier).
Further fields: `cable`, `normally_open`, `status` (`temporary`...).

### Metadata and views
`meta.drawing_number`, `meta.scale`, `meta.contributors[]`; `installation.ik1_kA`, `uln_V`, `du_max_pct`.
`views[].direction` accepts `up`, `right`, `left` (direction away from the source; the reference renderer draws downwards).
Additional circuit schedule rows: `circuit`, `ib_A`, `cos_phi`, `cable_type`, `cable_ref`, `install`, `frame_A`,
`count`, `un_V`.

### Out of scope (planned for 2.0)
Nodes with several parents / graph as the primary form (MV rings, double busbars), `board` reduced to an
enclosure, cable as a first-class edge (sections, shared trunk), named ports (`Q1#MX`, `T1#N`).


## 3b. PLCs and product references

### Product reference (`product`) on any node and any module
```json
"product": {"manufacturer": "WAGO", "part_number": "750-8212", "range": "PFC200 G2",
            "description": "PFC200 2ETH RS controller", "ean": "…", "url": "…", "quantity": 1,
            "accessories": [{"part_number": "…", "description": "Vigi block"}]}
```
`product` takes precedence over the simple `manufacturer` / `part_number` fields (which are kept). The quantity of a
bill of materials line is `product.quantity`, otherwise `count`, otherwise 1. `uniwire bom file.uniwire.json` produces the bill
of materials (CSV): one line per part number, summed quantities, reference designations involved (`-A1.3` = module in slot 3 of `-A1`).
Equipment without a reference is grouped by type and main characteristics (`spec`: rating, curve, sensitivity, poles,
breaking capacity, e.g. `C16 1P+N 6kA`), and cables by type, composition and material with their total known length
(`length_m`), so that the bill of materials is useful before products are chosen.

### Modular PLC (`plc`)
| Field | Description |
|---|---|
| `role` | `controller` (CPU), `coupler` (remote I/O head), `expansion`, `hmi` |
| `family` | 'PFC200', 'S7-1200', 'LOGO! 8', 'M241' |
| `protocols[]` | 'Modbus TCP', 'PROFINET', 'EtherNet/IP', 'KNX'… |
| `onboard[]` | I/O built into the head unit (slot 0) |
| `modules[]` | Expansion modules **in local bus order**: `slot`, `kind`, `part_number` / `product`, `channels`, `un_V`, `rating_A`, `signal`, `protocol`, `channel_labels` |

Module `kind`: `cpu`, `coupler`, `power_feed`, `power_supply`, `di`, `do`, `ai`, `ao`, `relay_out`, `mixed_io`, `counter`,
`temperature`, `power_measurement`, `comm`, `safety`, `motor`, `end`, `other`.

A PLC is placed **in the tree at the end of its supply circuit** (often behind a `power_supply`
230 V AC → 24 V DC). What it controls or reads goes through links.

### Channel ports (`from_port` / `to_port`)
A link can target a channel: `"from_port": "3.1"` = slot 3, channel 1 (slot 0 = built-in I/O). `protocol` field on
`data` links. Example:
```json
{"kind": "control", "from": "API1", "from_port": "4.1", "to": "KM21", "label": "Pump 1"},
{"kind": "data", "from": "RIO1", "to": "API1", "protocol": "Modbus TCP"}
```

### Power supply (`power_supply`)
`u1_V`, `u2_V`, `output` (DC/AC), `in_A`, `p_W`, `redundant`. `controller` gains `in_A` and `poles` (time switch, load-shedding contact).

### Rules (`core` profile)
`plc.port` (non-existent slot, channel beyond the number of channels, unreadable port), `plc.port-shared` (one channel controls
several devices), `plc.coil` (24 V output driving a 230 V coil without a relay), `plc.slots` (duplicate or
out-of-order slots), `plc.wago-end` / `plc.wago-feed` (WAGO local bus without an end module / power feed module).

### Rendering
The PLC is drawn as a head unit followed by a strip of modules (one rectangle per slot, coloured by kind, slot
number above); links leave from below the relevant module and carry the channel number.

## 4. Links (`links`)

| `kind` | Direction | Rendering |
|---|---|---|
| `transfer` | `from` = last device of the 2nd source, `to` = a `transfer_switch` | Arrives at the "standby" input of the transfer switch |
| `tie` | `from` / `to` = two nodes with a busbar; `device` = coupling device | Horizontal coupling between busbars |
| `bypass`, `parallel` | Additional power connection | Solid line |
| `infeed` | Additional supply to a node (2nd incomer, alternative position of a feeder) | Solid line landing on the input conductor of `to` (junction dot) |
| `control`, `interlock`, `trip`, `measure` | Control, interlocking, tripping, measurement | Dashed line |

Fields: `kind`, `from`, `to` (**existing** identifiers), `label`, `device` (node inserted on the link: bus
coupler, removable link, switch, fuse…), `normally_open`, `locks[]`, `cable`, `id`, `ext`.

A power link (`transfer`, `tie`, `bypass`, `parallel`, `infeed`) with `normally_open: true` is drawn with a
**long dash** (control links use a short dash). Its `device` is drawn on the route, in its normal state, with
its tag, rating and state (`N.O.`, interlock keys) placed beside it.

### 4.1 Interlocks (`locks`, `interlocks`)

`locks[]` (on any node and on any link) lists the interlock keys engaged by a device. Trapped-key principle:
all the members (nodes and links) whose `locks` contain the same identifier form **one interlock**; with *K*
keys, at most *K* members may be **closed** at the same time. A link and the device it carries are one member
(their `locks` are merged).

* A node is closed unless its `normal_state` is `open` (a `transfer_switch` engages its interlocked alternate
  position only when its `normal_state` is `closed`).
* A link is closed unless it is `normally_open` or its `device` has `normal_state: "open"`.

The optional document-level `interlocks` section gives the number of keys of an interlock (a key used in
`locks` without a declaration has **one** key):

| Field | Required | Description |
|---|---|---|
| `key` | **yes** | Identifier used in `locks` |
| `keys` | no (default 1) | Number of keys: maximum number of members closed at the same time |
| `label` | no | Description |
| `kind` | no | `trapped_key`, `mechanical`, `removable_link`, `electrical` |

Typical uses: 1 key = mutually exclusive positions (removable links, changeover jumpers, either/or supplies,
UPS maintenance bypass / UPS output); 2 keys for 3 breakers = two transformers and a bus coupler never
paralleled ("2 of 3").

Example: feeder `-QA` selectable between busbars `W1` and `W2` by removable links. The default position is
in the tree, the alternative position is an `infeed` link from the other busbar; both carry the key `LA`:

```json
{"id": "W1", "type": "busbar", "children": [
  {"id": "X11", "type": "disconnector", "ref": "-X11", "normal_state": "closed", "locks": ["LA"],
   "children": [{"id": "QA", "type": "breaker", "ref": "-QA", "in_A": 250}]}]}
```

```json
"links": [{"kind": "infeed", "from": "W2", "to": "QA", "normally_open": true,
           "device": {"type": "disconnector", "ref": "-X21", "normal_state": "open", "locks": ["LA"]}}],
"interlocks": [{"key": "LA", "kind": "removable_link", "label": "Feeder A: links on W1 or W2"}]
```

The rule `core.interlock` checks it (see §10); [example 52](https://github.com/uniwire-dev/uniwire/blob/main/examples/52_dual_source_selectable_feeders.uniwire.json)
shows three such feeders.

## 5. Type registry (core 1.0)

The registry ([`src/uniwire/registry/core.json`](https://github.com/uniwire-dev/uniwire/blob/main/src/uniwire/registry/core.json)) gives, for each type,
its category, the usual IEC 81346 letter (`iec81346`), the 2- or 3-letter IEC 81346-2:2019 class
(`iec81346_class`, e.g. `breaker` → `QAB`, `rcd` → `FBA`, `null` if no class fits), the
labels (English and French), the symbol and the CIM / IFC / IEC 61850 SCL mappings. The
`iec81346_class` field only stores a class code. The full IEC 81346-2 class table (codes and headings)
is available from the optional data package `uniwire-data-iec81346` (`pip install "uniwire[iec81346]"`,
licensed **CC BY-SA 4.0**, separately from the Apache-2.0 library); once installed it is read with
`uniwire.registry.iec81346_table()` (empty table otherwise).

| Category | Types and specific attributes |
|---|---|
| **Sources** | `grid` (`supply`, `un_V`, `ik_kA`) · `transformer` (`sn_kVA`, `u1_V`, `u2_V`, `ucc_pct`, `coupling`, `insulation`) · `generator` (`sn_kVA`, `p_kW`, `un_V`, `fuel`) · `ups` (`sn_kVA`, `autonomy_min`, `bypass`) · `pv_array` (`modules`, `module_W`, `strings`, `p_kW`, `voc_V`, `isc_A`) · `battery` (`capacity_kWh`, `un_V`, `technology`) · `inverter` (`kind` string/central/micro/hybrid/battery, `p_kVA`, `count`, `mppt`) · `meter` (`kind`, `in_A`, `bidirectional`) |
| **Protection / switching** (common `in_A`, `poles`) | `breaker` (`curve` B/C/D/K/Z/MA, `icn_kA`, `frame_A`, `range`, `trip_unit`, `ir_A`, `isd_A`, `aux[]`, e.g. heating control-wire contact) · `rcd` (`idn_mA`, `idn_range_mA`, `rcd_type` AC/A/F/B/A-SI/Hpi, `delay`) · `rcbo` (breaker + rcd) · `main_breaker` / AGCP (main incoming circuit breaker) (`range_A` "15-45", `idn_mA`, `idn_range_mA`, `rcd_type`, `selective`, `icn_kA`, `subscribed_kVA`) · `fuse` (`fuse_class`, `size`) · `fuse_switch` (`fuse_A`, `fuse_class`, `size`) · `switch_disconnector` (`dc`) · `disconnector` · `contactor` (`function` HC/power/lighting/load_shedding, `coil_V`, `manual`) · `impulse_relay` (`coil_V`) · `thermal_relay` (`range_A`, `setting_A`) · `motor_starter` (`method` dol/reversing/star_delta/soft_starter/vfd, `p_kW`) · `transfer_switch` (`mode`, `interlock`) · `spd` (`spd_type` 1/2/1+2/3, `imax_kA`, `in_kA`, `up_kV`, `dc`) · `controller` (`function`, `symbol_text`) |
| **Connections / containers** | `busbar` (`in_A`, `ik_kA`, `dimensions`) · `board` (`kind` main/distribution/sub/ac_box/dc_box/mcc/switchboard/enclosure, `ik_kA`, `own_sheet`) · `earth` (`resistance_ohm`) · `offpage` (`target`): cross-reference to another sheet or document |
| **Loads** (common `p_kW`, `p_max_kW`, `room`) | `lighting` (`points`) · `socket` (`points`, `poles` 2P+T / 3P+N+T…, `socket_type`) · `heating` (`pilot_wire`) · `water_heater` (`volume_L`) · `cooking` (`kind` hob/oven/range) · `appliance` (`kind` washing_machine/dishwasher/dryer/freezer/fridge) · `motor` (`in_A`, `cos_phi`, `rpm`, `phases`) · `ev_charger` (`mode`) · `ventilation` · `shutter` · `load` (`symbol_text`) · `spare` |

Common enumerations: `poles` ∈ {1P, 1P+N, 2P, 3P, 3P+N, 4P}.

## 6. Quantities and units

* A published file **MUST** contain numbers in the unit indicated by the field suffix:
  `_A`, `_mA`, `_kA`, `_V`, `_kV`, `_kW`, `_kVA`, `_kWh`, `_W`, `_mm2`, `_m`, `_pct`, `_ohm`, `_Hz`, `_min`.
* All quantities are ≥ 0.
* An implementation **MAY** accept strings as input (`"16 A"`, `"2,5 mm²"`, `"0,03 A"`) or
  `{"value": 30, "unit": "mA"}` and **MUST** then convert them on output
  (`uniwire normalize` rewrites a document in its canonical form).

## 7. Views (`views`)

| Field | Default | Description |
|---|---|---|
| `id` | `sld` | Identifier |
| `kind` | `single-line` | `single-line` or `multi-line` (power diagram, one line per conductor, §7.1) |
| `title` | - | Sheet title |
| `root` | - | Draw only the subtree of this node |
| `paper` / `orientation` | `A3` / `landscape` | Sheet format. When `paper` is absent, a renderer may choose the smallest format that holds the drawing at full size (the reference library: A4 landscape when it fits, else A3) |
| `direction` | `down` | Direction of power flow (future values reserved) |
| `pitch_mm` | 20 | Width of an outgoing feeder column |
| `cartouche` | `label, ref, protection, idn_mA, cable, p_kW` | Rows of the circuit schedule (among `label`, `ref`, `protection`, `in_A`, `curve`, `icn_kA`, `idn_mA`, `rcd_type`, `poles`, `cable`, `section_mm2`, `length_m`, `p_kW`, `phase`, `room`, `points`, and the 1.2 rows below, e.g. `cable_ref` "Cable tag"); an `idn_mA` value carried by a device upstream of the feeder (incomer, group RCD), not by its own protection, reads "30mA (upstream)" |
| `folio_split` | `auto` | `auto`: split across sheets if needed; `none`: everything on one sheet |
| `min_scale` | 0.7 | Maximum reduction before splitting |
| `annotations` | `true` | Reference designation and characteristics next to the symbols |
| `tag_field` | `ref` | Displayed identifier: `ref` or `part_number` (diagrams that print only catalogue part numbers) |
| `conductor_marks` | `true` | Conductor-count strokes (IEC 60617: one stroke per conductor, or one stroke and the number) and phase of single-phase circuits on each outgoing feeder, on the line leaving each source / transformer, and below each switching device whose `poles` change the conductors of the line above it (not repeated lower in the same column). A neutral the device does not cut is shown apart: `3P+N` → three strokes and `+N`, `4P` → one stroke and `4`; `3P` gets `+N` only when circuits below use the neutral. PE is not counted |
| `frames` | `[]` | Enclosure frames `{label, nodes[]}` drawn around arbitrary nodes (cabinet, cubicle) when they do not form a `board` subtree |
| `title_block` | `true` | Sheet border and title block |
| `first_folio`, `total_folios` | 1, - | Numbering within a partial set of sheets ("sheet 1/3") |
| `show_pe` | `true` | `multi-line` views: draw the protective conductor (PE) |
| `color` | `none` | Colour mode: `conductors` (multi-line: every conductor in its colour; single-line: single-phase feeders in their phase colour), `phase` (single-phase feeders by phase, phase cell of the schedule tinted), `source` (what each source (tree root) feeds in normal operation; normally-open alternative supplies in the colour of the source they come from, dashed), `status` (`status` of nodes and links, inherited downstream: existing grey, new black, future blue dashed, temporary orange, removed red), `voltage` (MV > 1 kV AC, LV, ELV ≤ 50 V AC, DC). Strokes only: texts stay black, frames and earth / data links keep their colour; a legend of the colours used is drawn in a free corner of each sheet. Omitted: black drawing |
| `palette` | - | Colour overrides `{key: "#rrggbb"}` for the colour mode: conductor names (`L1` … `PE`, `PEN`, `L+`, `L-`), source ids, status values, `mv` / `lv` / `elv` / `dc` |
| `conductor_colors` | - | Preset of the `conductors` mode: `iec` (IEC 60445: L1 brown, L2 black, L3 grey, N blue, PE green-yellow) or `us` (L1 black, L2 red, L3 blue (brown / orange / yellow from 480 V), N white drawn light grey, ground green). Omitted: `us` when `installation.standard` names the NEC / CEC, else `iec` |
| `wire_marking` | - | Wire marking rules (§7.2): `scheme` (`manual`, `sequential`, `potential`, `pattern`), `pattern`, `start`, `step`, `prefix`, `suffix`, `per`, `power`, `keep_manual`, `order` |
| `wire_marks` | `true` with `wire_marking` | Show the wire marks on the multi-line drawing (§7.2) |
| `overrides` | `{}` | Per `id`: `label_offset` [dx, dy] in mm, `hide` |

A view **never** contains topology. Deleting all views does not change the meaning of the document.

### 7.1 View kinds

A document may declare several views, of either kind, e.g.
`"views": [{"id": "sld"}, {"id": "ml", "kind": "multi-line", "paper": "A3"}]`.

* `single-line` (default): the single-line diagram, one line per circuit.
* `multi-line`: the **multi-line power diagram**, derived from the same tree with no extra data: every circuit is
  drawn with one line per conductor (`L1`, `L2`, `L3`, `N`, `PE`, `PEN`, `L+` / `L-` in DC) and every
  switching device with one contact per pole. The conductors of a node are deduced, in order of precedence, from
  its `phase` (a single-phase circuit taps that phase; without `phase`, `L1`), its `poles` (`1P` and `3P` leave the
  neutral uncut, `1P+N` / `3P+N` add an unprotected neutral pole, `2P` / `4P` switch every live conductor), its
  cable `cores` (`3G` = L + N + PE, `4G` = 3 L + PE, `5G` = 3 L + N + PE), the number of `phases` of a motor, the
  `system` of a board or busbar and the usual connection of the load type, otherwise from upstream. The supply
  follows `installation.system` / `grid.system` and the earthing system: TN-C and TN-C-S carry a PEN, split into
  PE + N at the board flagged `pen_split` (by default the first board in TN-C-S); TN-S carries a PE from the source;
  TT and IT get their PE at the first board. A transformer starts a new system (neutral from the vector group,
  `Dyn11` → N); inverters and power supplies feed a DC pair.

  Rendering of the reference implementation: busbars as one rail per conductor (named at their end); circuit
  breakers with the breaker cross on each protected pole, the poles linked by a dashed mechanical link; RCDs with a
  toroid around all live conductors; fuses on each phase; transformers as two windings with their vector group;
  motors as `M 3~` with terminals `U V W` and PE; loads as a box with one terminal per conductor; other types as a
  labelled box across their conductors. Ratings and tags are written as on the single-line diagram, load
  descriptions under the loads, outgoing cables above them. Large documents are split into sheets like the
  single-line diagram. Auxiliary devices, links other than the tree and `frames` are not drawn in this view.

### 7.2 Wire marking and wiring exports (part of UEP-0001)

This is the part of the 2.0 proposal
[UEP-0001](uep/0001-terminals-and-wires.md) §3.3.2 and §3.5 that the current format can carry, with the same names and
meaning, so that 2.0 extends it without breaking it.

**Wires in the current format.** Without a `wires[]` section, the wires are the conductors of the cables of the power tree:
the cable of a node (`node.cable`) feeds it from its parent and carries the conductors of the node's input as
derived for the multi-line view (§7.1). A conductor that starts in the node (the PE at the main earthing terminal of
a TT installation) is not part of the cable; the `N` and `PE` of a board that splits a PEN arrive on one `PEN` core.
Each conductor has the identifiers 2.0 gives to implicit wires: cable `<node id>.cable`, wire
`<node id>.cable.<conductor>` (`M1.cable.L1`). Its `from` end is the parent node, its `to` end the node.

**Manual marks.** `cable.marks` gives the marks (ferrule texts) of the conductors of a cable, by conductor:
`"marks": {"L1": "1L1", "L2": "1L2", "L3": "1L3", "PE": "PE"}`. This field has no counterpart in UEP-0001, where
marks are written on `wires[].mark`; it is their place in the current format, and a 2.0 migration moves them there.

**Marking rules**: `views[].wire_marking` (and `wire_marks`, default `true` when `wire_marking` is set, to show or
hide the marks on the drawing):

| Field | Default | Description |
|---|---|---|
| `scheme` | `manual` | `manual`: only the marks of the document (`cable.marks`). `sequential`: one number per conductor. `potential`: one number per potential (net), shared by its conductors. `pattern`: marks built from `pattern` |
| `pattern` | - | Template of `pattern`: `{circuit}` (`circuit` of the feeder), `{conductor}`, `{ref}` (tag of the `from` node), `{from}`, `{to}` (tags of the two ends), `{cable}` (cable `ref`, else its id), `{n}` (sequence number). `{from_port}`, `{to_port}`, `{potential}`, `{strip}`, `{terminal}` are reserved for 2.0 and empty in the current format; other tokens are errors. Example `"{circuit}-{conductor}"` → `C3-L1` |
| `start`, `step` | 1, 1 | First number and increment |
| `prefix`, `suffix` | `""` | Added around generated numbers (`{n}` included) |
| `per` | `document` | Numbering restarts per `document`, `sheet` (multi-line sheet) or `enclosure` (of the `from` end: an `enclosures[]` entry, else the board) |
| `power` | `conductor` | `sequential` and `potential` schemes: `conductor` marks the power conductors with their name (`L1`, `N`, `PE`), `number` numbers them, `none` leaves them unmarked (also for `pattern`). As every wire of the current format is a power conductor, numbering needs `"power": "number"` |
| `keep_manual` | `true` | `cable.marks` are kept; generated numbers skip the values they use |
| `order` | `layout` | `layout`: sheet, then column, then top to bottom in the multi-line drawing of the view; `document`: order of the tree |

Marking is deterministic: the same document and view always give the same marks. Potentials (`potential` scheme)
follow UEP-0001 §3.4.2: a conductor keeps its net through boards, busbars, meters and any device that does not switch
it (an uncut neutral, the PE); each pole of a switching device, a drive, a transformer or converter, and the neutral
created by a PEN split start a new net.

**Display.** In the multi-line view, each marked conductor of a cable carries its mark along the line, left of it,
just above the node the cable feeds (for a cable held by a device above a load: above the load, where the cable text
is written). When an edge between two devices is too short for its marks, they are carried only in the SVG
(`data-uw-mark`) and in the exports. The single-line view is unchanged.

**Cable tag.** `cable.ref` is written with the cable text: in the `cable` row of the circuit schedule (`W12 · 4G2.5`,
unless the view also has a `cable_ref` row, header "Cable tag"), and before the cable designation in the multi-line
view.

**Freezing.** `uniwire marks FILE --view ID --write` writes the generated marks into `cable.marks`, so that later edits
do not renumber printed ferrules (with `keep_manual`, the view then gives the same marks).

**Exports** (CSV, UTF-8, comma separated, stable English column names, UEP-0001 §3.5.2):

* wire list `uniwire wires FILE [--view ID]`: `wire_id, mark, from, from_display, from_enclosure, to, to_display,
  to_enclosure, potential, conductor, section_mm2, color, cable, core, length_m, status` (in the current format every row is an
  implicit power connection; `potential`, `color`, `core` are empty);
* wire marker list `uniwire markers FILE [--view ID]`: `mark, wire_id, end, terminal_display, section_mm2, color,
  enclosure, quantity`, one row per end of a marked wire;
* cable schedule `uniwire cables FILE`: `cable_id, ref, designation, cores, section_mm2, length_m, from_enclosure,
  to_enclosure, from, to, cores_used, cores_spare, status` (tree cables `<node id>.cable`, then link cables
  `<link id or index>.cable`).

Without `--view`, the rules of the first view that declares `wire_marking` apply (none: manual marks only).

## 8. Derived graph form

`uniwire graph file.uniwire.json` produces the canonical "network" form:

* `components[]`: each node with its terminals (`in`, `out`, `in2` for the transfer switch), its attributes and
  its mappings (`cim`, `ifc`, `scl`); each cable becomes a `cable` component;
* `connectivity_nodes[]`: connectivity nodes (`cn:<parent id>`), one busbar = a single node;
* `signals[]`: control connections.

This form is the starting point for exports to calculation tools (pandapower, power-grid-model),
CIM/CGMES, IEC 61850 SCL or IFC4 (`IfcDistributionPort` + `IfcRelConnectsPorts`).

## 9. Extensibility and versions

* Every object accepts `ext`: `{"<vendor prefix>": {...}}`. A tool **MUST** preserve the extensions
  it does not understand.
* Everywhere else, undefined properties are forbidden (`additionalProperties: false`).
* Versions: `1.y.z`. A minor version only adds optional fields or enumeration values.
  An incompatible change bumps the major version and the `$id` path (`/v2/`).
* A reader **MUST** accept any `1.y.z` document. A document written for a newer minor version than the
  reader supports loads as long as it uses only fields the reader knows; otherwise its unknown fields are
  rejected like any other, and the reader **SHOULD** say that a newer version is needed.

## 10. Validation

1. **Structure**: JSON Schema (`schema/uniwire.schema.json`), usable with any validator.
   The node union is dispatched by `if/then` on `type` (for performance on deep trees).
2. **Integrity** (reference implementation): templates exist and have the same type, identifiers are unique,
   link endpoints exist.
3. **Business rules** per profile (`uniwire check`):
   * `core` (always): unique reference designations per board, downstream rating ≤ upstream rating, consistency of links / transfer switches;
     `core.interlock` (§4.1): **error** when more members of an interlock are closed in normal operation than it
     has keys (or when a key is declared twice), **warning** when a declared interlock is used by fewer than
     2 members, or when an undeclared `locks` key is used by a single member (it interlocks nothing);
   * `nfc15100`: checks of a French low-voltage installation under NF C 15-100. The rules of part 7-771
     (dwellings, marked *dwelling*) apply when `installation.premises` is `dwelling` or absent; for other
     premises only the general rules apply (30 mA on socket-outlet and charging circuits, part 4-41 411.3.3;
     EV charging, part 7-722; selectivity), and the cable table becomes a warning to size the cable for its
     installation method (part 5-52, guide UTE C 15-105). Each rule carries a `source` (document and page) and
     a `confidence` (`high` / `medium`), available in `uniwire.rules.RULE_INFO`. Each `Finding` repeats the
     source.

     | Rule | Check | Level |
     |---|---|---|
     | `nfc15100.section` | Copper cross-section ↔ rating: 1.5 → 16 A, 2.5 → 20 A, 4 → 25 A, 6 → 32 A; outside dwellings, a warning to check the cable for its installation method | error (dwelling) / warning |
     | `nfc15100.points` | *Dwelling*. Lighting: at most 8 points. Sockets: at most 8 on 1.5 mm², at most 12 on 2.5 mm² | error |
     | `nfc15100.lighting-rating` | *Dwelling*. Lighting protected at 16 A at most | error |
     | `nfc15100.rcd-30mA` | 30 mA protection for sockets and EV charging (all premises) and for every dwelling circuit | error |
     | `nfc15100.rcd-type-A` | No type AC RCD for EV charging (all premises) and, in dwellings, for washing machine, dryer, hob / cooker | error |
     | `nfc15100.rcd-count` | *Dwelling*. At least 2 30 mA RCCBs (ID) per dwelling, including 1 type A | warning |
     | `nfc15100.rcd-circuits` | *Dwelling*. At most 8 circuits per 30 mA RCCB | error |
     | `nfc15100.heating` | *Dwelling*. Heating power per circuit: 3.5 / 4.5 / 5.75 / 7.25 kW at 16 / 20 / 25 / 32 A | warning |
     | `nfc15100.dedicated-circuit` | *Dwelling*. Dedicated circuits: washing machine, dishwasher, dryer, freezer, oven, hob, water heater, EV charging (one load per circuit), heating and shutters (circuit reserved for that use) | error |
     | `nfc15100.ev-rcd` | EV charging: type B in three-phase mode 2 (error). In mode 3 with a type A or F, reminder of 6 mA DC detection (info) | error / info |
     | `nfc15100.selectivity` | Selective (S) incoming residual current device upstream of other RCDs | warning |

   * `iec60364` *(optional, must be declared in `profiles`)*: current-carrying capacity of cables.
     * **Rule `iec60364.iz`**
       * Condition: the cable specifies `section_mm2`, `material`, `insulation` and `install`.
       * Check: the rating of the protective device supplying the cable does not exceed Iz. The rating
         used is `ir_A`, otherwise `fuse_A`, otherwise `in_A`. Iz is multiplied by `parallel`.
       * Level: **warning**, never error. The message cites the source.
     * **Data**: [`registry/data/iz_tables.json`](https://github.com/uniwire-dev/uniwire/blob/main/src/uniwire/registry/data/iz_tables.json),
       readable with `uniwire.registry.iz_tables()`.
       * Source: official Spanish guide **GUIA-BT-19** (Feb. 2009, rev. 2).
       * Table A, p. 9: reproduces table A.52-1 bis of **UNE 20460-5-523:2004**, the transposition of
         IEC 60364-5-523.
       * Table D, p. 12: buried cables in ducts.
     * **Coverage**
       * Copper, PVC or XLPE (`PR` and `EPR` are treated as XLPE).
       * Installation methods `A1`, `A2`, `B1`, `B2`, `C`, `E`, `F`, with 2 or 3 loaded conductors.
       * Cross-sections from 1.5 to 300 mm².
       * Method `D-duct` (buried in duct, XLPE): copper and aluminium.
       * Non-buried aluminium is not provided by the source: the rule then emits an info.
     * **Number of loaded conductors**: 3 if the protective device is `3P`, `3P+N` or `4P`. Otherwise 2.
       If the poles are not specified, `installation.system` is used.
     * **Limitations**
       * Referenced to **40 °C ambient**, versus 30 °C in IEC: Iz is therefore about 9 to 13 %
         lower.
       * No grouping or temperature correction factor is applied.
       * The IEC 60364-5-52:2009 edition may differ slightly.

   * `enedis` *(optional, must be declared in `profiles`)*: connection of a low-voltage installation to the
     French public network (NF C 14-100, Enedis technical reference Enedis-NMO-RAC_001E), separate from
     `nfc15100`, which starts downstream of the service main breaker. Rules `enedis.connection` (power tiers
     of the connection), `enedis.agcp-setting` (the setting `in_A` of the service `main_breaker` carries the
     connection power: 0.2 kVA per ampere single-phase, 0.6 kVA per ampere three-phase, 60 A at most),
     `enedis.agcp-rcd` (500 mA residual-current service breaker recommended), `enedis.production` (PV
     injection and installed power limits) and `enedis.decoupling` (decoupling protection of PV inverters).
     Applies only to a low-voltage supply from a `grid` source. Details and levels:
     [Rules](rules.md#enedis-connection-to-the-french-public-network).

   These rules are consistency checks: they do not replace the standard.

## 11. History

| Version | Changes |
|---|---|
| 1.0 | Initial release |

## 12. Complete minimal example

```json
{
  "uniwire": "1.0.0",
  "installation": { "earthing": "TT", "system": "1P+N", "un_V": 230 },
  "sources": [
    { "type": "grid", "label": "Grid", "children": [
      { "type": "main_breaker", "ref": "-Q0", "range_A": "15-45", "in_A": 45, "idn_mA": 500, "selective": true,
        "children": [
          { "type": "rcd", "ref": "-Q1", "in_A": 40, "idn_mA": 30, "rcd_type": "A", "children": [
            { "type": "breaker", "ref": "-Q11", "in_A": 16, "curve": "C",
              "cable": { "cores": "3G", "section_mm2": 1.5 },
              "children": [ { "type": "lighting", "label": "Lighting", "points": 6 } ] },
            { "type": "breaker", "ref": "-Q12", "in_A": 20, "curve": "C",
              "cable": { "cores": "3G", "section_mm2": 2.5 },
              "children": [ { "type": "socket", "label": "Sockets", "points": 8 } ] }
          ] }
      ] }
    ] }
  ]
}
```

See [`examples/`](https://github.com/uniwire-dev/uniwire/tree/main/examples) for complete documents, from a dwelling board to industrial installations.
