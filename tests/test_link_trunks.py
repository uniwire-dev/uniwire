"""One device linked to many: the links of one kind sharing one end (a multi-channel meter measuring every feeder, a
gateway reading every charger) drawn as one trunk with a tee tap to each other end, not as a stair of parallel runs.
Invented boards."""

import pytest

from tests.drawing_audit import _groups, audit
from uniwire import load
from uniwire.render import render_views
from uniwire.render.scene import Circle, Group, Polyline, Text
from uniwire.render.semantics import has_cls


def board(feeders: int = 10, kind: str = "measure", label: str | None = None, protocol: str | None = None,
          above: int = 0, below: int = 0, paper: str = "A3", sub: int = 0) -> dict:
    """A board: an incomer, ``feeders`` breakers each feeding a load, and a multi-channel meter (out of the tree)
    linked to every feeder breaker by one link of ``kind``. ``above``: also to the incomer and to the first sub-board
    switches (targets above the feeders); ``below``: also to the loads of the first feeders (targets below them).
    ``sub``: a sub-board with that many feeders on the last feeder, its breakers also linked to the meter."""
    outs, links = [], []
    for i in range(1, feeders + 1):
        load_ = {"type": "socket" if i % 2 else "lighting", "id": f"L{i}", "ref": f"-E{i}", "label": f"Zone {i}"}
        outs.append({"type": "breaker", "id": f"Q{i}", "ref": f"-Q{i}", "in_A": 16, "curve": "C", "poles": "1P+N",
                     "children": [load_]})
        links.append({"kind": kind, "from": f"Q{i}", "to": "P1"})
    if sub:
        outs[-1]["children"] = [{"type": "board", "id": "SB", "ref": "SB1", "in_A": 40, "system": "3P+N", "children": [
            {"type": "breaker", "id": f"S{j}", "ref": f"-F{j}", "in_A": 10, "curve": "C", "poles": "1P+N",
             "children": [{"type": "load", "ref": f"-X{j}", "label": f"Pump {j}"}]} for j in range(1, sub + 1)]}]
        links += [{"kind": kind, "from": f"S{j}", "to": "P1"} for j in range(1, sub + 1)]
    for i in range(1, below + 1):
        links.append({"kind": kind, "from": f"L{i}", "to": "P1"})
    if above:
        links.append({"kind": kind, "from": "Q0", "to": "P1"})
    for link in links:
        if label:
            link["label"] = label
        if protocol:
            link["protocol"] = protocol
    return {"uniwire": "1.0.0-draft", "meta": {"title": "Metered board"},
            "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
            "views": [{"kind": "single-line", "paper": paper}],
            "sources": [{"type": "grid", "un_V": 400, "children": [
                {"type": "board", "id": "MB", "ref": "MB1", "in_A": 100, "system": "3P+N", "children": [
                    {"type": "switch_disconnector", "id": "Q0", "ref": "-Q0", "in_A": 100, "poles": "4P",
                     "children": outs}]}]}],
            "devices": [{"type": "meter", "id": "P1", "ref": "-P1", "label": "Multi-channel meter"}],
            "links": links}


def _links(root: Group) -> dict[str, Group]:
    return {g.attrs["data-uw-link"]: g for g in _groups(root) if has_cls(g, "uw-link") and "data-uw-link" in g.attrs}


def _drawn(g: Group) -> list[Polyline]:
    """The visible strokes of a link (its hover copy left out)."""
    out: list[Polyline] = []
    for it in g.items:
        if isinstance(it, Polyline):
            out.append(it)
        elif isinstance(it, Group) and not has_cls(it, "uw-hit"):
            out += _drawn(it)
    return out


def _horizontal_runs(g: Group) -> list[tuple[float, float, float]]:
    return [(p[1], min(p[0], q[0]), max(p[0], q[0])) for pl in _drawn(g) for p, q in zip(pl.points, pl.points[1:])
            if abs(p[1] - q[1]) < 1e-6 and abs(p[0] - q[0]) > 1e-6]


@pytest.mark.parametrize("feeders", [8, 12])
def test_links_sharing_an_end_are_drawn_as_one_trunk_with_taps(feeders):
    """Every measure link of the meter on one trunk: one horizontal run at one height, drawn once (no two links on one
    another), a junction dot at each tee, no stair of parallel runs."""
    page = render_views(load(board(feeders)))[0]
    links = _links(page.root)
    assert len(links) == feeders and {g.attrs.get("data-uw-trunk") for g in links.values()} == {"P1:measure"}
    runs = [r for g in links.values() for r in _horizontal_runs(g) if r[2] - r[1] > 6.0]  # (not the short stubs)
    assert len({round(y, 3) for y, _a, _b in runs}) <= 2, runs  # the trunk (and the hub's own lead, if it turns)
    pieces = sorted((a, b) for y, a, b in runs if abs(y - runs[0][0]) < 1e-6)
    assert all(b0 <= a1 + 1e-6 for (_a0, b0), (a1, _b1) in zip(pieces, pieces[1:])), pieces  # drawn once, no overlap
    dots = [it for g in links.values() for it in g.items if isinstance(it, Circle)]
    assert len(dots) >= feeders - 2
    findings = [f for f in audit(page.root) if f.kind in ("shared_run", "link_through_symbol", "text_crossed")]
    assert findings == [], "\n".join(map(str, findings))


def test_each_link_of_a_trunk_hovers_its_whole_route():
    """A link of a trunk draws only its piece, but its hover path runs from the meter to its feeder."""
    doc = load(board(8))
    page = render_views(doc)[0]
    for key, g in _links(page.root).items():
        hit = next(it for it in g.items if isinstance(it, Group) and has_cls(it, "uw-hit"))
        path = hit.items[0].points
        link = doc.links[int(key)]
        assert link.to == "P1"
        ends = {round(path[0][0], 1), round(path[-1][0], 1)}
        assert len(ends) == 2  # from one device to the other, not along the trunk only


def test_data_links_carry_one_protocol_text_on_the_trunk():
    """Data links of one protocol: the protocol written once (on the trunk), not once per tap."""
    page = render_views(load(board(8, "data", protocol="Modbus RTU")))[0]
    texts = [t for g in _links(page.root).values() for t in _texts(g) if t == "Modbus RTU"]
    assert texts == ["Modbus RTU"]
    findings = [f for f in audit(page.root) if f.kind in ("shared_run", "text_crossed", "text_overlap")]
    assert findings == [], "\n".join(map(str, findings))


def test_different_labels_stay_on_their_taps():
    doc = board(8)
    for i, link in enumerate(doc["links"]):
        link["label"] = f"CH{i + 1}"
    page = render_views(load(doc))[0]
    texts = sorted(t for g in _links(page.root).values() for t in _texts(g))
    assert texts == sorted(f"CH{i}" for i in range(1, 9))
    findings = [f for f in audit(page.root) if f.kind in ("shared_run", "text_crossed", "text_overlap")]
    assert findings == [], "\n".join(map(str, findings))


def _texts(g: Group) -> list[str]:
    out: list[str] = []
    for it in g.items:
        if isinstance(it, Text):
            out.append(it.text)
        elif isinstance(it, Group):
            out += _texts(it)
    return out


def test_targets_above_and_below_the_trunk():
    """Taps going up (the feeders, the incomer) and down (the loads) from one trunk."""
    page = render_views(load(board(8, above=1, below=3)))[0]
    links = _links(page.root)
    trunked = [g for g in links.values() if g.attrs.get("data-uw-trunk") == "P1:measure"]
    assert len(trunked) >= 8
    findings = [f for f in audit(page.root) if f.kind in ("shared_run", "link_through_symbol")]
    assert findings == [], "\n".join(map(str, findings))


def test_a_target_on_another_sheet_keeps_its_off_sheet_stub():
    """The links to devices on another sheet keep their stubs; the ones on the meter's sheet share a trunk."""
    pages = render_views(load(board(14, sub=8, paper="A4")))
    assert len(pages) > 1
    first = _links(pages[0].root)
    refs = [g for g in _groups(pages[0].root) if has_cls(g, "uw-ref")]
    assert any(g.attrs.get("data-uw-trunk") == "P1:measure" for g in first.values())
    assert any(not g.attrs.get("data-uw-trunk") for g in first.values()) and refs


def test_a_controller_keeps_its_own_points():
    """A controller reached by many links keeps one point each on its sides (not a trunk)."""
    doc = board(8)
    doc["devices"] = [{"type": "controller", "id": "P1", "ref": "-A1", "label": "Energy manager"}]
    page = render_views(load(doc))[0]
    assert not any(g.attrs.get("data-uw-trunk") for g in _links(page.root).values())


def test_two_links_are_routed_one_by_one():
    doc = board(8)
    doc["links"] = doc["links"][:2]
    page = render_views(load(doc))[0]
    assert not any(g.attrs.get("data-uw-trunk") for g in _links(page.root).values())


def test_links_naming_their_terminal_on_the_shared_device_stay_apart():
    """Each link to its own named terminal of the meter: separate wires, routed one by one (not one line)."""
    doc = board(8)
    for i, link in enumerate(doc["links"]):
        link["to_port"] = f"I{i + 1}"
    page = render_views(load(doc))[0]
    assert not any(g.attrs.get("data-uw-trunk") for g in _links(page.root).values())
