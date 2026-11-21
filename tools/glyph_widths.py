"""Writes ``src/uniwire/render/glyph_widths.py``: the advance widths of Liberation Sans (the widths of Arial),
which the layout uses to estimate the width of a text.

    python tools/glyph_widths.py [/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf]

Reads the font file with reportlab (a dev dependency); the font itself is not part of the repository. The table
covers Latin, Greek, the Cyrillic of Russian and Serbian, punctuation, arrows and mathematical signs, in hundredths
of an em rounded up (the estimate is never narrower than the text). The most frequent width, that of the digits and
of most lowercase letters, is left out: it is the default.
"""
from __future__ import annotations

import math
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from reportlab.pdfbase.ttfonts import TTFontFile

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
RANGES = [(0x20, 0x180), (0x370, 0x400), (0x400, 0x460), (0x2000, 0x2300)]
OUT = Path(__file__).resolve().parent.parent / "src" / "uniwire" / "render" / "glyph_widths.py"


def _literal(chars: str) -> str:
    """``chars`` as a Python string literal: letters and printable ASCII as they are, the rest escaped."""
    out = ""
    for ch in chars:
        if ch in "\"\\":
            out += "\\" + ch
        elif (" " < ch < "\x7f") or unicodedata.category(ch).startswith("L"):
            out += ch
        else:
            out += f"\\u{ord(ch):04x}"
    return f'"{out}"'


def main(font: str = FONT) -> None:
    widths = TTFontFile(font).charWidths  # code point -> advance width, thousandths of an em
    default = widths[ord("0")]
    groups: dict[int, str] = defaultdict(str)
    for cp in sorted(widths):
        if any(a <= cp < b for a, b in RANGES) and round(widths[cp]) != round(default):
            groups[math.ceil(widths[cp] / 10 - 1e-6)] += chr(cp)
    lines = ['"""Advance widths of Liberation Sans (the widths of Arial), in hundredths of an em, rounded up.',
             "Written by tools/glyph_widths.py: do not edit.", '"""', "",
             f"DEFAULT = {default / 1000:.6g}  # the digits and most lowercase letters", "", "WIDTHS = {"]
    lines += [f"    {w}: {_literal(groups[w])}," for w in sorted(groups)]
    lines += ["}", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
