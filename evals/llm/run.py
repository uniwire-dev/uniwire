#!/usr/bin/env python3
"""Score uniwire documents produced by any LLM against the task specs of this folder.

    python evals/llm/run.py score <candidates_dir> [--tasks DIR] [--json OUT] [-v]
    python evals/llm/run.py prompt <task_id|all> [--lang en|fr] [--full] [--out DIR]
    python evals/llm/run.py list

Candidates are files named ``<task_id>.json`` (or ``<task_id>.uniwire.json``) in the candidates folder.
No network access and no model API is used: generate the candidates with the model of your choice.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

try:
    from uniwire.llm.evaluate import find_candidate, load_tasks, score, task_prompt
except ImportError:  # running from a source checkout without installing
    sys.path.insert(0, str(HERE.parent.parent / "src"))
    from uniwire.llm.evaluate import find_candidate, load_tasks, score, task_prompt


def _select(tasks: list[dict], key: str) -> list[dict]:
    if key == "all":
        return tasks
    sel = [t for t in tasks if t["id"] == key or t["id"].startswith(f"{key}_")]
    if not sel:
        sys.exit(f"unknown task {key!r}")
    return sel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", default=str(HERE / "tasks"), help="folder of task specs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("score", help="score a folder of candidate documents")
    p.add_argument("candidates")
    p.add_argument("--json", help="write the detailed results to this JSON file")
    p.add_argument("-v", "--verbose", action="store_true", help="show every failed check")
    p = sub.add_parser("prompt", help="print the self-contained prompt of a task (card + request)")
    p.add_argument("task")
    p.add_argument("--lang", default="en")
    p.add_argument("--full", action="store_true", help="use the full reference card")
    p.add_argument("--out", help="write one <task_id>.prompt.txt per task in this folder")
    sub.add_parser("list", help="list the tasks")
    a = ap.parse_args(argv)
    tasks = load_tasks(a.tasks)

    if a.cmd == "list":
        for t in tasks:
            print(f"{t['id']:36} {len(t['expect']) + 1:2} checks  {t['request'][:70]}…")
        return 0
    if a.cmd == "prompt":
        for t in _select(tasks, a.task):
            text = task_prompt(t, lang=a.lang, level="full" if a.full else "compact")
            if a.out:
                Path(a.out).mkdir(parents=True, exist_ok=True)
                (Path(a.out) / f"{t['id']}.prompt.txt").write_text(text, "utf-8")
            else:
                sys.stdout.write(text)
        return 0

    results = []
    for t in tasks:
        path = find_candidate(a.candidates, t["id"])
        r = score(path, t) if path else score(None, t)
        if not path:
            r["results"][0]["detail"] = "missing candidate file"
        results.append(r)
        print(f"{t['id']:36} {r['passed']:2}/{r['total']:<2} {r['score']:.2f}" + ("" if r["valid"] else "  INVALID"))
        if a.verbose:
            for x in r["results"]:
                if not x["ok"]:
                    print(f"    x {x['check']}: {x['detail']}")
    mean = sum(r["score"] for r in results) / len(results) if results else 0.0
    valid = sum(1 for r in results if r["valid"])
    print(f"\nmean score {mean:.3f}, valid documents {valid}/{len(results)}")
    if a.json:
        Path(a.json).write_text(json.dumps({"mean": mean, "results": results}, ensure_ascii=False, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
