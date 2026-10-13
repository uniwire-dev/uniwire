/* uniwire viewer: Web Worker running the Python library in Pyodide.
 *
 * Protocol (postMessage):
 *   in : {id, type: "process"|"export"|"pdf", req: {...}}
 *   out: {type: "progress", step, pct} | {type: "ready", version} | {type: "fatal", message}
 *        {id, type: "result", result} | {id, type: "error", message}
 */
"use strict";

const PYODIDE_VERSION = "0.27.7";
const PYODIDE_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const REPORTLAB = "reportlab==5.0.1"; // PDF export, installed on first use

let py = null;
let api = null;
let reportlab = null; // Promise once the PDF backend install was requested

function progress(step, pct) {
  self.postMessage({ type: "progress", step, pct });
}

async function init() {
  progress("runtime", 5);
  importScripts(PYODIDE_BASE + "pyodide.js");
  py = await loadPyodide({ indexURL: PYODIDE_BASE });
  progress("packages", 45);
  await py.loadPackage(["micropip", "pydantic"]);
  progress("library", 75);
  const version = await (await fetch("version.json", { cache: "no-cache" })).json();
  const micropip = py.pyimport("micropip");
  // Fetch the wheel ourselves (revalidated, so a new deploy is picked up) and install it from
  // the in-memory file system.
  const wheelResp = await fetch(version.wheel, { cache: "no-cache" });
  if (!wheelResp.ok) throw new Error(`cannot download ${version.wheel} (${wheelResp.status})`);
  const wheelPath = "/tmp/" + version.wheel.split("/").pop();
  py.FS.writeFile(wheelPath, new Uint8Array(await wheelResp.arrayBuffer()));
  await micropip.install.callKwargs("emfs:" + wheelPath, { deps: false });
  progress("glue", 90);
  const glue = await (await fetch("viewer.py", { cache: "no-cache" })).text();
  py.FS.writeFile("/home/pyodide/uniwire_viewer.py", glue);
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  api = py.pyimport("uniwire_viewer");
  progress("ready", 100);
  self.postMessage({ type: "ready", version: version.uniwire, pyodide: PYODIDE_VERSION });
}

const ready = init().catch((err) => {
  self.postMessage({ type: "fatal", message: String((err && err.message) || err) });
  throw err;
});

async function ensureReportlab() {
  if (!reportlab) {
    reportlab = (async () => {
      await py.loadPackage(["pillow"]);
      const micropip = py.pyimport("micropip");
      // Exact pin: same release as the library's [pdf] extra is tested with (pure-Python wheel from PyPI);
      // its dependency charset-normalizer comes from PyPI too, pillow from the Pyodide distribution.
      await micropip.install(REPORTLAB);
    })();
    reportlab.catch(() => { reportlab = null; });
  }
  return reportlab;
}

self.onmessage = async (ev) => {
  const { id, type, req } = ev.data || {};
  try {
    await ready;
    let result;
    if (type === "process") {
      result = JSON.parse(api.process(JSON.stringify(req)));
    } else if (type === "export") {
      result = JSON.parse(api.export(JSON.stringify(req)));
    } else if (type === "pdf") {
      await ensureReportlab();
      const path = api.export_pdf(JSON.stringify(req));
      const bytes = py.FS.readFile(path);
      result = { ok: true, bytes };
      self.postMessage({ id, type: "result", result }, [bytes.buffer]);
      return;
    } else {
      throw new Error("unknown request " + type);
    }
    self.postMessage({ id, type: "result", result });
  } catch (err) {
    let message = String((err && err.message) || err);
    // Python tracebacks: keep the last line (the exception itself)
    const lines = message.trim().split("\n");
    if (lines.length > 1 && /Traceback/.test(lines[0])) message = lines[lines.length - 1];
    self.postMessage({ id, type: "error", message });
  }
};
