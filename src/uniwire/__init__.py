"""uniwire: an open exchange format for electrical installations, and its reference library.

Validation, rule checks, bills of materials, wiring exports and drawings of electrical diagrams
(single-line and multi-line, SVG and PDF).

>>> import uniwire
>>> doc = uniwire.load("installation.uniwire.json")
>>> uniwire.render_svg(doc, "out")          # SVG sheets
>>> uniwire.check(doc)                       # rule checks (profiles)
"""

from .model import FORMAT_VERSION, Document
from .render import render_pages, render_pdf, render_svg
from .resolve import UniwireError, dump, load
from .rules import check

__version__ = "0.1.4"
__all__ = ["FORMAT_VERSION", "Document", "UniwireError", "check", "dump", "load", "render_pages",
           "render_pdf", "render_svg"]
