import re

from uniwire import load, render_pages
from uniwire.i18n import BS, CATALOGS, DE, EN, ES, FR, HR, IT, JA, NL, PL, PT, RU, SR, TR, ZH, normalize_lang, t
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
    assert set(CATALOGS) == {"en", "fr", "ru", "zh", "es", "de", "pt", "it", "pl", "tr", "nl", "hr", "sr", "sr-Cyrl", "bs", "ja"}
    drawing = {k for k in EN if k.split(".")[0] in ("tb", "notes", "legend", "ann", "cell", "about")}
    rules = {k for k in EN if k.split(".")[0] in ("core", "rules", "nfc15100", "vde0100", "iec60364", "enedis", "plc")}
    for cat in (RU, ZH, ES, DE, PT, IT, PL, TR, NL, HR, SR, BS, JA):  # the drawing texts in every language
        assert drawing <= set(cat) <= set(EN)
        for k, v in cat.items():  # same placeholders and formats as the English text (the order follows each language)
            assert sorted(re.findall(r"{[^{}]*}", v)) == sorted(re.findall(r"{[^{}]*}", EN[k])), k
    for cat in (RU, ZH, ES, DE, PT, NL, IT, PL, TR, HR, SR, BS, JA):  # and the rule messages (English for the CLI and validation)
        assert rules <= set(cat)
        assert set(cat) == set(RU)


def test_rule_messages_follow_the_language(monkeypatch):
    d = load({"profiles": ["vde0100"], "sources": [{"type": "grid", "children": [
        {"type": "breaker", "in_A": 16, "children": [{"type": "socket", "id": "S"}]}]}]})
    for lang, word in (("de", "Steckdosenstromkreis"), ("es", "diferencial"), ("pt", "DR"), ("ru", "УЗО"),
                       ("zh", "剩余电流保护器"), ("it", "differenziale"), ("pl", "różnicowoprądowym"),
                       ("tr", "kaçak akım")):
        monkeypatch.setenv("UNIWIRE_LANG", lang)
        msg = next(f.message for f in check(d) if f.rule == "vde0100.rcd-30mA")
        assert word in msg, (lang, msg)


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
    assert {"Hinweise", "BMK", "Leitung (mm²)", "Blatt"} <= set(de)
    assert "1,5" in " ".join(de)  # decimal comma


def test_portuguese_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    pt = [s for p in render_pages(load({**DOC, "meta": {"lang": "pt-BR"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Observações", "Ident.", "Cabo (mm²)", "Folha"} <= set(pt)
    assert "1,5" in " ".join(pt)  # decimal comma


def test_italian_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    it = [s for p in render_pages(load({**DOC, "meta": {"lang": "it-IT"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Note", "Sigla", "Cavo (mm²)", "Foglio"} <= set(it)
    assert "1,5" in " ".join(it)  # decimal comma


def test_polish_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    pl = [s for p in render_pages(load({**DOC, "meta": {"lang": "pl-PL"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Uwagi", "Oznaczenie", "Przewód (mm²)", "Arkusz"} <= set(pl)
    assert "1,5" in " ".join(pl)  # decimal comma


def test_turkish_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    tr = [s for p in render_pages(load({**DOC, "meta": {"lang": "tr-TR"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Notlar", "Etiket", "Kablo (mm²)", "Pafta"} <= set(tr)
    assert "1,5" in " ".join(tr)  # decimal comma


def test_dutch_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    nl = [s for p in render_pages(load({**DOC, "meta": {"lang": "nl-BE"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Opmerkingen", "Codering", "Kabel (mm²)", "Blad"} <= set(nl)
    assert "1,5" in " ".join(nl)  # decimal comma


def test_japanese_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable"]}
    ja = [s for p in render_pages(load({**DOC, "meta": {"lang": "ja-JP"}, "views": [view]})) for s in _texts(p.root)]
    assert {"注記", "記号", "ケーブル（mm²）", "シート"} <= set(ja)
    assert "1.5" in " ".join(ja)  # decimal point


def test_japanese_pdf_kanji_in_the_japanese_font():
    from uniwire.render.pdf import _CJK_FONTS, _cjk_font

    assert _cjk_font("分電盤", "ja") == _CJK_FONTS["ja"]  # kanji only: Japanese forms in a Japanese document
    assert _cjk_font("配电箱") == _CJK_FONTS["zh"]


def test_croatian_serbian_bosnian_drawing_texts():
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable", "circuit"]}

    def texts(lang):
        return [s for p in render_pages(load({**DOC, "meta": {"lang": lang}, "views": [view]})) for s in _texts(p.root)]
    hr, sr, bs = texts("hr-HR"), texts("sr-Latn-RS"), texts("bs-BA")
    assert {"Napomene", "Oznaka", "Kabel (mm²)", "Strujni krug", "List"} <= set(hr)
    assert {"Napomene", "Oznaka", "Kabl (mm²)", "Strujno kolo", "List"} <= set(sr)
    assert {"Napomene", "Oznaka", "Kabl (mm²)", "Strujni krug", "List"} <= set(bs)
    assert all("1,5" in " ".join(x) for x in (hr, sr, bs))  # decimal comma
    assert t("tb.default_sheet_title", lang="hr") == "Jednopolna shema"
    assert t("tb.default_sheet_title", lang="sr") == t("tb.default_sheet_title", lang="bs") == "Jednopolna šema"



def test_serbian_in_cyrillic():
    from uniwire.i18n import cyrillic

    assert normalize_lang("sr-Cyrl") == normalize_lang("sr-Cyrl-RS") == "sr-Cyrl"
    assert normalize_lang("sr") == normalize_lang("sr-Latn-RS") == normalize_lang("sr-RS") == "sr"
    # letter for letter, digraphs included; kept: placeholders, quoted fields, capitals, symbols, units
    assert cyrillic("Uzemljivač i punjač, džep") == "Уземљивач и пуњач, џеп"
    assert cyrillic("Iz {iz:g} A, kabl 2,5 mm² od 25 m, 'count' FID (IEC)") == "Iz {iz:g} A, кабл 2,5 mm² од 25 m, 'count' FID (IEC)"
    view = {"id": "sld", "title_block": True, "cartouche": ["ref", "cable", "circuit"]}
    texts = [s for p in render_pages(load({**DOC, "meta": {"lang": "sr-Cyrl"}, "views": [view]})) for s in _texts(p.root)]
    assert {"Напомене", "Ознака", "Кабл (mm²)", "Струјно коло", "Лист"} <= set(texts)
    assert "1,5" in " ".join(texts)  # decimal comma
    message = t("core.rating_cascade", lang="sr-Cyrl", in_a=32.0, up="-Q1", up_in_a=16.0)
    assert message.startswith("називна струја 32 A") and "-Q1 (16 A)" in message  # the reference as written

def test_type_labels_in_every_language():
    from uniwire import registry

    for type_, info in registry.registry()["types"].items():
        assert set(info["label"]) == {"en", "fr", "ru", "zh", "es", "de", "pt", "it", "pl", "tr", "nl", "hr", "sr", "bs", "ja"}, type_


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
