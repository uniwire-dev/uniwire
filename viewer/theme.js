// uniwire viewer: light / dark toggle. The choice is shared with the landing page and the docs
// (localStorage "uniwire-theme", same origin). Light by default, like a drawing on paper, whatever the OS setting.
(function () {
  var KEY = "uniwire-theme", root = document.documentElement;
  var LABELS = { en: ["Switch to light mode", "Switch to dark mode"], fr: ["Passer en mode clair", "Passer en mode sombre"] };
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  function current() { return root.getAttribute("data-theme") || "light"; }
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
  new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ["lang"] });
  sync();
})();
