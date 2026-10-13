#!/usr/bin/env python3
"""Build the uniwire web viewer (static site, no server).

Steps:

1. build the ``uniwire`` wheel into ``viewer/dist/`` (``uv build`` when available, else ``pip wheel``);
2. copy ``examples/*.uniwire.json`` into ``viewer/examples/`` and write ``viewer/examples/index.json``;
3. write ``viewer/version.json`` (library version + wheel file name, read by the worker);
4. copy the favicons from ``docs/brand/assets/`` (the single source of the brand files) into ``viewer/``.

With ``--out DIR`` the complete static site (page, scripts, wheel, examples) is also copied to DIR,
e.g. ``python viewer/build.py --out site/viewer`` when assembling a site that serves it under /viewer/.

Local development::

    python viewer/build.py
    python -m http.server -d viewer 8000     # then open http://localhost:8000/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIEWER = Path(__file__).resolve().parent
ROOT = VIEWER.parent
DIST = VIEWER / "dist"
EXAMPLES = VIEWER / "examples"
BRAND = ROOT / "docs" / "brand" / "assets"
FAVICONS = ["favicon.svg", "favicon-16.svg"]

#: Static files of the viewer (relative to viewer/), copied as-is by ``--out``.
STATIC = ["index.html", "app.js", "editor.js", "interact.js", "i18n.js", "worker.js", "viewer.py", "style.css", "theme.js"]


def build_wheel() -> Path:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    uv = shutil.which("uv")
    if uv:
        cmd = [uv, "build", "--wheel", "--out-dir", str(DIST), str(ROOT)]
    else:
        cmd = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(DIST), str(ROOT)]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)
    wheels = sorted(DIST.glob("uniwire-*.whl"))
    if not wheels:
        sys.exit("no uniwire wheel was produced")
    for extra in DIST.iterdir():  # keep only the wheel (uv may add a .gitignore)
        if extra != wheels[-1]:
            extra.unlink() if extra.is_file() else shutil.rmtree(extra)
    return wheels[-1]


def copy_examples() -> list[dict]:
    if EXAMPLES.exists():
        shutil.rmtree(EXAMPLES)
    EXAMPLES.mkdir(parents=True)
    index = []
    for src in sorted((ROOT / "examples").glob("*.uniwire.json")):
        shutil.copy2(src, EXAMPLES / src.name)
        name = src.name[: -len(".uniwire.json")]
        try:
            meta = json.loads(src.read_text("utf-8")).get("meta", {})
        except json.JSONDecodeError:
            meta = {}
        index.append({
            "name": name,
            "file": src.name,
            "title": meta.get("title") or name,
            "lang": meta.get("lang") or "en",
        })
    (EXAMPLES / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), "utf-8")
    return index


def library_version() -> str:
    text = (ROOT / "src" / "uniwire" / "__init__.py").read_text("utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else "0"


#: Assets referenced from index.html and app.js. The published copies refer to them as ``name?v=<hash>``, so a
#: browser or CDN that caches scripts and styles for hours still gets a new release at once (index.html itself
#: is served with ``Cache-Control: no-cache``).
VERSIONED = ("style.css", "theme.js", "app.js", "i18n.js", "editor.js", "interact.js", "worker.js")


def stamp_assets(out: Path) -> str:
    """Rewrite the asset references of the published copy (``out``) with a content hash; return the hash."""
    digest = hashlib.sha256()
    for name in VERSIONED:
        digest.update((out / name).read_bytes())
    v = digest.hexdigest()[:12]
    refs = "|".join(re.escape(n) for n in VERSIONED)
    html = out / "index.html"
    html.write_text(re.sub(rf'((?:src|href)=")({refs})"', rf'\1\2?v={v}"', html.read_text("utf-8")), "utf-8")
    app = out / "app.js"
    text = re.sub(rf'(from ")(\./(?:{refs}))"', rf'\1\2?v={v}"', app.read_text("utf-8"))
    text = text.replace('new Worker("worker.js")', f'new Worker("worker.js?v={v}")')
    app.write_text(text, "utf-8")
    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="also copy the complete static site to this directory")
    ap.add_argument("--skip-wheel", action="store_true", help="reuse the wheel already in viewer/dist/")
    a = ap.parse_args(argv)

    if a.skip_wheel and list(DIST.glob("uniwire-*.whl")):
        wheel = sorted(DIST.glob("uniwire-*.whl"))[-1]
    else:
        wheel = build_wheel()
    examples = copy_examples()
    for name in FAVICONS:
        shutil.copy2(BRAND / name, VIEWER / name)
    version = {"uniwire": library_version(), "wheel": f"dist/{wheel.name}"}
    (VIEWER / "version.json").write_text(json.dumps(version, indent=1) + "\n", "utf-8")
    print(f"wheel: {wheel.name}; {len(examples)} examples")

    if a.out:
        out = Path(a.out).resolve()
        out.mkdir(parents=True, exist_ok=True)
        for name in STATIC + FAVICONS + ["version.json"]:
            shutil.copy2(VIEWER / name, out / name)
        stamp_assets(out)
        for sub in ("dist", "examples"):
            if (out / sub).exists():
                shutil.rmtree(out / sub)
            shutil.copytree(VIEWER / sub, out / sub)
        print(f"site copied to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
