"""Readability of the shipped examples: overlapping texts, links drawn over one another or on a conductor.
The counts may only go down: lower a number when a fix removes findings."""

import json

import pytest

from tests.conftest import ROOT
from tests.drawing_audit import audit, text_box
from uniwire import load
from uniwire.render import default_view, render_pages, render_views
from uniwire.render.scene import Group, Polyline, Text

KNOWN: dict[str, int] = {"38": 1, "44": 1}  # findings tolerated per example (single-line views): an off-sheet text
# on its own stub (38), a data link through the ellipsis of a protocol list (44)
# multi-line view of every example: power links outside the tree still drawn along a conductor or a frame
KNOWN_ML: dict[str, int] = {"49": 1, "50": 2, "53": 1}
EXAMPLES = sorted((ROOT / "examples").glob("*.uniwire.json"))


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name.split("_")[0] for p in EXAMPLES])
def test_example_drawing_readable(path):
    findings = [f for pg in render_views(load(json.loads(path.read_text(encoding="utf-8")))) for f in audit(pg.root)]  # every view
    assert len(findings) <= KNOWN.get(path.name.split("_")[0], 0), "\n".join(map(str, findings))


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name.split("_")[0] for p in EXAMPLES])
def test_example_multiline_readable(path):
    doc = load(json.loads(path.read_text(encoding="utf-8")))
    findings = [f for pg in render_pages(doc, default_view(doc, kind="multi-line")) for f in audit(pg.root)]
    assert len(findings) <= KNOWN_ML.get(path.name.split("_")[0], 0), "\n".join(map(str, findings))


def _arrows(item) -> list[Polyline]:
    if isinstance(item, Polyline) and item.closed and len(item.points) == 3:
        return [item]
    return [a for i in item.items for a in _arrows(i)] if isinstance(item, Group) else []


def _refs(item) -> list[Text]:
    if isinstance(item, Text):
        return [item] if "→" in item.text else []
    return [t for i in item.items for t in _refs(i)] if isinstance(item, Group) else []


def test_off_page_texts_end_before_the_point_of_their_arrow():
    """The texts of an off-page stub beside its arrow, not run onto its point ('sheet 2' under the arrowhead)."""
    doc = load(json.loads((ROOT / "examples" / "52_dual_source_selectable_feeders.uniwire.json").read_text("utf-8")))
    for page in render_views(doc):
        texts = [text_box(t) for t in _refs(page.root)]
        for a in _arrows(page.root):
            xs, ys = [p[0] for p in a.points], [p[1] for p in a.points]
            for b in texts:
                assert not (b[0] < max(xs) and min(xs) + 0.2 < b[2] and b[1] < max(ys) and min(ys) < b[3]), b
