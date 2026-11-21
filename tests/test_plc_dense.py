"""PLCs with many wired channels: closer wires where the PLC would otherwise make its sheet smaller, every off-sheet
stub joined to its device, a safety relay no taller than its stubs need. Invented machine panels."""

from tests.test_control_links import _box, _groups, _node, panel
from uniwire import load
from uniwire.layout.engine import _layout_sheet, fit_scale, layout_sheet, plan_sheets
from uniwire.render import render_views
from uniwire.render.scene import Group, Polyline
from uniwire.symbols import PORT_STEP, PORT_STEP_TIGHT


def _first_sheet(d: dict):
    doc = load(d)
    view = doc.views[0] if doc.views else None
    if view is None:
        from uniwire.model.document import View
        view = View(id="sld")
    spec = plan_sheets(doc, view)[0]
    return doc, view, spec


def test_a_plc_widening_its_sheet_draws_its_wires_closer():
    """Ten contactors driven and read back by a PLC, three drives: the modules widened for their wires set the
    width of the sheet. Their wires are drawn closer, the sheet at a larger scale than with the usual spacing."""
    doc, view, spec = _first_sheet(panel(10, 3))
    lay = layout_sheet(doc, view, spec)
    usual = _layout_sheet(doc, view, spec, None, None, (None, None), None, None, (None, None), port_step=PORT_STEP)
    assert lay.port_step == PORT_STEP_TIGHT
    assert round(fit_scale(lay, view), 2) > round(fit_scale(usual, view), 2)


def test_a_plc_on_a_sheet_at_full_size_keeps_its_usual_wire_spacing():
    doc, view, spec = _first_sheet(panel(3, 0))
    lay = layout_sheet(doc, view, spec)
    assert fit_scale(lay, view) >= 1.0 and lay.port_step == PORT_STEP


def _plc_sheet(motors: int, drives: int):
    d = panel(motors, drives)
    ways = d["sources"][0]["children"][0]["children"][0]["children"]
    ways[0] = {"type": "board", "ref": "CP2", "own_sheet": True, "children": [ways[0]]}  # the PLC on its own sheet
    pages = render_views(load(d))
    return next(p for p in pages if _node(p.root, "PLC") is not None)


def test_every_off_sheet_stub_of_a_busy_plc_is_joined_to_it():
    """A PLC on a sheet of its own, some twenty links to devices on the other sheets: each stub is joined to the PLC
    by its lead (past the first ones, the stubs were drawn alone, joined to nothing)."""
    page = _plc_sheet(8, 2)
    x0, y0, x1, y1 = _box(_node(page.root, "PLC"))
    stubs = 0
    for g in _groups(page.root):
        if not (g.cls and "uw-link" in g.cls.split() and "PLC" in (g.attrs.get("data-uw-from"), g.attrs.get("data-uw-to"))
                and any(isinstance(i, Group) and i.cls == "uw-ref" for i in g.items)):
            continue
        pts = [p for i in g.items if isinstance(i, Polyline) and not i.closed for p in i.points]
        assert any(x0 - 1.5 <= x <= x1 + 1.5 and y0 - 1.5 <= y <= y1 + 1.5 for x, y in pts), \
            (g.attrs, pts)
        stubs += 1
    assert stubs >= 20


def test_a_safety_relay_is_no_taller_than_its_stubs_need():
    """A safety relay stopping contactors drawn on the next sheet, its links named by their terminal only: one line
    of text beside each stub, the relay drawn some 3 mm per stub (it took 5 mm each, room for a label it has not)."""
    d = panel(14, 0, feedback=False)
    d["views"] = [{"id": "sld", "paper": "A4", "min_scale": 1.0}]
    doc, view, spec = _first_sheet(d)
    lay = layout_sheet(doc, view, spec)
    here = {n.node.id for n in lay.lnodes if n.node is not None}
    away = sum(1 for l in doc.links if l.from_ == "SR" and l.to not in here)
    assert away >= 5
    sr = next(n for n in lay.lnodes if n.node is not None and n.node.id == "SR")
    assert sr.sym.height < 3.0 * away + 1.5 * (14 - away) + 10.0, (sr.sym.height, away)
