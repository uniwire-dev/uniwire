"""The Notes band prints every line the author wrote, and no bare type word as the supply."""
import uniwire
from uniwire.render import render_views
from uniwire.render.scene import Group, Text


def _doc(notes: list[str], lang: str = "en", supply: str = "grid") -> dict:
    return {"meta": {"title": "Workshop board", "notes": notes, "lang": lang},
            "installation": {"earthing": "TT", "un_V": 400, "system": "3P+N", "supply": supply},
            "sources": [{"type": "grid", "ref": "G", "children": [
                {"type": "breaker", "ref": "-Q1", "poles": 4, "in_A": 40, "children": [
                    {"type": "load", "ref": "-L1", "label": "Lathe", "p_kW": 5}]}]}]}


def _notes_text(doc: dict) -> list[str]:
    out: list[str] = []

    def walk(g):
        for it in g.items:
            if isinstance(it, Group):
                walk(it)
            elif isinstance(it, Text):
                out.append(it.text)

    for page in render_views(uniwire.load(doc)):
        for it in page.root.items:
            if isinstance(it, Group) and it.cls == "notes":
                walk(it)
    return out


def test_long_notes_are_all_printed():
    notes = [f"Note {i}: the spare way is kept for a future machine in bay {i}" for i in range(1, 31)]
    text = " ".join(_notes_text(_doc(notes)))
    assert all(f"Note {i}:" in text for i in range(1, 31))
    assert "more note line" not in text


def test_bare_type_word_is_not_printed_as_the_supply():
    for lang in ("en", "fr", "de"):
        text = " ".join(_notes_text(_doc(["Keep the door closed."], lang)))
        assert "grid" not in text
    assert "Tarif Bleu" in " ".join(_notes_text(_doc(["x"], "fr", "Tarif Bleu")))
