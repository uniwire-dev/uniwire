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
    # core
    "core.ref_unique": "tag {ref!r} already used by {other!r}",
    "core.normalized": "{where}: {field} {old!r} read as {new!r}; write it in this form",
    "core.normalized_field": "{where}: unknown field {old!r} read as {new!r}; use {new!r}",
    "core.transfer_target": "a 'transfer' link must end on a transfer switch (transfer_switch)",
    "core.tie_device": "bus tie without a described device",
    "core.transfer_source": "transfer switch without a 2nd source ('transfer' link)",
    "core.terminal_node": "a {type} node normally feeds nothing",
    "core.rating_cascade": "rating {in_a:g} A higher than the upstream protection {up} ({up_in_a:g} A)",
    "core.interlock_closed": "interlock {lock!r}: {count} members closed in normal operation ({members}) for {keys} key(s)",
    "core.interlock_single": "lock {lock!r} is used by a single member and declared in no 'interlocks' entry: it interlocks nothing",
    "core.interlock_unused": "declared interlock {lock!r} is used by {count} member(s) ('locks'), at least 2 expected",
    "core.interlock_duplicate": "interlock {lock!r} declared twice",
    # plc
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
    "iec60364.install_uncovered": "installation method {install!r} not covered (A1, A2, B1, B2, C, E, F, D-duct)",
    "iec60364.iz_unavailable": "Iz not available for {material} {insulation} {section:g} mm² "
                               "method {method}, {loaded} loaded conductors",
    "iec60364.iz_exceeded": "protection {rating:g} A > Iz {iz:g} A ({material} {insulation} {section:g} mm², "
                            "method {method}, {loaded} loaded cond., {ambient})",
    "iec60364.ambient_ground": "ground 25 °C",
    "iec60364.ambient_air": "40 °C ambient",
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
    "cli.help.wires": "wire list as CSV: one row per conductor of the cables of the power tree, with its mark",
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
    "core.ref_unique": "repère {ref!r} déjà utilisé par {other!r}",
    "core.normalized": "{where} : {field} {old!r} lu comme {new!r} ; écrire cette forme",
    "core.normalized_field": "{where} : champ inconnu {old!r} lu comme {new!r} ; utiliser {new!r}",
    "core.transfer_target": "un lien 'transfer' doit aboutir sur un inverseur (transfer_switch)",
    "core.tie_device": "couplage sans appareil décrit",
    "core.transfer_source": "inverseur sans 2e source (lien 'transfer')",
    "core.terminal_node": "un nœud {type} n'alimente normalement rien",
    "core.rating_cascade": "calibre {in_a:g} A supérieur à la protection amont {up} ({up_in_a:g} A)",
    "core.interlock_closed": "verrouillage {lock!r} : {count} membres fermés en exploitation normale ({members}) pour {keys} clé(s)",
    "core.interlock_single": "la serrure {lock!r} n'équipe qu'un seul membre et n'est déclarée dans aucune entrée 'interlocks' : elle ne verrouille rien",
    "core.interlock_unused": "le verrouillage déclaré {lock!r} n'équipe que {count} membre(s) ('locks'), 2 au moins attendus",
    "core.interlock_duplicate": "verrouillage {lock!r} déclaré deux fois",
    "plc.duplicate_slots": "slots en double : {slots}",
    "plc.unsorted_slots": "modules non rangés par ordre de slot",
    "plc.wago_end": "bus local WAGO sans module de fin (750-600) en dernière position",
    "plc.wago_feed": "aucun module d'alimentation de potentiel (750-602...) déclaré",
    "plc.port_unreadable": "port {port!r} illisible (attendu 'slot.voie')",
    "plc.port_missing_slot": "port {port!r} : slot {slot} absent",
    "plc.port_channels": "port {port!r} : le module {module} n'a que {channels} voies",
    "plc.coil": "sortie {port} ({un_v:g} V) pilote une bobine {coil:g} V : prévoir un relais d'interface ou un module relais",
    "plc.port_shared": "la voie {port} commande {count} appareils",
    "iec60364.install_uncovered": "mode de pose {install!r} non couvert (A1, A2, B1, B2, C, E, F, D-duct)",
    "iec60364.iz_unavailable": "Iz non disponible pour {material} {insulation} {section:g} mm² "
                               "pose {method}, {loaded} conducteurs chargés",
    "iec60364.iz_exceeded": "protection {rating:g} A > Iz {iz:g} A ({material} {insulation} {section:g} mm², "
                            "pose {method}, {loaded} cond. chargés, {ambient})",
    "iec60364.ambient_ground": "sol 25 °C",
    "iec60364.ambient_air": "40 °C ambiant",
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
    "cli.help.wires": "liste des fils en CSV : une ligne par conducteur des câbles de l'arbre de puissance, avec son repère",
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

CATALOGS: dict[str, dict[str, str]] = {"en": EN, "fr": FR}


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
    cat = CATALOGS[normalize_lang(lang) if lang is not None else current_lang()]
    template = cat.get(key) or EN.get(key) or key
    return template.format(**kwargs) if kwargs else template
