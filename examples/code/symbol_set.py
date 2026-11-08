"""Symbol sets: draw a document with symbols of your own.

uniwire "schematics as code" example. Run ``python symbol_set.py`` from any folder: it writes
``symbol_set.uniwire.json``, ``symbol_set.pdf`` (the drawing) and ``symbol_set_sheet.svg`` (every symbol of the set)
in the current folder.

The set registered here, "boxes" (protective devices drawn as labelled boxes), is invented to show the mechanism: it
follows no standard. Symbols a set does not give are drawn as in the built-in "iec" set. A package makes its set
available to every program through an entry point (see the API documentation, "Symbol sets").
"""

from pathlib import Path

from uniwire.build import *
from uniwire.render.scene import THIN, Line, Rect, Style, Text
from uniwire.render.svg import page_to_svg
from uniwire.symbols import Symbol, register_symbol_set
from uniwire.symbols.sheet import symbol_sheet


def box(letters):
    """A factory: the node first (None on the symbol sheet), then the variants of the built-in symbol, unused here.
    Local frame in mm: input terminal at (0, 0), y pointing down, output terminal at (0, height)."""
    def factory(node=None, *variants, **named):
        return Symbol(f"box-{letters.lower()}", [
            Line((0, 0), (0, 2.5)),
            Rect(-3.5, 2.5, 7, 7, Style(width=THIN)),
            Text((0, 6.7), letters, 2.0, "middle"),
            Line((0, 9.5), (0, 12.5)),
        ], height=12.5, left=3.5, right=3.5)
    return factory


register_symbol_set("boxes", {"breaker": box("CB"), "rcd": box("RCD"), "rcbo": box("RCBO")})

with Installation("Symbol set example", earthing="TN-S", system="1P+N", un="230 V",
                  profiles=["iec60364"], symbols="boxes") as inst:
    with Grid("Supply"), MainBreaker("-Q0", "40 A", label="Main switch"), Board("DB1", label="Distribution board"):
        with RCD("-Q1", "40 A", "30 mA", type="A"):
            Breaker("-F1", "B10", label="Lighting") >> Lighting("Lights", count=6, p_kW=0.06)
            Breaker("-F2", "C16", label="Sockets") >> Socket("Sockets", count=6)
        RCBO("-F3", "C20", "30 mA", label="Oven") >> Cooking("Oven", p_kW=3.5)

if __name__ == "__main__":
    for f in inst.check():
        print(f)
    inst.save("symbol_set.uniwire.json")
    print(inst.render("symbol_set.pdf"))
    Path("symbol_set_sheet.svg").write_text(page_to_svg(symbol_sheet(symbols="boxes")), "utf-8")
