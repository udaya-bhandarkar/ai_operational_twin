# Evals

> **Status: rebuild pending.** The MVP's domain-specific question sets were archived to
> [`docs/archive/mvp/eval-datasets/`](../docs/archive/mvp/eval-datasets/). General-agent datasets
> and the improved evaluators (numeric matching, independent judge, per-metric gate,
> trajectory checks) are planned — see `docs/IMPROVEMENTS.md` and `docs/KNOWN_BUGS.md` → *Evals*.

## How it works

- `evals/datasets/<name>.jsonl` — one example per line. Each file becomes the LangSmith dataset
  `<name>`:
  ```json
  {"inputs": {"messages": [{"role": "user", "content": "question"}]}, "outputs": {"answer": "reference"}, "metadata": {"task": "label"}}
  ```
  Omit `outputs.answer` (`"outputs": {}`) when there is no reference — the example is then
  graded by relevance only.
- `evals/evaluators/` — `string_match.py` (code, no model) and `llm_judge.py` (openevals
  correctness + relevance judges).
- `evals/run_evals.py` — runs the agent graph against each dataset with LangSmith `evaluate()`;
  `--gate` exits 1 if the average score is below the threshold.

## Run

```bash
cd backend
uv pip install -e ".[dev]"                        # openevals for the judges
python scripts/upload_datasets.py                 # push every datasets/*.jsonl to LangSmith
python -m evals.run_evals                         # all datasets
python -m evals.run_evals --dataset <name> --gate # one dataset, CI exit code
```

Needs `LANGSMITH_API_KEY` and a provider key in `backend/.env`. Re-running the upload appends
examples — delete the dataset in the LangSmith UI first for a clean re-upload. Results: open the
experiment link printed in the terminal (one row per example; click a cell for the full reply,
tool calls and judge reasoning).
