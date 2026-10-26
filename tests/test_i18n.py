import re

from uniwire import load, render_pages
from uniwire.i18n import CATALOGS, DE, EN, ES, FR, PT, RU, ZH, normalize_lang, t
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
    assert set(CATALOGS) == {"en", "fr", "ru", "zh", "es", "de", "pt"}
    drawing = {k for k in EN if k.split(".")[0] in ("tb", "notes", "legend", "ann", "cell")}
    for cat in (RU, ZH, ES, DE, PT):  # the drawing texts, English for the other messages
        assert drawing <= set(cat) <= set(EN)
        assert set(cat) == set(RU)
        for k, v in cat.items():  # same placeholders as the English text
            assert re.findall(r"{\w+}", v) == re.findall(r"{\w+}", EN[k]), k


def test_russian_drawing_texts():
    doc = load({**DOC, "meta": {"lang": "ru", "title": "Щит"}, "views": [{"id": "sld", "title_block": True,
                                                                          "cartouche": ["ref", "cable"]}]})
    texts = [s for p in render_pages(doc) for s in _texts(p.root)]
    assert {"Примечания", "Обозначение", "Кабель (мм²)", "Лист"} <= set(texts)
    assert "1,5" in " ".join(texts)  # decimal comma
    assert t("tb.title", lang="ru-RU") == "Наименование"
    assert t("validation.unknown_node_type", lang="ru", type="x") == t("validation.unknown_node_type", lang="en", type="x")


def test_chinese_and_spanish_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    zh = [s for p in render_pages(load({**DOC, "meta": {"lang": "zh-CN"}, "views": [view]})) for s in _texts(p.root)]
    assert {"说明", "编号", "电缆（mm²）", "张次"} <= set(zh)
    assert "1.5" in " ".join(zh)
    es = [s for p in render_pages(load({**DOC, "meta": {"lang": "es-AR"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Notas", "Designación", "Cable (mm²)", "Hoja"} <= set(es)
    assert "1,5" in " ".join(es)  # decimal comma


def test_german_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    de = [s for p in render_pages(load({**DOC, "meta": {"lang": "de-AT"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Hinweise", "BMK", "Kabel (mm²)", "Blatt"} <= set(de)
    assert "1,5" in " ".join(de)  # decimal comma


def test_portuguese_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    pt = [s for p in render_pages(load({**DOC, "meta": {"lang": "pt-BR"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Observações", "Identificação", "Cabo (mm²)", "Folha"} <= set(pt)
    assert "1,5" in " ".join(pt)  # decimal comma


def test_type_labels_in_every_language():
    from uniwire import registry

    for type_, info in registry.registry()["types"].items():
        assert set(info["label"]) == {"en", "fr", "ru", "zh", "es", "de", "pt"}, type_


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
