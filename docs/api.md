# Python API and CLI

The `uniwire` package exposes a small functional API around the `Document` model, and a `uniwire`
command-line tool. To *write* documents in Python, see the [code-first API](build.md).

```bash
pip install uniwire            # add [pdf] for PDF output, [iec81346] for the IEC 81346-2 class table
```

## Loading and validating

```python
import uniwire

doc = uniwire.load("house.uniwire.json")      # path, pathlib.Path or an already-parsed dict
print(doc.meta.title, len(doc.sources))
```

`load()` parses the JSON, validates it against the model (closed types: unknown fields are errors),
applies `templates`, assigns missing identifiers and checks integrity (unique ids, existing link
endpoints, enclosure members). Units given as strings (`"16 A"`, `"2,5 mm²"`) are converted to the
canonical numeric fields.

On failure it raises `uniwire.UniwireError`, whose `issues` attribute lists every problem found:

```python
try:
    doc = uniwire.load({"sources": [{"type": "grid", "children": [{"type": "breaker", "calibre": 16}]}]})
except uniwire.UniwireError as e:
    for issue in e.issues:
        print(issue)          # ... unknown field (typo? use 'ext' for extensions)
```

`uniwire.dump(doc)` returns the resolved document as canonical JSON (templates applied, ids assigned,
numbers in the unit of each field).

## Checking rules

```python
findings = uniwire.check(doc)                          # core + the profiles listed in doc.profiles
findings = uniwire.check(doc, ["nfc15100", "iec60364"]) # core + explicit profiles
for f in findings:
    print(f.level, f.rule, f.node, f.message, f.source)
```

Each `Finding` has a `level` (`error`, `warning`, `info`), a stable `rule` id, the `node` id concerned, a
translated `message` and, for standard-based rules, the `source` it relies on. Rule metadata is available
in `uniwire.rules.RULE_INFO`. See [Rules](rules.md).

## Rendering

```python
paths = uniwire.render_svg(doc, "out/house", stem="house")   # list of SVG files, one per sheet
pdf = uniwire.render_pdf(doc, "out/house.pdf")               # one multi-page PDF (needs uniwire[pdf])
pages = uniwire.render_pages(doc)                            # in-memory pages (layout primitives)
```

Both functions accept an optional `view` (a `View` from `doc.views`); by default the first view, or a
default single-line view, is used. Large installations are split across sheets automatically
(`folio_split`), with cross-references between sheets and a title block on each.

The multi-line power diagram (one line per conductor, see SPEC §7.1) is a view of kind `multi-line`:

```python
from uniwire.render import default_view

view = default_view(doc, kind="multi-line")    # the document's multi-line view, or one derived from the first view
uniwire.render_svg(doc, "out/house-ml", stem="house-ml", view=view)
```

The language of the drawing (title block, table headings, type labels) follows `meta.lang` of the
document: `"en"` (default) or `"fr"`.

Colours: a view with `color` set (`conductors`, `phase`, `source`, `status`, `voltage`, SPEC §7) recolours
the strokes and adds a legend on each sheet, in SVG and PDF alike:

```python
view = default_view(doc, kind="multi-line").model_copy(update={"color": "conductors", "conductor_colors": "us"})
uniwire.render_svg(doc, "out/house-colour", view=view)
```

PDF output has one bookmark per sheet ("Sheet n: title") and every cross-sheet reference (off-page arrow,
"→ sheet n" label, busbar continuation, cross-sheet link end, incoming feed) is a link to its sheet.

## SVG structure

Each SVG sheet carries the meaning of what it draws, so a viewer or another tool can find the drawing of a
node, a link or a conductor without parsing geometry. Units are mm (`viewBox` = sheet size). Ids are those
of the document (`id` of nodes, `id` or index of links). The structure below is stable within format 1.x;
new classes / attributes may be added.

| Element | Class / attributes | What it holds |
|---|---|---|
| root `<svg>` | `data-uw-sheet="n"` (1-based position in the rendered set), `data-uw-view-kind="single-line"` or `"multi-line"` | one sheet |
| node | `<g class="sym sym-… uw-node" data-uw-id="ID">` (multi-line: `ml-sym …`); a board is its frame and name: `<g class="board uw-node" data-uw-id="ID">` | symbol of a node of the tree, of an auxiliary device (`devices`), of a device carried by a link (then also `data-uw-link="KEY"`, and `data-uw-id` only if the device has an `id`) |
| tree edge | `<g class="uw-edge" data-uw-edge="CHILD" data-uw-parent="PARENT">` | the conductor(s) feeding `CHILD` from its parent or from the busbar tap; multi-line: one sub-group per conductor (`data-uw-cond`) |
| busbar | `<g class="uw-busbar" data-uw-id="OWNER">`; multi-line: one per rail, with `data-uw-cond` | busbar of the node with several outgoing feeders (riser from its output included) |
| link | `<g class="uw-link" data-uw-link="KEY" data-uw-kind="KIND" data-uw-from="ID" data-uw-to="ID">` | drawn path(s), carried device, label, plus a last child `<g class="uw-hit" pointer-events="stroke">`: the same paths with `stroke="transparent"`, 3 mm wide, for easy hovering. `KEY` = link `id`, else its index in `links` |
| conductor | `data-uw-cond="L1"` (`L2`, `L3`, `N`, `PE`, `PEN`, `L+`, `L-`) on a small `<g>` (or on a pole group `class="pole"`) | multi-line only: one conductor segment, inside the edge / busbar / link / node it belongs to. With wire marking (SPEC §7.2), the conductor groups of the edge fed by a marked cable also carry `data-uw-mark="101"` (the mark, also written next to the line when there is room) |
| reference | `<g class="uw-ref" data-uw-target-sheet="n" data-uw-target-id="ID">` (`n` empty when unknown) | off-page arrow of a board drawn on its own sheet (and its "→ sheet n" schedule label), busbar continuation, cross-sheet link end, incoming feed of a detached board (target: the feeding node) |
| schedule column | `<g class="uw-cell" data-uw-id="ID">`, one `<g data-uw-field="FIELD">` per cell | feeder-table column of a leaf / feeder node |
| legend | `<g class="uw-legend">` | colour legend (colour modes) |

Other groups (`annotation`, `conductors`, `cartouche`, `title-block`, `notes`, `page`) carry no ids.
Selectors should use the classes (`.uw-node[data-uw-id="Q1"]`), as `data-uw-id` is also found on busbars
and schedule columns.

Each SVG embeds a small `<style>` so that, opened alone in a browser, hovering a node, edge, busbar or
link turns its strokes orange (`@media screen` only: printing is unchanged).

```python
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
svg = ET.parse("out/house/house.svg").getroot()
feeders = {g.get("data-uw-edge"): g.get("data-uw-parent") for g in svg.iter(NS + "g")
           if "uw-edge" in (g.get("class") or "").split()}
```

## Bill of materials and graph

```python
from uniwire.bom import bom, bom_csv
from uniwire.graph import to_graph

rows = bom(doc)        # [{"manufacturer", "part_number", "range", "description", "type", "quantity", "refs"}, ...]
csv_text = bom_csv(doc)
graph = to_graph(doc)  # {"components": [...], "connectivity_nodes": [...], "signals": [...]}
```

The bill of materials aggregates every node and PLC module that carries a `product` (or
`manufacturer` / `part_number`), including product accessories. The graph is the derived
terminal / connectivity-node form described in the [specification](SPEC.md) §8, with CIM / IFC / SCL
mappings.

## Wire marks and wiring exports

The conductors of the cables of the power tree, with their marks (SPEC §7.2, subset of UEP-0001):

```python
from uniwire.marks import marked_wires, freeze
from uniwire.exports import wires_csv, markers_csv, cables_csv

view = default_view(doc, "marks")                 # a view with "wire_marking"
for w in marked_wires(doc, view):                 # numbering order
    print(w.id, w.mark, w.from_display, w.to_display, w.cable_ref)   # M1.cable.L1 101 -KM1 -M1 W11
csv_text = wires_csv(doc, view)                   # also markers_csv(doc, view), cables_csv(doc)
```

`marked_wires(doc)` without a view gives the manual marks (`cable.marks`) only. `freeze(data, doc, wires)` writes
the marks into the `cable.marks` of the parsed JSON `data` (what `uniwire marks --write` does).

## Registry

```python
from uniwire import registry

registry.label("rcd", "fr")          # 'Interrupteur différentiel' (type label in a given language)
registry.category("breaker")         # 'protection'
registry.iec81346_class("breaker")   # 'QAB'
registry.iec81346_table()            # full IEC 81346-2 table if uniwire[iec81346] is installed, else {}
```

## Command line

| Command | Purpose |
|---|---|
| `uniwire validate FILE...` | Validate one or more documents (schema + integrity) |
| `uniwire check FILE... [--profile P]` | Validate, then apply the rule profiles; exit code 1 if any error |
| `uniwire render FILE [-f svg\|pdf] [-o OUT] [--view ID] [--kind single-line\|multi-line]` | Draw the sheets (SVG directory by default, `out/<name>/`). `--view` picks a view by id; `--kind multi-line` draws the multi-line power diagram even if the document declares no such view (files named `<name>-multiline`) |
| `uniwire schema [-o FILE]` | Write the JSON Schema |
| `uniwire graph FILE` | Print the derived terminal / connectivity-node graph (JSON) |
| `uniwire bom FILE [-o FILE]` | Bill of materials as CSV (semicolon-separated) |
| `uniwire wires FILE [--view ID] [-o FILE]` | Wire list as CSV: one row per conductor of the cables of the power tree, with its mark (`--all` accepted: in the current format every wire is an implicit power connection) |
| `uniwire markers FILE [--view ID] [-o FILE]` | Wire marker list as CSV (one row per end of a marked wire, `quantity`) |
| `uniwire cables FILE [-o FILE]` | Cable schedule as CSV |
| `uniwire marks FILE [--view ID] [--write] [-o FILE]` | Print the wire marks of a view; `--write` freezes them into the cables' `marks` (in place, or into `-o FILE`; the JSON is rewritten with 2-space indentation) |
| `uniwire symbols [-o FILE]` | SVG sheet of all symbols |
| `uniwire normalize FILE` | Print the resolved document (templates applied, ids assigned, canonical units) |

```bash
uniwire validate examples/*.uniwire.json
uniwire check house.uniwire.json --profile iec60364
uniwire render house.uniwire.json -f pdf -o house.pdf
uniwire render house.uniwire.json --kind multi-line      # multi-line power diagram
uniwire bom house.uniwire.json -o house.bom.csv
uniwire markers mcc.uniwire.json --view marks -o mcc.markers.csv   # ferrules for a marker printer
uniwire marks mcc.uniwire.json --view marks --write              # freeze the generated marks
```

CLI output, validation errors and rule findings follow the `UNIWIRE_LANG` environment variable
(`en` by default, `fr` available):

```bash
UNIWIRE_LANG=fr uniwire check house.uniwire.json
```
