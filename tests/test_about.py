"""Page "About this document" after the sheets of a PDF: content, links, languages, options."""

import json
import re

import pytest

from uniwire import load
from uniwire.render import render_pages, with_about
from uniwire.render.about import About, about_page
from uniwire.render.scene import Group, Path, Text, bbox, parse_path, transform
from uniwire.render.svg import page_to_svg

from .conftest import ROOT

STUDIO = ROOT / "examples" / "01_studio_apartment.uniwire.json"


def _doc(lang=None):
    d = json.loads(STUDIO.read_text("utf-8"))
    if lang:
        d["meta"]["lang"] = lang
    return load(d)


def _texts(item) -> list[str]:
    if isinstance(item, Text):
        return [item.text]
    if isinstance(item, Group):
        return [s for c in item.items for s in _texts(c)]
    return []


def _links(item) -> list[str]:
    if isinstance(item, Group):
        own = [item.attrs["data-uw-href"]] if item.cls == "uw-href" else []
        return own + [u for c in item.items for u in _links(c)]
    return []


def test_page_after_the_sheets():
    doc = _doc()
    pages = render_pages(doc)
    out = with_about(doc, pages, About("Yq9tQhb3rDAt"))
    assert len(out) == len(pages) + 1 and out[:-1] == pages
    about = out[-1]
    assert (about.width, about.height) == (pages[0].width, pages[0].height)
    assert about.attrs == {"data-uw-about": "1"} and about.title == "À propos de ce document"
    text = " ".join(_texts(about.root))
    for words in ("Contrôles effectués", "NF C 15-100", "attestation de conformité", "Copie en ligne",
                  "On serait ravis de vous lire", "Merci d'utiliser uniwire"):
        assert words in text, words
    assert "–" in _texts(about.root)  # folio outside the numbering


def test_links_with_and_without_a_stored_copy():
    doc = _doc("en")
    links = set(_links(about_page(doc, 297, 210, ["Sheet"], About("Yq9tQhb3rDAt")).root))
    assert links == {"https://uniwire.sh/viewer/#d=Yq9tQhb3rDAt", "https://uniwire.sh/r/Yq9tQhb3rDAt",
                     "https://uniwire.sh/pdf/Yq9tQhb3rDAt?about=0", "mailto:contact@uniwire.sh",
                     "https://github.com/uniwire-dev/uniwire"}
    page = about_page(doc, 297, 210, ["Sheet"], About(None, "https://example.org"))
    assert set(_links(page.root)) == {"https://example.org/contact", "mailto:contact@uniwire.sh",
                                      "https://github.com/uniwire-dev/uniwire"}
    assert "Online copy" not in " ".join(_texts(page.root))  # nothing stored: no online copy to speak of
    assert '<a href="https://example.org/contact">' in page_to_svg(page)


@pytest.mark.parametrize("lang", ["en", "fr", "de", "es", "pt", "it", "pl", "tr", "ru", "zh"])
def test_every_language_fits_its_frame(lang):
    page = about_page(_doc(lang), 297, 210, ["a", "b"], About("Yq9tQhb3rDAt"))
    x0, y0, x1, y1 = bbox(page.root)
    assert x0 >= 0 and y0 >= 0 and x1 <= 297 and y1 <= 210
    assert not any("about." in t for t in _texts(page.root))  # every text translated


def test_pdf_has_the_page_and_its_links(tmp_path):
    pytest.importorskip("reportlab")
    from uniwire.render import render_pdf

    path = render_pdf(_doc(), tmp_path / "a.pdf", about=About("Yq9tQhb3rDAt"))
    data = path.read_bytes()
    assert len(re.findall(rb"/Type /Page\b", data)) == 2
    assert b"(https://uniwire.sh/r/Yq9tQhb3rDAt)" in data and b"(mailto:contact@uniwire.sh)" in data
    plain = render_pdf(_doc(), tmp_path / "b.pdf").read_bytes()  # not asked for: the sheets only
    assert len(re.findall(rb"/Type /Page\b", plain)) == 1 and b"/URI" not in plain


def test_pdf_route_adds_the_page_unless_asked_not_to(tmp_path):
    pytest.importorskip("reportlab")
    pytest.importorskip("mcp.server.mcpserver")
    from starlette.testclient import TestClient

    from uniwire.llm.store import DocStore
    from uniwire.mcp_server import _add_pdf_route, build_server

    store = DocStore(tmp_path)
    id_ = store.put(STUDIO.read_text("utf-8"))
    server = build_server(None, store)
    _add_pdf_route(server, store, None, "https://uniwire.sh")
    client = TestClient(server.streamable_http_app())
    full, bare = client.get(f"/pdf/{id_}").content, client.get(f"/pdf/{id_}?about=0").content
    assert len(re.findall(rb"/Type /Page\b", full)) == 2 and f"/r/{id_}".encode() in full
    assert len(re.findall(rb"/Type /Page\b", bare)) == 1


def test_path_outline():
    segs = parse_path("M1 2L3 4H5V6Q7 8 9 10Z", dx=1, scale=2)
    assert segs == [("M", 3, 4), ("L", 7, 8), ("L", 11, 8), ("L", 11, 12), ("Q", 15, 16, 19, 20), ("Z",)]
    p = transform(Path(segs), 10, 0)
    assert bbox(p) == (13, 4, 29, 20)
