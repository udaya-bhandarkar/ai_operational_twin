# Running the Evals

How to score the agent automatically against the QA test questions. For the eval architecture
(evaluators, CI gate) see the main `backend/README.md` → *Evaluations + CI*.

## Already set up

- **Questions loaded** — the 116 QA questions (`QA Testing test questions.docx`) are converted
  into `evals/datasets/v1/ops.jsonl` (60 with reference answers, 56 without).
- **Matching data loaded** — the June-14 dataset the answers were computed against
  (`JsonForQA.rtf`) is in `data/raw/sensor_data_20260614_164152.json` and built into the gold DB.
  Verified: the agent reproduces the reference answers (e.g. Chennai electricity → 14,585.16 kWh).
  The old July-2 snapshot is archived as `sensor_data_*.json.bak` (excluded from the build).

> If you regenerate or replace the raw data, the reference answers will no longer match — they
> are pinned to that exact June-14 snapshot. Rebuild the gold DB after any data change:
> `python src/data_pipeline/build_gold_layer.py` (from repo root).

## What you need once

- `backend/.env` with:
  - `LANGSMITH_API_KEY=...`  (free tier is fine — datasets + results live here)
  - a provider key + `BACKEND_MODEL` (e.g. `MISTRAL_API_KEY` + `BACKEND_MODEL=mistral-large-latest`).
    The same model answers the questions AND acts as the grader.

## Step 1 — (optional) edit the questions

The questions are already in `backend/evals/datasets/v1/ops.jsonl` (converted from your docx).
Only edit this file if you want to add, remove, or fix questions/answers. **One question per
line**, as JSON.

**Question WITH a known answer** (gets graded for correctness):
```json
{"inputs": {"messages": [{"role": "user", "content": "Which department had the highest material yield loss at Chennai Recycling Plant?"}]}, "outputs": {"answer": "PRE_PROCESSING"}, "metadata": {"task": "material_loss"}}
```

**Question WITHOUT an answer** (still runs — graded only for relevance, not correctness):
```json
{"inputs": {"messages": [{"role": "user", "content": "Which machine had the biggest drop in efficiency vs its 7-day average?"}]}, "outputs": {}, "metadata": {"task": "efficiency_drop"}}
```

Rules of thumb:
- `content` = the question exactly as a user would ask it.
- `outputs.answer` = the expected answer. Keep it short and specific (a name, a number, a short
  phrase) — the grader checks if the agent's reply matches it. Omit `outputs.answer` (use `{}`)
  when you don't have a reference answer.
- `metadata.task` = any short label for your own filtering (optional).

> You can put every question in `ops.jsonl` — the agent handles all question types. (The
> `research.jsonl` / `supervisor.jsonl` files are legacy buckets; ignore them unless you want
> to organise by category.)

## Step 2 — upload to LangSmith

```bash
cd backend
python scripts/upload_datasets.py
```

Uploads `ops.jsonl` as the `ops-v1` dataset. **Note:** re-running *appends* (creates duplicate
examples). If you change questions and want a clean re-upload, delete the dataset in the
LangSmith UI first, then re-run.

## Step 3 — run the evals

```bash
cd backend
python -m evals.run_evals --dataset ops-v1           # recommended — runs the QA questions
python -m evals.run_evals --dataset ops-v1 --gate    # same, exit code 1 if avg < 0.70 (for CI)
```

Use `--dataset ops-v1` — the QA questions live there. (`research-v1` / `supervisor-v1` are
legacy placeholder datasets; running them just wastes agent calls.)

Each question is scored by up to three evaluators:

| Evaluator | Needs an answer? | What it checks |
|---|---|---|
| `correctness` | yes | Agent's reply matches your reference answer (LLM judge) |
| `string_contains` | yes | Your reference answer text appears in the reply |
| `relevance` | no | Reply is on-topic for the question (LLM judge) |

Questions without an answer are scored by `relevance` only — `correctness` / `string_contains`
skip them (they don't count against the score). Full results (per-question pass/fail + the
judge's reasoning) appear in the LangSmith UI under your project.

## Tips

- Start small (5-10 questions) to confirm the loop works, then add the rest.
- Mistral free tier is slow here (the agent + graders make several calls each, paced to avoid
  rate limits). Expect a few minutes for a batch. Anthropic / paid tiers are much faster.
- `--gate` is what CI uses; a run "passes" if the average score across graded questions ≥ 0.70.
