// uniwire viewer: main thread: UI, editor, drawing viewport, worker orchestration.
import { applyStatic, lang, onLangChange, setLang, t } from "./i18n.js";
import { createEditor, firstLine, locatePath, scanJson } from "./editor.js";
import { createInteraction } from "./interact.js";

const $ = (sel) => document.querySelector(sel);
const DEBOUNCE_MS = 400;
const DRAFT_KEY = "uniwire-viewer-draft";
const SPLIT_KEY = "uniwire-viewer-split";
const COLORS_KEY = "uniwire-viewer-colors";
const MAX_SHARED_MB = 5;  // #doc= links: decompressed size limit (a small link can inflate to gigabytes)

const state = {
  editor: null,
  examples: [],
  stem: "uniwire",
  result: null,        // last worker result
  pages: [],           // pages currently displayed (last valid render)
  nodes: {},           // node id -> {path, type, ref, label, parent, children, summary, cable} (last valid render)
  links: [],           // links of the document (last valid render)
  viewOptions: {},     // overridable View fields supported by the library: name -> choices
  colors: loadColors(), // {color, preset}: colour-mode overrides chosen in the UI ("" = as in the document)
  docSerial: 0,        // incremented for each loaded document (history entries of older documents are ignored)
  navIdx: 0,           // depth of the cross-sheet navigation history
  initialSheet: null,  // sheet number requested by the URL (#sheet=n), applied on the first render
  hashDoc: null,       // #doc= payload last loaded
  hashShort: null,     // #d= id last loaded (short link)
  pendingDownload: null, // export requested by the URL (#doc=…&download=pdf), run after the first valid render
  sheet: 0,
  view: "",            // requested view id ("" = first)
  kind: "",            // requested kind ("" = the view's own)
  selectedNode: null,
  ready: false,
  busy: false,
  dirty: false,        // text changed while a render was running
  tree: null,          // scanJson() cache
  treeText: null,
  vb: null,            // current viewBox {x, y, w, h}
  page: null,          // current page size {w, h}
  versions: null,
};

function loadColors() {
  try {
    const c = JSON.parse(localStorage.getItem(COLORS_KEY) || "null");
    if (c && typeof c === "object") return { color: String(c.color || ""), preset: String(c.preset || "") };
  } catch (_) { /* ignore */ }
  return { color: "", preset: "" };
}

/** Name of the View field holding the conductor colour preset (IEC / US...), if the library has one. */
function presetField() {
  const opts = state.viewOptions || {};
  const names = Object.keys(opts).filter((k) => k !== "color" && Array.isArray(opts[k]) && opts[k].length);
  return names.find((k) => /conductor/i.test(k)) || names.find((k) => /palette|preset/i.test(k)) || null;
}

/** View overrides sent to the worker. */
function viewOverrides() {
  const out = {};
  const opts = state.viewOptions || {};
  if (state.colors.color && Array.isArray(opts.color) && opts.color.includes(state.colors.color)) out.color = state.colors.color;
  const pf = presetField();
  if (pf && state.colors.preset && opts[pf].includes(state.colors.preset)) out[pf] = state.colors.preset;
  return out;
}

const interaction = createInteraction({
  nodes: () => state.nodes,
  links: () => state.links,
  tip: $("#tip"),
  viewport: $("#viewport"),
  t,
});

/* ================================================================== worker */

const worker = new Worker("worker.js");
let nextId = 1;
const pending = new Map();

function call(type, req) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, type, req });
  });
}

worker.onmessage = (ev) => {
  const msg = ev.data;
  if (msg.type === "progress") return showProgress(msg.step, msg.pct);
  if (msg.type === "ready") {
    state.ready = true;
    state.versions = { version: msg.version, pyodide: msg.pyodide };
    $("#powered").textContent = t("footer.powered", state.versions);
    $("#loader").hidden = true;
    scheduleRender(0);
    return;
  }
  if (msg.type === "fatal") return showFatal(msg.message);
  const p = pending.get(msg.id);
  if (!p) return;
  pending.delete(msg.id);
  if (msg.type === "result") p.resolve(msg.result);
  else p.reject(new Error(msg.message));
};
worker.onerror = (ev) => showFatal(ev.message || "worker error");

function showProgress(step, pct) {
  $("#loader-step").textContent = t(`load.${step}`);
  $("#loader-step").dataset.i18n = `load.${step}`;
  $("#loader-bar").style.width = `${pct}%`;
  $("#loader-progress").setAttribute("aria-valuenow", String(pct));
}

function showFatal(message) {
  $("#loader").hidden = false;
  $("#loader-error").hidden = false;
  $("#loader-error-msg").textContent = message;
  setStatus(t("load.fatal"), "bad");
}

/* ================================================================== rendering loop */

let timer = null;
function scheduleRender(delay = DEBOUNCE_MS) {
  clearTimeout(timer);
  timer = setTimeout(runRender, delay);
}

async function runRender() {
  if (!state.ready || !state.editor) return;
  if (state.busy) { state.dirty = true; return; }
  state.busy = true;
  state.dirty = false;
  const text = state.editor.getText();
  setStatus(t("status.rendering"));
  try {
    const result = await call("process", { text, view: state.view, kind: state.kind, lang: lang(), options: viewOverrides() });
    if (state.editor.getText() === text) {
      applyResult(result, text);
      if (state.pendingDownload) {
        const kind = state.pendingDownload;
        state.pendingDownload = null;
        onDownload(kind);  // an invalid document gets the usual "fix the errors first" message
      }
    }
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
    state.busy = false;
    if (state.dirty) scheduleRender(0);
  }
}

function jsonTree(text) {
  if (state.treeText !== text) { state.tree = scanJson(text); state.treeText = text; }
  return state.tree;
}

function applyResult(res, text) {
  state.result = res;
  // ---- errors -> editor diagnostics
  const diags = [];
  const tree = res.stage === "json" ? null : jsonTree(text);
  for (const e of res.errors) {
    let range = null;
    if (res.stage === "json" && e.pos != null) range = { from: e.pos, to: Math.min(e.pos + 1, text.length) };
    else if (e.path) {
      const loc = locatePath(tree, e.path);
      if (loc) range = firstLine(text, loc.from, loc.to);
    }
    e.range = range;
    if (range) diags.push({ ...range, severity: "error", message: (e.path ? e.path + ": " : "") + e.message });
  }
  // findings -> warnings on node lines
  if (res.ok) {
    for (const f of res.findings) {
      const node = f.node && res.nodes[f.node];
      const loc = node ? locatePath(tree, node.path) : null;
      if (loc) {
        diags.push({ ...firstLine(text, loc.from, loc.to), severity: f.level === "error" ? "error" : f.level === "warning" ? "warning" : "info",
                     message: `${f.rule}: ${f.message}` });
      }
    }
  }
  state.editor.setDiagnostics(diags);

  if (res.options) state.viewOptions = res.options;
  if (res.ok) {
    state.nodes = res.nodes;
    state.links = res.links || [];
    let keepSheet = state.pages.length === res.pages.length ? state.sheet : 0;
    const sameShape = state.pages.length && state.page && res.pages.length && !state.refit;
    state.refit = false;
    state.pages = res.pages.map((p) => {
      const m = /<svg\b[^>]*\bdata-uw-sheet="([^"]*)"/.exec(p.svg.slice(0, 2000));
      return { ...p, sheetNo: m ? m[1] : null };
    });
    if (state.initialSheet != null) {
      const k = sheetIndexOf(state.initialSheet);
      state.initialSheet = null;
      if (k >= 0) keepSheet = k;
    }
    renderViewControls(res);
    renderColorControls();
    showSheet(Math.min(keepSheet, res.pages.length - 1), { keepView: !!sameShape });
    setStatus(t("status.ok", { sheets: res.pages.length, findings: res.findings.length }), "ok");
  } else {
    setStatus(res.stage === "json" ? t("status.json") : t("status.invalid", { count: res.errors.length }), "bad");
  }
  $("#stale").hidden = res.ok || !state.pages.length;
  $("#empty").hidden = !!state.pages.length;
  renderIssues();
}

function setStatus(text, cls = "") {
  const el = $("#status");
  el.textContent = text;
  el.className = cls;
}

/* ================================================================== view controls & sheets */

function renderViewControls(res) {
  const sel = $("#view-select");
  const views = res.views || [];
  sel.hidden = views.length < 2;
  sel.innerHTML = "";
  for (const v of views) {
    const o = document.createElement("option");
    o.value = v.id;
    o.textContent = v.title + (v.kind === "multi-line" ? ` (${t("kind.multi-line")})` : "");
    sel.append(o);
  }
  if (res.view) {
    if (views.some((v) => v.id === res.view.id)) sel.value = res.view.id;
    document.querySelectorAll("#kind-toggle button").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.kind === res.view.kind));
    });
  }
  const tabs = $("#sheet-tabs");
  tabs.innerHTML = "";
  state.pages.forEach((p, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "tab");
    b.textContent = state.pages.length > 1 ? `${i + 1}. ${p.title}` : p.title;
    b.title = p.title;
    b.addEventListener("click", () => showSheet(i));
    tabs.append(b);
  });
}

function showSheet(i, { keepView = false } = {}) {
  if (!state.pages.length) return;
  state.sheet = i;
  document.querySelectorAll("#sheet-tabs button").forEach((b, k) => {
    b.setAttribute("aria-selected", String(k === i));
    b.tabIndex = k === i ? 0 : -1;
    if (k === i) b.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  const vp = $("#viewport");
  vp.querySelector(":scope > svg")?.remove();
  const doc = new DOMParser().parseFromString(state.pages[i].svg, "image/svg+xml");
  const svg = document.importNode(doc.documentElement, true);
  const [, , w, h] = (svg.getAttribute("viewBox") || "0 0 420 297").split(/\s+/).map(Number);
  const prevPage = state.page;
  state.page = { w, h };
  // the stand-alone hover styles of the sheet would leak into the page: the viewer has its own
  svg.querySelectorAll(":scope > style").forEach((el) => el.remove());
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", state.pages[i].title);
  vp.prepend(svg);
  if (keepView && state.vb && prevPage && prevPage.w === w && prevPage.h === h) setViewBox(state.vb);
  else fit();
  interaction.attach(svg);
}

/** Page index of the sheet numbered ``n`` (data-uw-sheet), else of the n-th sheet; -1 when unknown. */
function sheetIndexOf(n) {
  const s = String(n);
  const k = state.pages.findIndex((p) => p.sheetNo === s);
  if (k >= 0) return k;
  const i = parseInt(s, 10) - 1;
  return Number.isFinite(i) && i >= 0 && i < state.pages.length ? i : -1;
}

/* ================================================================== colour mode */

function colorLabel(v) {
  const k = `color.${v}`;
  const s = t(k);
  return s === k ? String(v) : s;
}

function presetLabel(v) {
  const k = `preset.${String(v).toLowerCase()}`;
  const s = t(k);
  return s === k ? String(v).toUpperCase() : s;
}

let colorSig = "";
function renderColorControls() {
  const opts = state.viewOptions || {};
  const colors = Array.isArray(opts.color) ? opts.color : null;
  const pf = presetField();
  const presets = pf ? opts[pf] : null;
  const sig = JSON.stringify([colors, pf, presets, lang()]);
  const cs = $("#color-select");
  const ps = $("#preset-select");
  if (sig !== colorSig) {
    colorSig = sig;
    cs.innerHTML = "";
    ps.innerHTML = "";
    if (colors) {
      cs.append(new Option(t("color.opt", { v: t("color.document") }), ""));
      for (const v of colors) cs.append(new Option(t("color.opt", { v: colorLabel(v) }), v));
    }
    if (presets) {
      ps.append(new Option(t("preset.opt", { v: t("color.document") }), ""));
      for (const v of presets) ps.append(new Option(t("preset.opt", { v: presetLabel(v) }), v));
    }
  }
  cs.hidden = !colors;
  ps.hidden = !presets;
  cs.value = colors && colors.includes(state.colors.color) ? state.colors.color : "";
  ps.value = presets && presets.includes(state.colors.preset) ? state.colors.preset : "";
}

function onColorChange() {
  state.colors = { color: $("#color-select").value, preset: $("#preset-select").value };
  try { localStorage.setItem(COLORS_KEY, JSON.stringify(state.colors)); } catch (_) { /* ignore */ }
  scheduleRender(0);
}

/* ================================================================== cross-sheet navigation */

function navState() {
  return { uw: 1, doc: state.docSerial, idx: state.navIdx, sheet: state.sheet, vb: state.vb ? { ...state.vb } : null };
}

function navUrl() {
  const url = new URL(location.href);
  const parts = url.hash.replace(/^#/, "").split("&").filter((p) => p && !p.startsWith("sheet="));
  const no = state.pages[state.sheet] && (state.pages[state.sheet].sheetNo || String(state.sheet + 1));
  if (state.sheet > 0 && no) parts.push("sheet=" + no);
  url.hash = parts.join("&");
  return url;
}

function updateBack() {
  $("#nav-back").hidden = !(state.navIdx > 0);
}

/** Follow an off-page reference: show sheet ``n`` and reveal ``targetId`` (history entry, Back returns). */
function gotoSheet(n, targetId) {
  const k = sheetIndexOf(n);
  if (k < 0) { toast(t("msg.no_sheet", { n })); return; }
  try { history.replaceState(navState(), "", location.href); } catch (_) { /* ignore */ }
  state.navIdx += 1;
  interaction.setSticky(null);
  if (k !== state.sheet) showSheet(k); else fit();
  const els = targetId ? interaction.elements(targetId) : [];
  if (els.length) {
    revealGroups(els, { zoomIn: true });
    interaction.flash(targetId);
  }
  try { history.pushState(navState(), "", navUrl()); } catch (_) { /* ignore */ }
  updateBack();
}

function onPopState(e) {
  const s = e.state;
  if (!s || !s.uw || s.doc !== state.docSerial || !state.pages.length) return;
  state.navIdx = s.idx || 0;
  const k = Math.min(Math.max(0, s.sheet || 0), state.pages.length - 1);
  if (k !== state.sheet) showSheet(k);
  if (s.vb) setViewBox(s.vb);
  updateBack();
}

function goBack() {
  if (state.navIdx > 0) history.back();
}

/* ================================================================== zoom & pan (viewBox based) */

function currentSvg() {
  return $("#viewport > svg");
}

function setViewBox(vb) {
  const svg = currentSvg();
  if (!svg) return;
  const vp = $("#viewport");
  const aspect = (vp.clientWidth || 1) / (vp.clientHeight || 1);
  // keep the viewBox aspect equal to the viewport aspect (so screen <-> drawing mapping is linear)
  const cx = vb.x + vb.w / 2;
  const cy = vb.y + vb.h / 2;
  let w = vb.w;
  let h = vb.h;
  if (w / h > aspect) h = w / aspect; else w = h * aspect;
  const maxW = state.page.w * 20;
  const minW = state.page.w / 60;
  if (w > maxW) { h *= maxW / w; w = maxW; }
  if (w < minW) { h *= minW / w; w = minW; }
  state.vb = { x: cx - w / 2, y: cy - h / 2, w, h };
  svg.setAttribute("viewBox", `${state.vb.x} ${state.vb.y} ${state.vb.w} ${state.vb.h}`);
}

function fit() {
  if (!state.page) return;
  const m = Math.max(state.page.w, state.page.h) * 0.03;
  setViewBox({ x: -m, y: -m, w: state.page.w + 2 * m, h: state.page.h + 2 * m });
}

function toDrawing(clientX, clientY) {
  const vp = $("#viewport").getBoundingClientRect();
  return {
    x: state.vb.x + ((clientX - vp.left) / vp.width) * state.vb.w,
    y: state.vb.y + ((clientY - vp.top) / vp.height) * state.vb.h,
  };
}

function zoomAt(factor, clientX, clientY) {
  if (!state.vb) return;
  const vpRect = $("#viewport").getBoundingClientRect();
  if (clientX == null) { clientX = vpRect.left + vpRect.width / 2; clientY = vpRect.top + vpRect.height / 2; }
  const p = toDrawing(clientX, clientY);
  const w = state.vb.w / factor;
  const h = state.vb.h / factor;
  setViewBox({ x: p.x - (p.x - state.vb.x) / factor, y: p.y - (p.y - state.vb.y) / factor, w, h });
}

function panBy(dxPx, dyPx) {
  const vp = $("#viewport");
  const s = state.vb.w / vp.clientWidth;
  setViewBox({ ...state.vb, x: state.vb.x - dxPx * s, y: state.vb.y - dyPx * s });
}

function setupViewport() {
  const vp = $("#viewport");
  vp.addEventListener("wheel", (e) => {
    if (!state.vb) return;
    e.preventDefault();
    // wheel (or trackpad pinch, reported with ctrlKey) zooms around the pointer; drag pans
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
    const k = e.ctrlKey ? 0.01 : 0.0015;
    zoomAt(Math.exp(-e.deltaY * unit * k), e.clientX, e.clientY);
  }, { passive: false });

  const pointers = new Map();
  let moved = 0;
  let pinch = null;
  vp.addEventListener("pointerdown", (e) => {
    if (!state.vb || e.button !== 0) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    vp.setPointerCapture(e.pointerId);
    moved = 0;
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) };
    }
  });
  vp.addEventListener("pointermove", (e) => {
    const prev = pointers.get(e.pointerId);
    if (!prev) return;
    const cur = { x: e.clientX, y: e.clientY };
    pointers.set(e.pointerId, cur);
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinch.d > 0) zoomAt(d / pinch.d, (a.x + b.x) / 2, (a.y + b.y) / 2);
      pinch.d = d;
      moved += 10;
      return;
    }
    moved += Math.abs(cur.x - prev.x) + Math.abs(cur.y - prev.y);
    if (moved > 4) {
      vp.classList.add("panning");
      panBy(cur.x - prev.x, cur.y - prev.y);
    }
  });
  const end = (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    vp.classList.remove("panning");
    if (e.type === "pointerup" && moved <= 4 && pointers.size === 0) {
      onDrawingClick(document.elementFromPoint(e.clientX, e.clientY), e);
    }
  };
  vp.addEventListener("pointerup", end);
  vp.addEventListener("pointercancel", end);

  // hover highlighting (mouse only; touch uses tap = sticky selection)
  let hoverFrame = 0;
  let lastMove = null;
  vp.addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse" || pointers.size || e.buttons) return;
    lastMove = e;
    if (hoverFrame) return;
    hoverFrame = requestAnimationFrame(() => {
      hoverFrame = 0;
      const ev = lastMove;
      interaction.setHover(interaction.resolve(ev.target), ev.clientX, ev.clientY);
    });
  });
  vp.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") interaction.setHover(null); });

  // keyboard (anywhere outside text fields): sheets, zoom, fit, back, clear
  document.addEventListener("keydown", (e) => {
    if (e.defaultPrevented || !state.vb) return;
    const el = e.target;
    if (el && el.closest && el.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], .cm-editor, .menu-list, .splitter")) return;
    if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); goBack(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const step = 60;
    const prev = () => state.sheet > 0 && showSheet(state.sheet - 1);
    const next = () => state.sheet < state.pages.length - 1 && showSheet(state.sheet + 1);
    const map = e.shiftKey ? {
      ArrowLeft: () => panBy(step, 0), ArrowRight: () => panBy(-step, 0),
      ArrowUp: () => panBy(0, step), ArrowDown: () => panBy(0, -step),
    } : {
      "+": () => zoomAt(1.25), "=": () => zoomAt(1.25), "-": () => zoomAt(0.8), "0": fit, f: fit, F: fit,
      ArrowLeft: prev, ArrowRight: next, PageUp: prev, PageDown: next,
      ArrowUp: () => panBy(0, step), ArrowDown: () => panBy(0, -step),
      Escape: clearSelection,
    };
    if (e.shiftKey && (e.key === "+" || e.key === "F")) map[e.key] = e.key === "F" ? fit : () => zoomAt(1.25);
    if (map[e.key]) { e.preventDefault(); map[e.key](); }
  });
  window.addEventListener("popstate", onPopState);
  $("#nav-back").addEventListener("click", goBack);

  new ResizeObserver(() => state.vb && setViewBox(state.vb)).observe(vp);
  $("#zoom-in").addEventListener("click", () => zoomAt(1.25));
  $("#zoom-out").addEventListener("click", () => zoomAt(0.8));
  $("#zoom-fit").addEventListener("click", fit);
}

/* ================================================================== node selection */

function markNode(id) {
  interaction.setSticky(id ? { type: "node", key: "node:" + id, id } : null);
  return id ? interaction.elements(id) : [];
}

/** Reveal a link of the document in the editor. */
function revealPath(path) {
  if (!path) return;
  const text = state.editor.getText();
  const loc = locatePath(jsonTree(text), path);
  if (loc) {
    const r = firstLine(text, loc.from, loc.to);
    state.editor.reveal(r.from, r.to);
  }
}

/** Click / tap on the drawing. */
function onDrawingClick(target, e) {
  const hit = interaction.resolve(target);
  if (hit && hit.type === "ref") {
    if (hit.sheet) gotoSheet(hit.sheet, hit.id);
    return;
  }
  if (hit && hit.type === "node") selectNode(hit.id, { from: "drawing" });
  else {
    selectNode(null);
    if (hit) {
      interaction.setSticky(hit);
      if (hit.type === "link") revealPath(hit.info.path);
    }
  }
  // touch has no hover: show the tooltip of the tapped element
  if (hit && e.pointerType && e.pointerType !== "mouse") interaction.showTip(hit, e.clientX, e.clientY);
}

function clearSelection() {
  selectNode(null);
  interaction.setSticky(null);
}

function selectNode(id, { from = "list", finding = null } = {}) {
  state.selectedNode = id;
  document.querySelectorAll(".issue.selected").forEach((el) => el.classList.remove("selected"));
  if (finding) finding.classList.add("selected");
  if (!id) { markNode(null); return; }
  // find the sheet that shows the node
  const needle = `data-uw-id="${id.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}"`;
  if (from !== "drawing" && state.pages.length && !state.pages[state.sheet].svg.includes(needle)) {
    const k = state.pages.findIndex((p) => p.svg.includes(needle));
    if (k >= 0) showSheet(k, { keepView: false });
  }
  const groups = markNode(id);
  if (from !== "drawing" && groups.length) revealGroups(groups);
  // reveal the node in the editor
  const node = state.nodes[id];
  const text = state.editor.getText();
  if (node) {
    const loc = locatePath(jsonTree(text), node.path);
    if (loc) {
      const r = firstLine(text, loc.from, loc.to);
      state.editor.reveal(r.from, r.to);
    }
  }
  if (from === "drawing") {
    // highlight the matching findings
    document.querySelectorAll(`#list-findings .issue[data-node="${CSS.escape(id)}"]`).forEach((el) => el.classList.add("selected"));
  }
}

function revealGroups(groups, { zoomIn = false } = {}) {
  let box = null;
  for (const g of groups) {
    let b;
    try { b = g.getBBox(); } catch (_) { continue; }
    if (!b || (!b.width && !b.height)) continue;
    box = box ? {
      x: Math.min(box.x, b.x), y: Math.min(box.y, b.y),
      x2: Math.max(box.x2, b.x + b.width), y2: Math.max(box.y2, b.y + b.height),
    } : { x: b.x, y: b.y, x2: b.x + b.width, y2: b.y + b.height };
  }
  if (!box || !state.vb) return;
  const cx = (box.x + box.x2) / 2;
  const cy = (box.y + box.y2) / 2;
  // zoom so the node is comfortably visible (never zoom out beyond the current view)
  const base = zoomIn ? state.page.w / 2.5 : state.page.w / 4;
  const w = Math.min(state.vb.w, Math.max((box.x2 - box.x) * 4, base));
  const h = state.vb.h * (w / state.vb.w);
  setViewBox({ x: cx - w / 2, y: cy - h / 2, w, h });
}

/* ================================================================== issues panel */

function renderIssues() {
  const res = state.result;
  const errors = res ? res.errors : [];
  const findings = res && res.ok ? res.findings : (state.lastFindings || []);
  if (res && res.ok) state.lastFindings = res.findings;

  const le = $("#list-errors");
  le.innerHTML = "";
  if (!errors.length) le.innerHTML = `<li class="none">${escapeHtml(t("issues.none.errors"))}</li>`;
  for (const e of errors) {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "issue";
    b.innerHTML = `<span class="sev error">${escapeHtml(t("level.error"))}</span>` +
      (e.path ? `<code class="chip">${escapeHtml(e.path)}</code>` : (e.line ? `<code class="chip">${e.line}:${e.col}</code>` : "")) +
      `<span class="msg">${escapeHtml(e.message)}</span>`;
    b.addEventListener("click", () => { if (e.range) state.editor.reveal(e.range.from, e.range.to); });
    li.append(b);
    le.append(li);
  }

  const lf = $("#list-findings");
  lf.innerHTML = "";
  if (!findings.length) lf.innerHTML = `<li class="none">${escapeHtml(t("issues.none.findings"))}</li>`;
  const order = { error: 0, warning: 1, info: 2 };
  [...findings].sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3)).forEach((f) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "issue";
    if (f.node) b.dataset.node = f.node;
    const node = f.node && state.nodes[f.node];
    const nodeLabel = node ? (node.ref || f.node) : f.node;
    b.innerHTML = `<span class="sev ${escapeHtml(f.level)}">${escapeHtml(t("level." + f.level))}</span>` +
      `<span class="rule">${escapeHtml(f.rule)}</span>` +
      `<span class="msg">${escapeHtml(f.message)}</span>` +
      (f.node ? `<code class="chip" title="${escapeHtml(t("finding.node"))} ${escapeHtml(f.node)}">${escapeHtml(nodeLabel)}</code>` : "");
    if (f.source) b.title = f.source;
    b.addEventListener("click", () => selectNode(f.node || null, { from: "list", finding: b }));
    li.append(b);
    lf.append(li);
  });

  const ce = $("#count-errors");
  ce.textContent = String(errors.length);
  ce.className = "count" + (errors.length ? " has-error" : "");
  const cf = $("#count-findings");
  cf.textContent = String(findings.length);
  const worst = findings.some((f) => f.level === "error") ? " has-error" : findings.some((f) => f.level === "warning") ? " has-warning" : "";
  cf.className = "count" + worst;
  const mobile = $("#mobile-issues-count");
  mobile.hidden = !errors.length;
  mobile.textContent = String(errors.length);
  if (errors.length) selectIssuesTab("errors");
  else if (state.issuesTab !== "findings" && findings.length) selectIssuesTab("findings");
}

function selectIssuesTab(which) {
  state.issuesTab = which;
  $("#tab-errors").setAttribute("aria-selected", String(which === "errors"));
  $("#tab-findings").setAttribute("aria-selected", String(which === "findings"));
  $("#list-errors").hidden = which !== "errors";
  $("#list-findings").hidden = which !== "findings";
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ================================================================== documents: examples, files, sharing */

/** Show `text` in the editor. keepDraft: the document comes from an example or a shared link, so the saved
 * draft stays as it is until the user edits (a restore button is offered when they differ). */
function loadText(text, stem, { keepDraft = false } = {}) {
  state.stem = stem || "uniwire";
  state.selectedNode = null;
  state.docSerial += 1;
  state.navIdx = 0;
  interaction.setSticky(null);
  updateBack();
  state.view = "";
  state.kind = "";
  state.pages = [];
  state.page = null;
  state.editor.setText(text);
  if (keepDraft) offerDraft(text);
  else saveDraft(text);
  scheduleRender(0);
}

async function loadExample(name, { updateUrl = true } = {}) {
  const ex = state.examples.find((e) => e.name === name || e.file === name || e.name.startsWith(name + "_") ||
                                       e.name.replace(/^\d+_/, "") === name);
  const file = ex ? ex.file : `${name}.uniwire.json`;
  try {
    const r = await fetch(`examples/${encodeURIComponent(file)}`);
    if (!r.ok) throw new Error(String(r.status));
    loadText(await r.text(), ex ? ex.name : name, { keepDraft: true });
    $("#examples").value = ex ? ex.name : "";
    if (updateUrl) {
      const url = new URL(location.href);
      url.hash = "";
      url.searchParams.set("example", ex ? ex.name : name);
      history.replaceState(null, "", url);
    }
  } catch (_) {
    toast(t("msg.example_error", { name }));
  }
}

async function loadExamplesIndex() {
  try {
    const r = await fetch("examples/index.json", { cache: "no-cache" });
    state.examples = await r.json();
  } catch (_) {
    state.examples = [];
  }
  const sel = $("#examples");
  for (const ex of state.examples) {
    const o = document.createElement("option");
    o.value = ex.name;
    o.textContent = `${ex.name.split("_")[0]} · ${ex.title}`;
    o.lang = ex.lang;
    sel.append(o);
  }
}

function readFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    loadText(String(reader.result), file.name.replace(/\.uniwire\.json$|\.json$/i, ""));
    $("#examples").value = "";
    const url = new URL(location.href);
    url.searchParams.delete("example");
    url.hash = "";
    history.replaceState(null, "", url);
  };
  reader.onerror = () => toast(t("msg.file_error"));
  reader.readAsText(file);
}

async function compress(text) {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream("deflate-raw"));
  const buf = new Uint8Array(await new Response(stream).arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

class SharedTooLarge extends Error {}

/** Re-indent a compact (single-line) JSON document, as produced by assistants building #doc= links.
 *  Already-formatted text and invalid JSON are returned unchanged (the editor then shows the parse error). */
function prettyJson(text) {
  const head = text.slice(0, 4000);
  if (head.includes("\n")) return text;
  try {
    return JSON.stringify(JSON.parse(text), null, 2) + "\n";
  } catch {
    return text;
  }
}

/** #doc= payload -> text. Streams the inflated bytes and stops at MAX_SHARED_MB (SharedTooLarge). */
async function decompress(b64) {
  const bin = atob(b64.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw")).getReader();
  const max = MAX_SHARED_MB * 1024 * 1024;
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      reader.cancel().catch(() => {});
      throw new SharedTooLarge();
    }
    chunks.push(value);
  }
  const all = new Uint8Array(size);
  let pos = 0;
  for (const c of chunks) { all.set(c, pos); pos += c.byteLength; }
  return new TextDecoder("utf-8", { fatal: true }).decode(all);
}

async function share() {
  const text = state.editor.getText();
  const url = new URL(location.href);
  url.searchParams.delete("example");
  state.hashDoc = await compress(text);
  url.hash = "doc=" + state.hashDoc;
  history.replaceState(null, "", url);
  const link = url.toString();
  try {
    if (!navigator.clipboard) throw new Error("no clipboard");
    await Promise.race([navigator.clipboard.writeText(link),
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 2000))]);
    toast(t("msg.copied") + (link.length > 30000 ? " " + t("msg.too_long") : ""));
  } catch (_) {
    // no clipboard access: show the link in a selectable field
    const el = $("#toast");
    el.textContent = t("msg.copy_failed") + " ";
    const input = document.createElement("input");
    input.readOnly = true;
    input.value = link;
    input.className = "toast-link";
    el.append(input);
    el.hidden = false;
    input.select();
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, 15000);
  }
}

let draftTimer = null;
function saveDraft(text) {
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ text, stem: state.stem })); } catch (_) { /* ignore */ }
  }, 800);
}

/** After an example or a shared link replaced the editor content: say that the draft is kept, offer it back. */
function offerDraft(loaded) {
  const draft = loadDraft();
  if (!draft || draft.text === loaded) return;
  const el = $("#toast");
  el.textContent = t("msg.draft_kept") + " ";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "toast-action";
  btn.textContent = t("msg.draft_restore");
  btn.addEventListener("click", () => {
    hideToast();
    $("#examples").value = "";
    const url = new URL(location.href);
    url.searchParams.delete("example");
    url.hash = "";
    history.replaceState(null, "", url);
    state.hashDoc = null;
    loadText(draft.text, draft.stem);
  });
  el.append(btn);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, 10000);
}

function loadDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    return d && typeof d.text === "string" && d.text.trim() ? d : null;
  } catch (_) {
    return null;
  }
}

/* ================================================================== downloads */

function download(name, content, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

function suffix() {
  return state.result && state.result.view && state.result.view.kind === "multi-line" ? "-multiline" : "";
}

function printAll() {
  if (!state.pages.length) return toast(t("msg.need_valid"));
  const first = new DOMParser().parseFromString(state.pages[0].svg, "image/svg+xml").documentElement;
  const w = first.getAttribute("width") || "420mm";
  const h = first.getAttribute("height") || "297mm";
  const body = state.pages.map((p) => `<section class="sheet">${p.svg.replace(/^<\?xml[^>]*>\s*/, "")}</section>`).join("\n");
  const title = escapeHtml((state.result && state.result.title) || state.stem);
  const html = `<!doctype html><html lang="${escapeHtml((state.result && state.result.lang) || "en")}"><head><meta charset="utf-8">
<title>${title}</title><style>
@page { size: ${w} ${h}; margin: 0; }
html, body { margin: 0; background: #888; }
.sheet { width: ${w}; height: ${h}; margin: 8mm auto; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.3); page-break-after: always; break-after: page; }
.sheet svg { width: 100%; height: 100%; display: block; }
@media print { html, body { background: #fff; } .sheet { margin: 0; box-shadow: none; } }
</style></head><body>
${body}
<script>window.addEventListener("load", () => setTimeout(() => window.print(), 300));<\/script>
</body></html>`;
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) download(`${state.stem}${suffix()}-sheets.html`, blob);
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function onDownload(kind) {
  closeMenu();
  const text = state.editor.getText();
  if (kind === "source") return download(`${state.stem}.uniwire.json`, text, "application/json");
  if (kind === "svg") {
    if (!state.pages.length) return toast(t("msg.need_valid"));
    const n = state.pages.length > 1 ? `-f${state.sheet + 1}` : "";
    return download(`${state.stem}${suffix()}${n}.svg`, state.pages[state.sheet].svg, "image/svg+xml");
  }
  if (kind === "print") return printAll();
  if (!(state.result && state.result.ok)) return toast(t("msg.need_valid"));
  if (kind === "json" || kind === "bom") {
    try {
      const r = await call("export", { text, what: kind === "json" ? "normalized" : "bom", lang: lang() });
      if (!r.ok) return toast(r.error);
      if (kind === "json") download(`${state.stem}.normalized.uniwire.json`, r.content, "application/json");
      else download(`${state.stem}-bom.csv`, "﻿" + r.content, "text/csv");
    } catch (err) {
      toast(String(err.message || err));
    }
    return;
  }
  if (kind === "pdf") {
    toast(t("msg.pdf_wait"), 60000);
    try {
      const r = await call("pdf", { text, view: state.view, kind: state.kind, lang: lang(), options: viewOverrides() });
      download(`${state.stem}${suffix()}.pdf`, new Blob([r.bytes], { type: "application/pdf" }));
      hideToast();
    } catch (err) {
      toast(t("msg.pdf_failed", { error: err.message || err }), 8000);
    }
  }
}

function closeMenu() {
  $("#dl-list").hidden = true;
  $("#btn-download").setAttribute("aria-expanded", "false");
}

/* ================================================================== misc UI */

let toastTimer = null;
function toast(text, ms = 3500) {
  const el = $("#toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, ms);
}
function hideToast() { $("#toast").hidden = true; }

function setPane(pane) {
  $(".workspace").dataset.pane = pane;
  document.querySelectorAll(".mobile-tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.pane === pane)));
  if (pane === "drawing" && state.vb) requestAnimationFrame(() => setViewBox(state.vb));
}

function setupSplitter() {
  const sp = $("#splitter");
  const ws = $(".workspace");
  const apply = (pct) => {
    pct = Math.min(75, Math.max(18, pct));
    ws.style.setProperty("--editor-width", pct + "%");
    sp.setAttribute("aria-valuenow", String(Math.round(pct)));
    return pct;
  };
  try { const saved = parseFloat(localStorage.getItem(SPLIT_KEY)); if (saved) apply(saved); } catch (_) { /* ignore */ }
  let dragging = false;
  sp.addEventListener("pointerdown", (e) => { dragging = true; sp.setPointerCapture(e.pointerId); sp.classList.add("dragging"); });
  sp.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const r = ws.getBoundingClientRect();
    const pct = apply(((e.clientX - r.left) / r.width) * 100);
    try { localStorage.setItem(SPLIT_KEY, String(pct)); } catch (_) { /* ignore */ }
  });
  sp.addEventListener("pointerup", () => { dragging = false; sp.classList.remove("dragging"); });
  sp.addEventListener("keydown", (e) => {
    const cur = parseFloat(getComputedStyle(ws).getPropertyValue("--editor-width")) || 40;
    if (e.key === "ArrowLeft") apply(cur - 3);
    if (e.key === "ArrowRight") apply(cur + 3);
  });
}

function setupUi() {
  // UI language
  const syncLangButtons = () => document.querySelectorAll("#ui-lang button").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.lang === lang()));
  });
  document.querySelectorAll("#ui-lang button").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  onLangChange(() => {
    syncLangButtons();
    renderColorControls();
    if (state.versions) $("#powered").textContent = t("footer.powered", state.versions);
    scheduleRender(0); // validation errors and findings are translated by the library
  });
  document.documentElement.lang = lang();
  applyStatic();
  syncLangButtons();

  $("#examples").addEventListener("change", (e) => { if (e.target.value) loadExample(e.target.value); });
  $("#btn-open").addEventListener("click", () => $("#file-input").click());
  $("#file-input").addEventListener("change", (e) => { const f = e.target.files[0]; if (f) readFile(f); e.target.value = ""; });
  $("#btn-share").addEventListener("click", share);

  $("#btn-download").addEventListener("click", (e) => {
    e.stopPropagation();
    const list = $("#dl-list");
    list.hidden = !list.hidden;
    $("#btn-download").setAttribute("aria-expanded", String(!list.hidden));
    if (!list.hidden) list.querySelector("button").focus();
  });
  document.querySelectorAll("#dl-list [data-dl]").forEach((b) => b.addEventListener("click", () => onDownload(b.dataset.dl)));
  document.addEventListener("click", (e) => { if (!e.target.closest("#dl-menu")) closeMenu(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

  $("#view-select").addEventListener("change", (e) => {
    state.view = e.target.value;
    state.kind = "";
    state.refit = true;
    scheduleRender(0);
  });
  document.querySelectorAll("#kind-toggle button").forEach((b) => b.addEventListener("click", () => {
    state.kind = b.dataset.kind;
    state.refit = true;
    document.querySelectorAll("#kind-toggle button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    scheduleRender(0);
  }));

  $("#tab-errors").addEventListener("click", () => selectIssuesTab("errors"));
  $("#tab-findings").addEventListener("click", () => selectIssuesTab("findings"));
  $("#issues-toggle").addEventListener("click", () => {
    const el = $("#pane-issues");
    el.classList.toggle("collapsed");
    $("#issues-toggle").setAttribute("aria-expanded", String(!el.classList.contains("collapsed")));
  });
  document.querySelectorAll(".mobile-tabs [role=tab]").forEach((b) => b.addEventListener("click", () => setPane(b.dataset.pane)));

  // drag and drop (anywhere on the page)
  let depth = 0;
  const overlay = $("#drop-overlay");
  window.addEventListener("dragenter", (e) => { if (e.dataTransfer.types.includes("Files")) { depth++; overlay.hidden = false; } });
  window.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) overlay.hidden = true; });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    overlay.hidden = true;
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) readFile(f);
  });
  window.addEventListener("hashchange", () => {
    // ignore the hash changes of the sheet navigation (#…&sheet=n) when the document is the same
    const m = /(?:^#|&)doc=([A-Za-z0-9_-]+)/.exec(location.hash);
    const payload = m ? m[1] : null;
    const short = shortId();
    const sm = /(?:^#|&)sheet=([^&]+)/.exec(location.hash);
    if (short === state.hashShort && (payload === state.hashDoc || (!payload && !state.hashDoc))) {
      if (sm && history.state == null && state.pages.length) {
        const k = sheetIndexOf(decodeURIComponent(sm[1]));
        if (k >= 0 && k !== state.sheet) showSheet(k);
      }
      return;
    }
    initialDocument(true);
  });
  $("#color-select").addEventListener("change", onColorChange);
  $("#preset-select").addEventListener("change", onColorChange);

  setupViewport();
  setupSplitter();
  setStatus(t("status.loading"));
}

async function initialDocument(fromHashChange = false) {
  await openInitialDocument(fromHashChange);
  const sm = /(?:^#|&)sheet=([^&]+)/.exec(location.hash);
  if (sm) state.initialSheet = decodeURIComponent(sm[1]);
}

/** Id of a short link (#d=<id>: a document kept by the hosted MCP server, served at /api/doc/<id>). */
function shortId() {
  const m = /(?:^#|&)d=([0-9A-Za-z]{6,32})(?=&|$)/.exec(location.hash);
  return m ? m[1] : null;
}

/** Open a document that came with the link; links made for assistants may also ask for the PDF (&download=pdf). */
function openShared(text, fromHashChange) {
  if (fromHashChange && text === state.editor.getText()) return;
  const dl = /(?:^#|&)download=(pdf)(?=&|$)/.exec(location.hash);
  if (dl) {
    state.pendingDownload = dl[1];
    history.replaceState(history.state, "", location.href.replace(/&download=pdf(?=&|$)/, ""));
  }
  loadText(text, titleStem(text), { keepDraft: true });
  $("#examples").value = "";
}

/** File name stem from the document title ("Small bakery, 400 V" -> "small-bakery-400-v"), as the PDF links of
 * the hosted server name their files; "uniwire" when there is no title. */
function titleStem(text) {
  let title = "";
  try { title = String((JSON.parse(text).meta || {}).title || ""); } catch (_) { /* invalid JSON: no title */ }
  const slug = title.normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80).replace(/-+$/, "");
  return slug || "uniwire";
}

/** A link whose document cannot be opened: say so, and do not show another document (the draft) instead. */
function sharedFailed(message) {
  toast(message, 15000);
  setStatus(message, "bad");
}

async function openInitialDocument(fromHashChange) {
  const params = new URLSearchParams(location.search);
  const m = /(?:^#|&)doc=([A-Za-z0-9_-]+)/.exec(location.hash);
  state.hashDoc = m ? m[1] : null;
  state.hashShort = shortId();
  if (m) {
    try {
      return openShared(prettyJson(await decompress(m[1])), fromHashChange);
    } catch (err) {
      return sharedFailed(err instanceof SharedTooLarge ? t("msg.hash_too_large", { mb: MAX_SHARED_MB }) : t("msg.hash_error"));
    }
  }
  if (state.hashShort) {
    try {
      const r = await fetch(`/api/doc/${state.hashShort}`, { cache: "no-store" });
      if (r.status === 404) return sharedFailed(t("msg.short_missing"));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return openShared(prettyJson(await r.text()), fromHashChange);
    } catch (err) {
      return sharedFailed(t("msg.short_error", { error: err.message || err }));
    }
  }
  if (fromHashChange) return;
  if (params.get("example")) return loadExample(params.get("example"), { updateUrl: false });
  const draft = loadDraft();
  if (draft) return loadText(draft.text, draft.stem);
  if (state.examples.length) return loadExample(state.examples[0].name, { updateUrl: false });
}

async function main() {
  setupUi();
  const [editor] = await Promise.all([
    createEditor($("#editor"), {
      label: t("editor.label"),
      onChange: (text) => { saveDraft(text); scheduleRender(); },
    }),
    loadExamplesIndex(),
  ]);
  state.editor = editor;
  document.body.dataset.editor = editor.kind;
  await initialDocument();
  // Small scripting hook (console, automated tests, embedding pages)
  window.uniwireViewer = {
    getText: () => state.editor.getText(),
    setText: (text) => { state.editor.setText(text); saveDraft(text); scheduleRender(0); },
    loadExample: (name) => loadExample(name),
    get result() { return state.result; },
    showSheet: (i) => showSheet(i),
    gotoSheet: (n, id) => gotoSheet(n, id),
    get sheet() { return state.sheet; },
    get colors() { return { ...state.colors }; },
  };
}

main();
