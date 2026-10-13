"""Checks every shipped example: ``examples/*.uniwire.json`` documents and ``examples/code/*.py`` scripts.

Example files are discovered by globbing, so the tests do not depend on their names; with no
example present the parametrized tests are skipped.
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET

import jsonschema
import pytest

from tests.conftest import ROOT
from uniwire import check, dump, load, render_pages, render_pdf, render_svg
from uniwire.layout import layout_sheet, plan_sheets
from uniwire.render import default_view
from uniwire.render.scene import bbox

EXAMPLES = sorted((ROOT / "examples").glob("*.uniwire.json"))
SCRIPTS = sorted((ROOT / "examples" / "code").glob("*.py"))
SCHEMA_FILE = ROOT / "schema" / "uniwire.schema.json"


@pytest.fixture(params=EXAMPLES, ids=[p.name.split(".")[0] for p in EXAMPLES])
def example(request):
    return request.param


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(SCHEMA_FILE.read_text("utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_loads(example):
    assert load(example).sources


def test_valid_against_published_schema(validator, example):
    errors = list(validator.iter_errors(json.loads(example.read_text("utf-8"))))
    assert not errors, [e.message for e in errors]


def test_no_rule_errors(example):
    errors = [str(f) for f in check(load(example)) if f.level == "error"]
    assert not errors, errors


def test_roundtrip_is_stable(example):
    text = dump(load(example))
    assert dump(load(json.loads(text))) == text


def test_render_svg_and_pdf(example, tmp_path):
    doc = load(example)
    paths = render_svg(doc, tmp_path, "t")
    assert paths
    for p in paths:
        assert ET.parse(p).getroot().tag.endswith("svg")  # well-formed XML
    pdf = render_pdf(doc, tmp_path / "t.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


def _layouts(path):
    doc = load(path)
    view = default_view(doc)
    return doc, [layout_sheet(doc, view, s) for s in plan_sheets(doc, view)]


def test_every_node_placed_once(example):
    doc, lays = _layouts(example)
    placed = [n.node.id for lay in lays for n in lay.lnodes + lay.annex if n.kind == "node" and n.node is not None]
    assert len(placed) == len(set(placed)), "node drawn twice"
    from uniwire.resolve import iter_nodes
    expected = {n.id for n, _, _ in iter_nodes(doc) if not any(n is l.device for l in doc.links)}
    assert expected <= set(placed)


def test_symbols_do_not_overlap(example):
    _, lays = _layouts(example)
    for lay in lays:
        boxes = [(n.id, n.sym_box()) for n in lay.lnodes if n.kind != "bus_in" and n.sym.height > 0]
        for i, (ia, a) in enumerate(boxes):
            for ib, b in boxes[i + 1:]:
                ov_x = min(a[2], b[2]) - max(a[0], b[0])
                ov_y = min(a[3], b[3]) - max(a[1], b[1])
                assert not (ov_x > 0.3 and ov_y > 0.3), f"overlap {ia} / {ib}"


def test_auxiliary_devices_do_not_overlap(example):
    _, lays = _layouts(example)
    for lay in lays:
        taken = [(n.id, n.sym_box()) for n in lay.lnodes if n.kind != "bus_in" and n.sym.height > 0]
        taken += [(n.id, n.ann_box()) for n in lay.lnodes if n.ann]
        for dev in lay.annex:
            for box in [dev.sym_box()] + ([dev.ann_box()] if dev.ann else []):
                for other, b in taken:
                    ov_x = min(box[2], b[2]) - max(box[0], b[0])
                    ov_y = min(box[3], b[3]) - max(box[1], b[1])
                    assert not (ov_x > 0.3 and ov_y > 0.3), f"overlap {dev.id} / {other}"
            taken += [(dev.id, dev.sym_box())] + ([(dev.id, dev.ann_box())] if dev.ann else [])


def test_columns_are_ordered_and_spaced(example):
    doc, lays = _layouts(example)
    pitch = default_view(doc).pitch_mm
    for lay in lays:
        xs = [c.x for c in lay.columns]
        assert xs == sorted(xs)
        assert all(b - a >= pitch - 1e-6 for a, b in zip(xs, xs[1:]))


def test_pages_fit_paper(example):
    for page in render_pages(load(example)):
        x0, y0, x1, y1 = bbox(page.root)
        assert x0 >= 0 and y0 >= 0 and x1 <= page.width + 0.01 and y1 <= page.height + 0.01


@pytest.mark.parametrize("script", SCRIPTS, ids=[p.stem for p in SCRIPTS])
def test_code_example_runs(script, tmp_path):
    res = subprocess.run([sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr[-2000:]
