// uniwire: when the reader switches Material's palette, remember it for the landing page and the viewer too.
document.addEventListener("change", function (e) {
  var input = e.target;
  if (!input || input.name !== "__palette") return;
  var scheme = input.getAttribute("data-md-color-scheme");
  try { localStorage.setItem("uniwire-theme", scheme === "slate" ? "dark" : "light"); } catch (err) { /* ignore */ }
});
