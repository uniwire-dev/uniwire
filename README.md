# uniwire

**Electrical diagrams, as code.**

An open standard to describe electrical installations, and the reference Python library that validates
them, checks them against rules and draws their single-line and multi-line diagrams.

[![CI](https://img.shields.io/github/actions/workflow/status/uniwire-dev/uniwire/ci.yml?branch=main&label=CI)](https://github.com/uniwire-dev/uniwire/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/uniwire)](https://pypi.org/project/uniwire/)
[![Python](https://img.shields.io/pypi/pyversions/uniwire)](https://pypi.org/project/uniwire/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/uniwire-dev/uniwire/blob/main/LICENSE)

You describe the **installation** (sources, protective devices, cables, loads, PLCs) in a `*.uniwire.json`
file or in Python, and uniwire computes the drawings. No coordinates, no CAD file: a text file you can
review and diff.

* **Format**: `*.uniwire.json`, format 1.0, defined by the [specification](https://uniwire.sh/docs/SPEC/)
  and validated by a published JSON Schema: <https://uniwire.sh/schema/v1/uniwire.schema.json>.
* **Library**: `pip install uniwire`: Python API, code-first builder and the `uniwire` command line.
* **Documentation**: <https://uniwire.sh/docs/>
* **Web viewer**: <https://uniwire.sh/viewer/>, paste a document to validate, check and draw it in the browser.

## Features

* **Single-line and multi-line diagrams** from the same document: the multi-line view derives every
  conductor (L1, L2, L3, N, PE, PEN) from the single-line data, with no extra input.
* **53 node types**: utility grid, transformers, generators, UPS, PV, batteries, inverters; breakers,
  RCDs, RCBOs, fuses, switch-disconnectors, contactors, motor starters, transfer switches, SPDs,
  protection relays, instrument transformers, insulation monitors; busbars, boards, terminal blocks;
  lighting, sockets, heating, motors, EV chargers, modular PLCs and more.
* **Tree + links**: the power tree is the backbone; transfers, bus ties, infeeds, earthing, control,
  interlocks, trips, measurements and data buses are links. A terminal / connectivity-node graph is
  derived automatically, with CIM, IFC and IEC 61850 SCL mappings.
* **Closed typing and unit-suffixed fields**: `in_A`, `idn_mA`, `section_mm2`, `p_kW`; unknown fields are
  errors (`calibre` instead of `in_A` is caught), extensions live in `ext`. Templates declare a device once.
* **Rule profiles**: `core` (always), `nfc15100` (French dwellings), `iec60364` (cable current-carrying
  capacity), `enedis` (connection to the French public network), plus PLC consistency checks.
* **Bill of materials**: structured `product` references (manufacturer, part number, range, accessories)
  on any node or PLC module, aggregated to CSV (`uniwire bom`).
* **Wire and cable marking**: marking rules per view (manual, sequential, per potential, pattern), marks
  drawn on the multi-line diagram, and CSV exports: wire list (`uniwire wires`), wire marker list
  (`uniwire markers`), cable schedule (`uniwire cables`); `uniwire marks --write` freezes the marks.
* **Colour modes**: conductors in their IEC 60445 or North-American colours, or colouring by phase,
  source, status or voltage level.
* **Sheets**: paper size, sub-tree views, automatic sheet splitting with cross-references, circuit schedule,
  enclosure frames, title block, revisions and notes. **SVG** output is deterministic and diff-friendly;
  the multi-sheet **PDF** has clickable links between sheets.
* **Drawings in English, French, German, Spanish, Russian and Simplified Chinese**, selected per document with
  `meta.lang`.
* **LLM tooling**: a reference card generated from the model (`uniwire card`), a text outline with
  stable ids (`uniwire describe`), id-based edits (`uniwire patch`), an MCP server (`uniwire-mcp`, stdio)
  and a hosted MCP endpoint at <https://mcp.uniwire.sh/mcp>, plus
  [llms.txt](https://uniwire.sh/llms.txt) for assistants (full reference card
  included). Setup for ChatGPT, Claude, Cursor and VS Code:
  [uniwire in your assistant](https://uniwire.sh/docs/assistants/); details in
  [LLM tools](https://uniwire.sh/docs/llm/).

## Gallery

<table>
<tr>
<td width="50%"><a href="https://github.com/uniwire-dev/uniwire/blob/main/examples/02_house_3_bedrooms_tt.uniwire.json"><img src="https://github.com/uniwire-dev/uniwire/raw/main/docs/gallery/02_house_3_bedrooms_tt.png" alt="French house, TT, single-line diagram"></a><br><sub>French house, TT (NF C 15-100), single-line</sub></td>
<td width="50%"><a href="https://github.com/uniwire-dev/uniwire/blob/main/examples/06_german_single_family_house.uniwire.json"><img src="https://github.com/uniwire-dev/uniwire/raw/main/docs/gallery/06_german_single_family_house.png" alt="German house, TN-C-S, multi-line diagram in conductor colours"></a><br><sub>German house, TN-C-S, multi-line in conductor colours</sub></td>
</tr>
<tr>
<td width="50%"><a href="https://github.com/uniwire-dev/uniwire/blob/main/examples/18_office_building_main_lv_switchboard.uniwire.json"><img src="https://github.com/uniwire-dev/uniwire/raw/main/docs/gallery/18_office_building_main_lv_switchboard.png" alt="Office building main LV switchboard"></a><br><sub>Office building, main LV switchboard</sub></td>
<td width="50%"><a href="https://github.com/uniwire-dev/uniwire/blob/main/examples/25_poste_hta_bt_1000kva.uniwire.json"><img src="https://github.com/uniwire-dev/uniwire/raw/main/docs/gallery/25_poste_hta_bt_1000kva.png" alt="MV/LV substation, 1000 kVA"></a><br><sub>MV/LV substation, 1000 kVA</sub></td>
</tr>
<tr>
<td width="50%"><a href="https://github.com/uniwire-dev/uniwire/blob/main/examples/27_standby_generator_ats_load_shedding.uniwire.json"><img src="https://github.com/uniwire-dev/uniwire/raw/main/docs/gallery/27_standby_generator_ats_load_shedding.png" alt="Standby generator, automatic transfer switch, load shedding"></a><br><sub>Standby generator, ATS, load shedding</sub></td>
<td width="50%"><a href="https://github.com/uniwire-dev/uniwire/blob/main/examples/24_factory_mcc_motor_starters.uniwire.json"><img src="https://github.com/uniwire-dev/uniwire/raw/main/docs/gallery/24_factory_mcc_motor_starters.png" alt="Motor control centre, multi-line diagram with wire marks"></a><br><sub>Motor control centre, multi-line with wire marks</sub></td>
</tr>
</table>

All 53 examples are in [examples/](https://github.com/uniwire-dev/uniwire/tree/main/examples) and listed in the
[documentation](https://uniwire.sh/docs/examples/); open any of them in the [web viewer](https://uniwire.sh/viewer/).

## Install

```bash
pip install uniwire                 # validation, rules, SVG rendering, bill of materials, exports
pip install "uniwire[pdf]"          # + PDF output (reportlab)
pip install "uniwire[mcp]"          # + MCP server (uniwire-mcp)
pip install "uniwire[iec81346]"     # + optional IEC 81346-2 class table (separate CC BY-SA 4.0 data package)
```

Python 3.10 or later. The only required dependency is pydantic.

## Quickstart

A document in JSON:

```json
{
  "$schema": "https://uniwire.sh/schema/v1/uniwire.schema.json",
  "uniwire": "1.0.0",
  "profiles": ["nfc15100"],
  "meta": { "title": "Small house", "lang": "en" },
  "installation": { "earthing": "TT", "system": "1P+N", "un_V": 230 },
  "templates": { "C16": { "type": "breaker", "in_A": 16, "curve": "C" } },
  "sources": [
    { "type": "grid", "label": "Utility", "children": [
      { "type": "main_breaker", "ref": "-Q0", "range_A": "15-45", "in_A": 45, "idn_mA": 500, "selective": true,
        "children": [
          { "type": "rcd", "ref": "-Q1", "in_A": 40, "idn_mA": 30, "rcd_type": "AC", "children": [
            { "type": "breaker", "ref": "-Q11", "use": "C16", "cable": { "cores": "3G", "section_mm2": 1.5 },
              "children": [ { "type": "lighting", "label": "Lighting", "points": 6 } ] }
          ] },
          { "type": "rcd", "ref": "-Q2", "in_A": 40, "idn_mA": 30, "rcd_type": "A", "children": [
            { "type": "breaker", "ref": "-Q21", "in_A": 20, "curve": "C", "cable": { "cores": "3G", "section_mm2": 2.5 },
              "children": [ { "type": "socket", "label": "Sockets", "points": 8 } ] }
          ] }
      ] }
    ] }
  ]
}
```

The tree is the power flow (source, protective devices, loads); whatever falls outside the tree
(transfer switches, bus ties, control and data connections) goes in `links`.

```bash
uniwire validate house.uniwire.json                 # schema + integrity
uniwire check house.uniwire.json                    # rule profiles (exit code 1 on errors)
uniwire render house.uniwire.json                   # SVG sheets in out/house/
uniwire render house.uniwire.json -f pdf -o house.pdf
uniwire render house.uniwire.json --kind multi-line # multi-line power diagram
uniwire bom house.uniwire.json -o house.bom.csv     # bill of materials
uniwire wires house.uniwire.json                    # wire list (also: markers, cables, marks)
uniwire card                                        # reference card for assistants
```

The same installation in Python:

```python
from uniwire.build import *

with Installation("Small house", earthing="TT", system="1P+N", un="230 V", profiles=["nfc15100"]) as inst:
    with Grid("Utility"), MainBreaker("-Q0", "15-45 A", idn="500 mA", selective=True):
        with RCD("-Q1", "40 A", "30 mA", type="AC"):
            Breaker("-Q11", "C16", cable="3G1,5") >> Lighting("Lighting", points=6)
        with RCD("-Q2", "40 A", "30 mA", type="A"):
            Breaker("-Q21", "C20", cable="3G2,5 18 m") >> Socket("Sockets", points=8)

for finding in inst.check():
    print(finding)
inst.save("house.uniwire.json")
inst.render("house.pdf")
```

`with` makes an element the parent of everything created inside it, `>>` chains elements, ratings and
cables are written the way they appear on drawings (`"C16"`, `"3G2,5 18 m"`). See the
[code-first API](https://uniwire.sh/docs/build/) and the [Python API and CLI](https://uniwire.sh/docs/api/).

## Roadmap

* **Terminals, terminal strips and wires**: [UEP-0001](https://uniwire.sh/docs/uep/0001-terminals-and-wires/),
  a draft for format 2.0 (named ports, terminal strips, wires and cables as objects, potentials).
* **Control schematics**: coils, auxiliary contacts with cross-references, terminal plans and wire numbers,
  built on named ports.
* **Exports**: DXF drawings, pandapower networks for load-flow and short-circuit studies.

Ideas and format proposals are welcome: see
[CONTRIBUTING.md](https://github.com/uniwire-dev/uniwire/blob/main/CONTRIBUTING.md).

## Contributing

Bug reports, examples, rules, symbols and translations are welcome. Read
[CONTRIBUTING.md](https://github.com/uniwire-dev/uniwire/blob/main/CONTRIBUTING.md) (development setup, tests,
uniwire Enhancement Proposals) and the
[Code of Conduct](https://github.com/uniwire-dev/uniwire/blob/main/CODE_OF_CONDUCT.md). Report security issues
privately, see [SECURITY.md](https://github.com/uniwire-dev/uniwire/blob/main/SECURITY.md).

## Licences

* Code, CLI and JSON Schema: [Apache License 2.0](https://github.com/uniwire-dev/uniwire/blob/main/LICENSE).
* Specification text: [CC BY 4.0](https://github.com/uniwire-dev/uniwire/blob/main/docs/LICENSE-SPEC.md):
  implement it freely, in any software.
* Optional data package `uniwire-data-iec81346` (IEC 81346-2 class table): CC BY-SA 4.0, distributed
  separately (`pip install "uniwire[iec81346]"`).

See [NOTICE](https://github.com/uniwire-dev/uniwire/blob/main/NOTICE) for third-party notices.
