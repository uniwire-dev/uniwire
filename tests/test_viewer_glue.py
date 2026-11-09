"""The editor's Python glue (viewer/viewer.py, run in Pyodide in the browser), run here with the library."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("viewer_glue", Path(__file__).parent.parent / "viewer" / "viewer.py")
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)

DOC = {"installation": {"earthing": "TT", "system": "1P+N", "un_V": 230},
       "sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 16, "children": [
           {"type": "breaker", "in_A": 32, "children": [{"type": "socket"}]}]}]}]}


def _messages(lang, ui="en"):
    doc = DOC | ({"meta": {"lang": lang}} if lang else {})
    res = json.loads(viewer.process(json.dumps({"text": json.dumps(doc), "lang": ui})))
    return [f["message"] for f in res["findings"] if f["rule"] == "core.rating-cascade"]


@pytest.mark.parametrize("lang, ui, word", [
    ("it", "en", "corrente nominale"), ("ja-JP", "fr", "定格"), ("pl", "fr", "prąd znamionowy"),
    ("en", "fr", "rating"),  # a document in English: its findings in English
    (None, "fr", "calibre"), ("ko", "fr", "calibre"),  # no language, or one uniwire lacks: the interface's
])
def test_findings_in_the_language_of_the_document(monkeypatch, lang, ui, word):
    monkeypatch.delenv("UNIWIRE_LANG", raising=False)
    found = _messages(lang, ui)
    assert len(found) == 1 and word in found[0], found
