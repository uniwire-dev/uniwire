// Checks the uniwire-native wheel built for Pyodide in Pyodide under Node, as the web editor loads it: installed
// with micropip next to the uniwire wheel, used by the library, and drawing every bundled example exactly as the
// pure Python search does.
//
//   npm install pyodide@<the version pinned in viewer/worker.js>
//   node packages/uniwire-native/pyodide-check.mjs <uniwire wheel> <uniwire-native wasm32 wheel> <examples dir>
import { loadPyodide } from "pyodide";
import fs from "node:fs";
import path from "node:path";

const [uniwireWheel, nativeWheel, examples] = process.argv.slice(2);
const py = await loadPyodide();
await py.loadPackage(["micropip", "pydantic"]);
const micropip = py.pyimport("micropip");
for (const wheel of [uniwireWheel, nativeWheel]) {
  const dest = "/tmp/" + path.basename(wheel);
  py.FS.writeFile(dest, fs.readFileSync(wheel));
  await micropip.install.callKwargs("emfs:" + dest, { deps: false });
}
const docs = {};
for (const name of fs.readdirSync(examples).filter((f) => f.endsWith(".uniwire.json")).sort()) {
  docs[name] = fs.readFileSync(path.join(examples, name), "utf8");
}
py.globals.set("DOCS", py.toPy(docs));
const out = py.runPython(`
import json, re
import uniwire
from uniwire.layout import routing
from uniwire.render import render_views
from uniwire.render.svg import page_to_svg

native = routing._grid_search
assert native is not None, "uniwire-native was installed but is not used"

def svgs(text):
    return [re.sub(r"_\\d{8,}", "_#", page_to_svg(p)) for p in render_views(uniwire.load(json.loads(text)))]

lines = []
for name, text in DOCS.items():
    fast = svgs(text)
    routing._grid_search = None
    slow = svgs(text)
    routing._grid_search = native
    if fast != slow:
        lines.append(f"DIFFERENT: {name}")
lines.append(f"{len(DOCS)} examples drawn with the compiled search: {len(DOCS) - len(lines)} the same as in pure Python")
"\\n".join(lines)
`);
console.log(out);
if (out.includes("DIFFERENT")) process.exit(1);
