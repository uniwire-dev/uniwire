// uniwire viewer: user-interface strings (English default, French available).

export const STRINGS = {
  en: {
    "app.title": "uniwire Viewer",
    "app.tagline": "Electrical diagrams, rendered in your browser",
    "brand.sub": "Viewer",
    "toolbar.examples": "Examples",
    "toolbar.examples.choose": "Load an example…",
    "toolbar.open": "Open",
    "toolbar.open.title": "Open a .uniwire.json file (you can also drop it on the editor)",
    "toolbar.share": "Share",
    "toolbar.share.title": "Copy a link containing the document",
    "toolbar.download": "Download",
    "toolbar.lang.title": "Interface language",
    "toolbar.docs": "Docs",
    "dl.svg": "Current sheet (SVG)",
    "dl.print": "Print all sheets…",
    "dl.pdf": "PDF, all sheets",
    "dl.about": "with the page “About this document”",
    "dl.json": "Normalized JSON",
    "dl.bom": "Bill of materials (CSV)",
    "dl.source": "Source JSON",
    "pane.editor": "Editor",
    "pane.drawing": "Drawing",
    "pane.issues": "Issues",
    "view.label": "View",
    "view.kind": "Diagram",
    "kind.single-line": "Single-line",
    "kind.multi-line": "Multi-line",
    "zoom.in": "Zoom in",
    "zoom.out": "Zoom out",
    "zoom.fit": "Fit",
    "sheet": "Sheet {n}",
    "sheets.none": "Nothing to display yet.",
    "issues.errors": "Errors",
    "issues.findings": "Rule findings",
    "issues.none.errors": "The document is valid.",
    "issues.none.findings": "No rule finding.",
    "issues.stale": "The drawing shows the last valid version.",
    "status.loading": "Loading…",
    "status.rendering": "Rendering…",
    "status.ok": "Valid · {sheets} sheet(s) · {findings} finding(s)",
    "status.invalid": "{count} error(s)",
    "status.json": "Invalid JSON",
    "load.runtime": "Downloading the Python runtime…",
    "load.packages": "Loading pydantic…",
    "load.library": "Installing the uniwire library…",
    "load.glue": "Starting…",
    "load.ready": "Ready",
    "load.fatal": "The viewer could not start.",
    "load.retry": "Reload",
    "load.note": "Runs entirely in your browser: nothing is uploaded.",
    "level.error": "error",
    "level.warning": "warning",
    "level.info": "info",
    "finding.node": "node",
    "msg.copied": "Link copied to the clipboard.",
    "msg.copy_failed": "Copy this link:",
    "msg.too_long": "The document is large: the link may not work in every browser.",
    "msg.file_error": "Cannot read the file.",
    "msg.example_error": "Cannot load the example {name}.",
    "msg.example_missing": "There is no example {name}: here is {first}. The list of examples is at the top left.",
    "msg.pdf_wait": "Preparing the PDF (first time: downloading the PDF engine)…",
    "msg.pdf_failed": "PDF generation failed: {error}. Use \"All sheets (print / PDF)\" instead.",
    "msg.need_valid": "Fix the errors first.",
    "msg.hash_error": "The shared link is damaged: its document cannot be read.",
    "msg.short_missing": "This link has expired or does not exist (links are kept 30 days after their last use).",
    "msg.short_deleted": "This document was deleted from uniwire.sh by someone who had its link.",
    "msg.short_error": "The shared document could not be loaded: {error}.",
    "msg.hash_too_large": "The shared document is larger than {mb} MB once decompressed: it was not opened.",
    "msg.draft_kept": "Your previous draft is kept until you edit this document.",
    "msg.draft_restore": "Restore the draft",
    "drop.hint": "Drop a .uniwire.json file",
    "editor.label": "uniwire JSON document",
    "nav.back": "Back",
    "nav.back.title": "Back to the previous sheet (Alt+←)",
    "color.label": "Colours",
    "color.title": "Colour the drawing (re-renders the sheets)",
    "color.opt": "Colours: {v}",
    "color.document": "as in the document",
    "color.none": "none",
    "color.conductors": "conductors",
    "color.phase": "phase",
    "color.source": "source",
    "color.status": "status",
    "color.voltage": "voltage",
    "preset.label": "Conductor colours",
    "preset.title": "Conductor colour convention",
    "preset.opt": "Conductors: {v}",
    "preset.iec": "IEC",
    "preset.us": "US",
    "tip.goto": "Go to sheet {n}",
    "tip.link": "Link: {kind}",
    "tip.device": "Device",
    "tip.cable": "Cable",
    "tip.no": "Normally open",
    "tip.conductor": "Conductor {c}",
    "tip.upstream": "upstream",
    "tip.downstream": "downstream",
    "msg.no_sheet": "Sheet {n} is not in this view.",
    "footer.powered": "uniwire {version} · Pyodide {pyodide}",
  },
  fr: {
    "app.title": "Éditeur web uniwire",
    "app.tagline": "Schémas électriques, dessinés dans votre navigateur",
    "brand.sub": "Éditeur web",
    "toolbar.examples": "Exemples",
    "toolbar.examples.choose": "Charger un exemple…",
    "toolbar.open": "Ouvrir",
    "toolbar.open.title": "Ouvrir un fichier .uniwire.json (ou le déposer sur l’éditeur)",
    "toolbar.share": "Partager",
    "toolbar.share.title": "Copier un lien contenant le document",
    "toolbar.download": "Télécharger",
    "toolbar.lang.title": "Langue de l’interface",
    "toolbar.docs": "Documentation",
    "dl.svg": "Folio courant (SVG)",
    "dl.print": "Imprimer tous les folios…",
    "dl.pdf": "PDF, tous les folios",
    "dl.about": "avec la page « À propos de ce document »",
    "dl.json": "JSON normalisé",
    "dl.bom": "Nomenclature (CSV)",
    "dl.source": "JSON source",
    "pane.editor": "Éditeur",
    "pane.drawing": "Schéma",
    "pane.issues": "Problèmes",
    "view.label": "Vue",
    "view.kind": "Schéma",
    "kind.single-line": "Unifilaire",
    "kind.multi-line": "Multifilaire",
    "zoom.in": "Zoom avant",
    "zoom.out": "Zoom arrière",
    "zoom.fit": "Ajuster",
    "sheet": "Folio {n}",
    "sheets.none": "Rien à afficher pour l’instant.",
    "issues.errors": "Erreurs",
    "issues.findings": "Remarques",
    "issues.none.errors": "Le document est valide.",
    "issues.none.findings": "Aucune remarque.",
    "issues.stale": "Le schéma affiche la dernière version valide.",
    "status.loading": "Chargement…",
    "status.rendering": "Dessin en cours…",
    "status.ok": "Valide · {sheets} folio(s) · {findings} remarque(s)",
    "status.invalid": "{count} erreur(s)",
    "status.json": "JSON invalide",
    "load.runtime": "Téléchargement de l’environnement Python…",
    "load.packages": "Chargement de pydantic…",
    "load.library": "Installation de la bibliothèque uniwire…",
    "load.glue": "Démarrage…",
    "load.ready": "Prêt",
    "load.fatal": "L’éditeur web n’a pas pu démarrer.",
    "load.retry": "Recharger",
    "load.note": "Tout s’exécute dans votre navigateur : rien n’est envoyé.",
    "level.error": "erreur",
    "level.warning": "avertissement",
    "level.info": "info",
    "finding.node": "nœud",
    "msg.copied": "Lien copié dans le presse-papiers.",
    "msg.copy_failed": "Copiez ce lien :",
    "msg.too_long": "Le document est volumineux : le lien peut ne pas fonctionner partout.",
    "msg.file_error": "Impossible de lire le fichier.",
    "msg.example_error": "Impossible de charger l’exemple {name}.",
    "msg.example_missing": "Il n’y a pas d’exemple {name} : voici {first}. La liste des exemples est en haut à gauche.",
    "msg.pdf_wait": "Préparation du PDF (la première fois : téléchargement du moteur PDF)…",
    "msg.pdf_failed": "Échec de la génération du PDF : {error}. Utilisez « Tous les folios (impression / PDF) ».",
    "msg.need_valid": "Corrigez d’abord les erreurs.",
    "msg.hash_error": "Le lien partagé est endommagé : son document est illisible.",
    "msg.short_missing": "Ce lien a expiré ou n’existe pas (les liens sont conservés 30 jours après leur dernière utilisation).",
    "msg.short_deleted": "Ce document a été supprimé de uniwire.sh par une personne qui avait son lien.",
    "msg.short_error": "Le document partagé n’a pas pu être chargé : {error}.",
    "msg.hash_too_large": "Le document partagé dépasse {mb} Mo une fois décompressé : il n’a pas été ouvert.",
    "msg.draft_kept": "Votre brouillon précédent est conservé tant que vous ne modifiez pas ce document.",
    "msg.draft_restore": "Restaurer le brouillon",
    "drop.hint": "Déposez un fichier .uniwire.json",
    "editor.label": "Document JSON uniwire",
    "nav.back": "Retour",
    "nav.back.title": "Revenir au folio précédent (Alt+←)",
    "color.label": "Couleurs",
    "color.title": "Colorer le schéma (redessine les folios)",
    "color.opt": "Couleurs : {v}",
    "color.document": "selon le document",
    "color.none": "aucune",
    "color.conductors": "conducteurs",
    "color.phase": "phase",
    "color.source": "source",
    "color.status": "état",
    "color.voltage": "tension",
    "preset.label": "Couleurs des conducteurs",
    "preset.title": "Convention de couleurs des conducteurs",
    "preset.opt": "Conducteurs : {v}",
    "preset.iec": "CEI",
    "preset.us": "US",
    "tip.goto": "Aller au folio {n}",
    "tip.link": "Liaison : {kind}",
    "tip.device": "Appareil",
    "tip.cable": "Câble",
    "tip.no": "Normalement ouvert",
    "tip.conductor": "Conducteur {c}",
    "tip.upstream": "amont",
    "tip.downstream": "aval",
    "msg.no_sheet": "Le folio {n} n’est pas dans cette vue.",
    "footer.powered": "uniwire {version} · Pyodide {pyodide}",
  },
};

const STORAGE_KEY = "uniwire-viewer-lang";

function initialLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "fr") return saved;
  } catch (_) { /* storage unavailable */ }
  const langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"];
  return String(langs[0] || "en").toLowerCase().startsWith("fr") ? "fr" : "en";
}

let current = initialLang();
const listeners = new Set();

export function lang() {
  return current;
}

export function setLang(l) {
  current = l === "fr" ? "fr" : "en";
  try { localStorage.setItem(STORAGE_KEY, current); } catch (_) { /* ignore */ }
  document.documentElement.lang = current;
  applyStatic();
  listeners.forEach((fn) => fn(current));
}

export function onLangChange(fn) {
  listeners.add(fn);
}

export function t(key, vars = {}) {
  const s = (STRINGS[current] && STRINGS[current][key]) || STRINGS.en[key] || key;
  return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`));
}

/** Translate elements carrying data-i18n (text), data-i18n-title and data-i18n-aria. */
export function applyStatic(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
  document.title = `${t("app.title")}: ${t("app.tagline")}`;
}
