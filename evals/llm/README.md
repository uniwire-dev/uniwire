# LLM evaluation tasks

This folder measures how well a language model writes and edits uniwire documents. It holds:

- `tasks/*.json`: 15 tasks. Each one pairs a natural-language request with checks a machine can run, such as "profile `nfc15100`", "at least 3 `rcd` with `idn_mA` 30", "a `water_heater` fed through a `contactor` with `function` HC", "no `error` finding" or "renders". Task 15 is an edit task: it starts from a bundled example (`base`).
- `reference/`: hand-written reference solutions for tasks 01, 05 and 15. They score 1.0, and the test suite uses them to check the scorer.
- `run.py`: the runner. It makes no network or API calls. You produce the candidate documents with any model or tool, and the runner scores them.

The scoring logic lives in `uniwire.llm.evaluate`. Its module docstring documents the check vocabulary.

## Run it with any model

1. Print the prompts. Each prompt holds the reference card, the request and, for edit tasks, the starting document:

   ```bash
   python evals/llm/run.py prompt all --out prompts/      # one <task_id>.prompt.txt per task
   python evals/llm/run.py prompt 01                      # one task to stdout
   ```

2. Send each prompt to the model you want to test, with any client: a chat UI, an API script, or an agent that uses the `uniwire-mcp` tools. Save each answer as `candidates/<task_id>.json`. The answer must be the JSON document only.

3. Score the answers:

   ```bash
   python evals/llm/run.py score candidates/ -v --json results.json
   ```

   Each task scores `passed / total`. Validity counts as the first point. An invalid or missing document scores 0. The runner prints the mean score over all tasks and the number of valid documents.

Run `python evals/llm/run.py score evals/llm/reference` to see the expected output format. Only three tasks have a reference solution, so the other tasks show as missing.

## Comparing setups

The same task set compares:

- prompt only (card in the prompt) and tool use (MCP server: `validate` / `check` / `apply_patch` loop);
- the compact and the full reference card (`prompt --full`);
- English and French prompts (`prompt --lang fr` translates the card; the requests stay as written).

## Adding a task

Add `tasks/NN_name.json` with `id` (the file name without `.json`), `request` and `expect`, plus `base` for an edit task. Then check that the task is solvable: write a solution, put it in `reference/` and run the scorer.
