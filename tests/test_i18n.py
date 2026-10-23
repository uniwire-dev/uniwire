from uniwire import load, render_pages
from uniwire.i18n import CATALOGS, EN, FR, normalize_lang, t
from uniwire.render.scene import Group, Text
from uniwire.rules import check

DOC = {"sources": [{"type": "grid", "children": [{"type": "breaker", "in_A": 32, "cable": {"section_mm2": 1.5},
                                                    "children": [{"type": "socket"}]}]}],
       "profiles": ["nfc15100"]}


def _texts(item) -> list[str]:
    if isinstance(item, Text):
        return [item.text]
    if isinstance(item, Group):
        return [s for c in item.items for s in _texts(c)]
    return []


def test_catalogs_have_same_keys():
    assert set(EN) == set(FR)
    assert set(CATALOGS) == {"en", "fr"}


def test_lang_selection(monkeypatch):
    monkeypatch.delenv("UNIWIRE_LANG", raising=False)
    assert t("notes.title") == "Notes" and t("tb.title") == "Title"
    monkeypatch.setenv("UNIWIRE_LANG", "fr")
    assert t("tb.title") == "Titre"
    assert t("tb.title", lang="en-GB") == "Title"
    assert normalize_lang("fr-FR") == "fr" and normalize_lang("xx") == "en" and normalize_lang(None) == "en"


def test_rule_messages_follow_env(monkeypatch):
    monkeypatch.delenv("UNIWIRE_LANG", raising=False)
    doc = load(DOC)
    en = {f.rule: f.message for f in check(doc)}
    monkeypatch.setenv("UNIWIRE_LANG", "fr")
    fr = {f.rule: f.message for f in check(doc)}
    assert set(en) == set(fr)  # rule ids are language-independent
    assert "32 A breaker on 1.5 mm²" in en["nfc15100.section"]
    assert "disjoncteur 32 A sur 1,5 mm²" in fr["nfc15100.section"]  # decimal comma


def test_title_block_follows_meta_lang():
    texts_fr = _texts(render_pages(load({**DOC, "meta": {"lang": "fr"}}))[0].root)
    texts_en = _texts(render_pages(load({**DOC, "meta": {"lang": "en"}}))[0].root)
    assert "Régime de neutre" in texts_fr and "Earthing system" not in texts_fr
    assert "Earthing system" in texts_en and "Régime de neutre" not in texts_en
