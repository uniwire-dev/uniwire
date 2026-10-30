"""Short links of the hosted MCP server: document store and link shortening."""

import json
import os
import time

import pytest

from uniwire.llm import tools
from uniwire.llm.link import document_from_link, viewer_link
from uniwire.llm.store import ID_LENGTH, DocStore, doc_id
from uniwire.mcp_server import _pdf_base, _shorten

from .conftest import ROOT

STUDIO = ROOT / "examples" / "01_studio_apartment.uniwire.json"


def test_store_put_get_expire(tmp_path):
    store = DocStore(tmp_path, ttl_days=1)
    text = STUDIO.read_text("utf-8")
    id_ = store.put(text)
    assert id_ == doc_id(text, store.key) and len(id_) == ID_LENGTH and id_.isalnum()
    assert id_ != doc_id(text) and DocStore(tmp_path).key == store.key  # a secret key, kept with the store
    assert store.put(text) == id_ and len(list(tmp_path.glob("*.json"))) == 1  # same content, same link
    assert store.get(id_) == text
    assert store.get("../../etc/passwd") is None and store.get("x" * ID_LENGTH) is None
    old = time.time() - 2 * 86400
    os.utime(tmp_path / f"{id_}.json", (old, old))
    assert store.get(id_) is None and not (tmp_path / f"{id_}.json").exists()


def test_store_delete(tmp_path):
    store = DocStore(tmp_path, ttl_days=1)
    text = STUDIO.read_text("utf-8")
    id_ = store.put(text)
    assert not store.deleted(id_) and store.delete(id_)
    assert store.get(id_) is None and store.deleted(id_) and not list(tmp_path.glob("*.json"))
    assert not store.delete(id_) and not store.delete("../../etc/passwd")  # nothing (left) to delete
    assert store.put(text) == id_ and store.get(id_) == text and not store.deleted(id_)  # stored again: a new request
    store.delete(id_)
    old = time.time() - 2 * 86400
    os.utime(tmp_path / f"{id_}.deleted", (old, old))
    assert not store.deleted(id_)
    store.prune()
    assert [p.name for p in tmp_path.iterdir()] == [".key"]  # the marker goes with the expiry


def test_store_limits(tmp_path):
    store = DocStore(tmp_path, max_total_bytes=200, max_doc_bytes=100)  # 4 documents of 78 bytes
    assert store.put("x" * 101) is None
    ids = []
    for i in range(4):
        ids.append(store.put(f'{{"n": {i}, "pad": "{"y" * 60}"}}'))
        t = time.time() - (10 - i)
        os.utime(tmp_path / f"{ids[-1]}.json", (t, t))
    store.prune()
    assert [store.get(i) is not None for i in ids] == [False, False, True, True]  # oldest removed first
    for i in range(4, 8):  # the total is checked at each write, not only at the hourly prune
        ids.append(store.put(f'{{"n": {i}, "pad": "{"y" * 60}"}}'))
        assert sum(p.stat().st_size for p in tmp_path.glob("*.json")) <= 200


def test_shorten_tool_results(tmp_path):
    store = DocStore(tmp_path)
    d = json.loads(STUDIO.read_text("utf-8"))
    res = _shorten(tools.check(d), store, "https://uniwire.sh/viewer/")
    id_ = res["viewer_url"].rpartition("#d=")[2]
    assert res["viewer_url"] == f"https://uniwire.sh/viewer/#d={id_}" and res["pdf_url"] == res["viewer_url"] + "&download=pdf"
    assert json.loads(store.get(id_)) == d and len(res["viewer_url"]) < 50
    assert res["summary"]["error"] == 0  # the rest of the result is unchanged
    assert _shorten(["rows"], store, "x") == ["rows"] and _shorten({"svg": "<svg/>"}, store, "x") == {"svg": "<svg/>"}
    assert document_from_link(viewer_link(d)) == json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    junk = tools.validate({"junk": "x" * 100})  # any JSON reaches validate: only diagrams are kept
    assert _shorten(junk, store, "https://uniwire.sh/viewer/") == junk and len(list(tmp_path.glob("*.json"))) == 1


def test_shorten_pdf_links(tmp_path):
    store = DocStore(tmp_path)
    d = json.loads(STUDIO.read_text("utf-8"))
    res = _shorten(tools.check(d), store, "https://uniwire.sh/viewer/", _pdf_base("https://uniwire.sh/viewer/"))
    id_ = res["viewer_url"].rpartition("#d=")[2]
    assert res["pdf_url"] == f"https://uniwire.sh/pdf/{id_}"
    assert _pdf_base("http://localhost:8080/editor.html") is None


def test_view_options_carry_over_to_short_links(tmp_path):
    """render with kind multi-line / color: both links show that view (editor hash, ?query of the PDF)."""
    store = DocStore(tmp_path)
    d = json.loads(STUDIO.read_text("utf-8"))
    long = tools.render(d, kind="multi-line", format="svg", color="phase")
    assert long["viewer_url"].endswith("&kind=multi-line&color=phase")
    res = _shorten(long, store, "https://uniwire.sh/viewer/", _pdf_base("https://uniwire.sh/viewer/"))
    id_ = res["viewer_url"].partition("#d=")[2].partition("&")[0]
    assert res["viewer_url"] == f"https://uniwire.sh/viewer/#d={id_}&kind=multi-line&color=phase"
    assert res["pdf_url"] == f"https://uniwire.sh/pdf/{id_}?kind=multi-line&color=phase"
    assert tools._view_params("multi-line", "rainbow", "us") == "&kind=multi-line&conductor_colors=us"  # unknown: dropped
    assert "&kind=" not in tools.render(d, format="svg")["viewer_url"]  # the document's own view: no option


def test_pdf_filename():
    assert tools.pdf_filename("Small bakery, 400 V") == "small-bakery-400-v.pdf"
    assert tools.pdf_filename("École: TGBT / TD-1") == "ecole-tgbt-td-1.pdf"
    assert tools.pdf_filename(None) == tools.pdf_filename("—") == "uniwire.pdf"


def test_pdf_route(tmp_path, monkeypatch):
    pytest.importorskip("reportlab")
    pytest.importorskip("mcp.server.mcpserver")
    from starlette.testclient import TestClient

    from uniwire.mcp_server import _add_pdf_route, build_server

    calls = []
    pdf_file = tools.pdf_file
    monkeypatch.setattr(tools, "pdf_file", lambda **kw: calls.append(kw) or pdf_file(**kw))
    store = DocStore(tmp_path)
    id_ = store.put(STUDIO.read_text("utf-8"))
    server = build_server(None, store)
    _add_pdf_route(server, store, None)
    client = TestClient(server.streamable_http_app())
    r = client.get(f"/pdf/{id_}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    assert r.headers["content-type"] == "application/pdf" and r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"] == 'inline; filename="studio-28-m2-tableau-de-repartition.pdf"'
    assert client.get(f"/pdf/{id_}").content == r.content and len(calls) == 1  # opened again: drawn once
    assert client.get("/pdf/AAAAAAAAAAAA").status_code == 404
    bad_id = store.put('{"uniwire": "1.0.0"}')
    bad = client.get(f"/pdf/{bad_id}")
    assert bad.status_code == 422 and "cannot draw" in bad.text
    ml = client.get(f"/pdf/{id_}?kind=multi-line&color=phase&x=1")
    assert ml.status_code == 200 and abs(len(ml.content) - len(r.content)) > 1000  # another drawing
    evil = client.get(f"/pdf/{id_}?kind=evil")  # unknown values are ignored: the document's own view
    assert evil.status_code == 200 and abs(len(evil.content) - len(r.content)) < 100


def test_pdf_route_pages_for_a_browser(tmp_path):
    """A person who opens a PDF link that cannot be served reads a short page in their language; scripts and
    assistants keep the plain text."""
    pytest.importorskip("mcp.server.mcpserver")
    from starlette.testclient import TestClient

    from uniwire.mcp_server import _add_doc_route, _add_pdf_route, build_server

    store = DocStore(tmp_path)
    server = build_server(None, store)
    _add_pdf_route(server, store, None, "https://example.org")
    _add_doc_route(server, store)
    client = TestClient(server.streamable_http_app())
    html = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    r = client.get("/pdf/AAAAAAAAAAAA", headers={**html, "accept-language": "xx,fr-FR;q=0.9,en;q=0.8"})
    assert r.status_code == 404 and r.headers["content-type"].startswith("text/html")
    assert '<html lang="fr">' in r.text and "Ce lien a expiré" in r.text and 'href="https://example.org/"' in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"] and "<script" not in r.text
    assert "expired" in client.get("/pdf/AAAAAAAAAAAA", headers=html).text  # no Accept-Language: English
    assert client.get("/pdf/AAAAAAAAAAAA").headers["content-type"].startswith("text/plain")
    id_ = store.put(STUDIO.read_text("utf-8"))
    client.post(f"/doc/{id_}/delete")
    gone = client.get(f"/pdf/{id_}", headers={**html, "accept-language": "de"})
    assert gone.status_code == 410 and "gelöscht" in gone.text
    bad_id = store.put(json.dumps({"uniwire": "1.0.0", "meta": {"title": "<b>"}}))
    bad = client.get(f"/pdf/{bad_id}", headers=html)
    assert bad.status_code == 422 and "<pre>" not in bad.text and "<b>" not in bad.text  # the document is not quoted


def test_svg_route(tmp_path):
    """The first sheet as SVG, for the web editor to show while its engine starts."""
    pytest.importorskip("mcp.server.mcpserver")
    from starlette.testclient import TestClient

    from uniwire.mcp_server import _add_svg_route, build_server

    store = DocStore(tmp_path)
    id_ = store.put(STUDIO.read_text("utf-8"))
    server = build_server(None, store)
    _add_svg_route(server, store, None)
    client = TestClient(server.streamable_http_app())
    r = client.get(f"/svg/{id_}")
    assert r.status_code == 200 and r.text.lstrip().startswith(("<svg", "<?xml"))
    assert r.headers["content-type"].startswith("image/svg+xml") and r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert client.get("/svg/AAAAAAAAAAAA").status_code == 404
    bad_id = store.put('{"uniwire": "1.0.0"}')
    bad = client.get(f"/svg/{bad_id}")
    assert bad.status_code == 422


def test_delete_route(tmp_path):
    """A link holder deletes the document with a POST; its links then answer 410 instead of 404."""
    pytest.importorskip("mcp.server.mcpserver")
    from starlette.testclient import TestClient

    from uniwire.mcp_server import _add_doc_route, _add_svg_route, build_server

    store = DocStore(tmp_path)
    id_ = store.put(STUDIO.read_text("utf-8"))
    server = build_server(None, store)
    _add_doc_route(server, store)
    _add_svg_route(server, store, None)
    client = TestClient(server.streamable_http_app())
    assert client.get(f"/doc/{id_}/delete").status_code in (404, 405)  # a GET never deletes
    assert client.get(f"/doc/{id_}").status_code == 200
    for origin in ("https://evil.example", "null"):  # a form posted by another site
        assert client.post(f"/doc/{id_}/delete", headers={"origin": origin}).status_code == 403
    assert client.get(f"/doc/{id_}").status_code == 200
    r = client.post(f"/doc/{id_}/delete", headers={"origin": "http://testserver"})
    assert r.status_code == 204 and r.headers["cache-control"] == "no-store"
    assert client.get(f"/doc/{id_}").status_code == 410 and client.get(f"/svg/{id_}").status_code == 410
    assert client.post(f"/doc/{id_}/delete").status_code == 410
    assert client.post("/doc/AAAAAAAAAAAA/delete").status_code == 404 and client.get("/doc/AAAAAAAAAAAA").status_code == 404


def test_linked_tools_not_read_only_with_store(tmp_path):
    """With a store, the tools that return links keep the document: not read-only (app directory checks)."""
    pytest.importorskip("mcp.server.mcpserver")
    import asyncio

    from uniwire.mcp_server import LINKED, build_server

    tools = asyncio.run(build_server(None, DocStore(tmp_path)).list_tools())
    for t in tools:
        assert t.annotations.read_only_hint is (t.name not in LINKED), t.name
        assert t.annotations.open_world_hint is (t.name in LINKED), t.name
        assert t.annotations.destructive_hint is False and t.annotations.idempotent_hint is True
