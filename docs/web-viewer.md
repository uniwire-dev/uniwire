# Web viewer

**[Open the viewer →](https://uniwire.sh/viewer/)**

The web viewer opens, edits and renders uniwire documents directly in the browser, with nothing to
install. It runs the real `uniwire` Python library (the same code as the CLI) on
[Pyodide](https://pyodide.org), so validation messages, rule findings, drawings and the bill of
materials are exactly those you get with `uniwire validate`, `check`, `render` and `bom`.

Everything runs on your machine: documents are never uploaded. The first visit downloads the Python
runtime (about 10 MB, then cached by the browser).

## Features

- **Editor** with JSON syntax highlighting, error markers in the gutter and live re-rendering
  (400 ms after the last keystroke). Open a file with *Open*, drag and drop it onto the page, or paste
  a document.
- **Drawing**: one tab per sheet, zoom with the mouse wheel or the +/− buttons, pan by dragging,
  *Fit* to show the whole sheet. Switch between the document's views and between the *single-line*
  and *multi-line* diagrams. The drawing language follows `meta.lang` of the document.
- **Exploring the drawing**:
    - hover a symbol to see its tag, type, ratings and cable, with its path up to the source
      highlighted in orange and everything it feeds in blue;
    - hover a link (transfer, tie, interlock, data…) to highlight it and its two ends, with a tooltip
      giving its kind, both ends, the device it carries and its cable;
    - in the multi-line diagram, hover a conductor (L1, L2, L3, N, PE…) to follow it across the
      sheet;
    - click (or tap) to keep the highlight; `Esc` or a click on an empty area clears it;
    - click an off-page reference ("→ sheet 3") to jump to that sheet, centred on the target;
      *Back* (or `Alt`+`←`, or the browser's back button) returns to the previous sheet and view.
- **Colours**: the *Colours* menu re-renders the drawing coloured by conductor, phase, source, status
  or voltage, and the *Conductors* menu picks the conductor colour convention (IEC or US). *As in the
  document* keeps the document's own view settings. The sheet stays white in dark mode.
- **Keyboard** (outside the editor): `←`/`→` or `PageUp`/`PageDown` change sheet, `F` or `0` fits the
  sheet, `+`/`-` zoom, `↑`/`↓` and `Shift`+arrows pan, `Esc` clears the selection, `Alt`+`←` goes
  back.
- **Issues**: validation errors with their JSON path, and rule findings (severity, rule, message,
  node). Clicking a finding highlights the node in the drawing and in the editor; clicking a symbol in
  the drawing selects its node in the editor. While the document is invalid, the last valid drawing
  stays visible.
- **Examples**: every document of the [examples](examples.md) gallery is available from the
  *Examples* menu.
- **Downloads**: current sheet as SVG, all sheets as a print-ready page (print to PDF from the
  browser), PDF generated in the browser, bill of materials (CSV), normalized JSON and the source
  JSON.
- **Sharing**: *Share* copies a link that contains the whole document (compressed in the URL
  fragment, so it is not sent to the server). Very large documents give long links that some tools
  truncate: share the file instead.
- English and French interface (follows the browser language; switch with EN / FR).

## Links

| URL | Opens |
|---|---|
| `https://uniwire.sh/viewer/` | the last document edited in this browser, else the first example |
| `https://uniwire.sh/viewer/?example=03` | an example, by number or full name (`03_house_three_phase_heat_pump_ev`) |
| `https://uniwire.sh/viewer/#doc=…` | a document shared with the *Share* button |
| `…?example=07#sheet=3` | a given sheet (also written to the address bar when you follow an off-page reference) |

## Limits

- A recent browser is required (WebAssembly, Web Workers, `CompressionStream`).
- PDF export downloads the PDF engine (reportlab) on first use and uses the built-in PDF fonts; for
  the most faithful output use *All sheets (print / PDF)*, which prints the SVG sheets.
- The optional data packages (such as `uniwire-data-iec81346`) are not loaded.

## Running it locally

The viewer is a static site in the [`viewer/`](https://github.com/uniwire-dev/uniwire/tree/main/viewer)
directory of the repository:

```bash
python viewer/build.py                # builds the wheel and copies the examples
python -m http.server -d viewer 8000  # open http://localhost:8000/
```
