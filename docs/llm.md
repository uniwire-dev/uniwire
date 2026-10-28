# LLM tools

uniwire includes tools that let an AI assistant write, read, edit, check and render electrical diagrams (single-line and multi-line):

| Tool | What it does | Python | CLI |
|---|---|---|---|
| Reference card | The format summarised for a model: skeleton, node types and fields, enums, links, pitfalls and examples | `uniwire.llm.card()` | `uniwire card` |
| Describe | A compact outline of a document with stable ids, for the model to read | `uniwire.llm.describe()` | `uniwire describe` |
| Patch | Edits by node id, with validation and precise errors | `uniwire.llm.patch()` | `uniwire patch` |
| Link | A link that opens a document in the web editor (drawing, findings, PDF and SVG downloads; `pdf=True` / `--pdf` also downloads the PDF); the document travels in the link after `#` | `uniwire.llm.viewer_link()` | `uniwire link` |
| Flat form | The node tree as a table with parent ids | `uniwire.llm.flatten()` / `unflatten()` | |
| MCP server | All of the above, plus validate, check, render, BOM and examples, as tools for any MCP client | `uniwire.mcp_server` | `uniwire-mcp` |
| Evaluations | 15 tasks that score documents produced by any model | `uniwire.llm.evaluate` | `evals/llm/run.py` |

## MCP server

Install the extra, which adds the official [MCP Python SDK](https://pypi.org/project/mcp/):

```bash
pip install "uniwire[mcp]"          # add "uniwire[mcp,pdf]" for PDF rendering
```

The `uniwire-mcp` command starts the server on stdio.

**Claude Code**

```bash
claude mcp add uniwire -- uniwire-mcp
```

**Claude Desktop** and other MCP clients (`claude_desktop_config.json`, `.mcp.json`, …):

```json
{"mcpServers": {"uniwire": {"command": "uniwire-mcp"}}}
```

If `uniwire-mcp` is not on the client's `PATH`, give the absolute path to the command, for example
`/path/to/venv/bin/uniwire-mcp`. You can also run `python -m uniwire.mcp_server` with the interpreter of that
environment.

### Tools

Every `document` argument accepts a JSON object, a JSON string or the path of a `*.uniwire.json` file.

| Tool | Arguments | Result |
|---|---|---|
| `get_reference_card` | `level` (`compact` / `full`), `lang` (`en` / `fr`) | Markdown card |
| `list_types` | `category`? | `[{type, category, label}]` |
| `type_info` | `type` | fields with descriptions and allowed values |
| `validate` | `document` | `{valid, issues, viewer_url}`; each issue names the node id and the field |
| `check` | `document`, `profiles`? | `{summary, findings: [{level, rule, node, message, source}], scope, viewer_url}`; `scope` states what the checks cover (not a conformity certificate) |
| `describe` | `document`, `lang`? | text outline |
| `apply_patch` | `document`, `ops`, `validate`? | `{ok, document}` or `{ok: false, errors}` |
| `render` | `document`, `kind` (`single-line` / `multi-line`), `format` (`svg` / `pdf`), `sheet`?, `view`?, `path`?, `color`? (`none`/`conductors`/`phase`/`source`/`status`/`voltage`), `conductor_colors`? (`iec`/`us`) | SVG text of each sheet; PDF written to `path` or returned as base64 |
| `viewer_link` | `document` | `{viewer_url, pdf_url}`: links that open the document in the web editor (drawing, findings, PDF and SVG downloads); `pdf_url` also downloads the PDF (on the hosted server, a plain PDF link: see [Short links](#short-links)) |
| `bom` | `document` | bill-of-materials rows: referenced products, then equipment without a reference grouped by type and characteristics (`spec`), then cables |
| `wiring` | `document`, `what` (`markers` / `wires` / `cables`), `view`? | wire marker list, wire list or cable schedule as rows (stable column names) |
| `list_examples`, `get_example` | `name` (e.g. `02` or `02_house_3_bedrooms_tt`) | the 53 bundled examples |
| `normalize` | `document` | resolved document (templates applied, ids assigned) |

`validate`, `check`, `apply_patch` and `render` also return `viewer_url` and `pdf_url` (omitted beyond 60,000 characters). Chat apps cannot hand a base64 PDF to the user as a file: the links are how the user gets the drawing and the PDF, so in public mode `render` with `format: "pdf"` returns `pdf_url` rather than base64. The document travels in the part of the link after `#` and is stored nowhere.

Resources: `uniwire://schema` (JSON Schema), `uniwire://card` and `uniwire://card/full`.

Prompt: `design_single_line` (argument `brief`). It guides the assistant through these steps: ask for the earthing system, the supply and the loads; write the document; validate; check; fix; render.

A typical session: the assistant reads the card, writes the document and calls `validate` and `check`. It then fixes the findings with `apply_patch`, reviews the result with `describe` and finishes with `render`.

### Public server

`uniwire-mcp --http --public` serves the tools over streamable HTTP for anyone (this is how the hosted
endpoint runs). Public mode refuses file paths and file writes and bounds every call:

| Limit | Value |
|---|---|
| Document | 2,000,000 characters of JSON; 1500 nodes, counted after templates are applied, auxiliary and link devices included; 256 levels of nesting (this one applies everywhere) |
| `render` | 40 sheets; 20,000,000 bytes of output (all SVG sheets together, or the PDF) |
| `apply_patch` | 500 operations per call; the patched document must stay within the document limits |
| Time and memory | the document tools (`validate`, `check`, `describe`, `apply_patch`, `render`, `wiring`, `bom`, `normalize`, `viewer_link`) run in worker processes: `--workers` of them (default 2, the concurrency limit), each killed and replaced after `--timeout` seconds (default 20). On Linux each worker is also limited to `--memory-mb` of address space (default 768) and to a CPU-time budget per call |
| HTTP | request bodies over 3 MB are refused (413) before the JSON is parsed |

A call beyond a limit fails with a short tool error (no stack trace), for example `document too large for this
server: 1601 nodes (at most 1500)`, `timed out after 20 s` or `server busy`. `GET /healthz` answers 200 `ok`
for container health checks. `uniwire-mcp --help` lists the same limits. Without `--public` (stdio, or HTTP for
your own use) none of these limits apply and the tools run in the server process.

#### Short links

Assistants retype links into their replies, and a long `#doc=` payload rarely survives that copy. With
`--store DIR`, the links returned by the tools are short (`https://uniwire.sh/viewer/#d=<id>`, about 40
characters): the server keeps the document text in `DIR` and serves it at `GET /doc/<id>`. The id is derived from
the content (the same document gives the same link) and cannot be guessed without it. A document is deleted 30
days after its last use, and the oldest documents go first when the store exceeds 500 MB. The hosted endpoint runs
with `--store`: documents sent to its tools are kept on that basis. `--link-base` sets the editor URL of the links.

Over HTTP with `--store`, `pdf_url` is a plain PDF link as well (`https://uniwire.sh/pdf/<id>`): the server draws
the PDF with the library (in a worker process in public mode) and serves it at `GET /pdf/<id>`, named after the
document title. It works without the editor and cannot be mistaken for `viewer_url`. `--pdf-base` sets its prefix
(default: the editor URL with `/viewer/` replaced by `/pdf/`). `GET /svg/<id>` serves the first sheet as SVG, which
the web editor shows while its engine starts, and `GET /doc/<id>` the document text.

The PDF of `GET /pdf/<id>` ends with a page "About this document", which is not a sheet of the diagram: the rule
profiles applied and the findings, the scope of the checks, the links of the online copy and how to delete it, and
how to write to the uniwire team. `?about=0` leaves it out. Whoever holds a link can delete its document before it
expires (`POST /doc/<id>/delete`, never a GET); the links of a deleted document answer 410.

## Reference card

```bash
uniwire card                 # compact card, ~3,100 tokens
uniwire card --full          # adds field descriptions, docstrings and every enum value (~5,000 tokens)
uniwire card --lang fr       # French prose and type labels
```

```python
from uniwire.llm import card
system_prompt = card(lang="en", level="compact")
```

The card is generated from the pydantic model, the type registry and the rules engine, so it follows the format version of the installed library. It covers:

- the document skeleton;
- the tree-and-links principle, and the difference between `id` and `ref`;
- units carried by field names;
- every node type grouped by category, with its own fields;
- the enums: poles, curves, RCD types, phases, earthing systems, link kinds and so on;
- links, interlocks and locks, views and rule profiles;
- common pitfalls;
- two tiny examples, which the tests check for validity.

To paste the card into a system prompt by hand, run `uniwire card > uniwire-card.md`.

## Describe

```bash
uniwire describe examples/01_studio_apartment.uniwire.json
```

```text
## Tree (id [ref] type "label" field=value… | cable; indentation = fed by the line above)
- grid grid "Réseau public" un_V=230 supply="Tarif Bleu"
  - CPT [PDL] meter "Compteur communicant" kind=Linky in_A=90
    - Q0 [-Q0] main_breaker "AGCP" … in_A=45 poles=2P range_A=15-45 idn_mA=500 selective=true | cable 3G10mm2 Cu 4m U1000R2V
      - TD [TD] board "Tableau du studio" ways=13
        - F1 [-F1] rcd "Interrupteur différentiel 1" (use ID40) in_A=40 poles=2P idn_mA=30 rcd_type=AC
          - Q11 [-Q11] breaker (use C10) in_A=10 poles=1P+N icn_kA=3 curve=C | cable 3G1.5mm2
...
## Links
- #0: control CPT -> KM1 label="Contact HC"
## Findings: no findings
```

The outline shows:

- the installation, counts and templates;
- the whole tree, one node per line, starting with its stable `id` (the one to use in patches), with fields written as `field=value` using the real field names and templates applied;
- auxiliary devices, links, interlocks with their members, enclosures, boards and views;
- a summary of the rule findings.

The same document always produces the same text.

## Patch

```bash
uniwire patch house.uniwire.json ops.json -o house-v2.uniwire.json     # "-" reads the operations from stdin
```

```json
[
  {"op": "set", "id": "Q11", "path": "in_A", "value": 16},
  {"op": "set", "id": "Q11", "path": "cable.section_mm2", "value": 2.5},
  {"op": "set", "path": "installation.earthing", "value": "TN-S"},
  {"op": "add", "parent": "F2", "node": {"type": "breaker", "id": "Q25", "in_A": 20, "curve": "C",
                                         "children": [{"type": "appliance", "kind": "dishwasher"}]}},
  {"op": "move", "id": "Q25", "parent": "F1", "index": 0},
  {"op": "rename", "id": "KM1", "new_id": "KM_HC"},
  {"op": "remove", "id": "Q13"},
  {"op": "link", "link": {"kind": "control", "from": "CPT", "to": "KM_HC"}},
  {"op": "unlink", "from": "CPT", "to": "KM_HC", "kind": "control"}
]
```

- Operations apply in order to a copy of the document, and the result is then validated.
- `set` with `value: null` removes the field. Without `id`, `set` addresses the document root. The `id` can also name a link.
- `remove` also drops the links, enclosure entries and view references to the removed subtree. `rename` updates them.
- Nodes without an `id` get the id that `uniwire.load` assigns, written into the result, so the ids shown by `describe` work directly. Templates (`use`) are kept.
- If an operation fails, `PatchError.errors` (and the CLI, exit code 2) gives the index of the failing operation and the reason, for example `operation #1: unknown id 'Q99'`.
- If the result is invalid, the error names the node and the field, for example `node 'Q11' (breaker), field 'curve': Input should be 'B', 'C', …`.

```python
from uniwire.llm import patch, PatchError, flatten, unflatten

new = patch(doc_dict, ops)                 # returns a new raw document (dict)
rows = flatten(doc_dict)                   # [{"id", "type", ..., "parent", "root"?}, ...] in tree order
doc2 = unflatten(rows, base=doc_dict)      # rebuild sources/devices from the rows, other keys from base
```

## Evaluations

`evals/llm/` contains 15 tasks. Each one pairs a natural-language request with checks a machine can run. Example: "French house, TT, 1P+N, three 30 mA RCD groups, water heater on an off-peak contactor". Its checks expect profile `nfc15100`, at least 3 `rcd` with `idn_mA` 30, a `water_heater` under a `contactor` with `function` HC, no `error` finding, and a successful render. Edit tasks start from a bundled example.

```bash
python evals/llm/run.py prompt all --out prompts/          # card + request (+ starting document) per task
# … send each prompt to any model, save the answers as candidates/<task_id>.json …
python evals/llm/run.py score candidates/ -v               # per-task score and the mean
```

The runner makes no network calls. Three reference solutions in `evals/llm/reference/` score 1.0 and serve as tests of the scorer. See `evals/llm/README.md` for the check vocabulary and how to add tasks.

## Limits

- The card's prose and pitfalls are translated into French, but field descriptions stay in English, as written in the model.
- `describe` lists every node, so a very large installation produces a long outline. For those, use `render` with `view.root`, or `flatten`.
- Patch validation runs on the final result. An error found there is reported against the resulting document, not against one operation.
- The MCP `render` tool returns SVG text (one string per sheet) or a PDF. It does not produce PNG.
