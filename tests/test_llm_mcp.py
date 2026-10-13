"""MCP server: registration, in-process calls and a stdio smoke test (skipped without the ``mcp`` SDK)."""

import json
import sys
from pathlib import Path

import pytest

from .conftest import ROOT

mcp = pytest.importorskip("mcp")

from uniwire.mcp_server import build_server  # noqa: E402

STUDIO = str(ROOT / "examples" / "01_studio_apartment.uniwire.json")
TOOLS = {"get_reference_card", "list_types", "type_info", "validate", "check", "describe", "apply_patch", "render",
         "bom", "list_examples", "get_example", "normalize", "viewer_link"}

Client = getattr(mcp, "Client", None)
needs_client = pytest.mark.skipif(Client is None, reason="mcp.Client (SDK >= 2) not available")


def _run(coro_fn):
    import anyio

    return anyio.run(coro_fn)


def _payload(result):
    """Structured result of a tool call (dict / list) or its text."""
    sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if sc is not None:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    text = result.content[0].text
    try:
        return json.loads(text)
    except ValueError:
        return text


def test_server_builds():
    assert build_server() is not None


@needs_client
def test_in_process_tools_resources_prompt():
    async def go():
        async with Client(build_server()) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert TOOLS <= names
            res = _payload(await c.call_tool("validate", {"document": STUDIO}))
            assert res["valid"] is True
            res = _payload(await c.call_tool("check", {"document": json.loads(open(STUDIO).read())}))
            assert res["summary"]["error"] == 0
            assert res["viewer_url"].startswith("https://uniwire.sh/viewer/#doc=")
            text = _payload(await c.call_tool("describe", {"document": STUDIO}))
            assert "Q11 [-Q11]" in text
            res = _payload(await c.call_tool("apply_patch", {
                "document": STUDIO, "ops": [{"op": "set", "id": "Q11", "path": "in_A", "value": 16}]}))
            assert res["ok"] is True
            res = _payload(await c.call_tool("render", {"document": STUDIO, "sheet": 1}))
            assert "<svg" in res["svg"]
            bad = await c.call_tool("type_info", {"type": "nope"})
            assert bad.is_error and "unknown node type" in bad.content[0].text
            uris = {str(r.uri) for r in (await c.list_resources()).resources}
            assert {"uniwire://schema", "uniwire://card"} <= uris
            card = await c.read_resource("uniwire://card")
            assert "reference card" in card.contents[0].text
            prompts = {p.name for p in (await c.list_prompts()).prompts}
            assert "design_single_line" in prompts
            p = await c.get_prompt("design_single_line", {"brief": "a small shop"})
            assert "a small shop" in p.messages[0].content.text
    _run(go)


@needs_client
def test_tool_metadata_and_usage_log(caplog):
    async def go():
        async with Client(build_server()) as c:
            tools = (await c.list_tools()).tools
            for t in tools:  # app directories require explicit annotations; every tool only computes
                assert t.title and t.annotations.read_only_hint is True and t.annotations.destructive_hint is False
                assert t.annotations.open_world_hint is False
            with caplog.at_level("INFO", logger="uniwire.mcp"):
                await c.call_tool("validate", {"document": STUDIO})
    _run(go)
    line = next(r.getMessage() for r in caplog.records if r.name == "uniwire.mcp")
    assert line.startswith("tool=validate status=ok ms=")


@needs_client
def test_stdio_smoke():
    from mcp import StdioServerParameters

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "uniwire.mcp_server"])
        async with Client(params) as c:
            res = _payload(await c.call_tool("get_example", {"name": "02"}))
            assert res["installation"]["earthing"] == "TT"
            card = _payload(await c.call_tool("get_reference_card", {"level": "compact", "lang": "fr"}))
            assert "Fiche de référence" in card
    _run(go)


def test_tools_render_colors_and_wiring():
    from uniwire.llm import tools as T

    doc = T.get_example("24")
    out = T.render(doc, "multi-line", color="conductors", conductor_colors="iec")
    assert "uw-legend" in out["svg"][0]
    with pytest.raises(T.ToolError):
        T.render(doc, color="rainbow")
    markers = T.wiring(doc, "markers")
    assert markers["view"] == "marks" and markers["rows"] and "mark" in markers["columns"]
    assert {r["mark"] for r in markers["rows"]} >= {"1L1", "101"}
    cables = T.wiring(doc, "cables")
    assert any(r["ref"] == "W11" for r in cables["rows"])
    with pytest.raises(T.ToolError):
        T.wiring(doc, "nope")


def test_public_mode_blocks_file_system(monkeypatch):
    from uniwire.llm import tools as T

    monkeypatch.setattr(T, "PUBLIC", True)
    doc = T.get_example("06")
    with pytest.raises(T.ToolError, match="file paths are disabled"):
        T.validate("/etc/passwd")
    target = Path("/tmp/should-not-exist.pdf")
    target.unlink(missing_ok=True)
    for path in (str(target), None):  # no file written, no base64: the PDF comes from the editor link
        r = T.render(doc, format="pdf", path=path)
        assert set(r) == {"viewer_url", "pdf_url", "note"} and r["pdf_url"].endswith("&download=pdf")
    assert not target.exists()
    assert T.render(doc)["sheets"] >= 1
