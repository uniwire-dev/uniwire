"""Labels of the devices drawn on a link beside a column (a switch across a contactor) never sit on another text."""
from uniwire import load, render_pages
from uniwire.render.scene import Group, Text, bbox


def _texts(item):
    if isinstance(item, Text):
        return [item]
    return [t for i in item.items for t in _texts(i)] if isinstance(item, Group) else []


def _column(i):
    return {"type": "breaker", "id": f"Q{i}", "ref": f"Q{i}", "poles": "1P+N", "in_A": 10,
            "label": "Feeder with a rather long description", "children": [
                {"type": "impulse_relay", "id": f"K{i}", "ref": f"K{i}", "label": "Impulse relay, phase contact", "children": [
                    {"type": "junction_box", "id": f"X{i}", "ref": f"X{i}", "label": "Hall lights", "children": [
                        {"type": "lighting", "id": f"E{i}"}]}]}]}


DOC = {
    "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400},
    "sources": [{"type": "grid", "children": [{"type": "board", "id": "B", "children": [_column(i) for i in range(1, 5)]}]}],
    "links": [{"kind": "bypass", "from": f"Q{i}", "to": f"X{i}",
               "device": {"type": "switch_disconnector", "id": f"S{i}", "ref": f"S{i}", "poles": "1P",
                          "label": "Manual override switch"}} for i in range(1, 5)],
}


def test_side_device_labels_overlap_no_other_text():
    for page in render_pages(load(DOC)):
        boxes = [(t.text, bbox(t)) for t in _texts(page.root) if t.text.strip()]
        for i, (a, p) in enumerate(boxes):
            for b, q in boxes[i + 1:]:
                assert min(p[2], q[2]) - max(p[0], q[0]) < 0.3 or min(p[3], q[3]) - max(p[1], q[1]) < 0.3, (a, b)
