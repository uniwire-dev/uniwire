"""Minimal message catalog for user-facing text (English default, French available).

Two sources pick the language:

* rendering (title block, sheet labels, table row titles) follows ``doc.meta.lang`` and is passed
  explicitly with ``t(key, lang=...)``;
* CLI output, validation errors and rule findings follow the ``UNIWIRE_LANG`` environment variable
  (default ``"en"``), read at call time.

Unknown languages fall back to English; a key missing from a catalog falls back to the English text,
then to the key itself. Messages are ``str.format`` templates (format specs such as ``{x:g}`` and
conversions such as ``{name!r}`` are allowed).
"""

from __future__ import annotations

import contextvars
import os
from typing import Any, Optional

#: Language of the document being rendered (set by ``render_pages``); used by number formatting,
#: registry labels and symbol abbreviations, which have no document at hand.
RENDER_LANG: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("uniwire_render_lang", default=None)

DEFAULT_LANG = "en"
ENV_VAR = "UNIWIRE_LANG"

EN: dict[str, str] = {
    # --- validation (resolve.py)
    "validation.extra_forbidden": "unknown field (typo? use 'ext' for extensions)",
    "validation.unknown_node_type": "unknown node type: {type!r}",
    "validation.unknown_template": "unknown 'use' template: {name!r}",
    "validation.template_type_mismatch": "template {name!r} is of type {ttype!r}, the node is of type {ntype!r}",
    "validation.template_unknown_type": "templates/{name}: unknown type {type!r}",
    "validation.duplicate_id": "duplicate identifier: {id!r}",
    "validation.link_unknown_id": "link {kind}: unknown identifier {id!r}",
    "validation.enclosure_id_used": "enclosure {id!r}: identifier already in use",
    "validation.enclosure_unknown_node": "enclosure {id!r}: unknown node {node!r}",
    "validation.enclosure_unknown_parent": "enclosure {id!r}: unknown parent enclosure {parent!r}",
    "validation.invalid_json": "invalid JSON: {error}",
    "validation.too_deep": "document nested too deeply (more than {max} levels of objects and lists)",
    "validation.too_deep_validator": "document nested too deeply for the validator on this platform (power tree too deep)",
    "validation.newer_minor": "the document declares format {declared}, newer than the format {supported} "
                              "supported by this version of uniwire: upgrade uniwire to read the fields it does not know",
    "units.unreadable": "unreadable quantity: {value!r}",
    "units.too_long": "quantity too long ({n} characters, at most {max}): {value!r}...",
    "units.unknown_unit": "unknown unit: {unit!r}",
    "units.incompatible": "unit {unit!r} is incompatible with {target!r}",
    # --- rules engine
    "rules.unknown_profile": "unknown profile: {profile!r}",
    "rules.no_profile": "no rule profile applied: only the consistency of the document was checked (tags, links, "
                        "interlocks, ratings in cascade), not the protections, cables and RCDs; profiles: 'nfc15100' "
                        "(France), 'vde0100' (Germany), 'iec60364'",
    "rules.standard_not_covered": "no rule profile covers {standard}: only the consistency of the document was "
                                  "checked (tags, links, interlocks, ratings in cascade); the protections, cables, "
                                  "residual-current devices and earthing were not checked against {standard}",
    # core
    "core.ref_unique": "tag {ref!r} already used by {other!r}",
    "core.normalized": "{where}: {field} {old!r} read as {new!r}; write it in this form",
    "core.normalized_field": "{where}: unknown field {old!r} read as {new!r}; use {new!r}",
    "core.transfer_target": "a 'transfer' link must end on a transfer switch (transfer_switch)",
    "core.tie_device": "bus tie without a described device",
    "core.transfer_source": "transfer switch without a 2nd source ('transfer' link)",
    "core.terminal_node": "a {type} node is a leaf and feeds nothing: draw it below the device that connects it (its "
                          "protection, converter or inverter), power may flow both ways",
    "core.rating_cascade": "rating {in_a:g} A higher than the upstream protection {up} ({up_in_a:g} A)",
    "core.interlock_closed": "interlock {lock!r}: {count} members closed in normal operation ({members}) for {keys} key(s)",
    "core.interlock_single": "lock {lock!r} is used by a single member and declared in no 'interlocks' entry: it interlocks nothing",
    "core.interlock_unused": "declared interlock {lock!r} is used by {count} member(s) ('locks'), at least 2 expected",
    "core.interlock_duplicate": "interlock {lock!r} declared twice",
    "core.control_scope": "this document describes control circuits ({nodes}): uniwire draws power distribution "
                          "(single-line and multi-line diagrams), not control schematics; coils, contacts, push "
                          "buttons and current paths are only summarized here, not drawn as a control schematic",
    # plc
    "tplan.title": "Terminal plan",
    "tplan.cont": "(cont.)",
    "tplan.terminal": "Terminal",
    "tplan.part": "Part",
    "tplan.summary": "{count} terminals: {detail}",
    "tplan.kind.feed_through": "feed-through",
    "tplan.kind.disconnect": "disconnect",
    "tplan.kind.fuse": "fuse",
    "tplan.kind.earth": "earth",
    "tplan.kind.neutral": "neutral",
    "tplan.kind.spare": "spare",
    "tplan.strip": "Terminal strip",
    "tplan.port": "Connection",
    "tplan.bridge": "Bridge",
    "tplan.label": "Function",
    "tplan.mark": "Mark",
    "tplan.site_note": "* connected on site by the installer",
    "tplan.inside": "Internal target",
    "tplan.outside": "External target",
    "wiring.no_owner": "{ref}: no node and no terminal strip has the id {owner!r}",
    "wiring.generated_id": "{ref}: {owner!r} is a generated id, not stable; give the node an explicit 'id'",
    "wiring.no_port": "{ref}: {owner} has no terminal {port!r} (terminals: {known}); declare it in 'ports'",
    "wiring.ambiguous": "{ref}: {port!r} names two terminals (declared twice, or the alias of two)",
    "wiring.control_wire": "a control wire",
    "wiring.same_ends": "wire {wire}: both ends on {ref}",
    "wiring.capacity": "{display}: {count} conductors for a terminal that takes {capacity}",
    "wiring.coil_unconnected": "{display}: coil terminal not connected, while {node} is wired",
    "wiring.gnye": "wire {wire}: green-and-yellow (GNYE) is reserved for the protective conductor, not {conductor}",
    "wiring.pe_on_live": "wire {wire}: PE conductor on {display}, which is not an earth terminal",
    "wiring.section_max": "wire {wire}: {section:g} mm² on {display}, which takes {max:g} mm² at most",
    "wiring.duplicate_terminal": "terminal strip {strip}: terminal {no!r} declared twice",
    "wiring.strip_enclosure": "terminal strip {strip}: unknown enclosure {enclosure!r}",
    "wiring.lone_bridge": "terminal strip {strip}: bridge group {group!r} has a single terminal",
    "plc.duplicate_slots": "duplicate slots: {slots}",
    "plc.unsorted_slots": "modules not sorted by slot",
    "plc.wago_end": "WAGO local bus without an end module (750-600) in last position",
    "plc.wago_feed": "no potential feed module (750-602...) declared",
    "plc.port_unreadable": "port {port!r} unreadable (expected 'slot.channel')",
    "plc.port_missing_slot": "port {port!r}: slot {slot} missing",
    "plc.port_channels": "port {port!r}: module {module} only has {channels} channels",
    "plc.coil": "output {port} ({un_v:g} V) drives a {coil:g} V coil: use an interface relay or a relay module",
    "plc.port_shared": "channel {port} controls {count} devices",
    # iec60364
    "iec60364.install_uncovered": "installation method {install!r} not covered (A1, A2, B1, B2, C, E, F, D1/D-duct)",
    "iec60364.iz_unavailable": "Iz not available for {material} {insulation} {section:g} mm² "
                               "method {method}, {loaded} loaded conductors",
    "iec60364.iz_exceeded": "protection {rating:g} A > Iz {iz:g} A ({material} {insulation} {section:g} mm², "
                            "method {method}, {loaded} loaded cond., {ambient})",
    "iec60364.ambient_ground": "ground {t:g} °C",
    "iec60364.ambient_air": "{t:g} °C ambient",
    "iec60364.ambient_default": ", ambient_C not given",
    "iec60364.ambient_uncovered": "Iz not checked: ambient {ambient:g} °C above the {limit} °C of the table for method {method}",
    "iec60364.iz_estimate_exceeded": "the cable does not state its material, insulation or installation method: "
                                     "estimated with {material} {insulation} {section:g} mm², method {method}, "
                                     "{loaded} loaded conductors, {t:g} °C: protection {rating:g} A > Iz {iz:g} A; "
                                     "give them to check it exactly",
    "iec60364.any_air_method": "most favourable in air",
    "iec60364.iz_estimated": "current-carrying capacity only estimated for {count} cable(s) ({tags}): material, "
                             "insulation or installation method missing (copper, PVC and the most favourable method "
                             "assumed); give them for an exact check",
    "iec60364.rcd_30mA_socket": "{what}: socket-outlet circuit up to 32 A not protected by an RCD of at most 30 mA",
    "iec60364.rcd_30mA_lighting": "{what}: lighting circuit of a dwelling not protected by an RCD of at most 30 mA",
    # nfc15100
    "nfc15100.section": "{in_a:g} A breaker on {section:g} mm² (max {limit} A)",
    "nfc15100.section_sizing": "{in_a:g} A breaker on {section:g} mm²: above the usual {limit} A, check the cable "
                               "for its installation method (NF C 15-100 part 5-52, guide UTE C 15-105)",
    "nfc15100.lighting_points": "{points} points on a lighting circuit (max {limit})",
    "nfc15100.lighting_rating": "lighting protected by {in_a:g} A (max 16 A)",
    "nfc15100.socket_section": " at {section:g} mm²",
    "nfc15100.socket_points": "{points} sockets on a socket-outlet circuit{where} (max {limit})",
    "nfc15100.heating": "heating {total:g} kW on a {in_a:g} A circuit (max {limit:g} kW)",
    "nfc15100.heating_unprotected": "heating {p:g} kW on one circuit (max {limit:g} kW at 32 A)",
    "nfc15100.rcd_30mA_socket": "{what}: socket-outlet / charging circuit not protected by a 30 mA RCD",
    "nfc15100.rcd_30mA_dwelling": "{what}: dwelling circuit not protected by a 30 mA RCD",
    "nfc15100.rcd_type_A": "{what}: type A (or F, B) RCD required, type AC excluded",
    "nfc15100.rcd_count_single": "only one 30 mA residual-current device (dwellings: at least 2; set installation.premises for other premises)",
    "nfc15100.rcd_count_type_A": "no type A 30 mA RCD (dwellings: at least 1; set installation.premises for other premises)",
    "nfc15100.rcd_circuits": "{count} circuits on one 30 mA RCD (max 8)",
    "nfc15100.dedicated_single": "{what}: must be alone on its circuit ({prot} also feeds {others})",
    "nfc15100.dedicated_shared": "{what}: dedicated circuit shared with another use",
    "nfc15100.ev_default": "EV charger",
    "nfc15100.ev_mode2_3ph": "{what}: three-phase mode 2, type B RCD required",
    "nfc15100.ev_mode3": "{what}: mode 3 with type {rtype} RCD: the charger must include 6 mA DC fault "
                         "detection (RDC-DD, IEC 62955), otherwise type B",
    "nfc15100.selectivity": "residual-current device upstream of other RCDs and not selective (type S)",
    "nfc15100.circuit_section": "{what}: {section:g} mm² (at least {need:g} mm² for this circuit)",
    "nfc15100.circuit_rating": "{what}: protected by {in_a:g} A (at most {need:g} A for this circuit)",
    "nfc15100.rcd_rating": "30 mA RCD rated {in_a:g} A, below the {need:g} A required by the circuits behind it",
    "nfc15100.rcd_spread_lighting": "the {count} lighting circuits are all behind the same 30 mA RCD (spread them "
                                    "over at least 2)",
    "nfc15100.rcd_spread_socket": "the {count} socket-outlet circuits are all behind the same 30 mA RCD (spread "
                                  "them over at least 2)",
    "nfc15100.spd_rcd": "{what}: the surge protective device at the origin must not be behind a 30 mA RCD",
    "nfc15100.agcp_rcd_adjustable": "{what}: adjustable sensitivity is not allowed on a limited-power supply",
    "nfc15100.agcp_rcd_max": "{what}: {idn:g} mA, at most 500 mA on a limited-power supply",
    "nfc15100.earth_resistance": "earth electrode of {r:g} Ω with a {idn:g} mA RCD: {limit:g} Ω at most (50 V)",
    "nfc15100.neutral_pole": "{what}: 1P breaker on a circuit with a neutral, which it does not isolate (1P+N or 2P)",
    "nfc15100.supply_section": "link to the main board in {section:g} mm² with a {in_a:g} A service breaker "
                               "(at least {need:g} mm² copper)",
    # enedis
    "vde0100.rcd_30mA_socket": "{what}: socket-outlet circuit up to 32 A not protected by an RCD of at most 30 mA",
    "vde0100.rcd_30mA_lighting": "{what}: lighting circuit of a dwelling not protected by an RCD of at most 30 mA",
    "vde0100.bathroom": "{what}: circuit of a room with a bath or a shower not protected by an RCD of at most 30 mA",
    "vde0100.ev_own_circuit": "{what}: a charging point needs its own final circuit (other loads on its protection)",
    "vde0100.ev_no_rcd": "{what}: charging point not protected by an RCD of at most 30 mA",
    "vde0100.ev_own_rcd": "{what}: a charging point needs its own RCD (the RCD also protects other loads)",
    "vde0100.ev_rcd_type": "{what}: RCD type {rtype}: type B, or type A / F with 6 mA DC fault detection in the "
                           "charging point, required",
    "vde0100.ev_rdc_dd": "{what}: type {rtype} RCD: the charging point must include 6 mA DC fault detection "
                         "(RDC-DD, IEC 62955), otherwise a type B RCD",
    "vde0100.spd": "no surge protective device: required for most buildings (DIN VDE 0100-443 / -534)",
    "vde0100.pen_section": "PEN conductor of {section:g} mm² {material}: at least {minimum:g} mm² required",
    "enedis.single_phase_max": "{kva:g} kVA in single-phase: a limited-power single-phase connection carries 12 kVA "
                               "at most, a three-phase connection is needed",
    "enedis.monitored": "{kva:g} kVA: monitored-power connection (37 to 250 kVA), the AGCP setting tiers of "
                        "limited-power connections do not apply",
    "enedis.mv": "{kva:g} kVA: beyond 250 kVA the connection is in medium voltage (HTA)",
    "enedis.dwelling_min": "{kva:g} kVA in a dwelling: limited-power connections of dwellings start at 6 kVA",
    "enedis.agcp_max": "service main breaker set to {in_a:g} A: a limited-power connection is set to 60 A at most",
    "enedis.agcp_low": "service main breaker set to {in_a:g} A carries {pr:g} kVA, below the {kva:g} kVA "
                       "subscribed: it would trip before the subscribed power",
    "enedis.agcp_no_rcd": "service main breaker without residual-current protection: NF C 14-100 recommends 500 mA "
                          "in new buildings (non-residual-current breaker on request to Enedis)",
    "enedis.agcp_rcd_value": "service main breaker with {idn:g} mA residual-current protection: NF C 14-100 "
                             "recommends 500 mA",
    "enedis.prod_installed_1p": "{kva:g} kVA of production and storage in single-phase ({what}): above 18 kVA of "
                                "installed power, a three-phase connection is needed",
    "enedis.prod_injection_1p": "{kva:g} kVA of production and storage in single-phase ({what}): injection is "
                                "limited to 6 kVA (limit the export or connect in three-phase)",
    "enedis.prod_installed_3p": "{kva:g} kVA of production and storage ({what}): installed power is limited to "
                                "250 kVA in low voltage",
    "enedis.prod_above_36": "{kva:g} kVA of production and storage ({what}): an injection above 36 kVA follows "
                            "the connection procedure of installations above 36 kVA",
    "enedis.service_cable_length": "individual service cable of {length:g} m: limited-power connections allow 30 m "
                                   "at most (voltage variation within 2 %)",
    "enedis.service_cable_section": "individual service cable of {section:g} mm²: the standard section is 35 mm² "
                                    "aluminium (2 x 35 single-phase, 4 x 35 three-phase)",
    "enedis.decoupling": "{what}: give its decoupling protection, mandatory for production and storage "
                         "(`protection`, e.g. NF EN 50549-1 / NF EN 50549-10)",
    # --- CLI
    "cli.description": "uniwire format: validation, rule checks and drawings of electrical diagrams (single-line and multi-line)",
    "cli.help.validate": "validate one or more documents",
    "cli.help.check": "validate then apply the rules (profiles)",
    "cli.help.profile": "profile(s) to apply (default: those of the document)",
    "cli.help.render": "generate the sheets",
    "cli.help.format": "output format",
    "cli.help.out_render": "folder (svg) or file (pdf)",
    "cli.help.view": "view identifier",
    "cli.help.kind": "view kind: 'multi-line' draws the multi-line power diagram even if the document declares no such view",
    "cli.help.schema": "write the JSON Schema",
    "cli.help.graph": "export the terminal / connection-node graph (JSON)",
    "cli.help.bom": "bill of materials (part numbers) as CSV",
    "cli.help.symbols": "SVG sheet of all symbols",
    "cli.help.normalize": "rewrite the resolved document (templates applied, ids assigned)",
    "cli.invalid_document": "{path}: invalid document",
    "cli.findings": "{path}: {count} finding(s)",
    "cli.help.card": "print the reference card of the format (for LLM assistants)",
    "cli.help.card_full": "full card (field descriptions) instead of the compact one",
    "cli.help.lang": "language: en or fr (default: UNIWIRE_LANG)",
    "cli.help.version": "show the library and format versions and exit",
    "cli.help.describe": "print a text outline of a document (stable ids, ratings, links, findings)",
    "cli.help.link": "print a link that opens the document in the web editor (drawing, findings, PDF)",
    "cli.help.link_pdf": "the link also downloads the PDF",
    "cli.help.patch": "apply id-based edit operations (JSON list) and validate the result",
    "cli.help.ops": "JSON file with the list of operations ('-' = standard input)",
    "cli.help.out_patch": "output file (default: standard output)",
    "cli.patch_failed": "{path}: patch failed",
    "cli.patch_op": "operation #{index}",
    "cli.patch_result": "resulting document",
    "cli.help.wires": "wire list as CSV: one row per conductor of the cables of the power tree, with its mark, then "
                      "one per declared wire",
    "cli.help.terminals": "terminal plan as CSV: one row per terminal of each terminal strip, in mounting order",
    "cli.help.strip": "only this terminal strip (id or reference designation)",
    "cli.help.wires_all": "include the implicit power connections (always the case in the current format)",
    "cli.help.markers": "wire marker list as CSV (ferrules: one row per wire end, quantities)",
    "cli.help.cables": "cable schedule as CSV (one row per cable)",
    "cli.help.marks": "print the wire marks of a view; --write freezes them into the file (cable 'marks')",
    "cli.help.marks_write": "write the generated marks into the cables' 'marks' (freezing), so that later edits do not renumber them",
    "cli.help.out_marks": "with --write: output file (default: the input file, rewritten)",
    "cli.help.view_marking": "view whose 'wire_marking' rules apply (default: the first view that has some)",
    "cli.marks_manual": "(manual)",
    "cli.marks_written": "{count} mark(s) written to {path}",
    "cli.marks_skipped": "{cable}: cable given by a template only, marks not written",
    # --- BOM
    "bom.headers": "Manufacturer;Part number;Range;Description;Type;Quantity;Tags",
    "bom.accessory": "accessory",
    # --- rendering
    "render.unknown_view": "unknown view: {id}",
    "render.incoming_from": "from {ref}",
    "render.incoming": "incoming",
    "render.incoming_folio": "{what} (sheet {folio})",
    "render.default_title": "General single-line diagram",
    "render.multiline_title": "Multi-line power diagram",
    "render.continued_from": "{label} (continued from sheet {folio})",
    "render.continued_on": "continued on sheet {folio}",
    "render.continuation_name": "{name} (cont.)",
    "render.to_folio": " → sheet {folio}",
    "label.rcd_type": "type {type}",
    "label.safety": "Safety circuit",
    "render.auxiliary_devices": "Auxiliary devices",
    "render.scale": "scale {scale}",
    "render.pdf_missing": "PDF output: install the 'uniwire[pdf]' extra (reportlab)",
    "render.sheet_bookmark": "Sheet {number}: {title}",
    "render.sheet_bookmark_untitled": "Sheet {number}",
    "legend.conductors": "Conductors ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "NEC practice",
    "legend.phase": "Phases",
    "legend.multi_phase": "polyphase",
    "legend.source": "Supply sources",
    "legend.status": "Status",
    "legend.status.new": "new",
    "legend.status.existing": "existing",
    "legend.status.future": "future",
    "legend.status.temporary": "temporary",
    "legend.status.removed": "removed",
    "legend.status.spare": "spare",
    "legend.voltage": "Voltage",
    "legend.voltage.mv": "HV / MV (> 1 kV AC)",
    "legend.voltage.lv": "LV",
    "legend.voltage.elv": "ELV (≤ 50 V AC)",
    "legend.voltage.dc": "DC",
    "tb.title": "Title",
    "tb.sheet_title": "Sheet",
    "tb.default_sheet_title": "Single-line diagram",
    "tb.project": "Project",
    "tb.client": "Client",
    "tb.earthing": "Earthing system",
    "tb.voltage": "Voltage",
    "tb.power": "Power",
    "tb.ik_max": "Ik max",
    "tb.earth_electrode": "Earth electrode",
    "tb.standard": "Standard",
    "tb.drawn_by": "Drawn by",
    "tb.checked_by": "Checked",
    "tb.company": "Company",
    "tb.date": "Date",
    "tb.revision": "Rev.",
    "tb.sheet": "Sheet",
    "tb.generated_by": "Generated by",
    "notes.title": "Notes",
    "notes.site": "Site: {site}",
    "notes.supply": "Supply: {supply}",
    "notes.revision": "Rev. {index} {date} {description}",
    "notes.more": "… (+{count} more note line(s))",
    # annotations next to symbols (labels.py)
    "ann.frame": "frame {frame} A",
    "ann.off_peak": "D/N (off-peak)",
    "ann.manual": "manual",
    "ann.automatic": "auto",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "{count} module(s)",
    "ann.normally_open": "N.O.",
    "ann.locks": "key {keys}",
    "cell.points_one": "{count} pt",
    "cell.points": "{count} pts",
    "cell.upstream": "{value} (upstream)",
    "symbols.page_title": "uniwire symbols",
    "symbols.heading": "uniwire symbol library (grid M = 2.5 mm)",
}

FR: dict[str, str] = {
    "validation.extra_forbidden": "champ inconnu (faute de frappe ? utiliser 'ext' pour les extensions)",
    "validation.unknown_node_type": "type de nœud inconnu : {type!r}",
    "validation.unknown_template": "modèle 'use' inconnu : {name!r}",
    "validation.template_type_mismatch": "le modèle {name!r} est de type {ttype!r}, le nœud de type {ntype!r}",
    "validation.template_unknown_type": "templates/{name}: type inconnu {type!r}",
    "validation.duplicate_id": "identifiant dupliqué : {id!r}",
    "validation.link_unknown_id": "lien {kind}: identifiant inconnu {id!r}",
    "validation.enclosure_id_used": "enveloppe {id!r} : identifiant déjà utilisé",
    "validation.enclosure_unknown_node": "enveloppe {id!r} : nœud inconnu {node!r}",
    "validation.enclosure_unknown_parent": "enveloppe {id!r} : enveloppe parente inconnue {parent!r}",
    "validation.invalid_json": "JSON invalide : {error}",
    "validation.too_deep": "document trop profondément imbriqué (plus de {max} niveaux d'objets et de listes)",
    "validation.too_deep_validator": "document trop profondément imbriqué pour le validateur sur cette plateforme (arbre trop profond)",
    "validation.newer_minor": "le document déclare le format {declared}, plus récent que le format {supported} "
                              "pris en charge par cette version d'uniwire : mettez uniwire à jour pour lire les champs "
                              "qu'il ne connaît pas",
    "units.unreadable": "grandeur illisible : {value!r}",
    "units.too_long": "grandeur trop longue ({n} caractères, au plus {max}) : {value!r}...",
    "units.unknown_unit": "unité inconnue : {unit!r}",
    "units.incompatible": "unité {unit!r} incompatible avec {target!r}",
    "rules.unknown_profile": "profil inconnu : {profile!r}",
    "rules.no_profile": "aucun profil de règles appliqué : seule la cohérence du document a été vérifiée (repères, "
                        "liens, verrouillages, calibres en cascade), pas les protections, câbles et différentiels ; "
                        "profils : 'nfc15100' (France), 'vde0100' (Allemagne), 'iec60364'",
    "rules.standard_not_covered": "aucun profil de règles ne couvre {standard} : seule la cohérence du document a été "
                                  "vérifiée (repères, liens, verrouillages, calibres en cascade) ; les protections, "
                                  "câbles, différentiels et la mise à la terre n'ont pas été vérifiés selon {standard}",
    "core.ref_unique": "repère {ref!r} déjà utilisé par {other!r}",
    "core.normalized": "{where} : {field} {old!r} lu comme {new!r} ; écrire cette forme",
    "core.normalized_field": "{where} : champ inconnu {old!r} lu comme {new!r} ; utiliser {new!r}",
    "core.transfer_target": "un lien 'transfer' doit aboutir sur un inverseur (transfer_switch)",
    "core.tie_device": "couplage sans appareil décrit",
    "core.transfer_source": "inverseur sans 2e source (lien 'transfer')",
    "core.terminal_node": "un nœud {type} est une feuille et n'alimente rien : le placer sous l'appareil qui le "
                          "raccorde (sa protection, son convertisseur ou son onduleur), l'énergie peut circuler dans "
                          "les deux sens",
    "core.rating_cascade": "calibre {in_a:g} A supérieur à la protection amont {up} ({up_in_a:g} A)",
    "core.interlock_closed": "verrouillage {lock!r} : {count} membres fermés en exploitation normale ({members}) pour {keys} clé(s)",
    "core.interlock_single": "la serrure {lock!r} n'équipe qu'un seul membre et n'est déclarée dans aucune entrée 'interlocks' : elle ne verrouille rien",
    "core.interlock_unused": "le verrouillage déclaré {lock!r} n'équipe que {count} membre(s) ('locks'), 2 au moins attendus",
    "core.interlock_duplicate": "verrouillage {lock!r} déclaré deux fois",
    "core.control_scope": "ce document décrit des circuits de commande ({nodes}) : uniwire dessine la distribution "
                          "(schémas unifilaire et multifilaire), pas les schémas de commande ; bobines, contacts, "
                          "boutons et chemins de courant n'y figurent qu'en résumé, pas en schéma développé",
    "tplan.title": "Plan de bornier",
    "tplan.cont": "(suite)",
    "tplan.terminal": "Borne",
    "tplan.part": "Article",
    "tplan.summary": "{count} bornes : {detail}",
    "tplan.kind.feed_through": "de passage",
    "tplan.kind.disconnect": "sectionnable",
    "tplan.kind.fuse": "à fusible",
    "tplan.kind.earth": "de terre",
    "tplan.kind.neutral": "de neutre",
    "tplan.kind.spare": "de réserve",
    "tplan.strip": "Bornier",
    "tplan.port": "Raccordement",
    "tplan.bridge": "Pont",
    "tplan.label": "Fonction",
    "tplan.mark": "Repère",
    "tplan.site_note": "* raccordé sur site par l'installateur",
    "tplan.inside": "Cible intérieure",
    "tplan.outside": "Cible extérieure",
    "wiring.no_owner": "{ref} : aucun nœud ni bornier n'a l'id {owner!r}",
    "wiring.generated_id": "{ref} : {owner!r} est un id généré, non stable ; donnez au nœud un 'id' explicite",
    "wiring.no_port": "{ref} : {owner} n'a pas de borne {port!r} (bornes : {known}) ; déclarez-la dans 'ports'",
    "wiring.ambiguous": "{ref} : {port!r} désigne deux bornes (déclarée deux fois, ou alias de deux)",
    "wiring.control_wire": "un fil de commande",
    "wiring.same_ends": "fil {wire} : les deux extrémités sur {ref}",
    "wiring.capacity": "{display} : {count} conducteurs sur une borne qui en prend {capacity}",
    "wiring.coil_unconnected": "{display} : borne de bobine non raccordée, alors que {node} est câblé",
    "wiring.gnye": "fil {wire} : le vert-jaune (GNYE) est réservé au conducteur de protection, pas à {conductor}",
    "wiring.pe_on_live": "fil {wire} : conducteur PE sur {display}, qui n'est pas une borne de terre",
    "wiring.section_max": "fil {wire} : {section:g} mm² sur {display}, qui prend {max:g} mm² au plus",
    "wiring.duplicate_terminal": "bornier {strip} : borne {no!r} déclarée deux fois",
    "wiring.strip_enclosure": "bornier {strip} : enveloppe {enclosure!r} inconnue",
    "wiring.lone_bridge": "bornier {strip} : le groupe de pontage {group!r} n'a qu'une borne",
    "plc.duplicate_slots": "slots en double : {slots}",
    "plc.unsorted_slots": "modules non rangés par ordre de slot",
    "plc.wago_end": "bus local WAGO sans module de fin (750-600) en dernière position",
    "plc.wago_feed": "aucun module d'alimentation de potentiel (750-602...) déclaré",
    "plc.port_unreadable": "port {port!r} illisible (attendu 'slot.voie')",
    "plc.port_missing_slot": "port {port!r} : slot {slot} absent",
    "plc.port_channels": "port {port!r} : le module {module} n'a que {channels} voies",
    "plc.coil": "sortie {port} ({un_v:g} V) pilote une bobine {coil:g} V : prévoir un relais d'interface ou un module relais",
    "plc.port_shared": "la voie {port} commande {count} appareils",
    "iec60364.install_uncovered": "mode de pose {install!r} non couvert (A1, A2, B1, B2, C, E, F, D1/D-duct)",
    "iec60364.iz_unavailable": "Iz non disponible pour {material} {insulation} {section:g} mm² "
                               "pose {method}, {loaded} conducteurs chargés",
    "iec60364.iz_exceeded": "protection {rating:g} A > Iz {iz:g} A ({material} {insulation} {section:g} mm², "
                            "pose {method}, {loaded} cond. chargés, {ambient})",
    "iec60364.ambient_ground": "sol {t:g} °C",
    "iec60364.ambient_air": "{t:g} °C ambiant",
    "iec60364.ambient_default": ", ambient_C non indiqué",
    "iec60364.ambient_uncovered": "Iz non vérifié : ambiante {ambient:g} °C au-dessus des {limit} °C de la table pour la pose {method}",
    "iec60364.iz_estimate_exceeded": "le câble ne précise pas sa matière, son isolant ou son mode de pose : "
                                     "estimation en {material} {insulation} {section:g} mm², mode {method}, "
                                     "{loaded} conducteurs chargés, {t:g} °C : protection {rating:g} A > Iz {iz:g} A ; "
                                     "les préciser pour une vérification exacte",
    "iec60364.any_air_method": "le plus favorable à l'air libre",
    "iec60364.iz_estimated": "courant admissible seulement estimé pour {count} câble(s) ({tags}) : matière, isolant "
                             "ou mode de pose manquant (cuivre, PVC et mode le plus favorable supposés) ; les "
                             "préciser pour une vérification exacte",
    "iec60364.rcd_30mA_socket": "{what} : circuit de prises jusqu'à 32 A non protégé par un différentiel de 30 mA "
                                "au plus",
    "iec60364.rcd_30mA_lighting": "{what} : circuit d'éclairage d'un logement non protégé par un différentiel de 30 "
                                  "mA au plus",
    "nfc15100.section": "disjoncteur {in_a:g} A sur {section:g} mm² (max {limit} A)",
    "nfc15100.section_sizing": "disjoncteur {in_a:g} A sur {section:g} mm² : au-delà des {limit} A usuels, vérifier "
                               "le câble selon son mode de pose (NF C 15-100 partie 5-52, guide UTE C 15-105)",
    "nfc15100.lighting_points": "{points} points sur un circuit d'éclairage (max {limit})",
    "nfc15100.lighting_rating": "éclairage protégé par {in_a:g} A (max 16 A)",
    "nfc15100.socket_section": " en {section:g} mm²",
    "nfc15100.socket_points": "{points} socles sur un circuit de prises{where} (max {limit})",
    "nfc15100.heating": "chauffage {total:g} kW sur un circuit {in_a:g} A (max {limit:g} kW)",
    "nfc15100.heating_unprotected": "chauffage {p:g} kW sur un circuit (max {limit:g} kW en 32 A)",
    "nfc15100.rcd_30mA_socket": "{what} : circuit de prises / de recharge non protégé par un différentiel 30 mA",
    "nfc15100.rcd_30mA_dwelling": "{what} : circuit de logement non protégé par un différentiel 30 mA",
    "nfc15100.rcd_type_A": "{what} : différentiel de type A (ou F, B) requis, type AC exclu",
    "nfc15100.rcd_count_single": "un seul dispositif différentiel 30 mA (logements : au moins 2 ; préciser installation.premises pour un autre local)",
    "nfc15100.rcd_count_type_A": "aucun différentiel 30 mA de type A (logements : au moins 1 ; préciser installation.premises pour un autre local)",
    "nfc15100.rcd_circuits": "{count} circuits sur un ID 30 mA (max 8)",
    "nfc15100.dedicated_single": "{what} : doit être seul sur son circuit ({prot} alimente aussi {others})",
    "nfc15100.dedicated_shared": "{what} : circuit spécialisé partagé avec un autre usage",
    "nfc15100.ev_default": "IRVE",
    "nfc15100.ev_mode2_3ph": "{what} : mode 2 triphasé, DDR de type B requis",
    "nfc15100.ev_mode3": "{what} : mode 3 avec DDR type {rtype}, la borne doit intégrer une détection de courant "
                         "continu 6 mA (DD-CDC, IEC 62955), sinon type B",
    "nfc15100.selectivity": "différentiel en amont d'autres différentiels et non sélectif (type S)",
    "nfc15100.circuit_section": "{what} : {section:g} mm² (au moins {need:g} mm² pour ce circuit)",
    "nfc15100.circuit_rating": "{what} : protégé par {in_a:g} A (au plus {need:g} A pour ce circuit)",
    "nfc15100.rcd_rating": "différentiel 30 mA de {in_a:g} A, sous les {need:g} A requis par les circuits en aval",
    "nfc15100.rcd_spread_lighting": "les {count} circuits d'éclairage sont tous derrière le même différentiel "
                                    "30 mA (les répartir sur au moins 2)",
    "nfc15100.rcd_spread_socket": "les {count} circuits de prises sont tous derrière le même différentiel 30 mA "
                                  "(les répartir sur au moins 2)",
    "nfc15100.spd_rcd": "{what} : le parafoudre de tête ne doit pas être derrière un différentiel 30 mA",
    "nfc15100.agcp_rcd_adjustable": "{what} : sensibilité réglable interdite en branchement à puissance limitée",
    "nfc15100.agcp_rcd_max": "{what} : {idn:g} mA, au plus 500 mA en branchement à puissance limitée",
    "nfc15100.earth_resistance": "prise de terre de {r:g} Ω avec un différentiel de {idn:g} mA : {limit:g} Ω au "
                                 "plus (50 V)",
    "nfc15100.neutral_pole": "{what} : disjoncteur 1P sur un circuit avec neutre, qu'il ne sectionne pas (1P+N "
                             "ou 2P)",
    "nfc15100.supply_section": "liaison vers le tableau principal en {section:g} mm² avec un AGCP de {in_a:g} A "
                               "(au moins {need:g} mm² cuivre)",
    "vde0100.rcd_30mA_socket": "{what} : circuit de prises jusqu'à 32 A non protégé par un différentiel de 30 mA au plus",
    "vde0100.rcd_30mA_lighting": "{what} : circuit d'éclairage d'un logement non protégé par un différentiel de 30 mA au plus",
    "vde0100.bathroom": "{what} : circuit d'une pièce avec baignoire ou douche non protégé par un différentiel de 30 mA "
                        "au plus",
    "vde0100.ev_own_circuit": "{what} : un point de recharge a son propre circuit terminal (d'autres charges sur sa "
                              "protection)",
    "vde0100.ev_no_rcd": "{what} : point de recharge non protégé par un différentiel de 30 mA au plus",
    "vde0100.ev_own_rcd": "{what} : un point de recharge a son propre différentiel (celui-ci protège d'autres charges)",
    "vde0100.ev_rcd_type": "{what} : différentiel type {rtype} : type B, ou type A / F avec détection de courant continu "
                           "6 mA dans le point de recharge, requis",
    "vde0100.ev_rdc_dd": "{what} : différentiel type {rtype} : le point de recharge doit intégrer une détection de "
                         "courant continu 6 mA (RDC-DD, IEC 62955), sinon un différentiel type B",
    "vde0100.spd": "aucun parafoudre : requis pour la plupart des bâtiments (DIN VDE 0100-443 / -534)",
    "vde0100.pen_section": "conducteur PEN de {section:g} mm² {material} : {minimum:g} mm² au moins requis",
    "enedis.single_phase_max": "{kva:g} kVA en monophasé : un branchement monophasé à puissance limitée porte "
                               "12 kVA au plus, il faut un branchement triphasé",
    "enedis.monitored": "{kva:g} kVA : branchement à puissance surveillée (37 à 250 kVA), les paliers de réglage "
                        "de l'AGCP des branchements à puissance limitée ne s'appliquent pas",
    "enedis.mv": "{kva:g} kVA : au-delà de 250 kVA, le raccordement se fait en HTA",
    "enedis.dwelling_min": "{kva:g} kVA dans un logement : les branchements à puissance limitée des logements "
                           "commencent à 6 kVA",
    "enedis.agcp_max": "disjoncteur de branchement réglé à {in_a:g} A : un branchement à puissance limitée est "
                       "réglé à 60 A au plus",
    "enedis.agcp_low": "disjoncteur de branchement réglé à {in_a:g} A, soit {pr:g} kVA, sous les {kva:g} kVA "
                       "souscrits : il déclencherait avant la puissance souscrite",
    "enedis.agcp_no_rcd": "disjoncteur de branchement non différentiel : la NF C 14-100 préconise 500 mA dans le "
                          "neuf (non différentiel sur demande écrite à Enedis)",
    "enedis.agcp_rcd_value": "disjoncteur de branchement différentiel {idn:g} mA : la NF C 14-100 préconise 500 mA",
    "enedis.prod_installed_1p": "{kva:g} kVA de production et de stockage en monophasé ({what}) : au-delà de "
                                "18 kVA de puissance installée, il faut un branchement triphasé",
    "enedis.prod_injection_1p": "{kva:g} kVA de production et de stockage en monophasé ({what}) : l'injection est "
                                "limitée à 6 kVA (brider l'injection ou passer en triphasé)",
    "enedis.prod_installed_3p": "{kva:g} kVA de production et de stockage ({what}) : la puissance installée est "
                                "limitée à 250 kVA en basse tension",
    "enedis.prod_above_36": "{kva:g} kVA de production et de stockage ({what}) : une injection au-delà de 36 kVA "
                            "suit la procédure de raccordement des installations de plus de 36 kVA",
    "enedis.service_cable_length": "dérivation individuelle de {length:g} m : un branchement à puissance limitée "
                                   "admet 30 m au plus (variation de tension dans les 2 %)",
    "enedis.service_cable_section": "dérivation individuelle en {section:g} mm² : la section normalisée est "
                                    "35 mm² aluminium (2 x 35 en monophasé, 4 x 35 en triphasé)",
    "enedis.decoupling": "{what} : préciser sa protection de découplage, obligatoire pour la production et le "
                         "stockage (`protection`, par ex. NF EN 50549-1 / NF EN 50549-10)",
    "cli.description": "Format uniwire : validation, vérification des règles et dessin des schémas électriques (unifilaires et multifilaires)",
    "cli.help.validate": "valider un ou plusieurs documents",
    "cli.help.check": "valider puis appliquer les règles (profils)",
    "cli.help.profile": "profil(s) à appliquer (défaut : ceux du document)",
    "cli.help.render": "générer les folios",
    "cli.help.format": "format de sortie",
    "cli.help.out_render": "dossier (svg) ou fichier (pdf)",
    "cli.help.view": "identifiant de vue",
    "cli.help.kind": "type de vue : 'multi-line' dessine le schéma multifilaire de puissance même si le document ne déclare pas cette vue",
    "cli.help.schema": "écrire le JSON Schema",
    "cli.help.graph": "exporter le graphe bornes / nœuds de connexion (JSON)",
    "cli.help.bom": "nomenclature (références matérielles) au format CSV",
    "cli.help.symbols": "planche SVG de tous les symboles",
    "cli.help.normalize": "réécrire le document résolu (modèles appliqués, ids attribués)",
    "cli.invalid_document": "{path}: document invalide",
    "cli.findings": "{path}: {count} remarque(s)",
    "cli.help.card": "afficher la fiche de référence du format (pour assistants LLM)",
    "cli.help.card_full": "fiche complète (descriptions des champs) au lieu de la fiche compacte",
    "cli.help.lang": "langue : en ou fr (défaut : UNIWIRE_LANG)",
    "cli.help.version": "afficher les versions de la bibliothèque et du format, puis quitter",
    "cli.help.describe": "afficher un résumé textuel d'un document (ids stables, calibres, liens, remarques)",
    "cli.help.link": "afficher un lien qui ouvre le document dans l'éditeur web (dessin, remarques, PDF)",
    "cli.help.link_pdf": "le lien télécharge aussi le PDF",
    "cli.help.patch": "appliquer des opérations d'édition par id (liste JSON) et valider le résultat",
    "cli.help.ops": "fichier JSON contenant la liste des opérations ('-' = entrée standard)",
    "cli.help.out_patch": "fichier de sortie (défaut : sortie standard)",
    "cli.patch_failed": "{path}: échec du patch",
    "cli.patch_op": "opération n° {index}",
    "cli.patch_result": "document obtenu",
    "cli.help.wires": "liste des fils en CSV : une ligne par conducteur des câbles de l'arbre de puissance, avec son "
                      "repère, puis une par fil déclaré",
    "cli.help.terminals": "plan de bornier en CSV : une ligne par borne de chaque bornier, dans l'ordre de montage",
    "cli.help.strip": "seulement ce bornier (id ou repère)",
    "cli.help.wires_all": "inclure les connexions de puissance implicites (toujours le cas au format actuel)",
    "cli.help.markers": "liste des repères de fils en CSV (manchons : une ligne par extrémité de fil, quantités)",
    "cli.help.cables": "carnet de câbles en CSV (une ligne par câble)",
    "cli.help.marks": "afficher les repères de fils d'une vue ; --write les fige dans le fichier ('marks' des câbles)",
    "cli.help.marks_write": "écrire les repères générés dans les 'marks' des câbles (figeage), pour que les modifications ultérieures ne les renumérotent pas",
    "cli.help.out_marks": "avec --write : fichier de sortie (défaut : le fichier d'entrée, réécrit)",
    "cli.help.view_marking": "vue dont les règles 'wire_marking' s'appliquent (défaut : la première vue qui en a)",
    "cli.marks_manual": "(manuel)",
    "cli.marks_written": "{count} repère(s) écrit(s) dans {path}",
    "cli.marks_skipped": "{cable} : câble donné uniquement par un modèle, repères non écrits",
    "bom.headers": "Fabricant;Référence;Gamme;Désignation;Type;Quantité;Repères",
    "bom.accessory": "accessoire",
    "render.unknown_view": "vue inconnue : {id}",
    "render.incoming_from": "depuis {ref}",
    "render.incoming": "arrivée",
    "render.incoming_folio": "{what} (folio {folio})",
    "render.default_title": "Schéma unifilaire général",
    "render.multiline_title": "Schéma multifilaire de puissance",
    "render.continued_from": "{label} (suite folio {folio})",
    "render.continued_on": "suite folio {folio}",
    "render.continuation_name": "{name} (suite)",
    "render.to_folio": " → folio {folio}",
    "label.rcd_type": "type {type}",
    "label.safety": "Circuit de sécurité",
    "render.auxiliary_devices": "Dispositifs annexes",
    "render.scale": "échelle {scale}",
    "render.pdf_missing": "Sortie PDF : installer l'extra 'uniwire[pdf]' (reportlab)",
    "render.sheet_bookmark": "Folio {number} : {title}",
    "render.sheet_bookmark_untitled": "Folio {number}",
    "legend.conductors": "Conducteurs ({standard})",
    "legend.preset.iec": "CEI 60445",
    "legend.preset.us": "pratique NEC",
    "legend.phase": "Phases",
    "legend.multi_phase": "polyphasé",
    "legend.source": "Sources d'alimentation",
    "legend.status": "État",
    "legend.status.new": "neuf",
    "legend.status.existing": "existant",
    "legend.status.future": "futur",
    "legend.status.temporary": "provisoire",
    "legend.status.removed": "déposé",
    "legend.status.spare": "réserve",
    "legend.voltage": "Tension",
    "legend.voltage.mv": "HTA (> 1 kV CA)",
    "legend.voltage.lv": "BT",
    "legend.voltage.elv": "TBT (≤ 50 V CA)",
    "legend.voltage.dc": "Courant continu",
    "tb.title": "Titre",
    "tb.sheet_title": "Folio",
    "tb.default_sheet_title": "Schéma unifilaire",
    "tb.project": "Affaire",
    "tb.client": "Client",
    "tb.earthing": "Régime de neutre",
    "tb.voltage": "Tension",
    "tb.power": "Puissance",
    "tb.ik_max": "Ik max",
    "tb.earth_electrode": "Prise de terre",
    "tb.standard": "Norme",
    "tb.drawn_by": "Établi par",
    "tb.checked_by": "Vérifié",
    "tb.company": "Société",
    "tb.date": "Date",
    "tb.revision": "Indice",
    "tb.sheet": "Folio",
    "tb.generated_by": "Généré par",
    "notes.title": "Notes",
    "notes.site": "Site : {site}",
    "notes.supply": "Alimentation : {supply}",
    "notes.revision": "Ind. {index} {date} {description}",
    "notes.more": "… (+{count} ligne(s) de notes)",
    "ann.frame": "boîtier {frame} A",
    "ann.off_peak": "J/N (HC)",
    "ann.manual": "manuel",
    "ann.automatic": "auto",
    "ann.peak_power_unit": "Wc",
    "ann.peak_power_kunit": "kWc",
    "ann.modules": "{count} module(s)",
    "ann.normally_open": "NO",
    "ann.locks": "clé {keys}",
    "cell.points_one": "{count} pt",
    "cell.points": "{count} pts",
    "cell.upstream": "{value} (amont)",
    "symbols.page_title": "Symboles uniwire",
    "symbols.heading": "Bibliothèque de symboles uniwire (grille M = 2,5 mm)",
}

#: Russian: the texts printed on drawings (title block, notes, legends, view titles, annotations). Messages
#: without a Russian text (CLI, validation, rules) fall back to English.
RU: dict[str, str] = {
    "render.unknown_view": "неизвестный вид: {id}",
    "render.incoming_from": "от {ref}",
    "render.incoming": "ввод",
    "render.incoming_folio": "{what} (лист {folio})",
    "render.default_title": "Схема электрическая однолинейная",
    "render.multiline_title": "Схема электрическая многолинейная силовых цепей",
    "render.continued_from": "{label} (продолжение с листа {folio})",
    "render.continued_on": "продолжение на листе {folio}",
    "render.continuation_name": "{name} (прод.)",
    "render.to_folio": " → лист {folio}",
    "label.rcd_type": "тип {type}",
    "label.safety": "Цепь систем безопасности",
    "render.auxiliary_devices": "Вспомогательные устройства",
    "render.scale": "масштаб {scale}",
    "render.sheet_bookmark": "Лист {number}: {title}",
    "render.sheet_bookmark_untitled": "Лист {number}",
    "legend.conductors": "Проводники ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "практика NEC",
    "legend.phase": "Фазы",
    "legend.multi_phase": "многофазные",
    "legend.source": "Источники питания",
    "legend.status": "Состояние",
    "legend.status.new": "новое",
    "legend.status.existing": "существующее",
    "legend.status.future": "перспективное",
    "legend.status.temporary": "временное",
    "legend.status.removed": "демонтируемое",
    "legend.status.spare": "резерв",
    "legend.voltage": "Напряжение",
    "legend.voltage.mv": "ВН / СН (> 1 кВ перем.)",
    "legend.voltage.lv": "НН",
    "legend.voltage.elv": "СНН (≤ 50 В перем.)",
    "legend.voltage.dc": "Постоянный ток",
    "tb.title": "Наименование",
    "tb.sheet_title": "Наименование листа",
    "tb.default_sheet_title": "Схема однолинейная",
    "tb.project": "Проект",
    "tb.client": "Заказчик",
    "tb.earthing": "Система заземления",
    "tb.voltage": "Напряжение",
    "tb.power": "Мощность",
    "tb.ik_max": "Iкз макс.",
    "tb.earth_electrode": "Заземлитель",
    "tb.standard": "Стандарт",
    "tb.drawn_by": "Разработал",
    "tb.checked_by": "Проверил",
    "tb.company": "Организация",
    "tb.date": "Дата",
    "tb.revision": "Изм.",
    "tb.sheet": "Лист",
    "tb.generated_by": "Выполнено в",
    "notes.title": "Примечания",
    "notes.site": "Объект: {site}",
    "notes.supply": "Питание: {supply}",
    "notes.revision": "Изм. {index} {date} {description}",
    "notes.more": "… (ещё строк примечаний: {count})",
    "ann.frame": "корпус {frame} А",
    "ann.off_peak": "день/ночь (ночной тариф)",
    "ann.manual": "ручн.",
    "ann.automatic": "авт.",
    "ann.peak_power_unit": "Вт пик",
    "ann.peak_power_kunit": "кВт пик",
    "ann.modules": "модулей: {count}",
    "ann.normally_open": "норм. разомкн.",
    "ann.locks": "ключ {keys}",
    "cell.points_one": "{count} шт.",
    "cell.points": "{count} шт.",
    "cell.upstream": "{value} (выше по цепи)",
    "symbols.page_title": "Символы uniwire",
    "symbols.heading": "Библиотека символов uniwire (сетка M = 2,5 мм)",
    # rule messages
    "rules.unknown_profile": "неизвестный профиль: {profile!r}",
    "rules.no_profile": "профиль правил не применён: проверена только согласованность документа (обозначения, связи, "
                        "блокировки, ступенчатость номиналов), но не аппараты защиты, кабели и УЗО; профили: "
                        "'nfc15100' (Франция), 'vde0100' (Германия), 'iec60364'",
    "rules.standard_not_covered": "ни один профиль правил не охватывает {standard}: проверена только согласованность "
                                  "документа (обозначения, связи, блокировки, ступенчатость номиналов); аппараты защиты, "
                                  "кабели, УЗО и заземление не проверены по {standard}",
    "core.ref_unique": "обозначение {ref!r} уже присвоено элементу {other!r}",
    "core.normalized": "{where}: {field} {old!r} прочитано как {new!r}; записывайте в этой форме",
    "core.normalized_field": "{where}: неизвестное поле {old!r} прочитано как {new!r}; используйте {new!r}",
    "core.transfer_target": "связь 'transfer' должна заканчиваться на переключателе источников (transfer_switch)",
    "core.tie_device": "межсекционная связь без указания аппарата",
    "core.transfer_source": "переключатель источников без второго источника (связь 'transfer')",
    "core.terminal_node": "узел {type} является конечным и ничего не питает: разместите его под аппаратом, через "
                          "который он подключён (защита, преобразователь или инвертор), энергия может идти в обе "
                          "стороны",
    "core.rating_cascade": "номинал {in_a:g} А больше номинала вышестоящей защиты {up} ({up_in_a:g} А)",
    "core.interlock_closed": "блокировка {lock!r}: в нормальном режиме замкнуто элементов: {count} ({members}), "
                             "ключей: {keys}",
    "core.interlock_single": "замок {lock!r} используется одним элементом и не объявлен ни в одной записи 'interlocks': "
                             "он ничего не блокирует",
    "core.interlock_unused": "объявленная блокировка {lock!r}: число элементов ('locks') {count}, ожидается не "
                             "менее 2",
    "core.interlock_duplicate": "блокировка {lock!r} объявлена дважды",
    "core.control_scope": "этот документ описывает цепи управления ({nodes}): uniwire рисует распределение энергии "
                          "(однолинейные и многолинейные схемы), а не схемы управления; катушки, контакты, кнопки и "
                          "ветви цепей здесь только перечислены, а не нарисованы как принципиальная схема управления",
    "plc.duplicate_slots": "повторяющиеся слоты: {slots}",
    "plc.unsorted_slots": "модули не упорядочены по слотам",
    "plc.wago_end": "локальная шина WAGO без концевого модуля (750-600) на последней позиции",
    "plc.wago_feed": "не объявлен модуль подачи питания (750-602...)",
    "plc.port_unreadable": "порт {port!r} не распознан (ожидается 'слот.канал')",
    "plc.port_missing_slot": "порт {port!r}: отсутствует слот {slot}",
    "plc.port_channels": "порт {port!r}: у модуля {module} каналов всего {channels}",
    "plc.coil": "выход {port} ({un_v:g} В) управляет катушкой {coil:g} В: используйте промежуточное реле или релейный "
                "модуль",
    "plc.port_shared": "канал {port} управляет {count} аппаратами",
    "iec60364.install_uncovered": "способ прокладки {install!r} не охвачен (A1, A2, B1, B2, C, E, F, D1/D-duct)",
    "iec60364.iz_unavailable": "Iz недоступен для {material} {insulation} {section:g} мм², способ {method}, {loaded} "
                               "нагруженных проводника",
    "iec60364.iz_exceeded": "защита {rating:g} А > Iz {iz:g} А ({material} {insulation} {section:g} мм², способ "
                            "{method}, {loaded} нагруж. пров., {ambient})",
    "iec60364.ambient_ground": "грунт {t:g} °C",
    "iec60364.ambient_air": "воздух {t:g} °C",
    "iec60364.ambient_default": ", ambient_C не указан",
    "iec60364.ambient_uncovered": "Iz не проверен: температура {ambient:g} °C выше {limit} °C таблицы для способа {method}",
    "iec60364.iz_estimate_exceeded": "для кабеля не указаны материал, изоляция или способ прокладки: оценка для "
                                     "{material} {insulation} {section:g} мм², способ {method}, нагруженных "
                                     "проводников: {loaded}, {t:g} °C: защита {rating:g} А > Iz {iz:g} А; укажите их "
                                     "для точной проверки",
    "iec60364.any_air_method": "наиболее благоприятный в воздухе",
    "iec60364.iz_estimated": "допустимый ток только оценён, кабелей: {count} ({tags}): не указаны материал, "
                             "изоляция или способ прокладки (приняты медь, ПВХ и наиболее благоприятный способ); "
                             "укажите их для точной проверки",
    "iec60364.rcd_30mA_socket": "{what}: розеточная цепь до 32 А не защищена УЗО не более 30 мА",
    "iec60364.rcd_30mA_lighting": "{what}: цепь освещения жилого помещения не защищена УЗО не более 30 мА",
    "nfc15100.section": "автоматический выключатель {in_a:g} А на {section:g} мм² (не более {limit} А)",
    "nfc15100.section_sizing": "автоматический выключатель {in_a:g} А на {section:g} мм²: выше обычных {limit} А, "
                               "проверьте кабель с учётом способа прокладки (NF C 15-100 часть 5-52, руководство "
                               "UTE C 15-105)",
    "nfc15100.lighting_points": "{points} точек на цепи освещения (не более {limit})",
    "nfc15100.lighting_rating": "защита цепи освещения {in_a:g} А (не более 16 А)",
    "nfc15100.socket_section": " при {section:g} мм²",
    "nfc15100.socket_points": "{points} розеток на розеточной цепи{where} (не более {limit})",
    "nfc15100.heating": "отопление {total:g} кВт на цепи {in_a:g} А (не более {limit:g} кВт)",
    "nfc15100.heating_unprotected": "отопление {p:g} кВт на одной цепи (не более {limit:g} кВт при 32 А)",
    "nfc15100.rcd_30mA_socket": "{what}: розеточная / зарядная цепь не защищена УЗО 30 мА",
    "nfc15100.rcd_30mA_dwelling": "{what}: цепь жилого помещения не защищена УЗО 30 мА",
    "nfc15100.rcd_type_A": "{what}: требуется УЗО типа A (или F, B), тип AC исключён",
    "nfc15100.rcd_count_single": "только одно УЗО 30 мА (жильё: не менее 2; для объектов другого назначения укажите "
                                 "installation.premises)",
    "nfc15100.rcd_count_type_A": "нет УЗО 30 мА типа A (жильё: не менее 1; для объектов другого назначения укажите "
                                 "installation.premises)",
    "nfc15100.rcd_circuits": "{count} цепей на одном УЗО 30 мА (не более 8)",
    "nfc15100.dedicated_single": "{what}: должно быть единственным на своей цепи ({prot} питает также {others})",
    "nfc15100.dedicated_shared": "{what}: выделенная цепь используется совместно с другим потребителем",
    "nfc15100.ev_default": "Зарядная станция",
    "nfc15100.ev_mode2_3ph": "{what}: трёхфазный режим 2, требуется УЗО типа B",
    "nfc15100.ev_mode3": "{what}: режим 3 с УЗО типа {rtype}: зарядная станция должна иметь обнаружение постоянного тока "
                         "утечки 6 мА (RDC-DD, IEC 62955), иначе тип B",
    "nfc15100.selectivity": "УЗО установлено выше других УЗО и не является селективным (тип S)",
    "nfc15100.circuit_section": "{what}: {section:g} мм² (не менее {need:g} мм² для этой цепи)",
    "nfc15100.circuit_rating": "{what}: защита {in_a:g} А (не более {need:g} А для этой цепи)",
    "nfc15100.rcd_rating": "УЗО 30 мА на {in_a:g} А, ниже {need:g} А, требуемых нижестоящими цепями",
    "nfc15100.rcd_spread_lighting": "все {count} цепей освещения за одним УЗО 30 мА (распределите их не менее чем на 2)",
    "nfc15100.rcd_spread_socket": "все {count} розеточных цепей за одним УЗО 30 мА (распределите их не менее чем на 2)",
    "nfc15100.spd_rcd": "{what}: УЗИП на вводе не должно стоять за УЗО 30 мА",
    "nfc15100.agcp_rcd_adjustable": "{what}: регулируемая уставка утечки недопустима при подключении ограниченной мощности",
    "nfc15100.agcp_rcd_max": "{what}: {idn:g} мА, не более 500 мА при подключении ограниченной мощности",
    "nfc15100.earth_resistance": "заземлитель {r:g} Ом при УЗО {idn:g} мА: не более {limit:g} Ом (50 В)",
    "nfc15100.neutral_pole": "{what}: однополюсный автомат на цепи с нейтралью, которую он не отключает (1P+N или 2P)",
    "nfc15100.supply_section": "линия до главного щита {section:g} мм² при вводном автомате {in_a:g} А (не менее "
                               "{need:g} мм² меди)",
    "vde0100.rcd_30mA_socket": "{what}: розеточная цепь до 32 А не защищена УЗО не более 30 мА",
    "vde0100.rcd_30mA_lighting": "{what}: цепь освещения жилого помещения не защищена УЗО не более 30 мА",
    "vde0100.bathroom": "{what}: цепь помещения с ванной или душем не защищена УЗО не более 30 мА",
    "vde0100.ev_own_circuit": "{what}: зарядной точке нужна собственная конечная цепь (другие потребители на её защите)",
    "vde0100.ev_no_rcd": "{what}: зарядная точка не защищена УЗО не более 30 мА",
    "vde0100.ev_own_rcd": "{what}: зарядной точке нужно собственное УЗО (это УЗО защищает и другие потребители)",
    "vde0100.ev_rcd_type": "{what}: УЗО типа {rtype}: требуется тип B или тип A / F с обнаружением постоянного тока "
                           "утечки 6 мА в зарядной точке",
    "vde0100.ev_rdc_dd": "{what}: УЗО типа {rtype}: зарядная точка должна иметь обнаружение постоянного тока утечки 6 мА "
                         "(RDC-DD, IEC 62955), иначе УЗО типа B",
    "vde0100.spd": "нет УЗИП: требуется для большинства зданий (DIN VDE 0100-443 / -534)",
    "vde0100.pen_section": "PEN-проводник {section:g} мм² {material}: требуется не менее {minimum:g} мм²",
    "enedis.single_phase_max": "{kva:g} кВА в однофазной сети: однофазное подключение ограниченной мощности допускает не "
                               "более 12 кВА, нужно трёхфазное подключение",
    "enedis.monitored": "{kva:g} кВА: подключение с контролируемой мощностью (от 37 до 250 кВА), ступени уставки AGCP для "
                        "подключений ограниченной мощности не применяются",
    "enedis.mv": "{kva:g} кВА: свыше 250 кВА подключение выполняется на среднем напряжении (HTA)",
    "enedis.dwelling_min": "{kva:g} кВА в жилом помещении: подключения ограниченной мощности для жилья начинаются с 6 кВА",
    "enedis.agcp_max": "уставка вводного автомата {in_a:g} А: при подключении ограниченной мощности уставка не "
                       "более 60 А",
    "enedis.agcp_low": "вводной автомат на {in_a:g} А пропускает {pr:g} кВА, меньше договорных {kva:g} кВА: он "
                       "сработает до достижения договорной мощности",
    "enedis.agcp_no_rcd": "вводной автомат без дифференциальной защиты: NF C 14-100 рекомендует 500 мА в новых зданиях "
                          "(автомат без дифзащиты по запросу в Enedis)",
    "enedis.agcp_rcd_value": "вводной автомат с дифференциальной защитой {idn:g} мА: NF C 14-100 рекомендует 500 мА",
    "enedis.prod_installed_1p": "{kva:g} кВА генерации и накопления в однофазной сети ({what}): свыше 18 кВА "
                                "установленной мощности нужно трёхфазное подключение",
    "enedis.prod_injection_1p": "{kva:g} кВА генерации и накопления в однофазной сети ({what}): выдача в сеть ограничена "
                                "6 кВА (ограничьте выдачу или подключитесь трёхфазно)",
    "enedis.prod_installed_3p": "{kva:g} кВА генерации и накопления ({what}): установленная мощность на низком напряжении "
                                "ограничена 250 кВА",
    "enedis.prod_above_36": "{kva:g} кВА генерации и накопления ({what}): выдача свыше 36 кВА следует процедуре "
                            "подключения установок свыше 36 кВА",
    "enedis.service_cable_length": "индивидуальный ввод длиной {length:g} м: подключения ограниченной мощности "
                                   "допускают не более 30 м (падение напряжения не более 2 %)",
    "enedis.service_cable_section": "индивидуальный ввод сечением {section:g} мм²: стандартное сечение 35 мм² по "
                                    "алюминию (2 x 35 однофазный, 4 x 35 трёхфазный)",
    "enedis.decoupling": "{what}: укажите делительную защиту (отделение от сети), обязательную для генерации и "
                         "накопления (`protection`, напр. NF EN 50549-1 / NF EN 50549-10)",
}

#: Simplified Chinese: the drawing texts, as RU (terms of IEC 60050 and the GB/T standards adopting IEC ones).
ZH: dict[str, str] = {
    "render.unknown_view": "未知视图：{id}",
    "render.incoming_from": "来自 {ref}",
    "render.incoming": "进线",
    "render.incoming_folio": "{what}（第 {folio} 张）",
    "render.default_title": "配电系统单线图",
    "render.multiline_title": "主回路多线图",
    "render.continued_from": "{label}（接自第 {folio} 张）",
    "render.continued_on": "续见第 {folio} 张",
    "render.continuation_name": "{name}（续）",
    "render.to_folio": " → 第 {folio} 张",
    "label.rcd_type": "{type}型",
    "label.safety": "安全设施回路",
    "render.auxiliary_devices": "辅助设备",
    "render.scale": "比例 {scale}",
    "render.sheet_bookmark": "第 {number} 张：{title}",
    "render.sheet_bookmark_untitled": "第 {number} 张",
    "legend.conductors": "导体（{standard}）",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "NEC 惯例",
    "legend.phase": "相线",
    "legend.multi_phase": "多相",
    "legend.source": "电源",
    "legend.status": "状态",
    "legend.status.new": "新建",
    "legend.status.existing": "现有",
    "legend.status.future": "远期",
    "legend.status.temporary": "临时",
    "legend.status.removed": "拆除",
    "legend.status.spare": "备用",
    "legend.voltage": "电压",
    "legend.voltage.mv": "高压（交流 > 1 kV）",
    "legend.voltage.lv": "低压",
    "legend.voltage.elv": "特低电压（交流 ≤ 50 V）",
    "legend.voltage.dc": "直流",
    "tb.title": "图名",
    "tb.sheet_title": "本张图名",
    "tb.default_sheet_title": "单线图",
    "tb.project": "工程名称",
    "tb.client": "建设单位",
    "tb.earthing": "接地型式",
    "tb.voltage": "电压",
    "tb.power": "容量",
    "tb.ik_max": "最大短路电流",
    "tb.earth_electrode": "接地极",
    "tb.standard": "标准",
    "tb.drawn_by": "制图",
    "tb.checked_by": "校核",
    "tb.company": "设计单位",
    "tb.date": "日期",
    "tb.revision": "版次",
    "tb.sheet": "张次",
    "tb.generated_by": "生成工具",
    "notes.title": "说明",
    "notes.site": "地点：{site}",
    "notes.supply": "电源：{supply}",
    "notes.revision": "版次 {index} {date} {description}",
    "notes.more": "…（另有 {count} 行说明）",
    "ann.frame": "壳架 {frame} A",
    "ann.off_peak": "峰谷（谷电）",
    "ann.manual": "手动",
    "ann.automatic": "自动",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "{count} 块组件",
    "ann.normally_open": "常开",
    "ann.locks": "钥匙 {keys}",
    "cell.points_one": "{count} 点",
    "cell.points": "{count} 点",
    "cell.upstream": "{value}（上级）",
    "symbols.page_title": "uniwire 图形符号",
    "symbols.heading": "uniwire 图形符号库（网格 M = 2.5 mm）",
    # rule messages
    "rules.unknown_profile": "未知规则配置：{profile!r}",
    "rules.no_profile": "未应用规则配置：仅检查了文档的一致性（编号、连接、联锁、额定电流逐级配合），未检查保护电器、电缆和剩余电流"
                        "保护器；可用配置：'nfc15100'（法国）、'vde0100'（德国）、'iec60364'",
    "rules.standard_not_covered": "没有规则配置涵盖 {standard}：仅检查了文档的一致性（编号、连接、联锁、额定电流逐级配合）；保护"
                                  "电器、电缆、剩余电流保护器和接地未按 {standard} 检查",
    "core.ref_unique": "编号 {ref!r} 已被 {other!r} 使用",
    "core.normalized": "{where}：{field} {old!r} 被读作 {new!r}；请按此形式书写",
    "core.normalized_field": "{where}：未知字段 {old!r} 被读作 {new!r}；请使用 {new!r}",
    "core.transfer_target": "'transfer' 连接必须终止于转换开关（transfer_switch）",
    "core.tie_device": "母联未描述电器",
    "core.transfer_source": "转换开关没有第二电源（'transfer' 连接）",
    "core.terminal_node": "{type} 节点是末端节点，不应有下级回路：请将其画在连接它的电器（保护电器、变换器或逆变器）之下，"
                          "能量可双向流动",
    "core.rating_cascade": "额定电流 {in_a:g} A 大于上级保护 {up}（{up_in_a:g} A）",
    "core.interlock_closed": "联锁 {lock!r}：正常运行时 {count} 个成员闭合（{members}），钥匙数为 {keys}",
    "core.interlock_single": "锁 {lock!r} 仅被一个成员使用，且未在任何 'interlocks' 条目中声明：不起联锁作用",
    "core.interlock_unused": "已声明的联锁 {lock!r} 被 {count} 个成员使用（'locks'），至少应为 2 个",
    "core.interlock_duplicate": "联锁 {lock!r} 重复声明",
    "core.control_scope": "本文档描述了控制回路（{nodes}）：uniwire 绘制配电（单线图和多线图），而非控制原理图；线圈、触点、按钮"
                          "和电流路径在此仅作概括，不绘制为控制原理图",
    "plc.duplicate_slots": "重复的槽位：{slots}",
    "plc.unsorted_slots": "模块未按槽位排序",
    "plc.wago_end": "WAGO 本地总线最后位置没有终端模块（750-600）",
    "plc.wago_feed": "未声明电位馈电模块（750-602...）",
    "plc.port_unreadable": "端口 {port!r} 无法识别（应为 '槽位.通道'）",
    "plc.port_missing_slot": "端口 {port!r}：缺少槽位 {slot}",
    "plc.port_channels": "端口 {port!r}：模块 {module} 只有 {channels} 个通道",
    "plc.coil": "输出 {port}（{un_v:g} V）驱动 {coil:g} V 线圈：请使用中间继电器或继电器模块",
    "plc.port_shared": "通道 {port} 控制 {count} 个电器",
    "iec60364.install_uncovered": "敷设方式 {install!r} 不在范围内（A1、A2、B1、B2、C、E、F、D1/D-duct）",
    "iec60364.iz_unavailable": "无 Iz 数据：{material} {insulation} {section:g} mm²，方式 {method}，{loaded} 根载流导体",
    "iec60364.iz_exceeded": "保护 {rating:g} A > Iz {iz:g} A（{material} {insulation} {section:g} mm²，方式 {method}，"
                            "{loaded} 根载流导体，{ambient}）",
    "iec60364.ambient_ground": "土壤 {t:g} °C",
    "iec60364.ambient_air": "环境温度 {t:g} °C",
    "iec60364.ambient_default": "，未给出 ambient_C",
    "iec60364.ambient_uncovered": "未校核 Iz：环境温度 {ambient:g} °C 高于敷设方式 {method} 表格的 {limit} °C",
    "iec60364.iz_estimate_exceeded": "电缆未注明导体材料、绝缘或敷设方式：按 {material} {insulation} {section:g} mm²、方式 "
                                     "{method}、{loaded} 根载流导体、{t:g} °C 估算：保护 {rating:g} A > Iz {iz:g} A；请注明以便精确校验",
    "iec60364.any_air_method": "空气中最有利方式",
    "iec60364.iz_estimated": "仅估算了 {count} 根电缆的载流量（{tags}）：缺少导体材料、绝缘或敷设方式（假定为铜、PVC 及最有利的敷设方式）；请注明以便精确校验",
    "iec60364.rcd_30mA_socket": "{what}：32 A 及以下插座回路未由不大于 30 mA 的剩余电流保护器保护",
    "iec60364.rcd_30mA_lighting": "{what}：住宅照明回路未由不大于 30 mA 的剩余电流保护器保护",
    "nfc15100.section": "{in_a:g} A 断路器配 {section:g} mm²（最大 {limit} A）",
    "nfc15100.section_sizing": "{in_a:g} A 断路器配 {section:g} mm²：超过通常的 {limit} A，请按敷设方式校核电缆（NF C 15-100 "
                               "第 5-52 部分，UTE C 15-105 指南）",
    "nfc15100.lighting_points": "照明回路有 {points} 个点（最多 {limit}）",
    "nfc15100.lighting_rating": "照明回路保护电器 {in_a:g} A（最大 16 A）",
    "nfc15100.socket_section": "（{section:g} mm²）",
    "nfc15100.socket_points": "插座回路{where}有 {points} 个插座（最多 {limit}）",
    "nfc15100.heating": "{in_a:g} A 回路带采暖负荷 {total:g} kW（最大 {limit:g} kW）",
    "nfc15100.heating_unprotected": "单一回路带采暖负荷 {p:g} kW（32 A 时最大 {limit:g} kW）",
    "nfc15100.rcd_30mA_socket": "{what}：插座 / 充电回路未由 30 mA 剩余电流保护器保护",
    "nfc15100.rcd_30mA_dwelling": "{what}：住宅回路未由 30 mA 剩余电流保护器保护",
    "nfc15100.rcd_type_A": "{what}：需要 A 型（或 F、B 型）剩余电流保护器，不允许 AC 型",
    "nfc15100.rcd_count_single": "只有一个 30 mA 剩余电流保护器（住宅：至少 2 个；其他场所请设置 installation.premises）",
    "nfc15100.rcd_count_type_A": "没有 30 mA A 型剩余电流保护器（住宅：至少 1 个；其他场所请设置 installation.premises）",
    "nfc15100.rcd_circuits": "一个 30 mA 剩余电流保护器下有 {count} 个回路（最多 8 个）",
    "nfc15100.dedicated_single": "{what}：必须单独占用一个回路（{prot} 还供电给 {others}）",
    "nfc15100.dedicated_shared": "{what}：专用回路与其他用途共用",
    "nfc15100.ev_default": "电动汽车充电桩",
    "nfc15100.ev_mode2_3ph": "{what}：三相模式 2，需要 B 型剩余电流保护器",
    "nfc15100.ev_mode3": "{what}：模式 3 配 {rtype} 型剩余电流保护器：充电桩必须内置 6 mA 直流故障检测（RDC-DD，IEC 62955），否则"
                         "需 B 型",
    "nfc15100.selectivity": "剩余电流保护器位于其他剩余电流保护器上级且不具选择性（S 型）",
    "nfc15100.circuit_section": "{what}：{section:g} mm²（该回路至少 {need:g} mm²）",
    "nfc15100.circuit_rating": "{what}：保护电器 {in_a:g} A（该回路最大 {need:g} A）",
    "nfc15100.rcd_rating": "30 mA 剩余电流保护器额定 {in_a:g} A，低于下级回路要求的 {need:g} A",
    "nfc15100.rcd_spread_lighting": "{count} 个照明回路都接在同一个 30 mA 剩余电流保护器下游（请分配到至少 2 个保护器）",
    "nfc15100.rcd_spread_socket": "{count} 个插座回路都接在同一个 30 mA 剩余电流保护器下游（请分配到至少 2 个保护器）",
    "nfc15100.spd_rcd": "{what}：进线处的浪涌保护器不得装在 30 mA 剩余电流保护器下游",
    "nfc15100.agcp_rcd_adjustable": "{what}：限定功率接入不允许剩余动作电流可调",
    "nfc15100.agcp_rcd_max": "{what}：{idn:g} mA，限定功率接入最大 500 mA",
    "nfc15100.earth_resistance": "接地电阻 {r:g} Ω，配 {idn:g} mA 剩余电流保护器：最大 {limit:g} Ω（50 V）",
    "nfc15100.neutral_pole": "{what}：带中性线回路上的 1P 断路器不能隔离中性线（应为 1P+N 或 2P）",
    "nfc15100.supply_section": "至总配电箱的进线截面 {section:g} mm²，进线断路器 {in_a:g} A（铜芯至少 {need:g} mm²）",
    "vde0100.rcd_30mA_socket": "{what}：32 A 及以下插座回路未由不大于 30 mA 的剩余电流保护器保护",
    "vde0100.rcd_30mA_lighting": "{what}：住宅照明回路未由不大于 30 mA 的剩余电流保护器保护",
    "vde0100.bathroom": "{what}：有浴缸或淋浴的房间的回路未由不大于 30 mA 的剩余电流保护器保护",
    "vde0100.ev_own_circuit": "{what}：充电点需要独立的终端回路（其保护电器上还有其他负载）",
    "vde0100.ev_no_rcd": "{what}：充电点未由不大于 30 mA 的剩余电流保护器保护",
    "vde0100.ev_own_rcd": "{what}：充电点需要独立的剩余电流保护器（该保护器还保护其他负载）",
    "vde0100.ev_rcd_type": "{what}：{rtype} 型剩余电流保护器：需要 B 型，或充电点内置 6 mA 直流故障检测的 A / F 型",
    "vde0100.ev_rdc_dd": "{what}：{rtype} 型剩余电流保护器：充电点必须内置 6 mA 直流故障检测（RDC-DD，IEC 62955），否则需 B 型"
                         "剩余电流保护器",
    "vde0100.spd": "没有浪涌保护器：大多数建筑物要求设置（DIN VDE 0100-443 / -534）",
    "vde0100.pen_section": "PEN 导体 {section:g} mm² {material}：至少需要 {minimum:g} mm²",
    "enedis.single_phase_max": "单相 {kva:g} kVA：单相限定功率接入最多 12 kVA，需要三相接入",
    "enedis.monitored": "{kva:g} kVA：监控功率接入（37 至 250 kVA），限定功率接入的 AGCP 整定档位不适用",
    "enedis.mv": "{kva:g} kVA：超过 250 kVA 需中压（HTA）接入",
    "enedis.dwelling_min": "住宅 {kva:g} kVA：住宅限定功率接入从 6 kVA 起",
    "enedis.agcp_max": "进线断路器整定为 {in_a:g} A：限定功率接入最大整定 60 A",
    "enedis.agcp_low": "进线断路器整定为 {in_a:g} A，对应 {pr:g} kVA，低于合同容量 {kva:g} kVA：会在达到合同容量前跳闸",
    "enedis.agcp_no_rcd": "进线断路器无剩余电流保护：NF C 14-100 建议新建筑采用 500 mA（可向 Enedis 申请无剩余电流保护的断路器）",
    "enedis.agcp_rcd_value": "进线断路器剩余电流保护为 {idn:g} mA：NF C 14-100 建议 500 mA",
    "enedis.prod_installed_1p": "单相发电和储能 {kva:g} kVA（{what}）：装机功率超过 18 kVA 需要三相接入",
    "enedis.prod_injection_1p": "单相发电和储能 {kva:g} kVA（{what}）：上网功率限制为 6 kVA（限制输出或改为三相接入）",
    "enedis.prod_installed_3p": "发电和储能 {kva:g} kVA（{what}）：低压装机功率限制为 250 kVA",
    "enedis.prod_above_36": "发电和储能 {kva:g} kVA（{what}）：上网功率超过 36 kVA 需按 36 kVA 以上装置的接入程序办理",
    "enedis.service_cable_length": "单独进户电缆长 {length:g} m：限定功率接入最长 30 m（电压降不超过 2 %）",
    "enedis.service_cable_section": "单独进户电缆截面 {section:g} mm²：标准截面为铝 35 mm²（单相 2 x 35，三相 4 x 35）",
    "enedis.decoupling": "{what}：请注明其解列保护，发电和储能必须设置（`protection`，例如 NF EN 50549-1 / NF EN 50549-10）",
}

#: Spanish: the drawing texts, as RU (IEC 60050 terms; where Spain and Argentina differ, a neutral term).
ES: dict[str, str] = {
    "render.unknown_view": "vista desconocida: {id}",
    "render.incoming_from": "desde {ref}",
    "render.incoming": "entrada",
    "render.incoming_folio": "{what} (hoja {folio})",
    "render.default_title": "Esquema unifilar general",
    "render.multiline_title": "Esquema multifilar de potencia",
    "render.continued_from": "{label} (viene de la hoja {folio})",
    "render.continued_on": "continúa en la hoja {folio}",
    "render.continuation_name": "{name} (cont.)",
    "render.to_folio": " → hoja {folio}",
    "label.rcd_type": "tipo {type}",
    "label.safety": "Circuito de seguridad",
    "render.auxiliary_devices": "Dispositivos auxiliares",
    "render.scale": "escala {scale}",
    "render.sheet_bookmark": "Hoja {number}: {title}",
    "render.sheet_bookmark_untitled": "Hoja {number}",
    "legend.conductors": "Conductores ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "práctica NEC",
    "legend.phase": "Fases",
    "legend.multi_phase": "polifásico",
    "legend.source": "Fuentes de alimentación",
    "legend.status": "Estado",
    "legend.status.new": "nuevo",
    "legend.status.existing": "existente",
    "legend.status.future": "futuro",
    "legend.status.temporary": "provisional",
    "legend.status.removed": "a desmontar",
    "legend.status.spare": "reserva",
    "legend.voltage": "Tensión",
    "legend.voltage.mv": "AT / MT (> 1 kV CA)",
    "legend.voltage.lv": "BT",
    "legend.voltage.elv": "MBT (≤ 50 V CA)",
    "legend.voltage.dc": "Corriente continua",
    "tb.title": "Título",
    "tb.sheet_title": "Título de hoja",
    "tb.default_sheet_title": "Esquema unifilar",
    "tb.project": "Proyecto",
    "tb.client": "Cliente",
    "tb.earthing": "Esquema de conexión a tierra",
    "tb.voltage": "Tensión",
    "tb.power": "Potencia",
    "tb.ik_max": "Icc máx.",
    "tb.earth_electrode": "Toma de tierra",
    "tb.standard": "Norma",
    "tb.drawn_by": "Dibujado",
    "tb.checked_by": "Revisado",
    "tb.company": "Empresa",
    "tb.date": "Fecha",
    "tb.revision": "Rev.",
    "tb.sheet": "Hoja",
    "tb.generated_by": "Generado con",
    "notes.title": "Notas",
    "notes.site": "Ubicación: {site}",
    "notes.supply": "Alimentación: {supply}",
    "notes.revision": "Rev. {index} {date} {description}",
    "notes.more": "… (+{count} línea(s) de notas)",
    "ann.frame": "caja {frame} A",
    "ann.off_peak": "día/noche (tarifa reducida)",
    "ann.manual": "manual",
    "ann.automatic": "automático",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "{count} módulo(s)",
    "ann.normally_open": "NA",
    "ann.locks": "llave {keys}",
    "cell.points_one": "{count} punto",
    "cell.points": "{count} puntos",
    "cell.upstream": "{value} (aguas arriba)",
    "symbols.page_title": "Símbolos uniwire",
    "symbols.heading": "Biblioteca de símbolos uniwire (cuadrícula M = 2,5 mm)",
    # rule messages
    "rules.unknown_profile": "perfil desconocido: {profile!r}",
    "rules.no_profile": "ningún perfil de reglas aplicado: solo se verificó la coherencia del documento (designaciones, "
                        "enlaces, enclavamientos, calibres en cascada), no las protecciones, los cables ni los "
                        "diferenciales; perfiles: 'nfc15100' (Francia), 'vde0100' (Alemania), 'iec60364'",
    "rules.standard_not_covered": "ningún perfil de reglas cubre {standard}: solo se verificó la coherencia del documento "
                                  "(designaciones, enlaces, enclavamientos, calibres en cascada); las protecciones, los "
                                  "cables, los diferenciales y la puesta a tierra no se verificaron según {standard}",
    "core.ref_unique": "designación {ref!r} ya usada por {other!r}",
    "core.normalized": "{where}: {field} {old!r} leído como {new!r}; escribirlo de esta forma",
    "core.normalized_field": "{where}: campo desconocido {old!r} leído como {new!r}; usar {new!r}",
    "core.transfer_target": "un enlace 'transfer' debe terminar en un conmutador de transferencia (transfer_switch)",
    "core.tie_device": "acoplamiento sin aparato descrito",
    "core.transfer_source": "conmutador de transferencia sin segunda fuente (enlace 'transfer')",
    "core.terminal_node": "un nodo {type} es una hoja y no alimenta nada: colocarlo bajo el aparato que lo conecta "
                          "(su protección, convertidor o inversor), la energía puede circular en ambos sentidos",
    "core.rating_cascade": "calibre {in_a:g} A superior a la protección aguas arriba {up} ({up_in_a:g} A)",
    "core.interlock_closed": "enclavamiento {lock!r}: {count} miembros cerrados en servicio normal ({members}) para {keys} "
                             "llave(s)",
    "core.interlock_single": "la cerradura {lock!r} la usa un solo miembro y no está declarada en ninguna entrada "
                             "'interlocks': no enclava nada",
    "core.interlock_unused": "el enclavamiento declarado {lock!r} lo usan {count} miembro(s) ('locks'), se esperan al "
                             "menos 2",
    "core.interlock_duplicate": "enclavamiento {lock!r} declarado dos veces",
    "core.control_scope": "este documento describe circuitos de mando ({nodes}): uniwire dibuja la distribución de "
                          "potencia (esquemas unifilar y multifilar), no esquemas de mando; bobinas, contactos, pulsadores "
                          "y caminos de corriente solo se resumen aquí, no se dibujan como esquema de mando",
    "plc.duplicate_slots": "ranuras duplicadas: {slots}",
    "plc.unsorted_slots": "módulos no ordenados por ranura",
    "plc.wago_end": "bus local WAGO sin módulo final (750-600) en última posición",
    "plc.wago_feed": "ningún módulo de alimentación de potencial (750-602...) declarado",
    "plc.port_unreadable": "puerto {port!r} ilegible (se espera 'ranura.canal')",
    "plc.port_missing_slot": "puerto {port!r}: falta la ranura {slot}",
    "plc.port_channels": "puerto {port!r}: el módulo {module} solo tiene {channels} canales",
    "plc.coil": "la salida {port} ({un_v:g} V) acciona una bobina de {coil:g} V: usar un relé de interfaz o un "
                "módulo de relés",
    "plc.port_shared": "el canal {port} controla {count} aparatos",
    "iec60364.install_uncovered": "método de instalación {install!r} no cubierto (A1, A2, B1, B2, C, E, F, D1/D-duct)",
    "iec60364.iz_unavailable": "Iz no disponible para {material} {insulation} {section:g} mm² método {method}, {loaded} "
                               "conductores cargados",
    "iec60364.iz_exceeded": "protección {rating:g} A > Iz {iz:g} A ({material} {insulation} {section:g} mm², método "
                            "{method}, {loaded} cond. cargados, {ambient})",
    "iec60364.ambient_ground": "terreno {t:g} °C",
    "iec60364.ambient_air": "ambiente {t:g} °C",
    "iec60364.ambient_default": ", ambient_C no indicado",
    "iec60364.ambient_uncovered": "Iz no comprobado: ambiente {ambient:g} °C por encima de los {limit} °C de la tabla para el método {method}",
    "iec60364.iz_estimate_exceeded": "el cable no indica material, aislamiento o método de instalación: estimación "
                                     "con {material} {insulation} {section:g} mm², método {method}, {loaded} "
                                     "conductores cargados, {t:g} °C: protección {rating:g} A > Iz {iz:g} A; "
                                     "indíquelos para una comprobación exacta",
    "iec60364.any_air_method": "el más favorable al aire",
    "iec60364.iz_estimated": "intensidad admisible solo estimada para {count} cable(s) ({tags}): falta material, "
                             "aislamiento o método de instalación (se suponen cobre, PVC y el método más "
                             "favorable); indíquelos para una comprobación exacta",
    "iec60364.rcd_30mA_socket": "{what}: circuito de tomas de hasta 32 A no protegido por un diferencial de 30 mA "
                                "como máximo",
    "iec60364.rcd_30mA_lighting": "{what}: circuito de iluminación de una vivienda no protegido por un diferencial "
                                  "de 30 mA como máximo",
    "nfc15100.section": "interruptor automático de {in_a:g} A en {section:g} mm² (máx. {limit} A)",
    "nfc15100.section_sizing": "interruptor automático de {in_a:g} A en {section:g} mm²: por encima de los {limit} A "
                               "habituales, verificar el cable según su método de instalación (NF C 15-100 parte 5-52, "
                               "guía UTE C 15-105)",
    "nfc15100.lighting_points": "{points} puntos en un circuito de iluminación (máx. {limit})",
    "nfc15100.lighting_rating": "iluminación protegida a {in_a:g} A (máx. 16 A)",
    "nfc15100.socket_section": " en {section:g} mm²",
    "nfc15100.socket_points": "{points} tomas en un circuito de tomas de corriente{where} (máx. {limit})",
    "nfc15100.heating": "calefacción de {total:g} kW en un circuito de {in_a:g} A (máx. {limit:g} kW)",
    "nfc15100.heating_unprotected": "calefacción de {p:g} kW en un circuito (máx. {limit:g} kW a 32 A)",
    "nfc15100.rcd_30mA_socket": "{what}: circuito de tomas / de recarga no protegido por un diferencial de 30 mA",
    "nfc15100.rcd_30mA_dwelling": "{what}: circuito de vivienda no protegido por un diferencial de 30 mA",
    "nfc15100.rcd_type_A": "{what}: diferencial tipo A (o F, B) requerido, tipo AC excluido",
    "nfc15100.rcd_count_single": "un solo diferencial de 30 mA (viviendas: al menos 2; indicar installation.premises para "
                                 "otros locales)",
    "nfc15100.rcd_count_type_A": "ningún diferencial de 30 mA tipo A (viviendas: al menos 1; indicar "
                                 "installation.premises para otros locales)",
    "nfc15100.rcd_circuits": "{count} circuitos en un diferencial de 30 mA (máx. 8)",
    "nfc15100.dedicated_single": "{what}: debe estar solo en su circuito ({prot} también alimenta {others})",
    "nfc15100.dedicated_shared": "{what}: circuito dedicado compartido con otro uso",
    "nfc15100.ev_default": "Punto de recarga",
    "nfc15100.ev_mode2_3ph": "{what}: modo 2 trifásico, diferencial tipo B requerido",
    "nfc15100.ev_mode3": "{what}: modo 3 con diferencial tipo {rtype}: el punto de recarga debe integrar una "
                         "detección de corriente continua de 6 mA (RDC-DD, IEC 62955); de lo contrario, diferencial "
                         "tipo B",
    "nfc15100.selectivity": "diferencial aguas arriba de otros diferenciales y no selectivo (tipo S)",
    "nfc15100.circuit_section": "{what}: {section:g} mm² (al menos {need:g} mm² para este circuito)",
    "nfc15100.circuit_rating": "{what}: protegido a {in_a:g} A (como máximo {need:g} A para este circuito)",
    "nfc15100.rcd_rating": "diferencial de 30 mA de {in_a:g} A, por debajo de los {need:g} A que requieren los circuitos "
                           "aguas abajo",
    "nfc15100.rcd_spread_lighting": "los {count} circuitos de iluminación están todos aguas abajo del mismo "
                                    "diferencial de 30 mA (repartirlos en al menos 2)",
    "nfc15100.rcd_spread_socket": "los {count} circuitos de tomas están todos aguas abajo del mismo diferencial de "
                                  "30 mA (repartirlos en al menos 2)",
    "nfc15100.spd_rcd": "{what}: el protector contra sobretensiones en el origen no debe estar aguas abajo de un "
                        "diferencial de 30 mA",
    "nfc15100.agcp_rcd_adjustable": "{what}: la sensibilidad regulable no se admite en un suministro de potencia limitada",
    "nfc15100.agcp_rcd_max": "{what}: {idn:g} mA, como máximo 500 mA en un suministro de potencia limitada",
    "nfc15100.earth_resistance": "toma de tierra de {r:g} Ω con un diferencial de {idn:g} mA: como máximo {limit:g} Ω (50 V)",
    "nfc15100.neutral_pole": "{what}: interruptor automático 1P en un circuito con neutro, que no secciona (1P+N o 2P)",
    "nfc15100.supply_section": "derivación al cuadro principal en {section:g} mm² con un interruptor general de {in_a:g} A "
                               "(al menos {need:g} mm² de cobre)",
    "vde0100.rcd_30mA_socket": "{what}: circuito de tomas de hasta 32 A no protegido por un diferencial de 30 mA como "
                               "máximo",
    "vde0100.rcd_30mA_lighting": "{what}: circuito de iluminación de una vivienda no protegido por un diferencial "
                                 "de 30 mA como máximo",
    "vde0100.bathroom": "{what}: circuito de un cuarto con bañera o ducha no protegido por un diferencial de 30 mA como "
                        "máximo",
    "vde0100.ev_own_circuit": "{what}: un punto de recarga necesita su propio circuito terminal (hay otras cargas "
                              "en su protección)",
    "vde0100.ev_no_rcd": "{what}: punto de recarga no protegido por un diferencial de 30 mA como máximo",
    "vde0100.ev_own_rcd": "{what}: un punto de recarga necesita su propio diferencial (el diferencial protege también otras "
                          "cargas)",
    "vde0100.ev_rcd_type": "{what}: diferencial tipo {rtype}: se requiere tipo B, o tipo A / F con detección de corriente "
                           "continua de 6 mA en el punto de recarga",
    "vde0100.ev_rdc_dd": "{what}: diferencial tipo {rtype}: el punto de recarga debe integrar una detección de "
                         "corriente continua de 6 mA (RDC-DD, IEC 62955); de lo contrario, un diferencial tipo B",
    "vde0100.spd": "ningún protector contra sobretensiones: requerido en la mayoría de los edificios (DIN VDE 0100-443 / "
                   "-534)",
    "vde0100.pen_section": "conductor PEN de {section:g} mm² {material}: se requieren al menos {minimum:g} mm²",
    "enedis.single_phase_max": "{kva:g} kVA en monofásico: un suministro monofásico de potencia limitada admite 12 kVA "
                               "como máximo, se necesita un suministro trifásico",
    "enedis.monitored": "{kva:g} kVA: suministro de potencia vigilada (37 a 250 kVA), los escalones de ajuste del AGCP de "
                        "los suministros de potencia limitada no se aplican",
    "enedis.mv": "{kva:g} kVA: por encima de 250 kVA el suministro es en media tensión (HTA)",
    "enedis.dwelling_min": "{kva:g} kVA en una vivienda: los suministros de potencia limitada de viviendas empiezan en "
                           "6 kVA",
    "enedis.agcp_max": "interruptor general ajustado a {in_a:g} A: un suministro de potencia limitada se ajusta a 60 A "
                       "como máximo",
    "enedis.agcp_low": "interruptor general ajustado a {in_a:g} A admite {pr:g} kVA, por debajo de los {kva:g} kVA "
                       "contratados: dispararía antes de alcanzar la potencia contratada",
    "enedis.agcp_no_rcd": "interruptor general sin protección diferencial: NF C 14-100 recomienda 500 mA en obra "
                          "nueva (interruptor no diferencial previa solicitud a Enedis)",
    "enedis.agcp_rcd_value": "interruptor general con protección diferencial de {idn:g} mA: NF C 14-100 recomienda 500 mA",
    "enedis.prod_installed_1p": "{kva:g} kVA de producción y almacenamiento en monofásico ({what}): por encima de 18 kVA "
                                "de potencia instalada se necesita un suministro trifásico",
    "enedis.prod_injection_1p": "{kva:g} kVA de producción y almacenamiento en monofásico ({what}): la inyección se "
                                "limita a 6 kVA (limitar la inyección o conectar en trifásico)",
    "enedis.prod_installed_3p": "{kva:g} kVA de producción y almacenamiento ({what}): la potencia instalada se limita a "
                                "250 kVA en baja tensión",
    "enedis.prod_above_36": "{kva:g} kVA de producción y almacenamiento ({what}): una inyección por encima de 36 kVA sigue "
                            "el procedimiento de conexión de las instalaciones de más de 36 kVA",
    "enedis.service_cable_length": "acometida individual de {length:g} m: los suministros de potencia limitada "
                                   "admiten 30 m como máximo (caída de tensión de hasta el 2 %)",
    "enedis.service_cable_section": "acometida individual de {section:g} mm²: la sección estándar es 35 mm² de aluminio "
                                    "(2 x 35 monofásico, 4 x 35 trifásico)",
    "enedis.decoupling": "{what}: indicar su protección de interconexión (desacoplamiento), obligatoria para "
                         "producción y almacenamiento (`protection`, p. ej. NF EN 50549-1 / NF EN 50549-10)",
}

DE: dict[str, str] = {
    "render.unknown_view": "unbekannte Ansicht: {id}",
    "render.incoming_from": "von {ref}",
    "render.incoming": "Einspeisung",
    "render.incoming_folio": "{what} (Blatt {folio})",
    "render.default_title": "Übersichtsschaltplan",
    "render.multiline_title": "Allpoliger Stromlaufplan (Hauptstromkreise)",
    "render.continued_from": "{label} (von Blatt {folio})",
    "render.continued_on": "weiter auf Blatt {folio}",
    "render.continuation_name": "{name} (Forts.)",
    "render.to_folio": " → Blatt {folio}",
    "label.rcd_type": "Typ {type}",
    "label.safety": "Sicherheitsstromkreis",
    "render.auxiliary_devices": "Hilfsgeräte",
    "render.scale": "Maßstab {scale}",
    "render.sheet_bookmark": "Blatt {number}: {title}",
    "render.sheet_bookmark_untitled": "Blatt {number}",
    "legend.conductors": "Leiter ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "NEC-Praxis",
    "legend.phase": "Außenleiter",
    "legend.multi_phase": "mehrphasig",
    "legend.source": "Einspeisungen",
    "legend.status": "Status",
    "legend.status.new": "neu",
    "legend.status.existing": "bestehend",
    "legend.status.future": "geplant",
    "legend.status.temporary": "provisorisch",
    "legend.status.removed": "rückgebaut",
    "legend.status.spare": "Reserve",
    "legend.voltage": "Spannung",
    "legend.voltage.mv": "HS / MS (> 1 kV AC)",
    "legend.voltage.lv": "NS",
    "legend.voltage.elv": "Kleinspannung (≤ 50 V AC)",
    "legend.voltage.dc": "Gleichstrom",
    "tb.title": "Titel",
    "tb.sheet_title": "Blatttitel",
    "tb.default_sheet_title": "Übersichtsschaltplan",
    "tb.project": "Projekt",
    "tb.client": "Auftraggeber",
    "tb.earthing": "Netzform",
    "tb.voltage": "Spannung",
    "tb.power": "Leistung",
    "tb.ik_max": "Ik max.",
    "tb.earth_electrode": "Erder",
    "tb.standard": "Norm",
    "tb.drawn_by": "Gezeichnet",
    "tb.checked_by": "Geprüft",
    "tb.company": "Firma",
    "tb.date": "Datum",
    "tb.revision": "Rev.",
    "tb.sheet": "Blatt",
    "tb.generated_by": "Erstellt mit",
    "notes.title": "Hinweise",
    "notes.site": "Standort: {site}",
    "notes.supply": "Einspeisung: {supply}",
    "notes.revision": "Rev. {index} {date} {description}",
    "notes.more": "… (+{count} weitere Zeile(n))",
    "ann.frame": "Baugröße {frame} A",
    "ann.off_peak": "Tag/Nacht (Niedertarif)",
    "ann.manual": "manuell",
    "ann.automatic": "automatisch",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "{count} Modul(e)",
    "ann.normally_open": "Normalstellung: offen",
    "ann.locks": "Schlüssel {keys}",
    "cell.points_one": "{count} Auslass",
    "cell.points": "{count} Auslässe",
    "cell.upstream": "{value} (vorgeschaltet)",
    "symbols.page_title": "uniwire-Symbole",
    "symbols.heading": "uniwire-Symbolbibliothek (Raster M = 2,5 mm)",
    # rule messages
    "rules.unknown_profile": "unbekanntes Profil: {profile!r}",
    "rules.no_profile": "kein Regelprofil angewendet: nur die Konsistenz des Dokuments wurde geprüft (BMK, "
                        "Verbindungen, Verriegelungen, Staffelung der Nennströme), nicht die Schutzorgane, "
                        "Leitungen und RCDs; Profile: 'nfc15100' (Frankreich), 'vde0100' (Deutschland), 'iec60364'",
    "rules.standard_not_covered": "kein Regelprofil deckt {standard} ab: nur die Konsistenz des Dokuments wurde "
                                  "geprüft (BMK, Verbindungen, Verriegelungen, Staffelung der Nennströme); "
                                  "Schutzorgane, Leitungen, Fehlerstrom-Schutzeinrichtungen und Erdung wurden nicht "
                                  "nach {standard} geprüft",
    "core.ref_unique": "BMK {ref!r} bereits von {other!r} verwendet",
    "core.normalized": "{where}: {field} {old!r} als {new!r} gelesen; in dieser Form schreiben",
    "core.normalized_field": "{where}: unbekanntes Feld {old!r} als {new!r} gelesen; {new!r} verwenden",
    "core.transfer_target": "eine 'transfer'-Verbindung muss an einem Netzumschalter (transfer_switch) enden",
    "core.tie_device": "Kupplung ohne angegebenes Schaltgerät",
    "core.transfer_source": "Netzumschalter ohne zweite Quelle ('transfer'-Verbindung)",
    "core.terminal_node": "ein Knoten {type} ist ein Endknoten und speist nichts: unter dem Gerät anordnen, über "
                          "das er angeschlossen ist (Schutzorgan, Wandler oder Wechselrichter), die Energie kann in "
                          "beide Richtungen fließen",
    "core.rating_cascade": "Nennstrom {in_a:g} A höher als das vorgeschaltete Schutzorgan {up} ({up_in_a:g} A)",
    "core.interlock_closed": "Verriegelung {lock!r}: {count} Schaltgeräte im Normalbetrieb geschlossen ({members}) "
                             "bei {keys} Schlüssel(n)",
    "core.interlock_single": "Schloss {lock!r} wird von nur einem Schaltgerät verwendet und in keinem "
                             "'interlocks'-Eintrag deklariert: es verriegelt nichts",
    "core.interlock_unused": "deklarierte Verriegelung {lock!r} wird von {count} Schaltgerät(en) verwendet "
                             "('locks'), mindestens 2 erwartet",
    "core.interlock_duplicate": "Verriegelung {lock!r} doppelt deklariert",
    "core.control_scope": "dieses Dokument beschreibt Steuerstromkreise ({nodes}): uniwire zeichnet die Energieverteilung "
                          "(Übersichtsschaltplan und allpoliger Stromlaufplan), keine Steuerstromlaufpläne; Spulen, "
                          "Kontakte, Taster und Strompfade werden hier nur zusammengefasst, nicht als Stromlaufplan "
                          "gezeichnet",
    "plc.duplicate_slots": "doppelte Steckplätze: {slots}",
    "plc.unsorted_slots": "Module nicht nach Steckplatz sortiert",
    "plc.wago_end": "WAGO-Lokalbus ohne Endmodul (750-600) an letzter Stelle",
    "plc.wago_feed": "kein Potentialeinspeisemodul (750-602...) deklariert",
    "plc.port_unreadable": "Anschluss {port!r} nicht lesbar ('Steckplatz.Kanal' erwartet)",
    "plc.port_missing_slot": "Anschluss {port!r}: Steckplatz {slot} fehlt",
    "plc.port_channels": "Anschluss {port!r}: Modul {module} hat nur {channels} Kanäle",
    "plc.coil": "Ausgang {port} ({un_v:g} V) steuert eine Spule {coil:g} V: Koppelrelais oder Relaismodul verwenden",
    "plc.port_shared": "Kanal {port} steuert {count} Geräte",
    "iec60364.install_uncovered": "Verlegeart {install!r} nicht abgedeckt (A1, A2, B1, B2, C, E, F, D1/D-duct)",
    "iec60364.iz_unavailable": "Iz nicht verfügbar für {material} {insulation} {section:g} mm² Verlegeart {method}, "
                               "{loaded} belastete Leiter",
    "iec60364.iz_exceeded": "Schutzorgan {rating:g} A > Iz {iz:g} A ({material} {insulation} {section:g} mm², Verlegeart "
                            "{method}, {loaded} belastete Leiter, {ambient})",
    "iec60364.ambient_ground": "Erdreich {t:g} °C",
    "iec60364.ambient_air": "Umgebung {t:g} °C",
    "iec60364.ambient_default": ", ambient_C nicht angegeben",
    "iec60364.ambient_uncovered": "Iz nicht geprüft: Umgebung {ambient:g} °C über den {limit} °C der Tabelle für Verlegeart {method}",
    "iec60364.iz_estimate_exceeded": "Leitung ohne Angabe von Leitermaterial, Isolierung oder Verlegeart: Schätzung "
                                     "mit {material} {insulation} {section:g} mm², Verlegeart {method}, {loaded} "
                                     "belastete Leiter, {t:g} °C: Schutzorgan {rating:g} A > Iz {iz:g} A; für eine "
                                     "genaue Prüfung angeben",
    "iec60364.any_air_method": "günstigste in Luft",
    "iec60364.iz_estimated": "Strombelastbarkeit nur geschätzt für {count} Leitung(en) ({tags}): Leitermaterial, "
                             "Isolierung oder Verlegeart fehlt (Kupfer, PVC und günstigste Verlegeart angenommen); "
                             "für eine genaue Prüfung angeben",
    "iec60364.rcd_30mA_socket": "{what}: Steckdosenstromkreis bis 32 A nicht durch einen RCD von höchstens 30 mA "
                                "geschützt",
    "iec60364.rcd_30mA_lighting": "{what}: Beleuchtungsstromkreis einer Wohnung nicht durch einen RCD von höchstens "
                                  "30 mA geschützt",
    "nfc15100.section": "Leitungsschutzschalter {in_a:g} A an {section:g} mm² (max. {limit} A)",
    "nfc15100.section_sizing": "Leitungsschutzschalter {in_a:g} A an {section:g} mm²: über den üblichen {limit} A, "
                               "Strombelastbarkeit der Leitung für die Verlegeart prüfen (NF C 15-100 Teil 5-52, "
                               "Leitfaden UTE C 15-105)",
    "nfc15100.lighting_points": "{points} Auslässe an einem Beleuchtungsstromkreis (max. {limit})",
    "nfc15100.lighting_rating": "Beleuchtung mit {in_a:g} A abgesichert (max. 16 A)",
    "nfc15100.socket_section": " bei {section:g} mm²",
    "nfc15100.socket_points": "{points} Steckdosen an einem Steckdosenstromkreis{where} (max. {limit})",
    "nfc15100.heating": "Heizung {total:g} kW an einem Stromkreis {in_a:g} A (max. {limit:g} kW)",
    "nfc15100.heating_unprotected": "Heizung {p:g} kW an einem Stromkreis (max. {limit:g} kW bei 32 A)",
    "nfc15100.rcd_30mA_socket": "{what}: Steckdosen- / Ladestromkreis nicht durch einen RCD 30 mA geschützt",
    "nfc15100.rcd_30mA_dwelling": "{what}: Stromkreis einer Wohnung nicht durch einen RCD 30 mA geschützt",
    "nfc15100.rcd_type_A": "{what}: RCD Typ A (oder F, B) erforderlich, Typ AC ausgeschlossen",
    "nfc15100.rcd_count_single": "nur ein RCD 30 mA (Wohnungen: mindestens 2; installation.premises für andere "
                                 "Räumlichkeiten angeben)",
    "nfc15100.rcd_count_type_A": "kein RCD 30 mA Typ A (Wohnungen: mindestens 1; installation.premises für andere "
                                 "Räumlichkeiten angeben)",
    "nfc15100.rcd_circuits": "{count} Stromkreise an einem RCD 30 mA (max. 8)",
    "nfc15100.dedicated_single": "{what}: muss allein an seinem Stromkreis sein ({prot} speist auch {others})",
    "nfc15100.dedicated_shared": "{what}: eigener Stromkreis wird mit anderen Verbrauchern geteilt",
    "nfc15100.ev_default": "Ladepunkt",
    "nfc15100.ev_mode2_3ph": "{what}: dreiphasig Mode 2, RCD Typ B erforderlich",
    "nfc15100.ev_mode3": "{what}: Mode 3 mit RCD Typ {rtype}: der Ladepunkt muss eine DC-Fehlerstromerkennung 6 mA "
                         "enthalten (RDC-DD, IEC 62955), sonst Typ B",
    "nfc15100.selectivity": "RCD anderen RCDs vorgeschaltet und nicht selektiv (Typ S)",
    "nfc15100.circuit_section": "{what}: {section:g} mm² (mindestens {need:g} mm² für diesen Stromkreis)",
    "nfc15100.circuit_rating": "{what}: mit {in_a:g} A abgesichert (höchstens {need:g} A für diesen Stromkreis)",
    "nfc15100.rcd_rating": "RCD 30 mA mit {in_a:g} A Nennstrom, unter den für die nachgeschalteten Stromkreise "
                           "erforderlichen {need:g} A",
    "nfc15100.rcd_spread_lighting": "die {count} Beleuchtungsstromkreise liegen alle hinter demselben RCD 30 mA (auf "
                                    "mindestens 2 verteilen)",
    "nfc15100.rcd_spread_socket": "die {count} Steckdosenstromkreise liegen alle hinter demselben RCD 30 mA (auf "
                                  "mindestens 2 verteilen)",
    "nfc15100.spd_rcd": "{what}: das Überspannungsschutzgerät am Anfang der Anlage darf nicht hinter einem RCD 30 mA "
                        "liegen",
    "nfc15100.agcp_rcd_adjustable": "{what}: einstellbare Empfindlichkeit an einem Anschluss begrenzter Leistung nicht "
                                    "zulässig",
    "nfc15100.agcp_rcd_max": "{what}: {idn:g} mA, höchstens 500 mA an einem Anschluss begrenzter Leistung",
    "nfc15100.earth_resistance": "Erdungswiderstand {r:g} Ω mit einem RCD {idn:g} mA: höchstens {limit:g} Ω (50 V)",
    "nfc15100.neutral_pole": "{what}: 1-poliger Leitungsschutzschalter an einem Stromkreis mit Neutralleiter, den er nicht "
                             "trennt (1P+N oder 2P)",
    "nfc15100.supply_section": "Verbindung zum Hauptverteiler mit {section:g} mm² bei einem Hauptschalter {in_a:g} A "
                               "(mindestens {need:g} mm² Kupfer)",
    "vde0100.rcd_30mA_socket": "{what}: Steckdosenstromkreis bis 32 A nicht durch einen RCD von höchstens 30 mA geschützt",
    "vde0100.rcd_30mA_lighting": "{what}: Beleuchtungsstromkreis einer Wohnung nicht durch einen RCD von höchstens 30 mA "
                                 "geschützt",
    "vde0100.bathroom": "{what}: Stromkreis eines Raums mit Badewanne oder Dusche nicht durch einen RCD von höchstens "
                        "30 mA geschützt",
    "vde0100.ev_own_circuit": "{what}: ein Ladepunkt braucht einen eigenen Endstromkreis (weitere Verbraucher an seinem "
                              "Schutzorgan)",
    "vde0100.ev_no_rcd": "{what}: Ladepunkt nicht durch einen RCD von höchstens 30 mA geschützt",
    "vde0100.ev_own_rcd": "{what}: ein Ladepunkt braucht einen eigenen RCD (der RCD schützt auch andere Verbraucher)",
    "vde0100.ev_rcd_type": "{what}: RCD Typ {rtype}: erforderlich ist Typ B oder Typ A / F mit "
                           "DC-Fehlerstromerkennung 6 mA im Ladepunkt",
    "vde0100.ev_rdc_dd": "{what}: RCD Typ {rtype}: der Ladepunkt muss eine DC-Fehlerstromerkennung 6 mA enthalten "
                         "(RDC-DD, IEC 62955), sonst ein RCD Typ B",
    "vde0100.spd": "kein Überspannungsschutzgerät: für die meisten Gebäude erforderlich (DIN VDE 0100-443 / -534)",
    "vde0100.pen_section": "PEN-Leiter {section:g} mm² {material}: mindestens {minimum:g} mm² erforderlich",
    "enedis.single_phase_max": "{kva:g} kVA einphasig: ein einphasiger Anschluss begrenzter Leistung ist auf "
                               "höchstens 12 kVA begrenzt, ein dreiphasiger Anschluss ist nötig",
    "enedis.monitored": "{kva:g} kVA: Anschluss mit überwachter Leistung (37 bis 250 kVA), die Einstellstufen des AGCP der "
                        "Anschlüsse begrenzter Leistung gelten nicht",
    "enedis.mv": "{kva:g} kVA: über 250 kVA erfolgt der Anschluss in Mittelspannung (HTA)",
    "enedis.dwelling_min": "{kva:g} kVA in einer Wohnung: Anschlüsse begrenzter Leistung von Wohnungen beginnen bei 6 kVA",
    "enedis.agcp_max": "Hauptschalter auf {in_a:g} A eingestellt: ein Anschluss begrenzter Leistung wird auf höchstens "
                       "60 A eingestellt",
    "enedis.agcp_low": "Hauptschalter auf {in_a:g} A eingestellt entspricht {pr:g} kVA, unter den {kva:g} kVA "
                       "Vertragsleistung: er würde vor Erreichen der Vertragsleistung auslösen",
    "enedis.agcp_no_rcd": "Hauptschalter ohne Fehlerstromschutz: NF C 14-100 empfiehlt 500 mA in Neubauten (Schalter "
                          "ohne Fehlerstromschutz auf Antrag bei Enedis)",
    "enedis.agcp_rcd_value": "Hauptschalter mit Fehlerstromschutz {idn:g} mA: NF C 14-100 empfiehlt 500 mA",
    "enedis.prod_installed_1p": "{kva:g} kVA Erzeugung und Speicher einphasig ({what}): über 18 kVA installierter "
                                "Leistung ist ein dreiphasiger Anschluss nötig",
    "enedis.prod_injection_1p": "{kva:g} kVA Erzeugung und Speicher einphasig ({what}): die Einspeisung ist auf 6 kVA "
                                "begrenzt (Einspeisung begrenzen oder dreiphasig anschließen)",
    "enedis.prod_installed_3p": "{kva:g} kVA Erzeugung und Speicher ({what}): die installierte Leistung ist in "
                                "Niederspannung auf 250 kVA begrenzt",
    "enedis.prod_above_36": "{kva:g} kVA Erzeugung und Speicher ({what}): eine Einspeisung über 36 kVA folgt dem "
                            "Anschlussverfahren der Anlagen über 36 kVA",
    "enedis.service_cable_length": "Hausanschlusskabel von {length:g} m: Anschlüsse begrenzter Leistung erlauben "
                                   "höchstens 30 m (Spannungsfall höchstens 2 %)",
    "enedis.service_cable_section": "Hausanschlusskabel von {section:g} mm²: der Standardquerschnitt ist 35 mm² Aluminium "
                                    "(2 x 35 einphasig, 4 x 35 dreiphasig)",
    "enedis.decoupling": "{what}: den Entkupplungsschutz (NA-Schutz) angeben, für Erzeugung und Speicher Pflicht "
                         "(`protection`, z. B. NF EN 50549-1 / NF EN 50549-10)",
}
PT: dict[str, str] = {
    "render.unknown_view": "vista desconhecida: {id}",
    "render.incoming_from": "de {ref}",
    "render.incoming": "alimentação",
    "render.incoming_folio": "{what} (folha {folio})",
    "render.default_title": "Diagrama unifilar geral",
    "render.multiline_title": "Diagrama multifilar de força",
    "render.continued_from": "{label} (continuação da folha {folio})",
    "render.continued_on": "continua na folha {folio}",
    "render.continuation_name": "{name} (cont.)",
    "render.to_folio": " → folha {folio}",
    "label.rcd_type": "tipo {type}",
    "label.safety": "Circuito de segurança",
    "render.auxiliary_devices": "Dispositivos auxiliares",
    "render.scale": "escala {scale}",
    "render.sheet_bookmark": "Folha {number}: {title}",
    "render.sheet_bookmark_untitled": "Folha {number}",
    "legend.conductors": "Condutores ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "prática NEC",
    "legend.phase": "Fases",
    "legend.multi_phase": "polifásico",
    "legend.source": "Fontes de alimentação",
    "legend.status": "Situação",
    "legend.status.new": "novo",
    "legend.status.existing": "existente",
    "legend.status.future": "futuro",
    "legend.status.temporary": "provisório",
    "legend.status.removed": "a remover",
    "legend.status.spare": "reserva",
    "legend.voltage": "Tensão",
    "legend.voltage.mv": "AT / MT (> 1 kV CA)",
    "legend.voltage.lv": "BT",
    "legend.voltage.elv": "EBT (≤ 50 V CA)",
    "legend.voltage.dc": "Corrente contínua",
    "tb.title": "Título",
    "tb.sheet_title": "Título da folha",
    "tb.default_sheet_title": "Diagrama unifilar",
    "tb.project": "Projeto",
    "tb.client": "Cliente",
    "tb.earthing": "Esquema de aterramento",
    "tb.voltage": "Tensão",
    "tb.power": "Potência",
    "tb.ik_max": "Icc máx.",
    "tb.earth_electrode": "Eletrodo de aterramento",
    "tb.standard": "Norma",
    "tb.drawn_by": "Desenho",
    "tb.checked_by": "Verificação",
    "tb.company": "Empresa",
    "tb.date": "Data",
    "tb.revision": "Rev.",
    "tb.sheet": "Folha",
    "tb.generated_by": "Gerado por",
    "notes.title": "Observações",
    "notes.site": "Local: {site}",
    "notes.supply": "Alimentação: {supply}",
    "notes.revision": "Rev. {index} {date} {description}",
    "notes.more": "… (+{count} linha(s))",
    "ann.frame": "carcaça {frame} A",
    "ann.off_peak": "fora de ponta",
    "ann.manual": "manual",
    "ann.automatic": "automático",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "{count} módulo(s)",
    "ann.normally_open": "NA",
    "ann.locks": "chave {keys}",
    "cell.points_one": "{count} ponto",
    "cell.points": "{count} pontos",
    "cell.upstream": "{value} (a montante)",
    "symbols.page_title": "Símbolos uniwire",
    "symbols.heading": "Biblioteca de símbolos uniwire (grade M = 2,5 mm)",
    # rule messages
    "rules.unknown_profile": "perfil desconhecido: {profile!r}",
    "rules.no_profile": "nenhum perfil de regras aplicado: só a coerência do documento foi verificada (identificações, "
                        "ligações, intertravamentos, correntes nominais em cascata), não as proteções, cabos e DR; "
                        "perfis: 'nfc15100' (França), 'vde0100' (Alemanha), 'iec60364'",
    "rules.standard_not_covered": "nenhum perfil de regras cobre {standard}: só a coerência do documento foi verificada "
                                  "(identificações, ligações, intertravamentos, correntes nominais em cascata); as "
                                  "proteções, cabos, dispositivos DR e aterramento não foram verificados segundo "
                                  "{standard}",
    "core.ref_unique": "identificação {ref!r} já usada por {other!r}",
    "core.normalized": "{where}: {field} {old!r} lido como {new!r}; escrever desta forma",
    "core.normalized_field": "{where}: campo desconhecido {old!r} lido como {new!r}; usar {new!r}",
    "core.transfer_target": "uma ligação 'transfer' deve terminar numa chave de transferência (transfer_switch)",
    "core.tie_device": "acoplamento sem dispositivo descrito",
    "core.transfer_source": "chave de transferência sem segunda fonte (ligação 'transfer')",
    "core.terminal_node": "um nó {type} é uma folha e não alimenta nada: colocá-lo sob o dispositivo que o liga "
                          "(sua proteção, conversor ou inversor), a energia pode circular nos dois sentidos",
    "core.rating_cascade": "corrente nominal {in_a:g} A acima da proteção a montante {up} ({up_in_a:g} A)",
    "core.interlock_closed": "intertravamento {lock!r}: {count} membros fechados em operação normal ({members}) para "
                             "{keys} chave(s)",
    "core.interlock_single": "a fechadura {lock!r} é usada por um só membro e não está declarada em nenhuma entrada "
                             "'interlocks': não intertrava nada",
    "core.interlock_unused": "o intertravamento declarado {lock!r} é usado por {count} membro(s) ('locks'), esperados pelo "
                             "menos 2",
    "core.interlock_duplicate": "intertravamento {lock!r} declarado duas vezes",
    "core.control_scope": "este documento descreve circuitos de comando ({nodes}): o uniwire desenha a distribuição de "
                          "energia (diagramas unifilar e multifilar), não diagramas de comando; bobinas, contatos, "
                          "botoeiras e caminhos de corrente são só resumidos aqui, não desenhados como diagrama de comando",
    "plc.duplicate_slots": "slots duplicados: {slots}",
    "plc.unsorted_slots": "módulos não ordenados por slot",
    "plc.wago_end": "barramento local WAGO sem módulo final (750-600) na última posição",
    "plc.wago_feed": "nenhum módulo de alimentação de potencial (750-602...) declarado",
    "plc.port_unreadable": "porta {port!r} ilegível (esperado 'slot.canal')",
    "plc.port_missing_slot": "porta {port!r}: falta o slot {slot}",
    "plc.port_channels": "porta {port!r}: o módulo {module} só tem {channels} canais",
    "plc.coil": "a saída {port} ({un_v:g} V) comanda uma bobina de {coil:g} V: usar um relé de interface ou um módulo de "
                "relés",
    "plc.port_shared": "o canal {port} comanda {count} dispositivos",
    "iec60364.install_uncovered": "método de instalação {install!r} não coberto (A1, A2, B1, B2, C, E, F, D1/D-duct)",
    "iec60364.iz_unavailable": "Iz indisponível para {material} {insulation} {section:g} mm² método {method}, {loaded} "
                               "condutores carregados",
    "iec60364.iz_exceeded": "proteção {rating:g} A > Iz {iz:g} A ({material} {insulation} {section:g} mm², método "
                            "{method}, {loaded} cond. carregados, {ambient})",
    "iec60364.ambient_ground": "solo {t:g} °C",
    "iec60364.ambient_air": "ambiente {t:g} °C",
    "iec60364.ambient_default": ", ambient_C não indicado",
    "iec60364.ambient_uncovered": "Iz não verificado: ambiente {ambient:g} °C acima dos {limit} °C da tabela para o método {method}",
    "iec60364.iz_estimate_exceeded": "o cabo não indica material, isolamento ou método de instalação: estimativa "
                                     "com {material} {insulation} {section:g} mm², método {method}, {loaded} "
                                     "condutores carregados, {t:g} °C: proteção {rating:g} A > Iz {iz:g} A; indique-os "
                                     "para uma verificação exata",
    "iec60364.any_air_method": "o mais favorável ao ar",
    "iec60364.iz_estimated": "corrente admissível apenas estimada para {count} cabo(s) ({tags}): falta material, "
                             "isolamento ou método de instalação (supostos cobre, PVC e o método mais favorável); "
                             "indique-os para uma verificação exata",
    "iec60364.rcd_30mA_socket": "{what}: circuito de tomadas até 32 A não protegido por um DR de no máximo 30 mA",
    "iec60364.rcd_30mA_lighting": "{what}: circuito de iluminação de uma habitação não protegido por um DR de no "
                                  "máximo 30 mA",
    "nfc15100.section": "disjuntor de {in_a:g} A em {section:g} mm² (máx. {limit} A)",
    "nfc15100.section_sizing": "disjuntor de {in_a:g} A em {section:g} mm²: acima dos {limit} A usuais, verificar o cabo "
                               "para o seu método de instalação (NF C 15-100 parte 5-52, guia UTE C 15-105)",
    "nfc15100.lighting_points": "{points} pontos num circuito de iluminação (máx. {limit})",
    "nfc15100.lighting_rating": "iluminação protegida por {in_a:g} A (máx. 16 A)",
    "nfc15100.socket_section": " em {section:g} mm²",
    "nfc15100.socket_points": "{points} tomadas num circuito de tomadas{where} (máx. {limit})",
    "nfc15100.heating": "aquecimento de {total:g} kW num circuito de {in_a:g} A (máx. {limit:g} kW)",
    "nfc15100.heating_unprotected": "aquecimento de {p:g} kW num circuito (máx. {limit:g} kW a 32 A)",
    "nfc15100.rcd_30mA_socket": "{what}: circuito de tomadas / de recarga não protegido por um DR de 30 mA",
    "nfc15100.rcd_30mA_dwelling": "{what}: circuito de habitação não protegido por um DR de 30 mA",
    "nfc15100.rcd_type_A": "{what}: DR tipo A (ou F, B) exigido, tipo AC excluído",
    "nfc15100.rcd_count_single": "só um DR de 30 mA (habitações: pelo menos 2; indicar installation.premises para outros "
                                 "locais)",
    "nfc15100.rcd_count_type_A": "nenhum DR de 30 mA tipo A (habitações: pelo menos 1; indicar installation.premises para "
                                 "outros locais)",
    "nfc15100.rcd_circuits": "{count} circuitos num DR de 30 mA (máx. 8)",
    "nfc15100.dedicated_single": "{what}: deve estar sozinho no seu circuito ({prot} também alimenta {others})",
    "nfc15100.dedicated_shared": "{what}: circuito dedicado compartilhado com outro uso",
    "nfc15100.ev_default": "Carregador de VE",
    "nfc15100.ev_mode2_3ph": "{what}: modo 2 trifásico, DR tipo B exigido",
    "nfc15100.ev_mode3": "{what}: modo 3 com DR tipo {rtype}: o carregador deve integrar uma detecção de corrente "
                         "contínua de 6 mA (RDC-DD, IEC 62955); caso contrário, DR tipo B",
    "nfc15100.selectivity": "DR a montante de outros DR e não seletivo (tipo S)",
    "nfc15100.circuit_section": "{what}: {section:g} mm² (pelo menos {need:g} mm² para este circuito)",
    "nfc15100.circuit_rating": "{what}: protegido por {in_a:g} A (no máximo {need:g} A para este circuito)",
    "nfc15100.rcd_rating": "DR de 30 mA de {in_a:g} A, abaixo dos {need:g} A exigidos pelos circuitos a jusante",
    "nfc15100.rcd_spread_lighting": "os {count} circuitos de iluminação estão todos a jusante do mesmo DR de 30 mA "
                                    "(distribuí-los em pelo menos 2)",
    "nfc15100.rcd_spread_socket": "os {count} circuitos de tomadas estão todos a jusante do mesmo DR de 30 mA "
                                  "(distribuí-los em pelo menos 2)",
    "nfc15100.spd_rcd": "{what}: o DPS na origem não deve estar a jusante de um DR de 30 mA",
    "nfc15100.agcp_rcd_adjustable": "{what}: sensibilidade regulável não admitida num fornecimento de potência limitada",
    "nfc15100.agcp_rcd_max": "{what}: {idn:g} mA, no máximo 500 mA num fornecimento de potência limitada",
    "nfc15100.earth_resistance": "eletrodo de aterramento de {r:g} Ω com um DR de {idn:g} mA: no máximo {limit:g} Ω (50 V)",
    "nfc15100.neutral_pole": "{what}: disjuntor 1P num circuito com neutro, que ele não secciona (1P+N ou 2P)",
    "nfc15100.supply_section": "ligação ao quadro geral em {section:g} mm² com um disjuntor geral de {in_a:g} A (pelo "
                               "menos {need:g} mm² de cobre)",
    "vde0100.rcd_30mA_socket": "{what}: circuito de tomadas até 32 A não protegido por um DR de no máximo 30 mA",
    "vde0100.rcd_30mA_lighting": "{what}: circuito de iluminação de uma habitação não protegido por um DR de no máximo "
                                 "30 mA",
    "vde0100.bathroom": "{what}: circuito de um cômodo com banheira ou chuveiro não protegido por um DR de no máximo 30 mA",
    "vde0100.ev_own_circuit": "{what}: um ponto de recarga precisa do seu próprio circuito terminal (há outras "
                              "cargas na sua proteção)",
    "vde0100.ev_no_rcd": "{what}: ponto de recarga não protegido por um DR de no máximo 30 mA",
    "vde0100.ev_own_rcd": "{what}: um ponto de recarga precisa do seu próprio DR (o DR protege também outras cargas)",
    "vde0100.ev_rcd_type": "{what}: DR tipo {rtype}: exigido tipo B, ou tipo A / F com detecção de corrente contínua de "
                           "6 mA no ponto de recarga",
    "vde0100.ev_rdc_dd": "{what}: DR tipo {rtype}: o ponto de recarga deve integrar uma detecção de corrente "
                         "contínua de 6 mA (RDC-DD, IEC 62955); caso contrário, um DR tipo B",
    "vde0100.spd": "nenhum DPS: exigido para a maioria dos edifícios (DIN VDE 0100-443 / -534)",
    "vde0100.pen_section": "condutor PEN de {section:g} mm² {material}: exigidos pelo menos {minimum:g} mm²",
    "enedis.single_phase_max": "{kva:g} kVA em monofásico: um fornecimento monofásico de potência limitada admite 12 kVA "
                               "no máximo, é preciso um fornecimento trifásico",
    "enedis.monitored": "{kva:g} kVA: fornecimento de potência monitorada (37 a 250 kVA), os patamares de ajuste do AGCP "
                        "dos fornecimentos de potência limitada não se aplicam",
    "enedis.mv": "{kva:g} kVA: acima de 250 kVA o fornecimento é em média tensão (HTA)",
    "enedis.dwelling_min": "{kva:g} kVA numa habitação: os fornecimentos de potência limitada das habitações começam em "
                           "6 kVA",
    "enedis.agcp_max": "disjuntor geral ajustado em {in_a:g} A: um fornecimento de potência limitada é ajustado em 60 A no "
                       "máximo",
    "enedis.agcp_low": "disjuntor geral ajustado em {in_a:g} A admite {pr:g} kVA, abaixo dos {kva:g} kVA "
                       "contratados: dispararia antes de atingir a potência contratada",
    "enedis.agcp_no_rcd": "disjuntor geral sem proteção diferencial: a NF C 14-100 recomenda 500 mA em construções "
                          "novas (disjuntor não diferencial mediante solicitação à Enedis)",
    "enedis.agcp_rcd_value": "disjuntor geral com proteção diferencial de {idn:g} mA: a NF C 14-100 recomenda 500 mA",
    "enedis.prod_installed_1p": "{kva:g} kVA de geração e armazenamento em monofásico ({what}): acima de 18 kVA de "
                                "potência instalada é preciso um fornecimento trifásico",
    "enedis.prod_injection_1p": "{kva:g} kVA de geração e armazenamento em monofásico ({what}): a injeção é "
                                "limitada a 6 kVA (limitar a injeção ou ligar em trifásico)",
    "enedis.prod_installed_3p": "{kva:g} kVA de geração e armazenamento ({what}): a potência instalada é limitada a "
                                "250 kVA em baixa tensão",
    "enedis.prod_above_36": "{kva:g} kVA de geração e armazenamento ({what}): uma injeção acima de 36 kVA segue o "
                            "procedimento de ligação das instalações acima de 36 kVA",
    "enedis.service_cable_length": "ramal de ligação individual de {length:g} m: os fornecimentos de potência "
                                   "limitada admitem 30 m no máximo (queda de tensão de até 2 %)",
    "enedis.service_cable_section": "ramal de ligação individual de {section:g} mm²: a seção padrão é 35 mm² de alumínio "
                                    "(2 x 35 monofásico, 4 x 35 trifásico)",
    "enedis.decoupling": "{what}: indicar a sua proteção de interface (desacoplamento), obrigatória para geração e "
                         "armazenamento (`protection`, p. ex. NF EN 50549-1 / NF EN 50549-10)",
}
IT: dict[str, str] = {
    "render.unknown_view": "vista sconosciuta: {id}",
    "render.incoming_from": "da {ref}",
    "render.incoming": "Alimentazione",
    "render.incoming_folio": "{what} (foglio {folio})",
    "render.default_title": "Schema unifilare generale",
    "render.multiline_title": "Schema multifilare (circuiti di potenza)",
    "render.continued_from": "{label} (dal foglio {folio})",
    "render.continued_on": "segue al foglio {folio}",
    "render.continuation_name": "{name} (segue)",
    "render.to_folio": " → foglio {folio}",
    "label.rcd_type": "tipo {type}",
    "label.safety": "Circuito di sicurezza",
    "render.auxiliary_devices": "Apparecchi ausiliari",
    "render.scale": "Scala {scale}",
    "render.sheet_bookmark": "Foglio {number}: {title}",
    "render.sheet_bookmark_untitled": "Foglio {number}",
    "legend.conductors": "Conduttori ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "pratica NEC",
    "legend.phase": "Fasi",
    "legend.multi_phase": "polifase",
    "legend.source": "Sorgenti di alimentazione",
    "legend.status": "Stato",
    "legend.status.new": "nuovo",
    "legend.status.existing": "esistente",
    "legend.status.future": "futuro",
    "legend.status.temporary": "provvisorio",
    "legend.status.removed": "da rimuovere",
    "legend.status.spare": "riserva",
    "legend.voltage": "Tensione",
    "legend.voltage.mv": "AT / MT (> 1 kV c.a.)",
    "legend.voltage.lv": "BT",
    "legend.voltage.elv": "Bassissima tensione (≤ 50 V c.a.)",
    "legend.voltage.dc": "Corrente continua",
    "tb.title": "Titolo",
    "tb.sheet_title": "Titolo foglio",
    "tb.default_sheet_title": "Schema unifilare",
    "tb.project": "Progetto",
    "tb.client": "Committente",
    "tb.earthing": "Sistema di distribuzione",
    "tb.voltage": "Tensione",
    "tb.power": "Potenza",
    "tb.ik_max": "Icc max",
    "tb.earth_electrode": "Dispersore",
    "tb.standard": "Norma",
    "tb.drawn_by": "Disegnato",
    "tb.checked_by": "Verificato",
    "tb.company": "Ditta",
    "tb.date": "Data",
    "tb.revision": "Rev.",
    "tb.sheet": "Foglio",
    "tb.generated_by": "Generato da",
    "notes.title": "Note",
    "notes.site": "Ubicazione: {site}",
    "notes.supply": "Alimentazione: {supply}",
    "notes.revision": "Rev. {index} {date} {description}",
    "notes.more": "… (+{count} riga/e di note)",
    "ann.frame": "taglia {frame} A",
    "ann.off_peak": "Tariffa bioraria",
    "ann.manual": "manuale",
    "ann.automatic": "automatico",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "{count} modulo/i",
    "ann.normally_open": "NA",
    "ann.locks": "Chiave {keys}",
    "cell.points_one": "{count} punto",
    "cell.points": "{count} punti",
    "cell.upstream": "{value} (a monte)",
    "symbols.page_title": "Simboli uniwire",
    "symbols.heading": "Libreria di simboli uniwire (griglia M = 2,5 mm)",
}
PL: dict[str, str] = {
    "render.unknown_view": "nieznany widok: {id}",
    "render.incoming_from": "z {ref}",
    "render.incoming": "Zasilanie",
    "render.incoming_folio": "{what} (arkusz {folio})",
    "render.default_title": "Ogólny schemat jednokreskowy",
    "render.multiline_title": "Schemat wielokreskowy (obwody główne)",
    "render.continued_from": "{label} (z arkusza {folio})",
    "render.continued_on": "ciąg dalszy na arkuszu {folio}",
    "render.continuation_name": "{name} (cd.)",
    "render.to_folio": " → arkusz {folio}",
    "label.rcd_type": "typ {type}",
    "label.safety": "Obwód bezpieczeństwa",
    "render.auxiliary_devices": "Aparaty pomocnicze",
    "render.scale": "Skala {scale}",
    "render.sheet_bookmark": "Arkusz {number}: {title}",
    "render.sheet_bookmark_untitled": "Arkusz {number}",
    "legend.conductors": "Przewody ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "praktyka NEC",
    "legend.phase": "Fazy",
    "legend.multi_phase": "wielofazowy",
    "legend.source": "Źródła zasilania",
    "legend.status": "Stan",
    "legend.status.new": "nowy",
    "legend.status.existing": "istniejący",
    "legend.status.future": "przyszły",
    "legend.status.temporary": "tymczasowy",
    "legend.status.removed": "do demontażu",
    "legend.status.spare": "rezerwa",
    "legend.voltage": "Napięcie",
    "legend.voltage.mv": "WN / SN (> 1 kV AC)",
    "legend.voltage.lv": "nN",
    "legend.voltage.elv": "Bardzo niskie napięcie (≤ 50 V AC)",
    "legend.voltage.dc": "Prąd stały",
    "tb.title": "Tytuł",
    "tb.sheet_title": "Tytuł arkusza",
    "tb.default_sheet_title": "Schemat jednokreskowy",
    "tb.project": "Projekt",
    "tb.client": "Inwestor",
    "tb.earthing": "Układ sieci",
    "tb.voltage": "Napięcie",
    "tb.power": "Moc",
    "tb.ik_max": "Ik max",
    "tb.earth_electrode": "Uziom",
    "tb.standard": "Norma",
    "tb.drawn_by": "Opracował",
    "tb.checked_by": "Sprawdził",
    "tb.company": "Firma",
    "tb.date": "Data",
    "tb.revision": "Rew.",
    "tb.sheet": "Arkusz",
    "tb.generated_by": "Wygenerowano w",
    "notes.title": "Uwagi",
    "notes.site": "Obiekt: {site}",
    "notes.supply": "Zasilanie: {supply}",
    "notes.revision": "Rew. {index} {date} {description}",
    "notes.more": "… (dodatkowe wiersze uwag: {count})",
    "ann.frame": "obudowa {frame} A",
    "ann.off_peak": "Taryfa nocna",
    "ann.manual": "ręczny",
    "ann.automatic": "automatyczny",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "moduły: {count}",
    "ann.normally_open": "NO",
    "ann.locks": "Klucz {keys}",
    "cell.points_one": "{count} pkt",
    "cell.points": "{count} pkt",
    "cell.upstream": "{value} (zab. nadrz.)",
    "symbols.page_title": "Symbole uniwire",
    "symbols.heading": "Biblioteka symboli uniwire (siatka M = 2,5 mm)",
}
TR: dict[str, str] = {
    "render.unknown_view": "bilinmeyen görünüm: {id}",
    "render.incoming_from": "besleme: {ref}",
    "render.incoming": "Besleme",
    "render.incoming_folio": "{what} (sayfa {folio})",
    "render.default_title": "Genel tek hat şeması",
    "render.multiline_title": "Çok hatlı şema (güç devreleri)",
    "render.continued_from": "{label} (sayfa {folio} devamı)",
    "render.continued_on": "devamı sayfa {folio}",
    "render.continuation_name": "{name} (devam)",
    "render.to_folio": " → sayfa {folio}",
    "label.rcd_type": "{type} tipi",
    "label.safety": "Güvenlik devresi",
    "render.auxiliary_devices": "Yardımcı cihazlar",
    "render.scale": "Ölçek {scale}",
    "render.sheet_bookmark": "Sayfa {number}: {title}",
    "render.sheet_bookmark_untitled": "Sayfa {number}",
    "legend.conductors": "İletkenler ({standard})",
    "legend.preset.iec": "IEC 60445",
    "legend.preset.us": "NEC uygulaması",
    "legend.phase": "Fazlar",
    "legend.multi_phase": "çok fazlı",
    "legend.source": "Besleme kaynakları",
    "legend.status": "Durum",
    "legend.status.new": "yeni",
    "legend.status.existing": "mevcut",
    "legend.status.future": "ileride yapılacak",
    "legend.status.temporary": "geçici",
    "legend.status.removed": "sökülecek",
    "legend.status.spare": "yedek",
    "legend.voltage": "Gerilim",
    "legend.voltage.mv": "YG / OG (> 1 kV AC)",
    "legend.voltage.lv": "AG",
    "legend.voltage.elv": "Çok düşük gerilim (≤ 50 V AC)",
    "legend.voltage.dc": "Doğru akım",
    "tb.title": "Başlık",
    "tb.sheet_title": "Sayfa başlığı",
    "tb.default_sheet_title": "Tek hat şeması",
    "tb.project": "Proje",
    "tb.client": "İşveren",
    "tb.earthing": "Topraklama sistemi",
    "tb.voltage": "Gerilim",
    "tb.power": "Güç",
    "tb.ik_max": "Ik maks.",
    "tb.earth_electrode": "Topraklama elektrodu",
    "tb.standard": "Standart",
    "tb.drawn_by": "Çizen",
    "tb.checked_by": "Kontrol",
    "tb.company": "Firma",
    "tb.date": "Tarih",
    "tb.revision": "Rev.",
    "tb.sheet": "Sayfa",
    "tb.generated_by": "Oluşturan",
    "notes.title": "Notlar",
    "notes.site": "Yer: {site}",
    "notes.supply": "Besleme: {supply}",
    "notes.revision": "Rev. {index} {date} {description}",
    "notes.more": "… (+{count} not satırı)",
    "ann.frame": "kasa {frame} A",
    "ann.off_peak": "Gece tarifesi",
    "ann.manual": "manuel",
    "ann.automatic": "otomatik",
    "ann.peak_power_unit": "Wp",
    "ann.peak_power_kunit": "kWp",
    "ann.modules": "{count} modül",
    "ann.normally_open": "NA",
    "ann.locks": "Anahtar {keys}",
    "cell.points_one": "{count} nokta",
    "cell.points": "{count} nokta",
    "cell.upstream": "{value} (üst koruma)",
    "symbols.page_title": "uniwire sembolleri",
    "symbols.heading": "uniwire sembol kütüphanesi (ızgara M = 2,5 mm)",
}
CATALOGS: dict[str, dict[str, str]] = {
    "en": EN, "fr": FR, "ru": RU, "zh": ZH, "es": ES, "de": DE, "pt": PT, "it": IT, "pl": PL, "tr": TR,
}


def normalize_lang(lang: Optional[str]) -> str:
    """Map a BCP 47 tag (``fr``, ``fr-FR``, ``en_GB``...) to a catalog language, English if unknown."""
    if not lang:
        return DEFAULT_LANG
    base = lang.replace("_", "-").split("-")[0].lower()
    return base if base in CATALOGS else DEFAULT_LANG


def current_lang() -> str:
    """Language for CLI, validation and rule messages: ``$UNIWIRE_LANG``, default English."""
    return normalize_lang(os.environ.get(ENV_VAR))


def render_lang() -> str:
    """Language of the document being rendered, else the environment language."""
    lang = RENDER_LANG.get()
    return normalize_lang(lang) if lang else current_lang()


def t(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """Translated message for ``key``, formatted with ``kwargs``.

    ``lang`` defaults to :func:`current_lang` (environment); rendering code passes ``doc.meta.lang``.
    """
    code = normalize_lang(lang) if lang is not None else current_lang()
    template = CATALOGS[code].get(key) or EN.get(key) or key
    if code in DECIMAL_COMMA:
        kwargs = {k: _CommaFloat(v) if isinstance(v, float) else v for k, v in kwargs.items()}
    return template.format(**kwargs) if kwargs else template


#: Languages whose messages write decimals with a comma ('1,5 mm²').
DECIMAL_COMMA = {"fr", "ru", "es", "de", "pt", "it", "pl", "tr"}


def number(value: float, lang: Optional[str] = None) -> str:
    """``value`` as a message writes it ('1.5', or '1,5' in French, Russian, Spanish), for numbers built into message arguments."""
    code = normalize_lang(lang) if lang is not None else current_lang()
    return format(_CommaFloat(value) if code in DECIMAL_COMMA else float(value), "g")


class _CommaFloat(float):
    """A number formatted with a decimal comma, whatever the format spec ('{section:g}' -> '1,5')."""

    def __format__(self, spec: str) -> str:
        return float.__format__(self, spec).replace(".", ",")

    def __str__(self) -> str:
        return format(self, "")
