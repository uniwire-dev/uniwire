# Changelog

All notable changes to the uniwire format and to the `uniwire` Python library are documented here.
The format and the library are versioned separately: the format follows `1.y.z` (see
[SPEC §9](https://uniwire.sh/docs/SPEC/#9-extensibility-and-versions)), the library follows its own semantic
version. Before the library's 1.0, a `0.x.y` release adds features and fixes that keep existing documents and
code working, and a `0.x.0` release may break compatibility (described here, with what to change).

## Unreleased

* Docs: uniwire is in ChatGPT's plugin directory ([uniwire in ChatGPT](https://chatgpt.com/plugins/plugin_asdk_app_6ace27d31ab08191b243ec37826969c2)); the hosted server's
  logging is described as it is (the request and the caller's address in the security logs, one year).
* Rules, iec60364: the current-carrying capacity of a cable is no longer compared with a protection on the other side
  of a converter (the AC breaker of an inverter against the DC cables of its strings).
* Documents with unambiguous mistakes are read instead of refused, each fix reported by `core.normalized`: a number
  written for a text (`"range_A": 10` read as `"10"`), and in an object, a single unknown field beside a single
  missing required one, read under the missing name (`{"rev": "A"}` in `meta.revisions` read as `{"index": "A"}`).
* An unknown field is reported with the fields that can be written at that place, and the required ones missing.
* Faster start: the node models are no longer built one by one on import (`import uniwire` and each command
  start about four times faster).
* Multi-line drawings: the device carried by a link is drawn on the verticals of the link when its horizontal run is
  too short for it (before, it was left out); a link to a load reaches the load's terminals instead of passing
  below it; a bypass parallels the live conductors, never the PE; a link leaving a conductor that goes on is marked
  with a junction dot.
* Multi-line drawings: an odd `x` core count (`"3x"`) is taken to include the PE only as a guess, after what the node
  states (a motor's `phases`), and never when the PE has its own section (`"3x"`, 95 mm², `pe_section_mm2` 50: three
  phases and a PE); a three-phase motor is no longer drawn on two phases.
* Drawings: the unit of a setting range is written only after numbers (`9-13 A`); a range given in words
  (`"to confirm"`) is shown as written.

## 0.1.6 (2026-10-30)

* Drawings: long texts are fitted in time proportional to their length (wrapping on several lines, cutting with an
  ellipsis, title block cells); drawings of usual documents are unchanged.
* MCP server, public mode: every tool result is bounded (30,000,000 characters of JSON, `normalize` 4,000,000),
  checked in the worker process.
* MCP server, short links: ids derive from the content and a secret key of the store (`DIR/.key`), so that the link
  of a document cannot be worked out from its text; existing links keep working. Only diagrams are stored, the size
  of the store is checked at each write, `/pdf` and `/svg` drawings are cached in memory, a deletion sent by a page
  of another site is refused, and the error page of a PDF link no longer quotes the document.
* `uniwire-mcp --http` warns when it listens on another address than loopback without `--public`.
* Web editor on uniwire.sh: each PDF export adds one to an hourly total kept by the site (nothing else is sent).
* Web editor: a document that takes more than a minute to draw stops the engine, which starts again, instead of
  leaving the page waiting; it is drawn again once edited.

## 0.1.5 (2026-10-30)

* Translations reviewed in every language: wrong meanings fixed (German "converter", Chinese and other languages on
  RCD selectivity, which now says to use a selective type S device, the French messages of the vde0100 profile on
  charging points), trade terms made consistent within each language (one term per device), labels shortened to fit
  their cells, Portuguese made consistently Brazilian (NBR 5410 vocabulary), Russian number agreement and no dash.
  The page "About this document" no longer names the button of the web page, which is in English and French only.
  `--lang` lists the ten languages. Web editor: the PDF error message names the current menu entry.
* Drawings: a load power below 1 kW is written in watts (`16.2 W`, `500 W`), from 1 kW in kilowatts; small DC loads
  no longer round to `0.016 kW`.
* Drawings: a DC converter shows its output voltage (`un_V`) and its current (`in_A`).
* Drawings: the text beside a device stops before the symbol on its right, however wide it is (converters side by
  side no longer touch the next one).
* Checks: a battery at the root of `sources`, the only source of a DC system (vehicle, boat, off-grid site), may
  feed the installation: no `core.terminal-node` warning.
* Checks: `core.no-cables` (info) when a profile that checks cables is active but no circuit gives its cable size,
  so that an empty result is not read as cables checked.
* Drawings: a link label with no clear place on one line (a short link) goes on two lines, clear of the symbols;
  a wrapped line no longer starts with a separator (a dash, `/`, `:`).
* Drawings: a device text that repeats its label in another case (`Type 2` under `… type 2`) is not repeated.
* Reference card for assistants: socket-outlets are entered as `socket` nodes even on a shared circuit (so the RCD
  rules see them), and a feeder continued elsewhere ends on an `offpage` node, not a `spare`.
* Drawings, dense control circuits (many auxiliary devices and links, several of them reaching one controller):
  * a controller reached by three links or more is drawn taller, with one point per link on its sides (on the right
    for the devices to its right), in the order of the other ends: its links no longer share one route;
  * its links to other sheets end on stubs along its side, and its column leaves room on its left for their texts;
  * each auxiliary device is placed with room for its link labels on the side facing its partner, and a label goes
    near the end of its link where fewer links meet;
  * a link label with no clear place near either end goes in the nearest free space, joined to its link by a thin
    leader, instead of over a symbol or another text;
  * the text of the last device of a row, with nothing drawn to its right, is no longer reduced or cut to fit its
    column.
* Drawings: an AWG size is no longer dropped when the composition holds the same digit (`6G` with `#6` gives
  `5-#6+G`, not `6G`).
* Drawings, multi-line view: a characteristic the label already gives (`25 kVA` in `25 kVA unit`) is not repeated.
* Drawings, multi-line view, the same for a controller many links reach: its box grows with its links, one point
  each a lane apart, its column leaves room on its left for their labels and stubs (no longer written across the
  conductors of the next feeders), and no auxiliary device is put in that room.
* Drawings: the texts of an off-page stub end before the point of its arrow.
* Drawings, sheets: a board wider than a sheet below another board goes to sheets of its own, so that the board
  feeding it keeps its ways together on one sheet (a main board of four ways feeding two large boards was cut way
  by way over three sheets).
* Drawings: the texts at the ends of a busbar continued on another sheet ('continued from', 'continued on') are
  placed clear of each other and of the name of the board: beyond the end of the busbar, or below it, when the
  space above is taken.
* Checks, `iec60364.iz` and `iec60364.iz-estimate`: Iz now follows IEC 60364-5-52, as formulas `a * S^m` that never
  give more than its values (`registry/data/iz_iec60364.json`, `uniwire.registry.iz_iec60364()`), instead of the
  Spanish GUIA-BT-19 tables at 40 °C. Aluminium in air, PVC in the ground and method `D2` (buried directly) are now
  covered. The ambient temperature corrects Iz at any value from 10 °C to 60 °C (PVC) or 80 °C (XLPE), by the
  heating of the conductor, instead of two steps at 30 and 40 °C. In the ground, without `ambient_C`, 20 °C and
  2.5 K·m/W, the IEC reference (the Spanish tables took 25 °C and 1.5 K·m/W). `registry.iz_tables()` still reads the
  Spanish tables, no longer used by the rules.
* Tests: the readability audit also counts texts written over a symbol, texts crossed by a link, link texts written
  across a conductor, texts reduced to fit, and two texts run into each other over a few letters however small their
  overlap; a set of dense documents (`tests/dense_docs.py`) holds the layout to these counts.
* Drawings: a device text too wide for its room (a surge protector beside a feeder) goes on more lines at its usual
  size before it is reduced; it is reduced only when no split fits.
* MCP server (`--http`): a PDF link opened in a browser that cannot be served (expired, deleted by a link holder,
  or a document that cannot be drawn) shows a short page in the browser's language saying what happened and to ask
  the assistant again, instead of a line of English text. Scripts and assistants still get the plain text.
* Format 1.1: a cable may give the conditions that lower its current-carrying capacity: `grouped` (circuits or
  multicore cables laid together), `arrangement` (how they lie in air), `supports` (stacked trays or ladders),
  `spacing_m` (between circuits in the ground), `soil_resistivity_K_m_W` and `third_harmonic_pct`. A 1.0 document
  is a valid 1.1 document.
* Checks: `iec60364.iz` and `iec60364.iz-estimate` apply the grouping, soil resistivity and third-harmonic factors
  of these fields, as formulas never above the factors of IEC 60364-5-52 (`registry.iz_iec60364()["factors"]`); the
  message lists them. Beyond their range (more than 20 circuits in air, 6 in the ground, a soil above
  3 K·m/W, harmonics above 50 %), Iz is not checked (`info`).

## 0.1.4 (2026-10-28)

* PDF: a page "About this document" may follow the sheets. It is not a sheet of the diagram (no folio number): the
  rule profiles applied and the number of findings, the scope of automatic checks, where the online copy is and how
  to delete it, and how to write to the uniwire team, with a QR code. Every address on it is a link. In the 10
  languages of the drawings. The hosted server adds it to `GET /pdf/<id>` (`?about=0` leaves it out), the web
  editor offers it with a box in the Download menu (remembered by the browser), and the command line with
  `uniwire render -f pdf --about` (`--doc-id` names the online copy); `render_pdf(..., about=About(...))`.
* PDF and SVG: web addresses can be links (groups of class `uw-href`); the drawings can hold filled outlines
  (`Path`, used for the logo).
* Web editor: a short link whose document was deleted says so.

## 0.1.3 (2026-10-28)

This release also ships the changes of 0.1.2, which was not published on its own (see below).

* Cable texts: a protective conductor run beside the cores (`pe_section_mm2` with a composition such as `4x`) is
  written with them, `4x25+PE16`, in the drawings, the feeder tables, the bill of materials and the cable lists; it
  was left out, so that a cable with its own PE read as a cable without one.
* Hosted MCP server (`--store`): whoever holds a short link can delete its document before it expires
  (`POST /doc/<id>/delete`, never a GET, so that link checkers cannot delete anything). The links of a deleted
  document answer 410 instead of 404, so that the web editor and the PDF link can say it was deleted; storing the
  same document again (a new request from an assistant) makes it available again.

* Multi-line view: the auxiliary devices (`devices`) and the control, interlock, trip, measure, data, key and earth
  links are drawn, placed and routed as in the single-line view (beside the node they are linked to, clear of the
  conductor bundles and the symbols), with a band above the feeder cables for their channels; a PLC is drawn with
  its modules, its links leaving from the module they use (port label); a link whose other end is on another sheet
  ends on a sheet reference.

* Multi-line view fixes: an earth or equipotential bar in a board is on the PE only (it took every conductor), drawn
  with its symbol; a single-phase transformer has a single-phase secondary (two unearthed conductors at 50 V or
  less); a power link from a source with a PEN feeds the neutral of a target with N and PE (the genset neutral of a
  4-pole changeover was missing); a current transformer is a ring on each phase, a connector a socket and plug on
  each conductor (no box repeating the tag); a mechanical interlock carries its triangle (it was missing in PDFs),
  between the delta and star contactors of a star-delta starter too. Split-phase (120/240 V): a "2P" breaker
  switches L1 and L2, the neutral going straight through, and a 240 V motor takes L1 L2 (L2 was lost). The PEN
  splits into N and PE at the entry of a board declared TN-S or TN-C-S (residual-current devices took the PEN). A
  genset of a TN-C-S installation has its own N and PE (its 4-pole breaker was drawn with 3 poles). An inverter or
  UPS at the head of the tree takes its AC input on top (it landed on its backup outputs). A power link carries the
  PE of its cable (solid, never drawn open) and its label, runs below the bars of a sub-board beside its source, and
  reaches the outputs of the last device of a board from its right (it wound round the device). An equipped spare
  way is its grey device with its rating, not a load fed straight from the bars. A control link leaves the operating
  line of a contactor by turning down at once, never as its continuation. A drive fed in single phase delivers the
  three phases of its three-phase motor (U V W, it delivered one phase and the neutral); a DC motor is marked "=";
  the PE passes beside a transformer to its earthed secondary side, or ends on the earthed enclosure when no PE
  leaves it (it ran into the windings); the cable of a feeder is no longer written on the run behind a drive or
  converter; the conductors of a power link stay solid when its device shows the normally open contacts.

* Single-line view, feeds between trees: a tree that only adds a supply to another one (a genset, a charger, a
  storage converter whose `infeed` lands on a busbar of that tree) is drawn beside it, whatever its place in
  `sources`; a link between two trees with a third tree between them is drawn as an interrupted line, a stub at
  each end naming the other end, instead of a run across the sheet; several feeds landing on one busbar each get
  their own tap on top of it, routed on separate channels without crossing (the second one ended on a stub of
  conductor that did not exist), the board frame enclosing the taps.

* Single-line view, sheets: several trees too wide for one sheet are cut into groups of whole trees that each fit
  (the fewest sheets, then the fewest links between them, each ending on an off-page reference), before any board
  is taken to its own sheet; such a sheet no longer shows an incoming feed, and a bus tie between two sheets ends on
  an off-page reference at each end (it was not drawn). The board taken to its own sheet is the smallest one that
  makes the sheet fit (it was the widest: a first sheet could hold only the incomer, the next one only the main
  board), and a main board as wide as the whole sheet stays with its supply, its busbar going on over the next
  sheets under the board's name (the first sheet held only the supply; the continuation was named after the device
  at the head of the busbar, a meter for instance). The output of a power supply with nothing drawn below is marked with its two poles
  (it was marked with its input, 'L1+N' under a 24 V DC supply). An instrument above a busbar (`measure`
  link) is connected straight down onto it; auxiliary devices are placed off the channels of the feeds tapping a
  busbar, and these channels pass below an off-sheet reference hanging over them.
  Feeder table: the cells of a column stay under its feeder when a long board name widens the drawing (they were
  centred between the feeders), and a board with a single outgoing (a panel fed through a transformer, an enclosure
  around one load) shows the protection and cable of the feeder above it (its cells were empty). A description too
  long for its cell goes on 2 or 3 lines before its text gets smaller (it shrank to a few tenths of a millimetre).

* Single-line view: a control or data link between two loads too close for its label runs under the loads, where
  the label has room (it was written over the symbols).

* Profile `iec60364`: rule `iec60364.rcd-30mA` (IEC 60364-4-41:2005+AMD1:2017, 411.3.3 and 411.3.4), socket-outlets
  up to 32 A and, in dwellings, lighting circuits protected by an RCD of at most 30 mA, except below the isolation
  transformer of a medical IT system; left to `nfc15100` and `vde0100` when the document declares one of them. Rule
  `iec60364.iz-estimate`: a cable without its material, insulation or installation method was not checked at all;
  its current-carrying capacity is now estimated (copper, PVC, the most favourable method in air, 30 °C) and one
  info finding lists the cables estimated. Example 27 draws the RCBOs of its treatment rooms. Rule `iec60364.iz`
  takes the cable's `ambient_C` (30 °C: the values brought back to 30 °C; up to 40 °C: the values at 40 °C; hotter:
  not checked, said in an info), and reads `D1`, the IEC name of cables in ducts in the ground, as `D-duct`;
  without `ambient_C` its message says that 40 °C was assumed (a cable at 30 °C was checked at 40 °C).

* Rule `core.terminal-node` (a PV array, a battery, an SPD or an earth electrode with children) says how to draw it:
  below the device that connects it, the power may flow both ways.

* PLC annotation: the protocols are cut on whole names, with an ellipsis ("Modbus TC" was printed).

* Rule checks: when no rule profile applies, an info finding `core.no-profile` says that only the consistency of the
  document was checked (an empty result read as a checked installation); for a standard no profile covers (NEC,
  for example) it says that the protections, cables, residual-current devices and earthing were not checked
  against it.

* North-American documents (NEC / CEC): cables are written with their AWG / kcmil size whenever it is given
  ("2x#6", "3G" with #12 written "2-#12+G"; the section in mm² was printed), and residual-current protection is
  written "GFCI" (6 mA or less) or "GFPE" instead of an IEC type ("5mA type A" was printed for a GFCI).

* An `infeed` link to a device that feeds nothing (the back-feed breaker of a PV inverter) lands on its output
  terminals, in both views (it arrived on the busbar side). A label without a tag goes on two lines rather than
  being cut when the room beside the symbol is short.

* Units: a number and its unit are written apart everywhere ("100 A", "20 A 30 mA", "C16 30 mA", "gG 32 A",
  "6 kA", "Ir 63 A", a spare way "125 A"), in the drawings, the circuit tables and the bill of materials; the
  ratings of protective devices were written "100A" and "30mA" beside "200 A" and "250 kVA". Curve designations
  ("C16") are unchanged.

* Examples 21 and 29: the feeders of the refrigeration board and of the smoke-control board carry a neutral
  (their 1P+N circuits need one).

* Drawings in Spanish (`meta.lang` "es") and Simplified Chinese ("zh"): title block, notes, legends, table
  headings, type names and the short texts in symbols, with IEC 60050 terms (GB/T terms for Chinese; neutral terms
  where Spain and Argentina differ). Spanish numbers take a decimal comma. Messages stay in English.

* Drawings in German (`meta.lang` "de", "de-AT", "de-CH"...): title block, notes, legends, table headings ("BMK",
  "Stromkreis"), type names and the short texts in symbols ("FU", "SPS", "USV"), with the terms of DIN EN 60617 and
  IEC 60050-826 practice. German numbers take a decimal comma. Messages stay in English.

* Rule profile `vde0100` (German installations, DIN VDE 0100): 30 mA RCD for socket-outlets up to 32 A and for
  the lighting of dwellings (410), circuits of bathrooms (701, a fixed water heater exempt), charging points with
  their own circuit and RCD of type B or A/F with 6 mA DC detection (722), surge protection (443/534) and PEN
  cross-section (540). Combine it with `iec60364`. Example 06 uses it. A document following DIN VDE 0100 without
  a profile is pointed to it.

* Rule findings in German, Spanish, Portuguese, Russian and Chinese (`UNIWIRE_LANG`), with the terms of each
  practice (RCD/FI, diferencial, DR, УЗО, 剩余电流保护器); CLI and validation messages stay in English.

* Drawings in Portuguese (`meta.lang` "pt", "pt-BR", "pt-PT"): title block, notes, legends, table headings
  ("Identificação", "Circuito"), type names and the short texts in symbols ("DR", "DPS", "CLP"), with the terms of
  ABNT NBR 5410 practice. Portuguese numbers take a decimal comma. Messages stay in English.

* Drawings in Italian (`meta.lang` "it", "it-IT"): title block, notes, legends, table headings ("Sigla",
  "Circuito"), type names and the short texts in symbols ("INV", "PLC", "UPS"), with the terms of CEI 64-8
  practice. Italian numbers take a decimal comma. Messages stay in English.

* Drawings in Polish (`meta.lang` "pl", "pl-PL"): title block, notes, legends, table headings ("Oznaczenie",
  "Obwód"), type names and the short texts in symbols ("PCZ", "PLC", "UPS"), with the terms of PN-HD 60364 and
  PN-EN 60617 practice. Polish numbers take a decimal comma. Messages stay in English.

* Drawings in Turkish (`meta.lang` "tr", "tr-TR"): title block, notes, legends, table headings ("Etiket",
  "Devre"), type names and the short texts in symbols ("SRÜ", "PLC", "KGK"), with the terms of TS HD 60364 and
  Elektrik İç Tesisleri Yönetmeliği practice. Turkish numbers take a decimal comma. Messages stay in English.

* A cable written in a device text comes after the device's own lines (settings, poles, vector group) and never
  replaces one; a composition ending with its section ("4x35+PE16") is not followed by the section again.
  "Safety circuit" is not repeated on every feeder of a safety board, nor a data link protocol already in a device
  text. Sheet references between the views of one PDF point to the right sheet numbers.

* Circuit table: "(upstream)" no longer marks the group RCD of a board on the columns of the boards it feeds on other
  sheets; a tag is prefixed with its board only when the same tag comes from different boards.

* The surge limiter's "L" no longer runs into its text; bold CJK text is drawn bold in PDFs.

* Formats: thousands grouped from 10 000 ("20 000 V"); phases separated ("L1-L2-L3"); the RCD type not repeated
  in the RCD cell when the table has its own row for it.

* A busbar that has feeders is no longer drawn twice (a short bar on the incoming conductor and the busbar).

* Circuit table: a tag found in two boards of the same table is prefixed with the board's ("PDU-A -Q1").
  Chinese and Japanese descriptions are written upright, one character under another.

* Information now shown: the drawing number (title block), the earth electrode resistance taken from an earth node,
  the setting of an overload relay ("Ir 48.5 A"), "Safety circuit" on the feeder of a safety service, and the
  protocol of a data link that has no label.

* Cables the circuit table does not show (feeder of a sub-board, a transformer or an inverter, incoming cable of a
  board) are written in the text of the device feeding them ("5G10 15 m", "W7 5x6 38 m").

* Multi-line view: a motor starter is drawn with contactor contacts; a reversing starter with its reverse contactor
  (phases L1 and L3 swapped, mechanical interlock), a star-delta starter with its delta contactor (to W2 U2 V2) and
  its star contactor.

* `uniwire render -f pdf` writes every view of the document in one PDF unless `--view` or `--kind` is given; the
  sheets of a drawing set are numbered across its views (1 / 3, 2 / 3, 3 / 3).

* CJK text (Chinese, Japanese) is wrapped between characters, not only at spaces: notes, title block values, frame
  labels and off-drawing targets stay in their cells. A device text too wide for its column goes on two lines before
  being cut with an ellipsis.

* Russian: device type names (circuit table and elsewhere) and "тип" for the RCD type.

* Small texts: an RCBO without a curve reads "20A 5mA"; transformer ratios in one unit where possible ("20 kV/400 V",
  "400/230 V"); a name whose label starts with its tag shows the tag once ("TGBT", not "TGBT TGBT"), and a device
  text no longer repeats its tag or a line already in its label; rule profiles named in the title block ("IEC 60364").

* PDF: characters the font lacks are replaced (subscript digits by digits, clocks by a circle) or left out, never
  drawn as empty boxes.

* North-American cables are written with their AWG / kcmil size when given, even with a section in mm² for the
  checks (unless the composition is written the IEC way, "3G" + mm²).

* The title block of a board drawn on its own sheet shows that board's voltage and short-circuit current.

* Fix: the breaker drawn for an equipped spare way has a stable id in the SVG (`<spare id>.breaker`).

* Link routes: control, data and measure links keep clear of dashed frames and busbars, no longer share
  segments or run along a conductor, and leave a device by its left or right side, whichever gives the clearer
  route; boards get room at the bottom of their frame for these links. Several links landing on one input
  conductor get one point each.

* An equipped spare way (`spare` with a rating) is drawn with its breaker, tag and rating.

* Circuit table: a feeder shows its overcurrent protection (breaker, fuse) rather than an RCD or switch below it;
  a way of a small sub-busbar shows the breaker or fuse feeding it, with its own tag.

* Off-sheet arrows carry their sheet reference or target drawing on the drawing itself.

* Fix: a node text moved by a view's `label_offset` is now avoided by link routes and labels.

* Rendering the same document again reuses its layout (a PDF after a check is drawn at once).

* Standby sources on several transfer switches (one generator per switch) are drawn side by side instead of on
  top of each other, and on the sheet of their switch when its board has a sheet of its own; a link with no free
  route no longer makes the drawing fail (internal error, PDF refused): it is routed below its feeder, or left out.

* Drawing of inverters and links: a PV string or battery way that also carries its surge protector, meter or
  insulation monitor stays on the DC side of the inverter (it was drawn on the AC busbar); an `infeed` link to an
  inverter or UPS at the head of the tree lands on its input, on top, the side being the DC terminal; a power link
  drawn as a plain line no longer runs along a busbar; links of different kinds no longer share one end point.

* Frame labels (`enclosures`, view `frames`) too long for their frame are written on two or three lines between
  the conductors that cross the frame, the frame widening over free room if need be, instead of crossing a
  busbar or a conductor.

* Circuit table: a `spare` way without its own rating, fed by its own breaker, shows that breaker (tag, rating,
  curve, poles); the columns were empty.

* New example 53: office with a hybrid inverter, rooftop PV, battery and an essential loads board.

* New `core.scope` finding (info): when a document describes control circuits (contactors or relays fed by a
  control power supply and switching nothing, coils, push buttons or signal lamps entered as loads), `check` says
  that uniwire draws power distribution and not control schematics, so that these circuits are only summarized.
  `llms.txt` and the assistants page state the same scope.

* A `main_breaker` without `idn_mA` is drawn as a circuit breaker, no longer with the residual-current toroid and
  "IΔ" of a residual-current breaker (the multi-line view already did so).

* Conductor-count marks of DC lines: a line behind a DC source, a DC box or a device declared `dc` is marked with
  its two poles, never with a "+N" neutral, whatever the poles of its devices (up to an inverter).

* French messages write decimals with a comma ("disjoncteur 32 A sur 1,5 mm²"), like the drawings.

* PDF: Chinese, Japanese and Korean texts are drawn with the CID fonts every PDF reader knows (they were missing
  before); Liberation Sans is used when installed (Linux), with the widths of Arial that the layout expects. The
  MCP server images install it.

* New rule profile `enedis` (opt-in): connection of a low-voltage installation to the French public network,
  following the Enedis technical reference (Enedis-NMO-RAC_001E) and NF C 14-100, separate from `nfc15100`,
  which starts downstream of the service main breaker. Rules: `enedis.connection` (12 kVA at most in
  single-phase, 36 kVA in three-phase for a limited-power connection; monitored power and medium voltage
  above), `enedis.agcp-setting` (the service main breaker setting carries the connection power and cannot be
  below the subscribed power or above 60 A), `enedis.agcp-rcd` (500 mA residual-current service breaker
  recommended), `enedis.production` (injection and installed power limits in single-phase and three-phase,
  storage included, Enedis-NMO-RES_032E), `enedis.service-cable` (individual service cable: 30 m and 35 mm²
  aluminium) and `enedis.decoupling` (decoupling protection of production and
  storage inverters). The French examples on a Tarif Bleu supply
  declare it.

* `nfc15100` profile checked against the text that gives presumption of conformity (NF C 15-100 2002 with its
  2005 update and amendments A1 to A5): the rules of dwellings now cite part 10-1 of amendment A5, which
  replaces part 7-771.
  * Fixes: the 30 mA protection of dwelling circuits and the minimum of 2 RCDs (now an error) are checked in
    three-phase dwellings too; lighting and socket points are added up per circuit; the circuits behind an RCD
    are counted through combs and boards, with `count`; the dryer no longer requires a type A RCD; a shared
    freezer circuit is a warning; outside dwellings, socket-outlets above 32 A no longer require 30 mA; a
    non-selective RCD upstream of other RCDs is an error in a dwelling.
  * New rules: `nfc15100.circuit-section` (section and protection of dedicated circuits), `nfc15100.rcd-rating`
    (rating of the 30 mA RCDs, warning), `nfc15100.rcd-spread` (lighting and sockets over at least 2 RCDs),
    `nfc15100.spd-rcd` (surge protector at the origin not behind 30 mA), `nfc15100.agcp-rcd` (500 mA at most,
    no adjustable sensitivity on a limited-power supply), `nfc15100.earth-resistance` (TT, 50 V),
    `nfc15100.neutral-pole` (no 1P breaker in a dwelling) and `nfc15100.supply-section` (link from the
    service breaker to the main board).
  * EV charging rules cite IEC 60364-7-722 / guide UTE C 15-722, which are not part of that text.
  * Examples 15 and 36: lighting and socket circuits spread over two RCDs; the reference card example and the
    quickstart use two RCDs.

## 0.1.2 (not published: shipped in 0.1.3)

* Bill of materials: equipment without a product reference is grouped by type and main characteristics (new
  `spec` key, e.g. `C16 1P+N 6kA`, `40A 30mA 2P type A`) and cables by type, composition and material (new
  `length_m` key with the total known length), instead of being left out. Rows with a reference are unchanged
  and come first; the CSV puts the characteristics in the description column. The utility's meter (fed directly
  by the grid) is not listed unless it carries a reference; sub-meters are.
* MCP server: every tool parameter is described in the input schemas (document, language, view, rule profiles...),
  and the descriptions say when to use each tool and which one to use instead (validate vs check, list_types
  then type_info, bom vs wiring).
* MCP server: tool descriptions say what each tool does, takes and returns; the guidance for assistants (which
  links to give, the conformity disclaimer, the workflow) lives in the server instructions only.
* Web viewer: a link to an example that does not exist (`?example=98`) opens the first example with a message,
  instead of an empty editor.
* Web viewer: clearer download menu: "PDF, all sheets" downloads the PDF, "Print all sheets…" opens the sheets
  for printing.
* Web viewer: panning the drawing no longer selects its text; text is selected on purpose only (double-click a
  text, or drag with Alt/Option held).
* Web viewer: the drawing shows at once, while the in-browser engine starts (10 to 25 seconds on a first visit):
  the examples come with their first sheet drawn at build time, and short links (`#d=`) with the first sheet drawn
  by the server (new route `GET /svg/<id>` of the hosted MCP server). The live drawing replaces it when ready.
* Sheets: when a view gives no `paper`, the drawing goes on an A4 landscape sheet if it fits there at full size,
  else on A3 as before. A drawing that uses little of its sheet is enlarged, up to 1.25 (annotations of 2.5 mm),
  with the same scale for all the sheets of a view so that the text keeps one size; large drawings are still
  reduced to fit.
* Battery symbol: the two cells are joined by a dashed line, with a lead below the last one and the + and − marked,
  so that it no longer reads as an earth symbol at small sizes.
* Heating symbol: the last of the four strokes no longer goes past the right side of the box.
* Single-line diagrams: an annotation is no longer cut with "…": its column widens as needed (the text may still
  be reduced, down to 1.5 mm), and a board's column widens to its name, so that board frames no longer cross
  their name or each other.
* Multi-line diagrams: board frames keep clear of the switch blades and of the frames next to them.
* Multi-line diagrams, TT and IT: the PE starts at the main earthing terminal of the first board, no longer at
  the incoming device whose cable carries a protective conductor; a board drawn on its own sheet starts its PE
  there, and the sheet that feeds it carries the live conductors only.
* Examples 03 and 09: three-phase smart meter rated 60 A.
* Boards fed from the same board are drawn side by side on one line (single-line and multi-line): their frames,
  names and first devices are aligned.
* Inverters/chargers and UPS feeding both a DC side (batteries, PV, DC converters, DC boards, or a device feeding
  one of them alone) and an AC side: in single-line diagrams the DC side is drawn from a side terminal of the
  symbol, no longer from the busbar of the AC outputs; in multi-line diagrams the AC outputs keep the AC
  conductors and only the DC side gets the L+/L- pair, also when the inverter/charger is the source.
* MCP server image: Python 3.14.
* Tests: the worker pool tests start from a warm worker with a wider timeout (they failed on slow CI runners).
* Web viewer and documentation: light by default, whatever the system setting; dark when the reader chooses it
  (the choice is remembered and shared with uniwire.sh).

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
