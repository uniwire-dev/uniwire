// uniwire viewer: light / dark toggle. The choice is shared with the landing page and the docs
// (localStorage "uniwire-theme", same origin); the OS preference gives the default.
(function () {
  var KEY = "uniwire-theme", root = document.documentElement, osDark = matchMedia("(prefers-color-scheme: dark)");
  var LABELS = { en: ["Switch to light mode", "Switch to dark mode"], fr: ["Passer en mode clair", "Passer en mode sombre"] };
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  function current() { return root.getAttribute("data-theme") || (osDark.matches ? "dark" : "light"); }
  function sync() {
    var dark = current() === "dark", l = LABELS[root.lang === "fr" ? "fr" : "en"];
    btn.setAttribute("aria-pressed", String(dark));  // pressed = dark mode on
    btn.setAttribute("aria-label", dark ? l[0] : l[1]);
    btn.title = dark ? l[0] : l[1];
  }
  btn.addEventListener("click", function () {
    var next = current() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch (e) { /* storage unavailable */ }
    sync();
  });
  osDark.addEventListener("change", sync);
  new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ["lang"] });
  sync();
})();
