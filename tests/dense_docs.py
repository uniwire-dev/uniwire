"""Dense documents built for the readability tests: many auxiliary devices and links, several of them converging on
one controller, links to devices drawn on other sheets, long link labels. The shipped examples carry a handful of
links each; these documents carry the density the layout must also hold."""

from __future__ import annotations

from typing import Any

WORDS = ["signal", "pair", "shielded", "monitored", "channel", "feedback", "release", "permit", "interface", "status"]


def _label(k: int, words: int) -> str:
    return " ".join([f"Line {k}"] + [WORDS[(k + j) % len(WORDS)] for j in range(words - 2)])


def _feeder(k: int, own_sheet: bool = False) -> dict[str, Any]:
    """A breaker and a contactor feeding a motor; on a sub-board drawn on its own sheet when ``own_sheet``."""
    motor = {"id": f"M{k}", "type": "motor", "ref": f"-M{k}", "label": f"Drive {k}", "p_kW": 4, "phases": 3,
             "cable": {"cores": "4G", "section_mm2": 2.5, "length_m": 20}}
    chain = {"id": f"Q{k}", "type": "breaker", "ref": f"-Q{k}", "in_A": 16, "curve": "C", "poles": "3P",
             "children": [{"id": f"K{k}", "type": "contactor", "ref": f"-K{k}", "poles": "3P", "children": [motor]}]}
    if not own_sheet:
        return chain
    return {"id": f"QS{k}", "type": "breaker", "ref": f"-QS{k}", "in_A": 32, "curve": "C", "poles": "3P",
            "children": [{"id": f"SB{k}", "type": "board", "ref": f"SB{k}", "label": f"Remote board {k}",
                          "kind": "sub", "own_sheet": True, "children": [chain]}]}


def dense_doc(sensors: int = 8, local: int = 3, remote: int = 2, words: int = 6, hub_links: bool = True,
              spread: int = 0, hub_label: str = "Process controller") -> dict[str, Any]:
    """``sensors`` auxiliary devices linked to one controller (the hub), the hub driving ``local`` contactors on the
    sheet and ``remote`` contactors on boards drawn on other sheets; ``spread`` more auxiliary devices, each linked
    to the contactor of one feeder. Link labels of ``words`` words; ``hub_label``: the label of the hub."""
    feeders = [_feeder(k) for k in range(1, local + 1)] + [_feeder(10 + k, own_sheet=True) for k in range(1, remote + 1)]
    hub = {"id": "HUB", "type": "controller", "ref": "-A1", "label": hub_label, "un_V": 24,
           "function": "sequencing and monitoring"}
    supply = {"id": "QC", "type": "breaker", "ref": "-QC", "in_A": 6, "curve": "C", "poles": "1P+N",
              "children": [{"id": "PS", "type": "power_supply", "ref": "-T1", "label": "Control supply",
                            "u1_V": 230, "u2_V": 24, "output": "DC", "children": [hub]}]}
    devices: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for k in range(1, sensors + 1):
        devices.append({"id": f"B{k}", "type": "controller", "ref": f"-B{k}", "label": f"Sensor {k}",
                        "function": "field input"})
        links.append({"kind": "measure" if k % 2 else "control", "from": f"B{k}", "to": "HUB",
                      "label": _label(k, words)})
    if hub_links:
        for k in list(range(1, local + 1)) + [10 + k for k in range(1, remote + 1)]:
            links.append({"kind": "control", "from": "HUB", "to": f"K{k}", "label": _label(20 + k, words)})
    for k in range(1, spread + 1):
        devices.append({"id": f"S{k}", "type": "controller", "ref": f"-S{k}", "label": f"Local station {k}",
                        "function": "operator buttons"})
        links.append({"kind": "control", "from": f"S{k}", "to": f"K{(k - 1) % max(local, 1) + 1}",
                      "label": _label(40 + k, words)})
    return {
        "uniwire": "1.0.0",
        "profiles": ["iec60364"],
        "meta": {"title": "Dense test document", "lang": "en"},
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400, "uln_V": 230, "f_Hz": 50},
        "sources": [{"id": "G", "type": "grid", "ref": "G", "label": "Supply", "children": [
            {"id": "Q0", "type": "breaker", "ref": "-Q0", "in_A": 100, "poles": "4P", "children": [
                {"id": "DB", "type": "board", "ref": "DB", "label": "Main board", "kind": "main",
                 "children": feeders + [supply]}]}]}],
        "devices": devices,
        "links": links,
    }


# name -> document: the cases the readability tests hold
DENSE = {
    "hub4": dense_doc(sensors=4, local=2, remote=1, words=4),
    "hub8": dense_doc(sensors=8),
    "hub12": dense_doc(sensors=12, local=4, remote=3),
    "long_labels": dense_doc(sensors=6, words=9),
    "spread": dense_doc(sensors=2, local=4, remote=0, spread=8),
    "mixed": dense_doc(sensors=10, local=4, remote=3, spread=6, words=7),
}


def _final(board: str, k: int) -> dict[str, Any]:
    load = ({"type": "lighting", "label": f"Lighting {k}", "p_kW": 0.4} if k % 3 == 0 else
            {"type": "socket", "label": f"Sockets {k}", "count": 4} if k % 3 == 1 else
            {"type": "load", "label": f"Unit {k}", "p_kW": 2})
    return {"id": f"{board}F{k}", "type": "rcbo", "ref": f"-F{k}", "in_A": 16, "curve": "C", "idn_mA": 30,
            "poles": "1P+N", "cable": {"cores": "3G", "section_mm2": 2.5}, "children": [dict(load, id=f"{board}L{k}")]}


def split_main_doc(ways: int = 28) -> dict[str, Any]:
    """A main board of four feeders: two feed large distribution boards (``ways`` final circuits each, more than a
    sheet holds), two leave for other drawings. The main board fits on one sheet; its large boards do not."""
    def board(name: str, label: str) -> dict[str, Any]:
        return {"id": f"{name}", "type": "board", "ref": name, "label": label, "kind": "distribution", "children": [
            {"id": f"{name}S", "type": "switch_disconnector", "ref": "-QS0", "in_A": 125, "poles": "4P",
             "children": [_final(name, k) for k in range(1, ways + 1)]}]}
    feeders = [
        {"id": "Q1", "type": "breaker", "ref": "-Q1", "in_A": 125, "poles": "4P", "children": [board("DA", "Board A")]},
        {"id": "Q2", "type": "breaker", "ref": "-Q2", "in_A": 100, "poles": "4P", "children": [board("DB", "Board B")]},
        {"id": "Q3", "type": "breaker", "ref": "-Q3", "in_A": 63, "poles": "4P",
         "children": [{"id": "X3", "type": "offpage", "label": "Outdoor board"}]},
        {"id": "Q4", "type": "breaker", "ref": "-Q4", "in_A": 63, "poles": "4P",
         "children": [{"id": "X4", "type": "offpage", "label": "Plant room"}]}]
    return {
        "uniwire": "1.0.0",
        "meta": {"title": "Split main board test document", "lang": "en"},
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400, "uln_V": 230, "f_Hz": 50},
        "sources": [{"id": "T", "type": "transformer", "ref": "TR1", "sn_kVA": 630, "children": [
            {"id": "MB", "type": "board", "ref": "MB", "label": "Main board", "kind": "main", "children": feeders}]}],
    }


def long_way_doc(ways: int = 30) -> dict[str, Any]:
    """A main board of five ways, the third feeding a busbar of ``ways`` final circuits: wider than a sheet and not a
    board, so the main busbar is continued over several sheets, one of them holding that way alone."""
    def final(k: int) -> dict[str, Any]:
        return {"id": f"F{k}", "type": "breaker", "ref": f"-F{k}", "in_A": 16, "poles": "1P+N",
                "children": [{"id": f"L{k}", "type": "socket", "label": f"Sockets {k}"}]}
    main = [final(1), final(2),
            {"id": "Q3", "type": "breaker", "ref": "-Q3", "in_A": 100, "poles": "4P", "children": [
                {"id": "W3", "type": "busbar", "ref": "W3", "children": [final(100 + k) for k in range(ways)]}]},
            final(4), final(5)]
    return {
        "uniwire": "1.0.0",
        "meta": {"title": "Long way test document", "lang": "en"},
        "installation": {"earthing": "TN-S", "system": "3P+N", "un_V": 400, "uln_V": 230, "f_Hz": 50},
        "sources": [{"id": "G", "type": "grid", "ref": "G", "label": "Supply", "children": [
            {"id": "MB", "type": "board", "ref": "MB", "label": "Main board", "kind": "main", "children": main}]}],
    }
