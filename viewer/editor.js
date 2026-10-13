// uniwire viewer: JSON editor (CodeMirror 6 when the CDN is reachable, plain textarea otherwise)
// and a small JSON scanner mapping JSON paths ("sources/0/children/2/in_A") to text offsets.

/* ------------------------------------------------------------------ JSON path -> offsets */

/** Parse `text` into a light tree of value spans. Returns null on invalid JSON. */
export function scanJson(text) {
  let i = 0;
  const n = text.length;
  const ws = () => { while (i < n && " \t\r\n".includes(text[i])) i++; };
  const fail = () => { throw new SyntaxError("json"); };
  function str() {
    const s = i;
    i++; // opening quote
    while (i < n && text[i] !== '"') i += text[i] === "\\" ? 2 : 1;
    if (i >= n) fail();
    i++;
    return JSON.parse(text.slice(s, i));
  }
  function value() {
    ws();
    const start = i;
    const c = text[i];
    if (c === "{") {
      i++;
      const members = new Map();
      ws();
      if (text[i] === "}") { i++; return { start, end: i, members }; }
      for (;;) {
        ws();
        if (text[i] !== '"') fail();
        const keyStart = i;
        const key = str();
        ws();
        if (text[i] !== ":") fail();
        i++;
        const v = value();
        v.keyStart = keyStart;
        members.set(key, v);
        ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "}") { i++; break; }
        fail();
      }
      return { start, end: i, members };
    }
    if (c === "[") {
      i++;
      const items = [];
      ws();
      if (text[i] === "]") { i++; return { start, end: i, items }; }
      for (;;) {
        items.push(value());
        ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "]") { i++; break; }
        fail();
      }
      return { start, end: i, items };
    }
    if (c === '"') { str(); return { start, end: i }; }
    const m = /^(-?\d+(\.\d+)?([eE][+-]?\d+)?|true|false|null)/.exec(text.slice(i, i + 64));
    if (!m) fail();
    i += m[0].length;
    return { start, end: i };
  }
  try {
    const root = value();
    ws();
    return i === n ? root : null;
  } catch (_) {
    return null;
  }
}

/**
 * Locate a JSON path in a scanned tree. Segments that do not match (e.g. the node type that
 * pydantic inserts for tagged unions) are skipped. Returns {from, to, exact} or null.
 */
export function locatePath(tree, path) {
  if (!tree) return null;
  let node = tree;
  let exact = true;
  for (const seg of String(path || "").split("/").filter(Boolean)) {
    if (node.members && node.members.has(seg)) node = node.members.get(seg);
    else if (node.items && /^\d+$/.test(seg) && +seg < node.items.length) node = node.items[+seg];
    else exact = false;
  }
  return { from: node.keyStart != null ? node.keyStart : node.start, to: node.end, exact };
}

/** Clamp a range to its first line (long objects would otherwise be fully underlined). */
export function firstLine(text, from, to) {
  const nl = text.indexOf("\n", from);
  return { from, to: nl >= 0 && nl < to ? nl : to };
}

/* ------------------------------------------------------------------ editors */

/**
 * Create the editor in `parent`. Options: {onChange(text), onCursor(offset), label}.
 * Returns {kind, getText, setText, setDiagnostics([{from,to,severity,message}]), reveal(from,to), focus}.
 */
export async function createEditor(parent, opts) {
  try {
    return await createCodeMirror(parent, opts);
  } catch (err) {
    console.warn("CodeMirror unavailable, using a plain editor:", err);
    parent.textContent = "";
    return createTextarea(parent, opts);
  }
}

async function createCodeMirror(parent, { onChange, onCursor, label }) {
  const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 15000));
  const [state, view, commands, language, search, autocomplete, lint, langJson, highlight] = await Promise.race([
    Promise.all([
      import("@codemirror/state"), import("@codemirror/view"), import("@codemirror/commands"),
      import("@codemirror/language"), import("@codemirror/search"), import("@codemirror/autocomplete"),
      import("@codemirror/lint"), import("@codemirror/lang-json"), import("@lezer/highlight"),
    ]),
    timeout,
  ]);
  const { EditorState } = state;
  const { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection } = view;
  const { tags } = highlight;

  const theme = EditorView.theme({
    "&": { height: "100%", fontSize: "13px", backgroundColor: "var(--editor-bg)", color: "var(--fg)" },
    ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.5" },
    ".cm-content": { caretColor: "var(--accent)" },
    ".cm-cursor": { borderLeftColor: "var(--accent)" },
    ".cm-gutters": { backgroundColor: "var(--editor-gutter)", color: "var(--muted)", border: "none",
                      borderRight: "1px solid var(--border)" },
    ".cm-activeLine": { backgroundColor: "var(--editor-active)" },
    ".cm-activeLineGutter": { backgroundColor: "var(--editor-active)" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection":
      { backgroundColor: "var(--editor-selection) !important" },
    ".cm-tooltip": { backgroundColor: "var(--surface)", color: "var(--fg)", border: "1px solid var(--border)" },
    ".cm-panels": { backgroundColor: "var(--surface)", color: "var(--fg)" },
    ".cm-uw-flash": { backgroundColor: "var(--flash)" },
  });
  const hl = language.HighlightStyle.define([
    { tag: tags.propertyName, color: "var(--syn-key)" },
    { tag: tags.string, color: "var(--syn-string)" },
    { tag: tags.number, color: "var(--syn-number)" },
    { tag: [tags.bool, tags.null], color: "var(--syn-keyword)" },
    { tag: [tags.brace, tags.squareBracket, tags.separator, tags.punctuation], color: "var(--muted)" },
  ]);

  // Transient highlight of a revealed range
  const flashEffect = state.StateEffect.define();
  const flashField = state.StateField.define({
    create: () => view.Decoration.none,
    update(deco, tr) {
      deco = deco.map(tr.changes);
      for (const e of tr.effects) {
        if (e.is(flashEffect)) {
          deco = e.value ? view.Decoration.set([view.Decoration.mark({ class: "cm-uw-flash" }).range(e.value.from, e.value.to)])
            : view.Decoration.none;
        }
      }
      return deco;
    },
    provide: (f) => EditorView.decorations.from(f),
  });

  let silent = false;
  const ev = new EditorView({
    parent,
    state: EditorState.create({
      doc: "",
      extensions: [
        lineNumbers(), highlightActiveLineGutter(), language.foldGutter(), drawSelection(),
        commands.history(), language.indentOnInput(), language.bracketMatching(), autocomplete.closeBrackets(),
        highlightActiveLine(), search.highlightSelectionMatches(), lint.lintGutter(),
        language.syntaxHighlighting(hl), langJson.json(), theme, flashField,
        EditorState.tabSize.of(2),
        EditorView.contentAttributes.of({ "aria-label": label || "JSON" }),
        keymap.of([
          ...autocomplete.closeBracketsKeymap, ...commands.defaultKeymap, ...search.searchKeymap,
          ...commands.historyKeymap, ...language.foldKeymap, commands.indentWithTab,
        ]),
        EditorView.updateListener.of((u) => {
          if (u.docChanged && !silent) onChange(u.state.doc.toString());
          if (u.selectionSet && !u.docChanged && onCursor && u.transactions.some((tr) => tr.isUserEvent("select"))) {
            onCursor(u.state.selection.main.head);
          }
        }),
      ],
    }),
  });

  let flashTimer = null;
  return {
    kind: "codemirror",
    getText: () => ev.state.doc.toString(),
    setText(text) {
      silent = true;
      ev.dispatch({ changes: { from: 0, to: ev.state.doc.length, insert: text }, selection: { anchor: 0 },
                    effects: EditorView.scrollIntoView(0) });
      silent = false;
    },
    setDiagnostics(diags) {
      const len = ev.state.doc.length;
      const clean = diags.map((d) => ({ ...d, from: Math.min(d.from, len), to: Math.min(Math.max(d.to, d.from), len) }));
      ev.dispatch(lint.setDiagnostics(ev.state, clean));
    },
    reveal(from, to) {
      const len = ev.state.doc.length;
      from = Math.min(from, len); to = Math.min(to, len);
      ev.dispatch({ selection: { anchor: from }, effects: [EditorView.scrollIntoView(from, { y: "center" }),
        flashEffect.of(to > from ? { from, to } : null)] });
      clearTimeout(flashTimer);
      flashTimer = setTimeout(() => ev.dispatch({ effects: flashEffect.of(null) }), 1800);
    },
    focus: () => ev.focus(),
  };
}

function createTextarea(parent, { onChange, onCursor, label }) {
  parent.classList.add("plain-editor");
  const gutter = document.createElement("div");
  gutter.className = "plain-gutter";
  gutter.setAttribute("aria-hidden", "true");
  const ta = document.createElement("textarea");
  ta.spellcheck = false;
  ta.setAttribute("autocapitalize", "off");
  ta.setAttribute("autocomplete", "off");
  ta.setAttribute("aria-label", label || "JSON");
  ta.wrap = "off";
  parent.append(gutter, ta);
  let marks = new Map();

  function renderGutter() {
    const lines = ta.value.split("\n").length;
    const out = [];
    for (let k = 1; k <= lines; k++) {
      const m = marks.get(k);
      out.push(m ? `<div class="bad" title="${m.replace(/"/g, "&quot;")}">${k}</div>` : `<div>${k}</div>`);
    }
    gutter.innerHTML = out.join("");
    gutter.scrollTop = ta.scrollTop;
  }
  ta.addEventListener("input", () => { renderGutter(); onChange(ta.value); });
  ta.addEventListener("scroll", () => { gutter.scrollTop = ta.scrollTop; });
  ta.addEventListener("click", () => onCursor && onCursor(ta.selectionStart));
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault();
      ta.setRangeText("  ", ta.selectionStart, ta.selectionEnd, "end");
      ta.dispatchEvent(new Event("input"));
    }
  });
  const lineOf = (off) => ta.value.slice(0, off).split("\n").length;
  return {
    kind: "textarea",
    getText: () => ta.value,
    setText(text) { ta.value = text; ta.scrollTop = 0; renderGutter(); },
    setDiagnostics(diags) {
      marks = new Map();
      for (const d of diags) marks.set(lineOf(d.from), d.message);
      renderGutter();
    },
    reveal(from, to) {
      ta.focus();
      ta.setSelectionRange(from, to);
      const lh = parseFloat(getComputedStyle(ta).lineHeight) || 19;
      ta.scrollTop = Math.max(0, (lineOf(from) - 5) * lh);
      gutter.scrollTop = ta.scrollTop;
    },
    focus: () => ta.focus(),
  };
}
