# uniwire

**Electrical diagrams, as code.** An open standard to describe electrical installations: single-line and
multi-line drawings, compliance checks, bills of materials and wire lists, from one file any tool can read.

uniwire is an open JSON exchange format for electrical installations, drawn as single-line and multi-line
diagrams, and a reference Python
library that validates documents, checks them against rule profiles (NF C 15-100, IEC 60364, PLC
consistency), produces bills of materials and draws SVG / PDF sheets. You describe the
**installation** (sources, protective devices, cables, loads) and uniwire computes the drawing.

* **Format**: `*.uniwire.json`, validated by a published [JSON Schema](https://uniwire.sh/schema/v1/uniwire.schema.json)
  (draft 2020-12). See the [specification](SPEC.md).
* **Library**: `pip install uniwire`, with the [Python API and CLI](api.md), [code-first API](build.md).
* **Licences**: code Apache-2.0, specification CC BY 4.0 ([details](license.md)).

## Install

```bash
pip install uniwire                 # validation, rules, SVG rendering, BOM
pip install "uniwire[pdf]"          # + PDF output (reportlab)
pip install "uniwire[iec81346]"     # + optional IEC 81346-2 class table (CC BY-SA 4.0 data package)
```

Python 3.10 or later is required.

## A document in 30 seconds

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
          { "type": "rcd", "ref": "-Q1", "in_A": 40, "idn_mA": 30, "rcd_type": "A", "children": [
            { "type": "breaker", "ref": "-Q11", "use": "C16", "cable": { "cores": "3G", "section_mm2": 1.5 },
              "children": [ { "type": "lighting", "label": "Lighting", "points": 6 } ] },
            { "type": "breaker", "ref": "-Q12", "in_A": 20, "curve": "C", "cable": { "cores": "3G", "section_mm2": 2.5 },
              "children": [ { "type": "socket", "label": "Sockets", "points": 8 } ] }
          ] }
      ] }
    ] }
  ]
}
```

```bash
uniwire validate house.uniwire.json          # schema + integrity
uniwire check house.uniwire.json             # rule profiles
uniwire render house.uniwire.json -f pdf     # out/house.pdf
```

## The same installation in Python

```python
from uniwire.build import *

with Installation("Small house", earthing="TT", system="1P+N", un="230 V", profiles=["nfc15100"]) as inst:
    with Grid("Utility"), MainBreaker("-Q0", "15-45 A", idn="500 mA", selective=True):
        with RCD("-Q1", "40 A", "30 mA", type="A"):
            Breaker("-Q11", "C16", cable="3G1,5") >> Lighting("Lighting", points=6)
            Breaker("-Q12", "C20", cable="3G2,5 18 m") >> Socket("Sockets", points=8)

for finding in inst.check():
    print(finding)
inst.save("house.uniwire.json")
inst.render("house.pdf")
```

See the [code-first API](build.md) for the full guide.

## Where next

* [Specification](SPEC.md): the format, field by field.
* [Python API and CLI](api.md): load, check, render, bill of materials.
* [Code-first API](build.md): schematics as Python code.
* [Rules](rules.md): the `core`, `nfc15100` and `iec60364` profiles and the PLC checks.
* [Examples](examples.md): complete documents and their drawings.
* [Contributing](contributing.md): development setup and the uniwire Enhancement Proposal process.
* Source code: <https://github.com/uniwire-dev/uniwire>
