"""LLM evaluation harness: task specs are well-formed, reference solutions pass, the scorer discriminates."""

import json
import subprocess
import sys

import pytest

from uniwire.llm.evaluate import find_candidate, load_tasks, matches, score, task_prompt

from .conftest import ROOT

EVALS = ROOT / "evals" / "llm"
if not (EVALS / "tasks").is_dir():  # the source distribution does not ship evals/
    pytest.skip("evals/llm is not available (source distribution)", allow_module_level=True)
TASKS = load_tasks(EVALS / "tasks")
REFERENCE = EVALS / "reference"


def test_task_specs():
    assert len(TASKS) >= 15
    ids = [t["id"] for t in TASKS]
    assert len(set(ids)) == len(ids)
    for t in TASKS:
        assert (EVALS / "tasks" / f"{t['id']}.json").is_file()
        assert t["request"] and t["expect"]
        assert {"check": "no_errors"} in t["expect"]


@pytest.mark.parametrize("task", [t for t in TASKS if find_candidate(REFERENCE, t["id"])], ids=lambda t: t["id"])
def test_reference_solutions_pass(task):
    r = score(find_candidate(REFERENCE, task["id"]), task)
    assert r["valid"] and r["score"] == 1.0, [x for x in r["results"] if not x["ok"]]


def test_at_least_three_references():
    assert sum(1 for t in TASKS if find_candidate(REFERENCE, t["id"])) >= 3


def test_scorer_discriminates():
    task = next(t for t in TASKS if t["id"].startswith("01_"))
    good = json.loads(find_candidate(REFERENCE, task["id"]).read_text("utf-8"))
    # remove the off-peak contactor: the 'under' check must fail, the rest still pass
    rcd = good["sources"][0]["children"][0]["children"][0]["children"][0]["children"][1]
    rcd["children"][2]["children"] = [{"type": "water_heater", "id": "WH", "p_kW": 2.4}]
    good["links"] = []
    r = score(good, task)
    assert r["valid"] and 0 < r["score"] < 1
    assert [x["check"] for x in r["results"] if not x["ok"]] == ["under"]
    assert score({"sources": []}, task)["score"] == 0.0
    assert score(None, task)["valid"] is False


def test_matches_patterns():
    n = {"type": "breaker", "in_A": 20, "cable": {"section_mm2": 2.5}, "aux": ["MX", "OF"]}
    assert matches(n, {"type": ["rcd", "breaker"], "in_A": {"min": 16, "max": 32}})
    assert matches(n, {"cable.section_mm2": 2.5, "aux": "MX", "curve": {"exists": False}})
    assert not matches(n, {"cable.length_m": {"exists": True}})
    assert not matches(n, {"in_A": {"min": 25}})


def test_task_prompt_contains_card_and_base():
    edit = next(t for t in TASKS if "base" in t)
    text = task_prompt(edit)
    assert "reference card" in text and edit["request"] in text and '"id": "CPT"' in text


def test_runner_script(tmp_path):
    out = tmp_path / "res.json"
    proc = subprocess.run([sys.executable, str(EVALS / "run.py"), "score", str(REFERENCE), "--json", str(out)],
                          capture_output=True, text=True, check=True)
    assert "mean score" in proc.stdout
    data = json.loads(out.read_text("utf-8"))
    assert sum(1 for r in data["results"] if r["score"] == 1.0) >= 3
