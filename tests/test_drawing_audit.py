"""Readability of the shipped examples: overlapping texts, links drawn over one another or on a conductor.
The counts may only go down: lower a number when a fix removes findings."""

import json

import pytest

from tests.conftest import ROOT
from tests.drawing_audit import audit
from uniwire import load
from uniwire.render import default_view, render_pages, render_views

KNOWN: dict[str, int] = {}  # findings tolerated per example (none today)
# multi-line view of every example: power links outside the tree still drawn along a conductor or a frame
KNOWN_ML: dict[str, int] = {"49": 1, "50": 1, "53": 1}
EXAMPLES = sorted((ROOT / "examples").glob("*.uniwire.json"))


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name.split("_")[0] for p in EXAMPLES])
def test_example_drawing_readable(path):
    findings = [f for pg in render_views(load(json.loads(path.read_text()))) for f in audit(pg.root)]  # every view
    assert len(findings) <= KNOWN.get(path.name.split("_")[0], 0), "\n".join(map(str, findings))


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name.split("_")[0] for p in EXAMPLES])
def test_example_multiline_readable(path):
    doc = load(json.loads(path.read_text()))
    findings = [f for pg in render_pages(doc, default_view(doc, kind="multi-line")) for f in audit(pg.root)]
    assert len(findings) <= KNOWN_ML.get(path.name.split("_")[0], 0), "\n".join(map(str, findings))
