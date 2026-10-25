"""Readability of the shipped examples: overlapping texts, links drawn over one another or on a conductor.
The counts may only go down: lower a number when a fix removes findings."""

import json

import pytest

from tests.conftest import ROOT
from tests.drawing_audit import audit
from uniwire import load, render_pages

KNOWN = {"30": 1}  # a stray mark beside a label (example 30)
EXAMPLES = sorted((ROOT / "examples").glob("*.uniwire.json"))


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name.split("_")[0] for p in EXAMPLES])
def test_example_drawing_readable(path):
    findings = [f for pg in render_pages(load(json.loads(path.read_text()))) for f in audit(pg.root)]
    assert len(findings) <= KNOWN.get(path.name.split("_")[0], 0), "\n".join(map(str, findings))
