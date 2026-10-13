"""Command-line interface: ``uniwire validate|check|render|schema|graph|bom|wires|markers|cables|marks|symbols|normalize|card|describe|patch``.

Messages follow the ``UNIWIRE_LANG`` environment variable (``en`` by default, ``fr`` available).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .i18n import t as _t
from .resolve import UniwireError, dump, load


def _load(path: str):
    try:
        return load(path)
    except UniwireError as e:
        print(_t("cli.invalid_document", path=path), file=sys.stderr)
        for issue in e.issues:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(2)


def _marking_view(doc, view_id):
    """View whose ``wire_marking`` rules apply: ``view_id``, else the first view that declares rules (none: manual
    marks only)."""
    if view_id:
        from .render import default_view

        try:
            return default_view(doc, view_id)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            sys.exit(2)
    return next((v for v in doc.views if v.wire_marking is not None), None)


def _write(text: str, out) -> None:
    if out:
        Path(out).write_text(text, "utf-8")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    from . import FORMAT_VERSION, __version__

    ap = argparse.ArgumentParser(prog="uniwire", description=_t("cli.description"))
    ap.add_argument("--version", action="version", version=f"uniwire {__version__} (format {FORMAT_VERSION})",
                    help=_t("cli.help.version"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help=_t("cli.help.validate"))
    p.add_argument("files", nargs="+")

    p = sub.add_parser("check", help=_t("cli.help.check"))
    p.add_argument("files", nargs="+")
    p.add_argument("--profile", action="append", help=_t("cli.help.profile"))

    p = sub.add_parser("render", help=_t("cli.help.render"))
    p.add_argument("file")
    p.add_argument("-f", "--format", choices=["svg", "pdf"], default="svg", help=_t("cli.help.format"))
    p.add_argument("-o", "--out", help=_t("cli.help.out_render"))
    p.add_argument("--view", help=_t("cli.help.view"))
    p.add_argument("--kind", choices=["single-line", "multi-line"], help=_t("cli.help.kind"))

    p = sub.add_parser("schema", help=_t("cli.help.schema"))
    p.add_argument("-o", "--out")

    p = sub.add_parser("graph", help=_t("cli.help.graph"))
    p.add_argument("file")

    p = sub.add_parser("bom", help=_t("cli.help.bom"))
    p.add_argument("file")
    p.add_argument("-o", "--out")

    p = sub.add_parser("wires", help=_t("cli.help.wires"))
    p.add_argument("file")
    p.add_argument("--view", help=_t("cli.help.view_marking"))
    p.add_argument("--all", action="store_true", help=_t("cli.help.wires_all"))
    p.add_argument("-o", "--out")

    p = sub.add_parser("markers", help=_t("cli.help.markers"))
    p.add_argument("file")
    p.add_argument("--view", help=_t("cli.help.view_marking"))
    p.add_argument("-o", "--out")

    p = sub.add_parser("cables", help=_t("cli.help.cables"))
    p.add_argument("file")
    p.add_argument("-o", "--out")

    p = sub.add_parser("marks", help=_t("cli.help.marks"))
    p.add_argument("file")
    p.add_argument("--view", help=_t("cli.help.view_marking"))
    p.add_argument("--write", action="store_true", help=_t("cli.help.marks_write"))
    p.add_argument("-o", "--out", help=_t("cli.help.out_marks"))

    p = sub.add_parser("symbols", help=_t("cli.help.symbols"))
    p.add_argument("-o", "--out", default="symbols.svg")

    p = sub.add_parser("normalize", help=_t("cli.help.normalize"))
    p.add_argument("file")

    p = sub.add_parser("card", help=_t("cli.help.card"))
    p.add_argument("--full", action="store_true", help=_t("cli.help.card_full"))
    p.add_argument("--lang", default=None, help=_t("cli.help.lang"))

    p = sub.add_parser("describe", help=_t("cli.help.describe"))
    p.add_argument("file")
    p.add_argument("--lang", default=None, help=_t("cli.help.lang"))

    p = sub.add_parser("link", help=_t("cli.help.link"))
    p.add_argument("file")
    p.add_argument("--pdf", action="store_true", help=_t("cli.help.link_pdf"))

    p = sub.add_parser("patch", help=_t("cli.help.patch"))
    p.add_argument("file")
    p.add_argument("ops", help=_t("cli.help.ops"))
    p.add_argument("-o", "--out", help=_t("cli.help.out_patch"))

    a = ap.parse_args(argv)

    if a.cmd == "validate":
        for f in a.files:
            _load(f)
            print(f"{f}: OK")
        return 0
    if a.cmd == "check":
        from .rules import check

        worst = 0
        for f in a.files:
            doc = _load(f)
            findings = check(doc, a.profile)
            print(_t("cli.findings", path=f, count=len(findings)))
            for x in findings:
                print(f"  {x}")
                worst = max(worst, 1 if x.level == "error" else 0)
        return worst
    if a.cmd == "render":
        from .render import default_view, render_pdf, render_svg

        doc = _load(a.file)
        view = default_view(doc, a.view, a.kind)
        stem = Path(a.file).name.split(".")[0]
        if view.kind == "multi-line":
            stem += "-multiline"
        if a.format == "svg":
            out = Path(a.out or f"out/{stem}")
            for pth in render_svg(doc, out, stem, view):
                print(pth)
        else:
            print(render_pdf(doc, a.out or f"out/{stem}.pdf", view))
        return 0
    if a.cmd == "schema":
        from .schema import schema_text

        text = schema_text()
        if a.out:
            Path(a.out).write_text(text, "utf-8")
        else:
            sys.stdout.write(text)
        return 0
    if a.cmd == "graph":
        from .graph import to_graph

        print(json.dumps(to_graph(_load(a.file)), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "bom":
        from .bom import bom_csv

        text = bom_csv(_load(a.file))
        if a.out:
            Path(a.out).write_text(text, "utf-8")
        else:
            sys.stdout.write(text)
        return 0
    if a.cmd in ("wires", "markers"):
        from .exports import markers_csv, wires_csv

        doc = _load(a.file)
        view = _marking_view(doc, a.view)
        _write((wires_csv if a.cmd == "wires" else markers_csv)(doc, view), a.out)
        return 0
    if a.cmd == "cables":
        from .exports import cables_csv

        _write(cables_csv(_load(a.file)), a.out)
        return 0
    if a.cmd == "marks":
        from .marks import freeze, marked_wires

        doc = _load(a.file)
        view = _marking_view(doc, a.view)
        wires = marked_wires(doc, view)
        if not a.write:
            for w in wires:
                print(f"{w.id}\t{w.mark}" + ("" if not w.manual or w.manual != w.mark else "\t" + _t("cli.marks_manual")))
            return 0
        data = json.loads(Path(a.file).read_text("utf-8"))
        count, skipped = freeze(data, doc, wires)
        out = a.out or a.file
        Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(_t("cli.marks_written", count=count, path=out))
        for cid in skipped:
            print("  - " + _t("cli.marks_skipped", cable=cid), file=sys.stderr)
        return 0
    if a.cmd == "symbols":
        from .render.svg import page_to_svg
        from .symbols.sheet import symbol_sheet

        Path(a.out).write_text(page_to_svg(symbol_sheet()), "utf-8")
        print(a.out)
        return 0
    if a.cmd == "normalize":
        print(dump(_load(a.file)))
        return 0
    if a.cmd == "card":
        from .i18n import current_lang
        from .llm import card

        sys.stdout.write(card(a.lang or current_lang(), "full" if a.full else "compact"))
        return 0
    if a.cmd == "describe":
        from .i18n import current_lang
        from .llm import describe

        sys.stdout.write(describe(_load(a.file), a.lang or current_lang()))
        return 0
    if a.cmd == "link":
        from .llm import viewer_link

        _load(a.file)  # invalid documents are reported (exit 2) rather than linked
        print(viewer_link(Path(a.file).read_text("utf-8"), pdf=a.pdf))
        return 0
    if a.cmd == "patch":
        from .llm import PatchError, patch

        try:
            data = json.loads(Path(a.file).read_text("utf-8"))
            ops = json.loads(sys.stdin.read() if a.ops == "-" else Path(a.ops).read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(_t("cli.patch_failed", path=a.file), file=sys.stderr)
            print(f"  - {e}", file=sys.stderr)
            return 2
        try:
            out = patch(data, ops)
        except PatchError as e:
            print(_t("cli.patch_failed", path=a.file), file=sys.stderr)
            for err in e.errors:
                where = _t("cli.patch_op", index=err["op"]) if err.get("op") is not None else _t("cli.patch_result")
                print(f"  - {where}: {err['error']}", file=sys.stderr)
            return 2
        text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
        if a.out:
            Path(a.out).write_text(text, "utf-8")
            print(a.out)
        else:
            sys.stdout.write(text)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
