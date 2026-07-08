# Evals — Setup & Checking Results

Score the agent automatically against the QA test suite (116 questions). This guide takes a
teammate from a fresh clone to reading the results. For the eval *architecture* (evaluators,
CI gate) see `backend/README.md` → *Evaluations + CI*.

## TL;DR (already-set-up machine)

```bash
cd backend
python scripts/upload_datasets.py                  # push questions to LangSmith (once)
python -m evals.run_evals --dataset ops-v1         # run + score
```
Then open the experiment link printed in the terminal to see per-question results.

---

## First-time setup (fresh clone)

**1. Install backend deps** (see `backend/README.md` for detail):
```bash
cd backend
uv venv .venv --python 3.11
uv pip install -e ".[dev]"          # .[dev] pulls in openevals, used by the graders
```

**2. Build the operational database.** The DB file is git-ignored, so build it from the
committed raw data (this is the June-14 dataset the answer key was computed against):
```bash
# from the repo root
python src/data_pipeline/build_gold_layer.py
```
This creates `data/database/operational_twin.db`. **Re-run it after any change to the raw
data** — the reference answers are pinned to the exact June-14 snapshot.

**3. Set keys in `backend/.env`:**
```env
LANGSMITH_API_KEY=...              # free tier is fine — datasets + results live here
LANGSMITH_PROJECT=RAIC             # results are grouped under this project
# one provider — this model both ANSWERS the questions and GRADES them:
MISTRAL_API_KEY=...
BACKEND_MODEL=mistral-large-latest
```

That's it — the 116 questions are already in `evals/datasets/v1/ops.jsonl` (committed).

---

## Run

**Step 1 — upload the questions to LangSmith** (once, or after editing them):
```bash
cd backend
python scripts/upload_datasets.py
```
Creates/updates the `ops-v1` dataset. **Re-running appends** (duplicates). To re-upload cleanly,
delete the `ops-v1` dataset in the LangSmith UI first.

**Step 2 — run the evals:**
```bash
python -m evals.run_evals --dataset ops-v1           # run + print scores
python -m evals.run_evals --dataset ops-v1 --gate    # same, exit 1 if avg < 0.70 (CI mode)
```
Use `--dataset ops-v1` — the QA questions live there (`research-v1` / `supervisor-v1` are legacy
placeholders; running them just wastes calls).

> Expect a few minutes: on Mistral's free tier the agent + graders make several paced calls per
> question. Anthropic / paid tiers are much faster.

---

## Checking the results

### In the terminal
The run prints a link to each experiment and a summary line:
```
Overall average score: 0.83  (threshold: 0.70)
EVAL GATE PASSED: 0.83 >= 0.70
```
The average is across every graded evaluator result; `--gate` turns that into an exit code
(0 = pass, 1 = fail) for CI.

### In the LangSmith UI (the detail)
1. Go to **smith.langchain.com** → your project (`RAIC`) → **Datasets & Experiments** →
   **ops-v1**. (Or just click the experiment link printed in the terminal.)
2. Open the latest **experiment**. You get a table: **one row per question**, with columns for
   the agent's answer and each evaluator's score.
3. Each question is scored by up to three evaluators:

   | Evaluator | Needs a reference answer? | What a pass means |
   |---|---|---|
   | `correctness` | yes | Agent's reply matches the reference answer (LLM judge) |
   | `string_contains` | yes | The reference answer text appears in the reply |
   | `relevance` | no | Reply is on-topic for the question (LLM judge) |

4. **Click any cell** to see the agent's full reply, the tools it called, and — for the LLM
   judges — the **reasoning** for why it passed or failed. This is how you tell a real wrong
   answer from a formatting mismatch.
5. **Sort/filter** by an evaluator column to find every failure fast.

### Reading it right
- Questions **without** a reference answer (56 of them) are scored by `relevance` only —
  `correctness`/`string_contains` skip them and don't count against the average.
- A `correctness` fail with a `relevance` pass usually means: the agent answered on-topic but
  got the number wrong (or the reference was phrased differently). Read the judge's comment.
- The anti-hallucination questions (Suite 8) pass when the agent **refuses** / says the data
  isn't available — check those replies rather than looking for a number.

---

## Editing the questions

Edit `evals/datasets/v1/ops.jsonl`, **one JSON object per line**:

```json
{"inputs": {"messages": [{"role": "user", "content": "Which department had the highest material yield loss at Chennai Recycling Plant?"}]}, "outputs": {"answer": "PRE_PROCESSING"}, "metadata": {"task": "suite3_I"}}
```
- `content` — the question as a user would ask it.
- `outputs.answer` — short, specific reference answer (name / number / phrase). Omit it
  (`"outputs": {}`) when you have no reference; that question is then graded by `relevance` only.
- `metadata.task` — any label (used for your own filtering).

After editing, re-upload (Step 1) — delete `ops-v1` in the UI first for a clean set.

---

## Troubleshooting

- **`No scores collected`** — the dataset isn't in LangSmith. Run `upload_datasets.py` first.
- **Every answer is "no records for today"** — the gold DB wasn't rebuilt from the June-14 data.
  Run `build_gold_layer.py` and confirm `data/raw/` has `sensor_data_20260614_*.json`.
- **`401 Unauthorized`** — provider or LangSmith key missing/invalid in `.env`.
- **`429` / very slow** — provider rate limit; expected on free tiers. It's paced to recover;
  just let it run, or switch to a paid tier / Anthropic.
- **Trend / "this week" questions look wrong** — the data is a single-day snapshot with no
  history; those questions have no data to compute against (most have no reference answer).
