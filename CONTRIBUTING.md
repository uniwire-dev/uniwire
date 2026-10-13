# Contributing to uniwire

Thank you for your interest in uniwire! Contributions of all kinds are welcome: bug reports, examples,
symbols, rules, translations, documentation and changes to the format itself.

uniwire has two layers:

* **the format**: the specification ([`docs/SPEC.md`](https://github.com/uniwire-dev/uniwire/blob/main/docs/SPEC.md)), the JSON Schema
  ([`schema/uniwire.schema.json`](https://github.com/uniwire-dev/uniwire/blob/main/schema/uniwire.schema.json)) and the type registry
  ([`src/uniwire/registry/core.json`](https://github.com/uniwire-dev/uniwire/blob/main/src/uniwire/registry/core.json));
* **the reference implementation**: the `uniwire` Python package (model, validation, rules, rendering,
  bill of materials, code-first API, CLI).

Please read and follow the [Code of Conduct](https://github.com/uniwire-dev/uniwire/blob/main/CODE_OF_CONDUCT.md). Security issues must be reported
privately, see [SECURITY.md](https://github.com/uniwire-dev/uniwire/blob/main/SECURITY.md).

## Repository layout

| Path | Content |
|---|---|
| `src/uniwire/` | the Python library (model, validation, rules, layout, rendering, exports, CLI, LLM tools, MCP server) |
| `schema/` | the published JSON Schema, generated from the models |
| `examples/` | example documents (`examples/code/`: examples written with the code-first API) |
| `tests/` | the test suite |
| `docs/` | the documentation (MkDocs): specification, guides, proposals (`docs/uep/`) and logo files (`docs/brand/assets/`), README gallery (`docs/gallery/`) |
| `viewer/` | the web viewer (static site running the library with Pyodide) |
| `docker/mcp/` | the official MCP server image |
| `packages/uniwire-data-iec81346/` | the optional CC BY-SA 4.0 data package |
| `evals/llm/` | evaluation tasks for model-written documents |

## Development setup

The project uses [uv](https://docs.astral.sh/uv/) (plain `python -m venv` and `pip` work too).

```bash
git clone https://github.com/uniwire-dev/uniwire.git
cd uniwire
uv venv
uv pip install -e ".[dev]" -e packages/uniwire-data-iec81346
```

Python 3.10 or later is required. The `dev` extra installs pytest, jsonschema, reportlab (PDF output), the
MCP SDK and ruff. No lock file is committed: the commands below run the tools of `.venv` directly, so they
do not create one (`uv run` would write a `uv.lock`).

## Running the tests and the linter

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

The suite covers the model, validation, rules, rendering, the code-first API, internationalisation and
the published schema. Every example in `examples/` is validated against the committed schema and rendered.
Please add or update tests with every change.

## Regenerating the JSON Schema

The pydantic models in `src/uniwire/model/` are the source of truth for the schema. After any model change:

```bash
.venv/bin/uniwire schema -o schema/uniwire.schema.json
```

and commit the regenerated file. A drift test (`tests/test_schema.py`) and a CI step fail when the
committed schema does not match the models.

## Documentation and viewer

```bash
uv run --no-project --with "mkdocs<2" --with mkdocs-material mkdocs build --strict -d /tmp/uniwire-docs
.venv/bin/python viewer/build.py --out /tmp/uniwire-viewer     # then: python -m http.server -d /tmp/uniwire-viewer
```

The logo files live in `docs/brand/assets/` only; the documentation and the viewer build read them from
there.

## Adding an example

1. Write `examples/<name>.uniwire.json` (or a Python script under `examples/code/` that builds it with
   `uniwire.build`). Use the `$schema` URL `https://uniwire.sh/schema/v1/uniwire.schema.json`.
2. Check it: `.venv/bin/uniwire validate examples/<name>.uniwire.json` then
   `.venv/bin/uniwire check examples/<name>.uniwire.json`.
3. Render it: `.venv/bin/uniwire render examples/<name>.uniwire.json -f pdf -o out/<name>.pdf` and look at the result.
4. Only publish data you are allowed to share: no personal data, no copyrighted drawings.

## Translations

uniwire renders in English by default and supports French. To improve or add a language:

* **Messages** (CLI, validation errors, rule findings, title block and sheet texts) live in the catalog
  [`src/uniwire/i18n.py`](https://github.com/uniwire-dev/uniwire/blob/main/src/uniwire/i18n.py): `EN` is the reference, other languages (`FR`) mirror its
  keys. A missing key falls back to English. `tests/test_i18n.py` checks that the catalogs stay in sync.
* **Type labels** (shown on drawings and in the bill of materials) live in the `label` object of each type
  in [`src/uniwire/registry/core.json`](https://github.com/uniwire-dev/uniwire/blob/main/src/uniwire/registry/core.json) (`{"en": …, "fr": …}`).
* **Viewer interface**: the strings of the web viewer live in `viewer/i18n.js` (English, French).

Rendering follows `meta.lang` of the document; the CLI follows the `UNIWIRE_LANG` environment variable.

## Changing the format: uniwire Enhancement Proposals (UEP)

Every change to the format goes through a short public proposal, opened as a GitHub issue with the
**Format proposal** template (label `uep`):

1. **Motivation**: which real installations or drawings need it? Describe the use case and, if possible,
   attach a small anonymised example.
2. **Proposal**: fields, types or link kinds, with JSON examples, and the mapping to CIM / IFC /
   IEC 61850 SCL where relevant.
3. **Compatibility**: minor versions (1.x) only add optional fields, types or enumeration values; anything
   that breaks existing files waits for the next major version and ships with a migration function.
4. **Implementation**: the change in the reference library, the schema regenerated, the specification
   updated, the changelog entry, at least one example or test using it, and the whole
   test suite green.

## Code style

* Python ≥ 3.10, type hints everywhere; pydantic v2 models are the source of truth for the schema.
* Keep the renderer deterministic (tests compare structures).
* User-facing text goes through `uniwire.i18n`: never hard-code English or French strings.
* Keep pull requests focused, and describe user-visible changes in `CHANGELOG.md`.

## Licensing of contributions

By contributing you agree that your code is licensed under the Apache License 2.0 and your specification
text under CC BY 4.0. Contributions to the optional `packages/uniwire-data-iec81346` data package are
licensed under CC BY-SA 4.0.
