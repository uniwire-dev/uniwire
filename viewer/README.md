# uniwire web viewer

A static, zero-install viewer and editor for uniwire documents. It runs the real `uniwire` Python
library in the browser with [Pyodide](https://pyodide.org) (inside a Web Worker), so validation,
rule checks, drawings and the bill of materials are exactly those of the CLI. Nothing is uploaded.

Published at <https://uniwire.sh/viewer/>, where the website build runs `python viewer/build.py --out <site>/viewer`.

## Run locally

```bash
python viewer/build.py                   # wheel -> viewer/dist/, examples -> viewer/examples/, viewer/version.json
python -m http.server -d viewer 8000     # then open http://localhost:8000/
```

`build.py` uses `uv build` when `uv` is on the PATH, otherwise `pip wheel` (needs network access to
fetch the `hatchling` build backend). `python viewer/build.py --out DIR` also copies the complete static
site to `DIR` (the uniwire.sh build uses `--out <site>/viewer`). After editing only the viewer files, use
`--skip-wheel` to reuse the existing wheel.

A web server is required (Web Workers and `fetch` do not work from `file://`).

## Files

| File | Role |
|---|---|
| `index.html` | page layout, CodeMirror import map |
| `app.js` | UI: documents, sharing, drawing viewport (zoom/pan), sheet navigation and history, colour modes, issues panel, downloads |
| `interact.js` | drawing interaction: hover / sticky highlighting (upstream, downstream, links, conductors), tooltips |
| `editor.js` | CodeMirror 6 editor with lint markers (falls back to a plain textarea), JSON path locator |
| `worker.js` | Web Worker: loads Pyodide, pydantic and the uniwire wheel; answers render/export requests |
| `viewer.py` | Python glue run in Pyodide (validate, check, node and link index, view overrides, render pages to SVG strings, BOM, PDF) |
| `i18n.js` | interface strings (English, French) |
| `style.css` | styles (light/dark, narrow screens) |
| `build.py` | build script (generated files are git-ignored: `dist/`, `examples/`, `version.json`, and the favicons copied from `docs/brand/assets/`) |

## URLs

- `?example=<name>` loads a bundled example (`?example=03` or the full name such as
  `03_house_three_phase_heat_pump_ev`).
- `#doc=<data>` carries a whole document (raw DEFLATE, base64url), written by the *Share* button. The
  decompressed document is limited to 5 MB (`MAX_SHARED_MB` in `app.js`): a larger one is refused with a
  message instead of being inflated in memory.
- Without either, the last draft of this browser is restored (local storage), else the first example.
- The draft is saved when you edit or open a file. Opening an example or a shared link does not replace
  it: the previous draft stays saved until you edit the loaded document, and a *Restore the draft* button
  brings it back.
- `#sheet=<n>` (alone or after `#doc=…&`) opens sheet `n`; following an off-page reference pushes a
  browser-history entry with it, so *Back* / `Alt`+`←` / the browser's back button return to the
  previous sheet and viewport.

## Drawing interaction

The viewer relies on the data attributes of the SVG sheets (`data-uw-id` on node groups, `.uw-edge`
`data-uw-edge`/`data-uw-parent` on tree edges, `.uw-link` with `data-uw-from`/`data-uw-to` and an
invisible `.uw-hit` path, `data-uw-cond` on multi-line conductors, `.uw-ref` with
`data-uw-target-sheet`/`data-uw-target-id` on off-page references, `data-uw-sheet` and
`data-uw-view-kind` on the `<svg>`). Every feature is detected: with sheets that lack an attribute the
corresponding highlight is simply not shown. Highlighting toggles CSS classes (`uw-hl-self`,
`uw-hl-up`, `uw-hl-down`, `uw-hl-link`, `uw-hl-end`, `uw-hl-cond`, and `uw-dim` on the `<svg>`) on
elements found through a per-sheet index, so it stays fast on large sheets. The tree (parent,
children), ratings summary and link details come from `viewer.py` (`nodes` and `links` of the
result).

The colour menus appear only when the installed library's `View` model has the fields (`color`, and a
conductor colour preset); `viewer.py` lists them (`options`) and applies the chosen values with
`View.model_copy(update=…)` for the drawing and the PDF.

## Pinned third-party code

- Pyodide `0.27.7` from `cdn.jsdelivr.net` (`PYODIDE_VERSION` in `worker.js`).
- CodeMirror 6 modules from `esm.sh` (import map in `index.html`). If they cannot be loaded, the
  viewer falls back to a plain textarea editor with line numbers.
- PDF export installs `reportlab` (pinned, `REPORTLAB` in `worker.js`) from PyPI with `micropip` on first use; built-in PDF fonts
  (Helvetica) are used, so a few symbols are transliterated. *All sheets (print / PDF)* opens a
  print-ready page of the SVG sheets as an alternative.
