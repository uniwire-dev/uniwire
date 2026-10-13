# Changelog

All notable changes to the uniwire format and to the `uniwire` Python library are documented here.
The format and the library are versioned separately: the format follows `1.y.z` (see
[SPEC §9](https://uniwire.sh/docs/SPEC/#9-extensibility-and-versions)), the library follows its own semantic
version.

## 0.1.1

* `nfc15100` profile: the rules of dwellings (part 7-771) apply only when `installation.premises` is `dwelling`
  or not set. For other premises the profile keeps the general rules (30 mA on socket-outlet and charging
  circuits, EV charging, selectivity) and the residential cable table becomes a warning to size the cable for
  its installation method (part 5-52, guide UTE C 15-105). The `scope` of `check` results says which rules applied.
* Symbols redrawn to follow the international drawing conventions: socket outlet with protective contact, inverter
  with direct current top left, junction box as a circle with a dot, motor starter, variable-speed drive as a
  frequency converter, protective earthing on earth bars, "IΔ" on residual-current devices, "V" on voltmeters,
  photovoltaic generator, water heater. Converters draw direct current as a full line over a dashed one; UPS
  symbols carry the "UPS" label.
* The MCP server announces its website and icon to clients.
* Hosted MCP server: the tools that return links (validate, check, apply_patch, render, viewer_link) are annotated
  as publishing (not read-only, open world) when the server keeps documents for short links (`--store`).
* Hosted MCP server: `pdf_url` is a plain PDF link (`GET /pdf/<id>`, drawn on the server and named after the
  document title) instead of an editor link that downloads the PDF; `--pdf-base` sets its prefix.
* Web editor: files downloaded from a shared link are named after the document title instead of "shared".
* PDF: the document title is the PDF title (shown by PDF readers and browser tabs), instead of the first sheet's.

## 0.1.0 (format 1.0)

First release of the uniwire format and of the `uniwire` Python library (Apache-2.0; specification text under
CC BY 4.0).

* Format 1.0: `*.uniwire.json` documents describing an installation as a power tree (sources, devices, loads)
  plus `links` for everything outside the tree; typed nodes (53 types), templates, views; published JSON
  Schema at <https://uniwire.sh/schema/v1/uniwire.schema.json>
  ([specification](https://uniwire.sh/docs/SPEC/)).
* Node types for utility supplies, MV/LV transformers, generators, UPS, PV, batteries, inverters, protective
  and switching devices, instrument transformers, protection relays, insulation monitors, busbars, boards,
  terminal blocks, loads, modular PLCs (ordered modules, roles, protocols, channel ports) and power supplies.
* Common node fields (`count`, `circuit`, `un_V`, `ib_A`, `normal_state`, `locks`...), auxiliary devices outside
  the tree (`devices[]`), addressable enclosures (`enclosures[]`), key interlocks (`interlocks[]`, `locks[]` on
  nodes and links).
* Link kinds `transfer`, `tie`, `bypass`, `parallel`, `infeed`, `earth`, `control`, `interlock`, `trip`,
  `measure`, `data` and `key`, with optional cable, device and terminal / channel ports.
* Structured `product` references on every node and PLC module; bill of materials as CSV (`uniwire bom`).
* Validation with explicit messages (unknown fields, wrong units, broken references); any `1.y.z` document is
  accepted.
* Rule profiles: `core`, `nfc15100` (French dwellings), `iec60364` (cable current-carrying capacity from the
  GUIA-BT-19 tables), PLC consistency checks, interlock check.
* Single-line diagrams: automatic layout, automatic sheet splitting with cross-references, circuit schedule,
  enclosure frames, title block, revisions and notes, top-down or bottom-up drawings.
* Multi-line power diagrams derived from the same document: one line per conductor (L1, L2, L3, N, PE / PEN),
  one contact per pole, RCD toroids, PEN split, transformer windings, motors, busbars as one rail per
  conductor; `uniwire render --kind multi-line` for any document.
* Colour modes per view: conductors (IEC 60445 or North-American colours), phase, source, status or voltage
  level, with palette overrides and a legend.
* Wire marking (the part of [UEP-0001](https://uniwire.sh/docs/uep/0001-terminals-and-wires/) that format 1.0
  can carry): marking rules per view, manual marks in `cable.marks`, cable tags on the drawings; CSV exports
  `uniwire wires`, `uniwire markers`, `uniwire cables`, and `uniwire marks [--write]`.
* SVG output with a documented structure contract
  ([Python API](https://uniwire.sh/docs/api/#svg-structure)); multi-sheet PDF with bookmarks and clickable
  cross-sheet references.
* English and French rendering (`meta.lang`); CLI messages follow `UNIWIRE_LANG`.
* Code-first API `uniwire.build`: installations as Python code
  ([guide](https://uniwire.sh/docs/build/)).
* Command line `uniwire`: `validate`, `check`, `render`, `bom`, `wires`, `markers`, `cables`, `marks`,
  `graph`, `normalize`, `schema`, `symbols`, `card`, `describe`, `patch`, `link`, `--version`.
* Terminal / connectivity-node graph derived from the document, with CIM, IFC and IEC 61850 SCL mappings.
* Tolerant reading of unambiguous near-miss values (`poles: 2`, `cores: "3G2.5"`, `range_A: [15, 45]`...), each
  reported by the rule `core.normalized`; `installation.premises` scopes dwelling-only rules.
* LLM tools ([guide](https://uniwire.sh/docs/llm/)): reference card generated from the model (`uniwire card`),
  text outline with stable ids (`uniwire describe`), id-based edits (`uniwire patch`), flat node table, links that
  open a document in the web editor (`uniwire link`, `viewer_url` in the MCP tool results).
* MCP server `uniwire-mcp` (extra `uniwire[mcp]`): stdio and HTTP transports, tools to validate, check,
  describe, patch, render and export documents, bundled examples; a public mode with bounded inputs,
  worker processes and timeouts, short editor links (`--store`) and a usage log without caller addresses,
  used by the hosted endpoint <https://mcp.uniwire.sh/mcp>; every tool has a title and read-only annotations;
  check results state their scope (automatic checks, not a conformity certificate).
  Setup for ChatGPT, Claude, Cursor and VS Code: [uniwire in your assistant](https://uniwire.sh/docs/assistants/).
* LLM evaluation tasks with a runner that makes no network calls
  ([evals/llm](https://github.com/uniwire-dev/uniwire/tree/main/evals/llm)).
* Hardened parsing: bounded quantity and reference parsers, nesting limit, CSV formula neutralisation,
  XML-safe SVG, PDF and CSV output.
* 52 example documents ([examples](https://github.com/uniwire-dev/uniwire/tree/main/examples)): dwellings,
  commercial and industrial boards, MV/LV substations, standby sources, PV, EV charging, UPS, PLCs.
* Optional IEC 81346-2 class table in the separate data package `uniwire-data-iec81346` (CC BY-SA 4.0),
  `pip install "uniwire[iec81346]"`.
* Draft proposal [UEP-0001 "Terminals, terminal strips and wires"](https://uniwire.sh/docs/uep/0001-terminals-and-wires/)
  for format 2.0.
