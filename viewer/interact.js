// uniwire viewer: drawing interaction: hover / sticky highlighting, tooltips, element lookup.
//
// Works on the SVG contract of the renderer (feature-detected, older SVGs degrade gracefully):
//   node groups .uw-node[data-uw-id], tree edges .uw-edge[data-uw-edge][data-uw-parent],
//   busbars .uw-busbar[data-uw-id], links .uw-link[data-uw-link][data-uw-kind][data-uw-from][data-uw-to]
//   (with an invisible .uw-hit path), multi-line conductors [data-uw-cond], off-page references
//   .uw-ref[data-uw-target-sheet][data-uw-target-id], feeder table cells .uw-cell[data-uw-id].
// Highlighting only toggles CSS classes (uw-hl-self / -up / -down / -link / -end / -cond) on the
// elements of a per-sheet index, plus "uw-dim" on the <svg> to fade the rest.

const HL = ["uw-hl-self", "uw-hl-up", "uw-hl-down", "uw-hl-link", "uw-hl-end", "uw-hl-cond"];

function push(map, key, el) {
  const list = map.get(key);
  if (list) list.push(el); else map.set(key, [el]);
}

export function buildIndex(svg) {
  const ix = { ids: new Map(), edges: new Map(), conds: new Map(), refs: [], links: [] };
  for (const el of svg.querySelectorAll("[data-uw-id]")) push(ix.ids, el.getAttribute("data-uw-id"), el);
  for (const el of svg.querySelectorAll(".uw-edge[data-uw-edge]")) push(ix.edges, el.getAttribute("data-uw-edge"), el);
  for (const el of svg.querySelectorAll("[data-uw-cond]")) push(ix.conds, el.getAttribute("data-uw-cond"), el);
  ix.refs = [...svg.querySelectorAll(".uw-ref")];
  ix.links = [...svg.querySelectorAll(".uw-link")];
  const kind = svg.getAttribute("data-uw-view-kind");
  ix.multi = kind ? kind === "multi-line" : !!svg.querySelector(".multiline");
  ix.contract = !!(kind || svg.querySelector(".uw-node, .uw-edge, .uw-link, .uw-ref"));
  return ix;
}

/**
 * @param {object} o
 * @param {() => object} o.nodes   id -> {ref, label, type, parent, children, summary, cable}
 * @param {() => object[]} o.links links of the document (index, id, kind, from, to, label, device, cable)
 * @param {HTMLElement} o.tip      tooltip element (absolutely positioned inside the viewport)
 * @param {HTMLElement} o.viewport
 * @param {(key: string, vars?: object) => string} o.t
 */
export function createInteraction(o) {
  let svg = null;
  let ix = null;
  let marked = [];
  let sticky = null;
  let hover = null;
  let flashTimer = null;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function attach(el) {
    svg = el;
    ix = el ? buildIndex(el) : null;
    marked = [];
    hover = null;
    hideTip();
    refresh();
  }

  function index() { return ix; }

  function elements(id) { return (ix && ix.ids.get(id)) || []; }

  function nodeName(id) {
    const n = o.nodes()[id];
    if (!n) return id;
    return n.ref || n.label || id;
  }

  function linkInfo(el) {
    const links = o.links() || [];
    const key = el.getAttribute("data-uw-link") || "";
    const from = el.getAttribute("data-uw-from");
    const to = el.getAttribute("data-uw-to");
    const kind = el.getAttribute("data-uw-kind");
    return links.find((l) => key && (l.id === key || String(l.index) === key)) ||
      links.find((l) => l.from === from && l.to === to && (!kind || l.kind === kind)) ||
      { kind: kind || "", from: from || "", to: to || "", label: "", device: null, cable: "" };
  }

  /** What the pointer is on: {type: ref|link|node|cond, ...} or null. */
  function resolve(target) {
    if (!svg || !target || !target.closest || !svg.contains(target)) return null;
    const ref = target.closest(".uw-ref");
    if (ref) {
      return { type: "ref", key: "ref", el: ref, sheet: ref.getAttribute("data-uw-target-sheet") || "",
               id: ref.getAttribute("data-uw-target-id") || "" };
    }
    const link = target.closest(".uw-link");
    if (link) {
      const info = linkInfo(link);
      return { type: "link", key: "link:" + (link.getAttribute("data-uw-link") || info.index), el: link, info };
    }
    if (ix && ix.multi) {
      const cond = target.closest("[data-uw-cond]");
      const node = target.closest(".uw-node");
      if (cond && (!node || !node.contains(cond))) {
        const c = cond.getAttribute("data-uw-cond");
        return { type: "cond", key: "cond:" + c, cond: c };
      }
    }
    const g = target.closest("[data-uw-id]");
    if (g) {
      const id = g.getAttribute("data-uw-id");
      return { type: "node", key: "node:" + id, id };
    }
    return null;
  }

  function clearMarks() {
    for (const [el, cls] of marked) el.classList.remove(cls);
    marked = [];
    if (svg) svg.classList.remove("uw-dim");
  }

  function mark(els, cls) {
    if (!els) return;
    for (const el of els) { el.classList.add(cls); marked.push([el, cls]); }
  }

  function apply(target) {
    clearMarks();
    if (!target || !svg || !ix) return;
    if (target.type === "node") {
      const nodes = o.nodes();
      const id = target.id;
      mark(ix.ids.get(id), "uw-hl-self");
      mark(ix.edges.get(id), "uw-hl-up");
      // upstream: path to the source
      const seen = new Set([id]);
      let cur = nodes[id] && nodes[id].parent;
      while (cur && !seen.has(cur)) {
        seen.add(cur);
        mark(ix.ids.get(cur), "uw-hl-up");
        mark(ix.edges.get(cur), "uw-hl-up");
        cur = nodes[cur] && nodes[cur].parent;
      }
      // downstream: whole subtree
      const down = new Set();
      const stack = [...((nodes[id] && nodes[id].children) || [])];
      while (stack.length) {
        const c = stack.pop();
        if (down.has(c) || seen.has(c)) continue;
        down.add(c);
        mark(ix.ids.get(c), "uw-hl-down");
        mark(ix.edges.get(c), "uw-hl-down");
        const n = nodes[c];
        if (n && n.children) stack.push(...n.children);
      }
      if (down.size || seen.size) {
        for (const r of ix.refs) {
          const tid = r.getAttribute("data-uw-target-id");
          if (tid && down.has(tid)) mark([r], "uw-hl-down");
          else if (tid && seen.has(tid)) mark([r], "uw-hl-up");
        }
      }
    } else if (target.type === "link") {
      mark([target.el], "uw-hl-link");
      mark(ix.ids.get(target.info.from), "uw-hl-end");
      mark(ix.ids.get(target.info.to), "uw-hl-end");
      if (target.info.device) mark(ix.ids.get(target.info.device.id), "uw-hl-end");
    } else if (target.type === "cond") {
      mark(ix.conds.get(target.cond), "uw-hl-cond");
    } else {
      return; // refs: no highlight
    }
    if (marked.length) svg.classList.add("uw-dim");
  }

  function current() { return hover || sticky; }

  /** Sticky selection (click / tap / finding); null clears it. */
  function setSticky(target) {
    sticky = target;
    if (!hover) apply(sticky);
    if (!target) hideTip();
  }

  function getSticky() { return sticky; }

  /** Re-resolve the sticky selection after the sheet was re-rendered (links keep their key). */
  function refresh() {
    if (sticky && sticky.type === "link" && svg) {
      const el = ix.links.find((l) => "link:" + (l.getAttribute("data-uw-link") || linkInfo(l).index) === sticky.key);
      sticky = el ? { ...sticky, el, info: linkInfo(el) } : null;
    }
    apply(current());
  }

  function setHover(target, clientX, clientY) {
    const key = target ? target.key : null;
    const prev = hover ? hover.key : null;
    if (key !== prev) {
      hover = target;
      apply(current());
    }
    if (target) showTip(target, clientX, clientY); else hideTip();
  }

  /* ---------------------------------------------------------------- tooltip */

  function tipHtml(target) {
    const t = o.t;
    if (target.type === "ref") {
      let s = `<b>${esc(t("tip.goto", { n: target.sheet }))}</b>`;
      if (target.id) s += `<div class="tip-muted">${esc(nodeName(target.id))}</div>`;
      return s;
    }
    if (target.type === "cond") return `<b>${esc(t("tip.conductor", { c: target.cond }))}</b>`;
    if (target.type === "link") {
      const l = target.info;
      let s = `<b>${esc(t("tip.link", { kind: l.kind }))}</b>` +
        `<div>${esc(nodeName(l.from))} → ${esc(nodeName(l.to))}</div>`;
      if (l.label) s += `<div class="tip-muted">${esc(l.label)}</div>`;
      if (l.device) {
        s += `<div><span class="tip-k">${esc(t("tip.device"))}</span> ${esc(l.device.ref || l.device.id)} ` +
          `<span class="tip-muted">${esc(String(l.device.type || "").replace(/_/g, " "))}</span>` +
          (l.device.summary ? ` · ${esc(l.device.summary)}` : "") + "</div>";
      }
      if (l.cable) s += `<div><span class="tip-k">${esc(t("tip.cable"))}</span> ${esc(l.cable)}</div>`;
      if (l.normally_open) s += `<div class="tip-muted">${esc(t("tip.no"))}</div>`;
      return s;
    }
    const n = o.nodes()[target.id];
    if (!n) return `<b>${esc(target.id)}</b>`;
    let s = `<b>${esc(n.ref || target.id)}</b> <span class="tip-muted">${esc(String(n.type || "").replace(/_/g, " "))}</span>`;
    if (n.label) s += `<div>${esc(n.label)}</div>`;
    if (n.summary) s += `<div>${esc(n.summary)}</div>`;
    if (n.cable) s += `<div><span class="tip-k">${esc(t("tip.cable"))}</span> ${esc(n.cable)}</div>`;
    if (ix && ix.contract && (n.parent || (n.children && n.children.length))) {
      s += `<div class="tip-legend"><i class="sw up"></i>${esc(t("tip.upstream"))} <i class="sw down"></i>${esc(t("tip.downstream"))}</div>`;
    }
    return s;
  }

  function showTip(target, clientX, clientY) {
    const tip = o.tip;
    const html = tipHtml(target);
    if (tip.dataset.key !== target.key || tip.hidden) {
      tip.innerHTML = html;
      tip.dataset.key = target.key;
      tip.hidden = false;
    }
    if (clientX == null) return;
    const vp = o.viewport.getBoundingClientRect();
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    let x = clientX - vp.left + 14;
    let y = clientY - vp.top + 16;
    if (x + w > vp.width - 6) x = Math.max(6, clientX - vp.left - w - 14);
    if (y + h > vp.height - 6) y = Math.max(6, clientY - vp.top - h - 12);
    tip.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  }

  function hideTip() {
    o.tip.hidden = true;
    o.tip.dataset.key = "";
  }

  /** Briefly flash the elements of a node (after a cross-sheet jump). */
  function flash(id) {
    const els = elements(id);
    if (!els.length) return;
    clearTimeout(flashTimer);
    els.forEach((el) => { el.classList.remove("uw-flash"); void el.getBoundingClientRect(); el.classList.add("uw-flash"); });
    flashTimer = setTimeout(() => els.forEach((el) => el.classList.remove("uw-flash")), 1800);
  }

  return { attach, index, elements, resolve, setSticky, getSticky, refresh, setHover, showTip, hideTip, flash, HL };
}
