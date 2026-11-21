"""Drawing conventions: future circuits named in their labels, transformer star points, conductor-count marks,
findings asking for what the drawing cannot guess, circuit table columns."""

import pytest

import uniwire
from uniwire.layout.multiline import conductors
from uniwire.render import default_view, render_pages, render_views
from uniwire.render.scene import Group, Text
from uniwire.rules import check


def _walk(item):
    yield item
    for i in getattr(item, "items", None) or []:
        yield from _walk(i)


def _texts(pages):
    return [i.text for p in pages for i in _walk(p.root) if isinstance(i, Text)]


def _groups(pages, cls):
    return [i for p in pages for i in _walk(p.root) if isinstance(i, Group) and cls in (i.cls or "").split()]


def _mark_texts(doc):
    return {g.id: " ".join(t.text for t in g.items if isinstance(t, Text))
            for g in _groups(render_pages(doc), "conductor-mark")}


def _board(*feeders, installation=None):
    return uniwire.load({"installation": installation if installation is not None else
                         {"earthing": "TT", "system": "3P+N", "un_V": 400},
                         "sources": [{"type": "grid", "id": "G", "children": [
                             {"type": "board", "id": "B", "label": "Board", "children": list(feeders)}]}]})


# ------------------------------------------------------------------ status future
def _future_doc(color=None):
    view = {"id": "v", "color": color} if color else {"id": "v"}
    return uniwire.load({"installation": {"earthing": "TT", "system": "1P+N"}, "views": [view],
                         "sources": [{"type": "grid", "id": "G", "children": [{"type": "board", "id": "B", "children": [
                             {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 16, "children": [
                                 {"type": "socket", "id": "X1", "label": "Sockets"}]},
                             {"type": "breaker", "id": "Q2", "ref": "-Q2", "in_A": 32, "status": "future", "children": [
                                 {"type": "ev_charger", "id": "EV", "label": "Car charger"}]},
                             {"type": "breaker", "id": "Q3", "ref": "-Q3", "in_A": 20, "status": "future", "children": [
                                 {"type": "load", "id": "L3", "label": "Future workshop", "symbol_text": "WS"}]}]}]}]})


def test_future_circuits_say_so_in_their_label_outside_the_status_colour_mode():
    texts = _texts(render_views(_future_doc()))
    assert "Car charger (future)" in texts  # inherited from the breaker above it
    assert "Sockets" in texts and "Sockets (future)" not in texts
    assert "Future workshop" in texts and not any("workshop (future)" in t for t in texts)  # already says it
    ml = _future_doc()
    assert "Car charger (future)" in _texts(render_pages(ml, default_view(ml, kind="multi-line")))
    # the status colour mode draws future blue and dashed: no word added
    assert not any("(future)" in t for t in _texts(render_views(_future_doc("status"))))


def test_future_word_follows_the_language():
    doc = _future_doc()
    doc.meta.lang = "fr"
    assert "Car charger (futur)" in _texts(render_views(doc))


# ------------------------------------------------------------------ transformer star point
def _transformer(earthing, extra=()):
    return uniwire.load({"installation": {"earthing": earthing, "system": "3P+N", "un_V": 400},
                         "views": [{"id": "ml", "kind": "multi-line"}, {"id": "sl"}],
                         "sources": [{"type": "grid", "id": "G", "un_V": 20000, "children": [
                             {"type": "transformer", "id": "T1", "ref": "-T1", "u1_V": 20000, "u2_V": 410,
                              "coupling": "Dyn11", "children": [*extra, {"type": "board", "id": "B", "children": [
                                  {"type": "breaker", "id": "Q1", "in_A": 16, "poles": "1P+N", "children": [
                                      {"type": "socket", "id": "X1"}]}]}]}]}]})


@pytest.mark.parametrize("earthing, star, drawn", [
    ("TN-S", "N", 0),  # already drawn: the neutral bonded to the PE and earthed beside the windings
    ("TN-C", "PEN", 1), ("TN-C-S", "PEN", 1), ("TT", "N", 1), ("IT", None, 0)])
def test_star_point_earthed_in_every_earthing_system(earthing, star, drawn):
    doc = _transformer(earthing)
    assert conductors(doc)["T1"].star == star
    ml, sl = (render_pages(doc, v) for v in doc.views)
    assert len(_groups(ml, "star-point-earth")) == drawn
    assert len(_groups(sl, "star-point-earth")) == (1 if star else 0)  # single-line: an earth on the transformer


def test_it_star_point_not_earthed_but_its_impedance_drawn():
    doc = _transformer("IT", [{"type": "neutral_impedance", "id": "Z", "ref": "-Z1", "impedance_ohm": 1000}])
    assert conductors(doc)["T1"].star is None
    pages = render_views(doc)
    assert not _groups(pages, "star-point-earth") and "-Z1" in _texts(pages)


def test_safety_extra_low_voltage_secondary_never_earthed():
    doc = uniwire.load({"installation": {"earthing": "TN-C", "system": "3P+N"}, "sources": [{"type": "grid", "children": [
        {"type": "breaker", "id": "Q", "poles": "1P+N", "children": [
            {"type": "transformer", "id": "T", "u1_V": 230, "u2_V": 24, "children": [{"type": "lighting"}]}]}]}]})
    assert conductors(doc)["T"].star is None


# ------------------------------------------------------------------ conductor-count marks
def test_no_neutral_mark_on_a_three_wire_supply():
    doc = _board({"type": "breaker", "id": "Q1", "in_A": 16, "poles": "1P", "children": [{"type": "lighting", "id": "E1"}]},
                 {"type": "breaker", "id": "Q2", "in_A": 16, "poles": "1P+N", "children": [{"type": "heating", "id": "H2"}]},
                 {"type": "breaker", "id": "Q3", "in_A": 16, "poles": "2P", "children": [{"type": "socket", "id": "X3"}]},
                 installation={"earthing": "IT", "system": "3P", "un_V": 230})
    texts = _mark_texts(doc)
    assert texts["E1"] == texts["H2"] == texts["X3"] == ""  # two conductors counted, no '+N'
    assert {g.cls.split()[-1] for g in _groups(render_pages(doc), "conductor-mark")} == {"cm-3", "cm-2"}


def test_marks_below_a_two_pole_device_follow_its_conductors():
    doc = _board({"type": "rcd", "id": "R1", "in_A": 40, "idn_mA": 30, "poles": "2P", "phase": "L2", "children": [
        {"type": "breaker", "id": "Q11", "in_A": 16, "children": [{"type": "socket", "id": "X11"}]},
        {"type": "breaker", "id": "Q12", "in_A": 10, "children": [{"type": "lighting", "id": "E12"}]}]},
        {"type": "breaker", "id": "Q4", "in_A": 20, "poles": "4P", "children": [{"type": "load", "id": "L4"}]})
    texts = _mark_texts(doc)
    assert texts["X11"] == texts["E12"] == "L2+N"  # not the installation's four conductors
    assert texts["L4"] == "4"


def test_one_phase_and_neutral_always_written_the_same():
    doc = _board({"type": "breaker", "id": "Q1", "in_A": 16, "poles": "1P+N", "phase": "L1", "children": [
                     {"type": "socket", "id": "X1"}]},
                 {"type": "breaker", "id": "Q2", "in_A": 16, "poles": "2P", "phase": "L3", "children": [
                     {"type": "socket", "id": "X2"}]},
                 {"type": "socket", "id": "X3", "phase": "L2", "cable": {"cores": "3G", "section_mm2": 2.5}})
    texts = _mark_texts(doc)
    assert (texts["X1"], texts["X2"], texts["X3"]) == ("L1+N", "L3+N", "L2+N")
    assert not any(" N" in t for t in texts.values())


def test_split_phase_neutral_passes_a_two_pole_main():
    doc = uniwire.load({"installation": {"earthing": "TN-S", "system": "split-phase", "un_V": 240, "uln_V": 120},
                        "sources": [{"type": "grid", "id": "G", "children": [
                            {"type": "main_breaker", "id": "QM", "poles": "2P", "in_A": 100, "children": [
                                {"type": "board", "id": "B", "children": [
                                    {"type": "breaker", "id": "Q1", "in_A": 15, "phase": "L1", "children": [
                                        {"type": "socket", "id": "X1"}]},
                                    {"type": "breaker", "id": "Q2", "in_A": 30, "poles": "2P", "phase": "L1L2",
                                     "children": [{"type": "water_heater", "id": "W2"}]}]}]}]}]})
    texts = _mark_texts(doc)
    assert texts["X1"] == "L1+N" and texts["W2"] == "L1L2"


def test_pen_split_at_the_first_board_unless_declared():
    guess = _board({"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]},
                   installation={"earthing": "TN-C-S", "system": "3P+N"})
    assert "PEN" in _texts(render_pages(guess))  # SPEC default, as in the multi-line view
    assert [f.rule for f in check(guess)].count("core.pen-split-missing") == 1
    declared = uniwire.load({"installation": {"earthing": "TN-C-S", "system": "3P+N"}, "sources": [
        {"type": "grid", "children": [{"type": "board", "id": "B", "pen_split": True, "children": [
            {"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]}]}]}]})
    assert "PEN" in _texts(render_pages(declared))
    assert "core.pen-split-missing" not in [f.rule for f in check(declared)]
    board = uniwire.load({"installation": {"earthing": "TN-C", "system": "3P+N"}, "sources": [
        {"type": "grid", "children": [{"type": "board", "id": "B", "earthing": "TN-C-S", "children": [
            {"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]}]}]}]})
    assert "PEN" in _texts(render_pages(board))


# ------------------------------------------------------------------ findings
def test_finding_asks_for_the_system_when_none_is_declared():
    none = _board({"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]}, installation={})
    assert [f.level for f in check(none) if f.rule == "core.system-missing"] == ["info"]
    declared = _board({"type": "breaker", "in_A": 16, "children": [{"type": "socket"}]})
    assert "core.system-missing" not in [f.rule for f in check(declared)]
    battery = uniwire.load({"sources": [{"type": "battery", "children": [{"type": "fuse", "children": [{"type": "load"}]}]}]})
    assert "core.system-missing" not in [f.rule for f in check(battery)]


def test_one_finding_suggests_symbol_text_for_every_empty_box():
    doc = _board({"type": "breaker", "in_A": 16, "children": [{"type": "load", "id": "L1", "ref": "-E1"}]},
                 {"type": "breaker", "in_A": 16, "children": [{"type": "load", "id": "L2", "ref": "-E2", "symbol_text": "AC"}]},
                 {"type": "breaker", "in_A": 16, "children": [{"type": "load", "id": "L3", "label": "Press"}]},
                 {"type": "controller", "id": "C", "ref": "-A1"})
    found = [f for f in check(doc) if f.rule == "core.symbol-text"]
    assert len(found) == 1 and found[0].level == "info"
    assert "-E1" in found[0].message and "Press" in found[0].message and "-A1" in found[0].message
    assert "-E2" not in found[0].message
    box = next(g for g in _groups(render_pages(doc), "sym") if g.id == "L3")
    assert not [i.text for i in _walk(box) if isinstance(i, Text) and i.text]  # no text guessed from the label in the box


# ------------------------------------------------------------------ circuit table
def test_source_column_in_the_table_only_with_content():
    def doc(gen):
        return uniwire.load({"installation": {"earthing": "TT", "system": "1P+N"}, "sources": [
            {"type": "grid", "id": "G", "children": [{"type": "board", "id": "B", "children": [
                {"type": "breaker", "id": "Q1", "ref": "-Q1", "in_A": 16, "children": [{"type": "socket", "id": "X1"}]},
                {"type": "breaker", "id": "Q2", "ref": "-Q2", "in_A": 16, "children": [{"type": "lighting", "id": "E2"}]}]}]},
            {"type": "generator", "id": "GEN", **gen}]})

    def cells(d):
        return {g.id for g in _groups(render_pages(d), "uw-cell")}

    assert "GEN" not in cells(doc({}))  # nothing to say: no empty column
    assert "GEN" in cells(doc({"label": "Standby set"}))
    assert "X1" in cells(doc({})) and "E2" in cells(doc({}))
