"""Short links of the hosted MCP server: document store and link shortening."""

import json
import os
import time

from uniwire.llm import tools
from uniwire.llm.link import document_from_link, viewer_link
from uniwire.llm.store import ID_LENGTH, DocStore, doc_id
from uniwire.mcp_server import _shorten

from .conftest import ROOT

STUDIO = ROOT / "examples" / "01_studio_apartment.uniwire.json"


def test_store_put_get_expire(tmp_path):
    store = DocStore(tmp_path, ttl_days=1)
    text = STUDIO.read_text("utf-8")
    id_ = store.put(text)
    assert id_ == doc_id(text) and len(id_) == ID_LENGTH and id_.isalnum()
    assert store.put(text) == id_ and len(list(tmp_path.glob("*.json"))) == 1  # same content, same link
    assert store.get(id_) == text
    assert store.get("../../etc/passwd") is None and store.get("x" * ID_LENGTH) is None
    old = time.time() - 2 * 86400
    os.utime(tmp_path / f"{id_}.json", (old, old))
    assert store.get(id_) is None and not (tmp_path / f"{id_}.json").exists()


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
