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
`medium`), available in `uniwire.rules.RULE_INFO`. Messages are translated: set `UNIWIRE_LANG=fr` for French.

An unknown profile name produces a `profile` warning.

## `core` (always active)

| Rule | Check | Level |
|---|---|---|
| `core.ref-unique` | A reference designation is unique within a board (it may repeat across boards) | warning |
| `core.rating-cascade` | A breaker, RCBO or fuse does not have a higher rating than the protective device directly upstream | warning |
| `core.transfer-target` | A `transfer` link ends on a `transfer_switch` | error |
| `core.transfer-source` | A transfer switch receives a second source (`transfer` link) | warning |
| `core.tie-device` | A `tie` link describes its coupling device | info |
| `core.terminal-node` | PV arrays, batteries, SPDs and earth electrodes feed nothing | warning |
| `core.normalized` | A near-miss value was read in its canonical form on load: `poles: 2` as `"2P"`, `cable.cores: 3` as `"3G"`, `"3G2.5"` as `"3G"` plus `section_mm2: 2.5`, a `[15, 45]` range as `"15-45"`, a view `type`/`single_line` as `kind`/`single-line`, `meta.description` as a note. Ambiguous values are not guessed: validation rejects them. `uniwire normalize` writes the canonical form | warning |
| `core.interlock` | Nodes and links sharing a `locks` key: no more members closed in normal operation than the interlock has `keys` (SPEC §4.1); a declared interlock is used by at least 2 members; an undeclared lock is not alone | error / warning |

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

Checks of a French low-voltage installation under NF C 15-100, which covers every kind of premises. The rules
of part 7-771 (dwellings) apply when `installation.premises` is `dwelling` or not set. For other premises
(`commercial`, `office`, `industrial`, `public`, `agricultural`, `other`) only the general rules apply: 30 mA
protection of socket-outlet and charging circuits (part 4-41, 411.3.3), EV charging (part 7-722) and
selectivity; the residential cable table becomes a warning to size the cable for its installation method
(part 5-52, guide UTE C 15-105). Rules marked *dwelling* below are skipped for other premises.

| Rule | Check | Level |
|---|---|---|
| `nfc15100.section` | Copper cross-section ↔ rating: 1.5 → 16 A, 2.5 → 20 A, 4 → 25 A, 6 → 32 A; outside dwellings, a warning to check the cable for its installation method | error (dwelling) / warning |
| `nfc15100.points` | *Dwelling*. Lighting: at most 8 points. Sockets: at most 8 on 1.5 mm², at most 12 on 2.5 mm² | error |
| `nfc15100.lighting-rating` | *Dwelling*. Lighting protected at 16 A at most | error |
| `nfc15100.rcd-30mA` | 30 mA protection for sockets and EV charging (all premises) and for every dwelling circuit | error |
| `nfc15100.rcd-type-A` | No type AC RCD for EV charging (all premises) and, in dwellings, for washing machine, dryer, hob / cooker | error |
| `nfc15100.rcd-count` | *Dwelling*. At least 2 30 mA RCDs per dwelling, including 1 type A | warning |
| `nfc15100.rcd-circuits` | *Dwelling*. At most 8 circuits per 30 mA RCD | error |
| `nfc15100.heating` | *Dwelling*. Heating power per circuit: 3.5 / 4.5 / 5.75 / 7.25 kW at 16 / 20 / 25 / 32 A | warning |
| `nfc15100.dedicated-circuit` | *Dwelling*. Dedicated circuits: washing machine, dishwasher, dryer, freezer, oven, hob, water heater, EV charging (one load per circuit), heating and shutters (circuit reserved for that use) | error |
| `nfc15100.ev-rcd` | EV charging: type B in three-phase mode 2 (error); in mode 3 with a type A or F RCD, reminder of 6 mA DC fault detection (info) | error / info |
| `nfc15100.selectivity` | Selective (type S) incoming RCD upstream of other RCDs | warning |

## `iec60364`: current-carrying capacity

One rule, `iec60364.iz`: the rating of the protective device feeding a cable (`ir_A`, otherwise
`fuse_A`, otherwise `in_A`) must not exceed the cable's current-carrying capacity Iz (multiplied by
`parallel`).

* Applies when the cable specifies `section_mm2`, `material`, `insulation` and `install`.
* Coverage: copper, PVC or XLPE (`PR` and `EPR` are treated as XLPE); installation methods `A1`, `A2`,
  `B1`, `B2`, `C`, `E`, `F` with 2 or 3 loaded conductors, 1.5 to 300 mm²; `D-duct` (buried in duct)
  for copper and aluminium. Combinations outside the table produce an `info`.
* Loaded conductors: 3 when the protective device is `3P`, `3P+N` or `4P`, otherwise 2; without poles,
  `installation.system` decides.
* Level: **warning**, never error. The tables (`src/uniwire/registry/data/iz_tables.json`, read with
  `uniwire.registry.iz_tables()`) are given at 40 °C ambient and are therefore conservative compared with
  IEC tables at 30 °C; no grouping or temperature correction factor is applied.

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
| `enedis.production` | Production and storage inverters (`p_kVA` × `count`: PV, hybrid and battery inverters; chargers, which only draw, are not counted): in single-phase, injection limited to 6 kVA (warning) and installed power to 18 kVA (error); in three-phase, 250 kVA. The installed power includes storage. Sources: Enedis-NMO-RAC_001E §3.2.1, Enedis-NMO-RES_032E §1.2.1.2 | error / warning |
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
