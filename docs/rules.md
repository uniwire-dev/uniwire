# Rules

Beyond the JSON Schema, uniwire checks documents against **rule profiles**. The `core` rules (including
the PLC checks) always run; other profiles are enabled per document with `"profiles": [...]`, or on the
command line with `--profile`.

```bash
uniwire check house.uniwire.json                       # core + the document's profiles
uniwire check house.uniwire.json --profile iec60364    # core + iec60364 only
```

```python
import uniwire
findings = uniwire.check(uniwire.load("house.uniwire.json"), ["nfc15100", "iec60364"])
```

!!! note
    These rules are consistency checks that help catch mistakes early. They do not replace the
    applicable standards, nor the verification of an installation by a qualified person.

## Findings

Each finding has a level, a stable rule id, the node concerned and a message:

```text
house.uniwire.json: 2 finding(s)
  WARNING nfc15100.rcd-count [Q1]: only one 30 mA residual-current device (dwellings: at least 2; set installation.premises for other premises)
  ERROR   nfc15100.section [Q12]: 25 A breaker on 2.5 mm² (max 20 A)
```

| Level | Meaning |
|---|---|
| `error` | The document contradicts a rule; `uniwire check` exits with code 1 |
| `warning` | Probably wrong, or a recommendation not met |
| `info` | Reminder, or a check that could not be completed (data not covered) |

In Python, a `Finding` has the attributes `level`, `rule`, `message`, `node` and `source`. Rules based on a
standard carry a `source` (the document and clause the rule relies on) and a `confidence` (`high` or
`medium`), available in `uniwire.rules.RULE_INFO`. Messages are translated: set `UNIWIRE_LANG` to `fr`, `de`, `es`, `pt`, `ru` or `zh`.

An unknown profile name produces a `profile` warning.

## `core` (always active)

| Rule | Check | Level |
|---|---|---|
| `core.ref-unique` | A reference designation is unique within a board (it may repeat across boards) | warning |
| `core.rating-cascade` | A breaker, RCBO or fuse does not have a higher rating than the protective device directly upstream | warning |
| `core.transfer-target` | A `transfer` link ends on a `transfer_switch` | error |
| `core.transfer-source` | A transfer switch receives a second source (`transfer` link) | warning |
| `core.tie-device` | A `tie` link describes its coupling device | info |
| `core.scope` | The document describes control circuits (contactors or relays fed by a control power supply and switching nothing, coils, push buttons or signal lamps entered as loads): uniwire draws power distribution, not control schematics, so they are only summarized | info |
| `core.terminal-node` | PV arrays, batteries, SPDs and earth electrodes feed nothing (a battery root of `sources`, the only source of a DC system, may) | warning |
| `core.normalized` | A near-miss value was read in its canonical form on load: `poles: 2` as `"2P"`, `cable.cores: 3` as `"3G"`, `"3G2.5"` as `"3G"` plus `section_mm2: 2.5`, a `[15, 45]` range as `"15-45"`, a view `type`/`single_line` as `kind`/`single-line`, `meta.description` as a note. Ambiguous values are not guessed: validation rejects them. `uniwire normalize` writes the canonical form | warning |
| `core.interlock` | Nodes and links sharing a `locks` key: no more members closed in normal operation than the interlock has `keys` (SPEC §4.1); a declared interlock is used by at least 2 members; an undeclared lock is not alone | error / warning |
| `core.no-cables` | A profile that checks cables is active (`nfc15100`, `vde0100`, `iec60364`) but no circuit gives its cable size: the cables were not checked, so an empty result does not mean they are right | info |

## PLC rules (part of `core`)

Modular PLCs (`plc`) are checked whenever they appear in a document.

| Rule | Check | Level |
|---|---|---|
| `plc.slots` | Module slots are unique (error) and in increasing order (warning) | error / warning |
| `plc.port` | A link port (`from_port` / `to_port`, `"slot.channel"`) is readable, targets an existing slot and a channel within the module's channel count | error |
| `plc.port-shared` | One output channel does not control several devices | warning |
| `plc.coil` | A 24 V digital output does not drive a coil of a much higher voltage (e.g. 230 V) without an interposing relay | warning |
| `plc.wago-end` | A WAGO local bus ends with an end module (750-600) | warning |
| `plc.wago-feed` | A WAGO controller declares a potential feed module | info |

## `nfc15100`: French low-voltage installations

Checks of a French low-voltage installation under NF C 15-100, which covers every kind of premises. The version
that gives presumption of conformity (order of 3 August 2016, art. 4) is the 2002 edition with its 2005 update
and amendments A1 to A5; for dwellings, part 10-1 of amendment A5 (June 2015) replaces the former parts 7-771
and 7-772. The rules of dwellings (marked *dwelling*) apply when `installation.premises` is `dwelling` or not
set. For other premises (`commercial`, `office`, `industrial`, `public`, `agricultural`, `other`) only the
general rules apply, and the residential cable table becomes a warning to size the cable for its installation
method (part 5-52, guide UTE C 15-105).

| Rule | Check | Level |
|---|---|---|
| `nfc15100.section` | Copper cross-section ↔ rating: 1.5 → 16 A, 2.5 → 20 A, 4 → 25 A, 6 → 32 A (table 10-1F); outside dwellings, a warning to check the cable for its installation method | error (dwelling) / warning |
| `nfc15100.circuit-section` | *Dwelling*. Minimum section and maximum protection of dedicated circuits (table 10-1F): washing machine, dishwasher, dryer, oven, water heater 2.5 mm² and 20 A; single-phase cooking 6 mm² and 32 A; three-phase cooking 2.5 mm² and 20 A; 16 A EV charging 2.5 mm² and 20 A; roller shutters 1.5 mm² and 16 A | error |
| `nfc15100.points` | *Dwelling*. Points added up per circuit: lighting at most 8; 16 A sockets at most 8 on 1.5 mm², 12 on 2.5 mm² (10.1.3.2.3, 10.1.3.3.3) | error |
| `nfc15100.lighting-rating` | *Dwelling*. Lighting protected at 16 A at most (table 10-1F) | error |
| `nfc15100.rcd-30mA` | 30 mA protection of every final circuit of a dwelling, single-phase or three-phase (order of 3 August 2016, 10.1.4.7.3.1); in all premises, socket-outlets up to 32 A (411.3.3, A4) and EV charging points | error |
| `nfc15100.rcd-type-A` | Type A (not AC) for cooker / hob, washing machine and EV charging circuits (table 10-1G rule 2) | error |
| `nfc15100.rcd-count` | *Dwelling*. At least 2 30 mA RCDs, single-phase or three-phase (table 10-1G rule 1) | error |
| `nfc15100.rcd-circuits` | *Dwelling*. At most 8 circuits per 30 mA RCD, counted down to the next RCD, through combs and boards (table 10-1G rule 3) | error |
| `nfc15100.rcd-rating` | *Dwelling*. Rated current of a 30 mA RCD at least the current of the service breaker (from the subscribed power when known), or 1 × its heating, water heater and EV circuits + 0.5 × the others (table 10-1G rule 4) | warning |
| `nfc15100.rcd-spread` | *Dwelling*. Lighting circuits on at least 2 RCDs, socket-outlet circuits too (table 10-1G rule 5) | error |
| `nfc15100.heating` | *Dwelling*. Heating power per circuit: 3.5 / 4.5 / 5.75 / 7.25 kW at 16 / 20 / 25 / 32 A (table 10-1B) | warning |
| `nfc15100.dedicated-circuit` | *Dwelling*. Dedicated circuits: washing machine, dishwasher, dryer, oven, hob, water heater, EV charging (one load per circuit), heating and shutters (circuit reserved for that use); freezer recommended (10.1.3.4) | error (freezer: warning) |
| `nfc15100.neutral-pole` | *Dwelling*. No 1P breaker on a circuit with a neutral: every circuit is isolated on all its live conductors (10.1.4.7.1.1) | error |
| `nfc15100.spd-rcd` | *Dwelling*. The surge protective device at the origin is not behind a 30 mA RCD (10.1.4.7.3.1) | error |
| `nfc15100.agcp-rcd` | *Dwelling*, limited-power supply. Service breaker and intermediate RCDs at 500 mA at most, without adjustable sensitivity (10.1.2.2.1) | error |
| `nfc15100.supply-section` | *Dwelling*. Copper link from the service breaker to the main board: 10 mm² at 30 and 45 A, 16 mm² at 60 A, 25 mm² at 90 A (table 10-1D) | error |
| `nfc15100.selectivity` | A residual-current device with other RCDs downstream is selective (type S): error in a dwelling (10.1.2.2.1), warning elsewhere (535.4.3.1) | error / warning |
| `nfc15100.earth-resistance` | TT: earth electrode resistance × highest RCD sensitivity ≤ 50 V, i.e. 100 Ω with a 500 mA service breaker (411.5.3) | error |
| `nfc15100.ev-rcd` | EV charging: type B in three-phase mode 2 (error); in mode 3 with a type A or F, reminder of 6 mA DC detection (info). Source: IEC 60364-7-722 / guide UTE C 15-722, not part of the 2002 edition and its amendments | error / info |

## `vde0100`: German low-voltage installations

DIN VDE 0100 is the German adoption of IEC 60364, with the same part numbers. The profile checks the German
requirements that go beyond the general rules; combine it with `iec60364` for the current-carrying capacity of
cables. Dwelling rules apply when `installation.premises` is `"dwelling"` or not set.

| Rule | Check | Level |
|---|---|---|
| `vde0100.rcd-30mA` | Socket-outlet circuits up to 32 A protected by an RCD of at most 30 mA, all premises (DIN VDE 0100-410:2018, 411.3.3); lighting circuits of dwellings, the same (411.3.4) | error |
| `vde0100.bathroom` | Every circuit of a room with a bath or a shower protected by an RCD of at most 30 mA, except a circuit supplying only a permanently connected water heater (DIN VDE 0100-701). The room is read from the load's `room` or `label` (Bad, Badezimmer, Dusche...) | error |
| `vde0100.ev-circuit` | Each charging point supplied by its own final circuit and protected by its own RCD of at most 30 mA (DIN VDE 0100-722) | error |
| `vde0100.ev-rcd` | RCD of a charging point: type AC or not stated (error); type A or F, reminder that the charging point must include 6 mA DC fault detection, RDC-DD, IEC 62955 (info) | error / info |
| `vde0100.spd` | No surge protective device in the installation: required for most buildings (DIN VDE 0100-443 and -534, 2016) | warning |
| `vde0100.pen-section` | A cable whose `conductors` include a PEN: at least 10 mm² copper or 16 mm² aluminium (DIN VDE 0100-540, 543.4) | warning |

Not checked: arc fault detection devices (DIN VDE 0100-420, required in some premises only), the connection
rules of VDE-AR-N 4100 (meter cabinet, selective main circuit breaker) and the minimum equipment of dwellings
(DIN 18015-2). The rules were written from the structure of the standard, without its text: report any
difference with the edition you apply.

## `iec60364`: current-carrying capacity and 30 mA RCDs

### `iec60364.iz`

The rating of the protective device feeding a cable (`ir_A`, otherwise
`fuse_A`, otherwise `in_A`) must not exceed the cable's current-carrying capacity Iz (multiplied by
`parallel`).

* Applies when the cable specifies `section_mm2`, `material`, `insulation` and `install`.
* Coverage: copper and aluminium, PVC or XLPE (`PR` and `EPR` are treated as XLPE); installation methods `A1`,
  `A2`, `B1`, `B2`, `C`, `D1` (in a duct in the ground, also written `D-duct`), `D2` (buried directly), `E`, `F`,
  with 2 or 3 loaded conductors, in the cross-sections the IEC tables give (1.5 to 300 mm², from 2.5 mm² for
  aluminium, from 25 mm² for `F`). Combinations outside them produce an `info`.
* Iz: formulas `a * S^m` after IEC 60364-5-52, never above its values. Reference conditions: 30 °C in air, 20 °C
  and 2.5 K·m/W in the ground.
* Ambient temperature: the cable's `ambient_C` corrects Iz by sqrt((θmax − θ) / (θmax − θref)), θmax 70 °C for PVC
  and 90 °C for XLPE, from 10 °C (colder is taken as 10 °C) up to 60 °C for PVC and 80 °C for XLPE; above, Iz is not checked (`info`). Without `ambient_C`: 40 °C in
  air and 20 °C in the ground, and the message says it.
* Loaded conductors: 3 when the protective device is `3P`, `3P+N` or `4P`, otherwise 2; without poles,
  `installation.system` decides.
* Grouping: `grouped` (circuits or multicore cables laid together, this one included) applies the grouping
  factor, in air by `arrangement` (`bunched` when not given, `single_layer`, `ceiling`, `perforated_tray`,
  `ladder`; with `supports`, 2 or 3 trays or ladders stacked, `grouped` counting the cables on one of them), in
  the ground by `spacing_m` (0 when not given; single-core cables in their own ducts when `cores` reads `1x`).
  Up to 20 circuits in air, 9 per stacked support, 6 in the ground.
* Soil: `soil_resistivity_K_m_W` corrects Iz in the ground (`D1`, `D2`) from 0.5 to 3 K·m/W (a lower value is
  taken as 0.5).
* Harmonics: `third_harmonic_pct` on a three-phase circuit with a neutral (`3P+N`, `4P`, or the system when the
  poles are not given) multiplies Iz by 1 / sqrt(1 + 4 h²), the heating of the phases and of a neutral carrying
  their third harmonics, up to 50 %; by 1 / sqrt(1 + 7 h²) up to 15 % when the neutral is smaller.
* The applied factors are listed in the message. Beyond the range of a factor, Iz is not checked (`info`).
* Level: **warning**, never error. The formulas of Iz and of the factors are in
  `src/uniwire/registry/data/iz_iec60364.json`, never above the values of IEC 60364-5-52, read with
  `uniwire.registry.iz_iec60364()`.

### `iec60364.iz-estimate`

A cable that gives `section_mm2` but not its `material`, `insulation` or `install` is not left unchecked:

* Iz is estimated with copper and PVC unless stated, and the most favourable installation method in air
  (`A1` to `F`) unless `install` is given, at 30 °C, or corrected as for `iec60364.iz` when `ambient_C` is given,
  with the grouping, soil and harmonic factors of `iec60364.iz`.
* A protection above that Iz is too high under these assumptions: **warning**, with the
  assumptions in the message.
* One **info** finding lists the cables estimated: give their material, insulation and installation method for
  the exact check of `iec60364.iz`.

### `iec60364.rcd-30mA`

IEC 60364-4-41:2005+AMD1:2017, 411.3.3 and 411.3.4: additional protection by an RCD of at most 30 mA (**error**
when missing; the 2005 edition without its amendment stopped at socket-outlets up to 20 A):

* socket-outlets up to 32 A (their own rating, otherwise the rating of their protection), in all premises;
* lighting circuits when `installation.premises` is `dwelling`.

Not applied below an isolation transformer (`kind: "isolation"`) feeding an IT system (`earthing: "IT"`): a
medical IT system (IEC 60364-7-710) is monitored by an insulation monitoring device instead. When the document
also declares `nfc15100` or `vde0100`, this rule leaves the check to them (their national rules go further).

See the [specification](SPEC.md) §10 for the data source and its limitations.

## `enedis`: connection to the French public network

Checks of the connection of a low-voltage installation to the public network operated by Enedis: service
cable, meter and service main breaker (AGCP). They follow NF C 14-100 and the Enedis technical reference, not
NF C 15-100, which starts downstream of the AGCP; combine the profile with `nfc15100` for the installation
itself. It applies only when the installation is supplied in low voltage by a `grid` source (no transformer,
`un_V` up to 1000 V). Enedis decides on each connection: these are consistency checks of the document.

| Rule | Check | Level |
|---|---|---|
| `enedis.connection` | Limited-power connection: at most 12 kVA in single-phase (3 to 12 kVA, from 6 kVA in dwellings), 6 to 36 kVA in three-phase; monitored power from 37 to 250 kVA (info); medium voltage above 250 kVA (warning). Source: Enedis-NMO-RAC_001E §3.1 | error / warning / info |
| `enedis.agcp-setting` | Limited power: the AGCP setting (`in_A` of the `main_breaker`, `range_A` being its range) carries the connection power, 60 A for 12 kVA single-phase or 36 kVA three-phase, so 0.2 kVA per ampere single-phase and 0.6 kVA per ampere three-phase. Error when it exceeds 60 A or carries less than `installation.subscribed_kVA`. Source: Enedis-NMO-RAC_001E §4.1 | error |
| `enedis.agcp-rcd` | AGCP without residual-current protection, or other than 500 mA: NF C 14-100 recommends 500 mA in new buildings (SéQuélec fiche n°2). Type S is checked by `nfc15100.selectivity` | info |
| `enedis.production` | Production and storage inverters (`p_kVA` × `count`: PV, hybrid and battery inverters; chargers, which only draw, are not counted): in single-phase, injection limited to 6 kVA (warning) and installed power to 18 kVA (error); in three-phase, 250 kVA (info above 36 kVA: injection beyond it follows another connection procedure). The installed power includes storage. Sources: Enedis-NMO-RAC_001E §3.2.1, Enedis-NMO-RES_032E §1.2.1.2 | error / warning |
| `enedis.service-cable` | Individual service cable (the `cable` of the connection meter, from the CCPI): at most 30 m and 35 mm² aluminium (2 x 35 single-phase, 4 x 35 three-phase), for a voltage variation within 2 %. Source: Enedis-NMO-RAC_001E §4.1.3 | warning |
| `enedis.decoupling` | Production or storage inverter without its decoupling protection (`protection`, e.g. NF EN 50549-1 / NF EN 50549-10), mandatory in every case. Sources: Enedis-NMO-RES_032E §1, Consuel, decoupling protections of PV inverters (2025) | info |

With the Linky meter, the AGCP is set to the connection power and the meter follows the subscribed power:
an AGCP set above the subscribed power is normal, one set below it is an error.

## Writing a rule

Rules are plain generator functions registered on a profile:

```python
from uniwire.rules import Finding, rule

@rule("myprofile")
def no_unlabelled_loads(doc, idx):
    for node_id, node in idx.nodes.items():
        if node.type == "load" and not node.label:
            yield Finding("warning", "myprofile.load-label", "load without a label", node_id)
```

Once the module defining it is imported, `"profiles": ["myprofile"]` enables it. Rules contributed to the
project must translate their messages through `uniwire.i18n` and come with tests.
