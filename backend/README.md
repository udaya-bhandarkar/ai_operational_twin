# AI Operational Twin — Backend

LLM agent built on LangGraph / LangChain / LangSmith. A single agent queries and writes to an operational DuckDB database and can search the web, with human-in-the-loop approval on write operations, a full middleware stack, and a CI eval gate.

> **Architecture note:** this started as a supervisor orchestrating two sub-agents (ops + research). That nesting made every question pay for two reasoning loops (supervisor → sub-agent → tools), roughly doubling model calls — which tripped provider rate limits and slowed responses. It was **collapsed into one agent with all tools attached directly**: ~half the model calls, faster replies, and cleaner answers (no double-summarisation). The multi-agent pattern is worth reintroducing only when there are many specialists or a need for per-agent isolation.

A **FastAPI gateway** (`api/`) sits in front of the graph and the DuckDB gold layer, serving the React dashboard (see [API Gateway](#api-gateway)).

---

## Setup

### Prerequisites

- Python 3.11+
- A supported LLM provider API key (Anthropic, Groq, or Mistral)
- A LangSmith API key (free tier works)

### Install

```bash
cd backend
uv venv .venv --python 3.11
.venv\Scripts\activate
uv pip install -e ".[all-providers,tavily]" "langgraph-cli[inmem]"
```

Or install only the provider you need:

```bash
uv pip install -e .              # Anthropic only (default)
uv pip install -e ".[groq]"      # adds langchain-groq
uv pip install -e ".[mistral]"   # adds langchain-mistralai
uv pip install -e ".[tavily]"    # adds tavily web search
uv pip install -e ".[dev]"       # adds pytest + openevals + ruff
uv pip install -e ".[mcp]"       # adds langchain-mcp-adapters
```

> **Important:** Install `langgraph-cli` into the same venv as your project deps. If `langgraph` is in a different Python (e.g. Anaconda base), it won't see your venv packages and will fail with `ModuleNotFoundError`.

### Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your keys.

**Anthropic (default)**
```env
ANTHROPIC_API_KEY=sk-ant-...
BACKEND_MODEL=anthropic:claude-opus-4-8
```

**Groq**
```env
GROQ_API_KEY=gsk_...
BACKEND_MODEL=groq:llama-3.3-70b-versatile
```

**Mistral**
```env
MISTRAL_API_KEY=...
BACKEND_MODEL=mistral-large-latest
```

LangSmith (required for traces in Studio UI):
```env
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=RAIC
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_TRACING=true
```

> **Note:** Keep `.env` comments ASCII-only. Unicode characters (`→`, `──`) cause a `python-dotenv could not parse statement` warning.

### Run

```bash
langgraph dev
```

Opens LangGraph Studio at `https://smith.langchain.com/studio/`. The supervisor graph loads automatically from `langgraph.json`.

For staging-parity with Postgres persistence (requires Docker):

```bash
langgraph up
```

---

## Project Structure

```
backend/
├── langgraph.json              # Graph entrypoint (points to make_graph factory)
├── pyproject.toml              # Dependencies
├── .env.example                # Environment variable template
│
├── api/                        # FastAPI gateway — frontend (React dashboard) ↔ backend
│   ├── app.py                  # FastAPI app + CORS + uvicorn entry (port 8000)
│   ├── db.py                   # read-only DuckDB access + scope filter + snapshot-time anchor
│   ├── dashboard.py            # 7 dashboard GET endpoints (match frontend mockData.js field-for-field)
│   └── chat.py                 # POST /api/chat → supervisor graph (async ainvoke)
│
├── config/
│   ├── settings.py             # Pydantic Settings — yaml defaults + .env overrides
│   └── environments/
│       ├── dev.yaml            # Dev defaults: CLI HITL
│       ├── staging.yaml        # Staging defaults: API HITL
│       └── prod.yaml           # Prod defaults: API HITL
│
├── agents/
│   └── supervisor/             # Single agent: DuckDB + web tools, one reasoning loop
│       ├── graph.py            # make_graph() — StateGraph: guardrail → agent → verify (+ HITL)
│       └── prompts/system.txt  # role + gold-table schema + tool rules + answer formatting
│
├── tools/
│   ├── web.py                  # web_search (Tavily, graceful degradation), web_fetch (httpx)
│   ├── duckdb.py               # 5 DuckDB tools (list, schema, checker, query, execute)
│   └── mcp_client.py           # MultiServerMCPClient — add MCP servers here
│
├── middleware/
│   ├── pii.py                  # PIIMiddleware — API key blocking (input + output)
│   ├── retry.py                # ModelRetryMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
│   ├── caching.py              # AnthropicPromptCachingMiddleware
│   ├── summarization.py        # SummarizationMiddleware — compress history at 80% token threshold
│   └── dynamic_model.py        # @wrap_model_call dev_cost_router — budget model in dev
│
├── hitl/
│   └── channels/
│       └── cli.py              # CLI runner: streams graph, handles interrupts
│
├── evals/
│   ├── datasets/v1/            # JSONL eval datasets (supervisor, research, ops)
│   ├── evaluators/             # contains, exact_match, llm_judge (openevals)
│   └── run_evals.py            # langsmith evaluate() + --gate flag
│
├── scripts/
│   └── upload_datasets.py      # one-time LangSmith dataset upload
│
└── tests/
    ├── test_evaluators.py      # unit tests for evaluators (no API calls)
    └── test_config.py          # unit tests for Settings validator
```

---

## API Gateway

FastAPI app (`api/`) that fronts the dashboard and chat for the React frontend (`frontend/`). Dashboard endpoints read the DuckDB gold layer directly; `/api/chat` forwards to the supervisor graph.

### Run

```bash
# 1. Build the gold DB once (from repo root)
python src/data_pipeline/build_gold_layer.py

# 2. Start the gateway (from backend/)
.venv/Scripts/python.exe -m uvicorn api.app:app --port 8000
# or: python -m api.app
```

Frontend connects by setting `VITE_API_BASE=http://localhost:8000/api`. CORS is enabled for any `localhost`/`127.0.0.1` origin in dev (no Vite proxy needed). For a **deployed** frontend, set `CORS_ORIGINS` in `.env` to a comma-separated list of allowed origins (e.g. `https://twin.example.com`) — localhost is auto-allowed only when `BACKEND_ENV=dev`.

### Endpoints

All responses match `frontend/src/mocks/mockData.js` field-for-field.

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{status}` |
| GET | `/api/kpis` | totals, efficiency, deltas, as_of |
| GET | `/api/waste-over-time` | `{range, points:[{bucket, waste_cost_inr}]}` |
| GET | `/api/waste-by-machine` | `{machines:[{machine_id, waste_cost_inr}]}` |
| GET | `/api/top-events` | `{events:[{machine_id, timestamp, efficiency_ratio, energy_cost_inr, total_waste_inr, status}]}` |
| GET | `/api/machines` | `{machines:[{machine_id, status}]}` |
| GET | `/api/facilities` | `{facilities:[{facility_id, label}]}` |
| GET | `/api/departments` | `{departments:[{department_id, label, facility_id}]}` |
| POST | `/api/chat` | `{reply, thread_id}` — forwards to supervisor graph |

**Scope params** — every dashboard GET accepts `view`, `facility_id`, `department_id` (all optional). `facility_id`/`department_id` apply as exact-match filters. Waste convention: `waste_cost = estimated_power_waste_cost_inr + estimated_water_waste_cost_inr + material_waste_cost_inr` (all excess-only). Windows anchor on `MAX(timestamp)` (data is a fixed snapshot, not live).

### Scoping

`view` needs no server-side logic — the dashboard sends the ids: factory scope sends `facility_id`, department scope sends `facility_id` + `department_id`, and CEO sends neither. The `scope_where` filter applies them as exact matches. `label` fields are derived from the id (no lookup table needed).

### Waste model

Waste is reported **excess-only**, across three components summed into total waste:
- `estimated_power_waste_cost_inr` — electricity over the 300 kW threshold
- `estimated_water_waste_cost_inr` — water over the 25 L threshold
- `material_waste_cost_inr` — material lost (intake − output) × PET rate

The `operational_power_cost_inr` / `operational_water_cost_inr` columns are total resource cost, not waste, and are never summed into the waste total.

---

## Agent

A custom LangGraph `StateGraph` wraps the LangChain agent, placing **deterministic** validation
nodes around the **agentic** core. This is the documented reason to use a hand-built `StateGraph`
rather than `create_agent` alone — mixing fixed steps (guardrails, verification) with an agent
node. `langgraph dev` and the API gateway both load it via the `make_graph` factory in
`langgraph.json`.

```
START → guardrail → agent → verify → END
          │           ▲       │
          └→ END       └───────┘   (one bounded retry if figures aren't grounded)
```

- **guardrail** (deterministic) — input validation before any model call: rejects empty /
  oversized input and attempts to spoof the web tools' untrusted-content markers. Un-promptable.
- **agent** (agentic) — `create_agent` with the full middleware stack + all tools:
  ```
  agent  (full middleware stack + HITL)
    ├── duckdb_query          (read — no HITL)
    ├── duckdb_query_checker  (validate before a write)
    ├── duckdb_list_tables / duckdb_schema  (explore other tables — rarely needed)
    ├── duckdb_execute        (write — HITL interrupt: approve / edit / reject)
    └── web_search / web_fetch
  ```
- **verify** (deterministic) — numeric grounding check: money-like figures in the final answer
  must appear in this turn's tool results. An LLM can claim any number; one that is in no tool
  output was not read from the database. Ungrounded figures trigger **one** corrective retry,
  then the answer is surfaced (never looped forever).

`HumanInTheLoopMiddleware` interrupts only on `duckdb_execute` (writes); reads and web calls
pass through. The agent's system prompt carries the `gold_operational_metrics` schema, so it
writes SQL directly instead of spending calls on `list_tables`/`schema` for the primary table.

**Why one agent, not a supervisor + sub-agents:** see the architecture note at the top. Nesting
sub-agents-as-tools doubled model calls (each sub-agent is its own reasoning loop) and caused
double-summarisation of results. A single agent halves the calls and preserves table output.

### Security (agent-layer)

Defense-in-depth aligned with the OWASP Top 10 for LLM Applications:

- **Text-to-SQL hardening** (`tools/duckdb.py`) — statements are classified read vs write by
  **AST** (`sqlglot`), not first-word matching, so bypasses like
  `WITH t AS (SELECT 1) DELETE FROM …` are caught. Read tools run on a `read_only=True`
  connection (enforcement at the DB layer, not the string level); `duckdb_schema` allowlists
  table names against the live catalog and parameterizes its metadata query; multi-statement
  payloads are rejected.
- **Indirect prompt-injection defense** (`tools/web.py`) — web content is wrapped in
  `<<<EXTERNAL_CONTENT>>>` boundary markers labelled as untrusted data; marker-spoofing is
  stripped; the system prompt instructs the agent to treat it as data, never instructions.
- **Numeric grounding** (verify node) — a deterministic hallucination check on the output.

---

## Tools

### Web tools (`tools/web.py`)

`web_search` calls the Tavily API if `TAVILY_API_KEY` is set. If the key is missing it returns a clear message instead of crashing:

```
[web_search] No results — TAVILY_API_KEY is not set.
Add it to .env and run: uv pip install -e ".[tavily]"
```

`web_fetch` uses `httpx` and truncates responses at 8 000 chars to protect the context window. Both tools wrap returned content in untrusted-content boundary markers (see [Security](#security-agent-layer)).

### DuckDB tools (`tools/duckdb.py`)

Five tools split by operation type:

| Tool | Type | Purpose |
|---|---|---|
| `duckdb_list_tables` | read | List all tables |
| `duckdb_schema` | read | Column definitions + 3 sample rows |
| `duckdb_query_checker` | validation | Validate SQL + classify as read or write |
| `duckdb_query` | read | Execute SELECT; rejects mutations; capped at 100 rows |
| `duckdb_execute` | write | Execute INSERT/UPDATE/DELETE/DROP/CREATE/ALTER; requires HITL approval |

Read vs write is classified by parsing the SQL **AST** (`sqlglot`), not by matching the first keyword — so CTE-wrapped or otherwise disguised writes are still caught (see [Security](#security-agent-layer)). Read tools additionally run on a `read_only=True` connection, so a misclassified statement still cannot mutate the database.

Database path: `DUCKDB_PATH` in `.env`. Default is the canonical gold-layer DB at the repo root: `data/database/operational_twin.db`, built by `src/data_pipeline/build_gold_layer.py` (run it once before starting the API — see root README). The API gateway reads the same DB.

### MCP tools (`tools/mcp_client.py`)

Wraps `MultiServerMCPClient` from `langchain-mcp-adapters`. Ships empty — add MCP servers as needed:

```python
# tools/mcp_client.py
MCP_SERVERS = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/workspace"],
        "transport": "stdio",
    },
}
```

```bash
uv pip install -e ".[mcp]"
```

Then pass MCP tools to any agent:

```python
from tools.mcp_client import get_mcp_tools
agent = create_agent(model=..., tools=[*existing_tools, *get_mcp_tools()])
```

`get_mcp_tools()` is sync-safe — handles both direct-script and langgraph dev (uvicorn) contexts via thread isolation.

---

## Middleware

### Middleware stack (the single agent)

```
PIIMiddleware (api_key block)              — outermost
ModelCallLimitMiddleware (15 calls)
ToolCallLimit (duckdb_execute=3, web_search=5)
ModelRetryMiddleware (rate-limit-aware)
SummarizationMiddleware (80%, keep 6)     — compress history before model call
dev_cost_router                           — swaps model per env
RateLimitMiddleware                       — paces model calls under provider RPM
HumanInTheLoopMiddleware                  — interrupts on duckdb_execute (writes)
AnthropicPromptCachingMiddleware          — innermost; caches prompt before model call
```

### PII (`middleware/pii.py`)

`PIIMiddleware("api_key", detector=r"sk-...", strategy="block", apply_to_input=True, apply_to_output=True)` blocks `sk-...` API key patterns in both directions.

Email middleware is intentionally omitted. Redacting emails on input breaks legitimate requests ("draft an email to x@y.com"), and the agent may need to return emails from database query results.

### Fault tolerance (`middleware/retry.py`)

Limits on the single agent (`get_ops_limits()` + `get_research_limits()`):

| Middleware | Value |
|---|---|
| `ModelRetryMiddleware` | rate-limit-aware, up to 5 attempts |
| `ModelCallLimitMiddleware` | 15 model calls per run |
| `ToolCallLimitMiddleware(duckdb_execute)` | 3 writes per run |
| `ToolCallLimitMiddleware(web_search)` | 5 searches per run |

`ModelCallLimitMiddleware` sits outside `ModelRetryMiddleware`. If the limit were inside the retry wrapper, a single transient failure would burn retry attempts against the call budget. With limit outside, retries are invisible to the counter.

**Rate-limit-aware retry.** `get_model_retry()` uses `retry_on` to retry **only** rate-limit / transient errors (429, 5xx, overloaded, timeout — matched on exception text, provider-agnostic), with long backoff (5 → 10 → 20 → 40 → 60 s, up to 5 attempts) to wait out the provider's window. Non-retryable failures (bad request, auth) surface immediately instead of burning attempts. Works with `RateLimitMiddleware` (proactive pacing) so a multi-call DB question completes on a free tier rather than failing with 429.

### Rate limiting (`middleware/rate_limit.py`)

Proactive throttle — the "waiting system" for provider rate limits. A single agent turn
(especially a DB question) fans into many rapid model calls; on a rate-limited provider
(e.g. Mistral free tier ~1 req/s) that burst returns HTTP 429.

`RateLimitMiddleware` blocks before each model call until a shared `InMemoryRateLimiter`
grants a token, spacing calls under the limit. The limiter is module-level (a single shared
instance), so pacing stays global even if more agents are added later. Implements both sync and
async hooks (works on `graph.invoke` and `graph.ainvoke`). Placed **inside** `ModelRetryMiddleware`
so retries are paced too. Tune with `MODEL_REQUESTS_PER_SECOND` (0 disables).

Paired with the retry middleware's rate-limit-aware backoff (below), a multi-step DB question
completes on a free tier instead of failing with 429 — at the cost of latency (calls are
serialized at the configured rate). Raise the rate on paid tiers / Anthropic for faster chat.

### Agent instructions (`agents/supervisor/prompts/system.txt`)

All agent instructions — role, gold-table schema, tool rules, write safety, answer formatting —
live in one file, loaded once at import. (An earlier `AGENTS.md` + deepagents `MemoryMiddleware`
duplicated most of these rules and injected ~1k tokens of unrelated memory guidelines per model
call; removed.)

### Summarization (`middleware/summarization.py`)

`SummarizationMiddleware` from `langchain.agents.middleware`. Triggers at 80% of the model's max input token budget; retains the 6 most recent messages after compression. Uses `SUMMARIZATION_MODEL` (defaults to `BACKEND_MODEL` when unset).

### Dynamic model routing (`middleware/dynamic_model.py`)

`dev_cost_router` via `@wrap_model_call`. In `BACKEND_ENV=dev`, routes supervisor model calls to `SUMMARIZATION_MODEL` — a cheaper model from the same provider. No-op when:
- `SUMMARIZATION_MODEL == BACKEND_MODEL` (not set, defaults applied)
- providers differ (prevents cross-provider key requirements)
- `BACKEND_ENV` is not `dev`

Set a budget model in `.env`:

```env
# Anthropic
SUMMARIZATION_MODEL=anthropic:claude-haiku-4-5

# Groq
SUMMARIZATION_MODEL=groq:llama-3.1-8b-instant

# Mistral
SUMMARIZATION_MODEL=mistral-small-latest
```

To disable dev routing entirely: set `BACKEND_ENV=staging` in `.env`.

### Prompt caching (`middleware/context.py`)

`AnthropicPromptCachingMiddleware(ttl="5m")` applied innermost on the supervisor. Caches the system prompt, tool definitions, and conversation history breakpoints on Anthropic's servers. Cache hits appear in LangSmith traces as `cache_read_input_tokens`. No-op for Groq / Mistral models.

---

## Configuration

### Environment variables

All settings live in `config/settings.py` (Pydantic) and are read from `backend/.env`. Full reference:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `BACKEND_MODEL` | yes (chat) | `anthropic:claude-opus-4-8` | Model that answers + grades. Provider is the prefix (`anthropic:` / `groq:` / none = Mistral) |
| `ANTHROPIC_API_KEY` / `GROQ_API_KEY` / `MISTRAL_API_KEY` | one, matching `BACKEND_MODEL` | — | Provider key. Gateway logs a clear warning at startup if the matching one is missing |
| `BACKEND_ENV` | no | `dev` | Loads `config/environments/<env>.yaml`; `dev` enables localhost CORS + budget-model routing |
| `SUMMARIZATION_MODEL` | no | = `BACKEND_MODEL` | Cheaper model for summarization + dev cost routing |
| `DUCKDB_PATH` | no | built gold DB path | Operational database file the agent + gateway read |
| `MODEL_REQUESTS_PER_SECOND` | no | `2.0` | Throttle to stay under provider rate limits; `0` disables |
| `CORS_ORIGINS` | no (prod) | — | Comma-separated allowed origins for a deployed frontend |
| `CORS_ORIGIN_REGEX` | no | — | Regex for dynamic origins (e.g. Vercel preview URLs) |
| `LANGSMITH_API_KEY` | no (evals) | — | Datasets + traces; required to run evals |
| `LANGSMITH_TRACING` | no | `false` | Send traces to LangSmith |
| `TAVILY_API_KEY` | no | — | Web search; degrades gracefully when unset |

Only the provider key + `BACKEND_MODEL` are needed for chat; the dashboard needs neither.

### Environment-specific defaults

`config/environments/dev.yaml`, `staging.yaml`, and `prod.yaml` define per-environment defaults. `config/settings.py` loads the yaml for `BACKEND_ENV` before reading `.env` — `.env` always wins, yaml provides sane baselines.

```
BACKEND_ENV=dev      → loads config/environments/dev.yaml
BACKEND_ENV=staging  → loads config/environments/staging.yaml
```

| Setting | dev | staging | prod |
|---|---|---|---|
| `hitl_channel` | cli | api | api |
| `backend_model` | claude-opus-4-8 | claude-opus-4-8 | claude-opus-4-8 |
| `summarization_model` | defaults to `backend_model` | defaults to `backend_model` | defaults to `backend_model` |

### Switching models

Set `BACKEND_MODEL` in `.env`. No code changes required.

```
anthropic:claude-opus-4-8        # default
anthropic:claude-haiku-4-5       # cheaper, faster
groq:llama-3.3-70b-versatile     # fast inference
groq:llama-3.1-8b-instant        # ultra-fast
mistral-large-latest             # Mistral (no prefix needed — auto-detected)
mistral-small-latest             # cheaper Mistral
```

Provider prefix rules:
- Anthropic → `anthropic:model-name`
- Groq → `groq:model-name`
- Mistral → model name only, no prefix (e.g. `mistral-large-latest`, not `mistral:mistral-large-latest`)

---

## Persistence

`langgraph dev` uses an in-memory checkpointer — threads are lost on restart. `langgraph up` (requires Docker) provisions a Postgres container automatically; threads and HITL interrupt state survive process restarts.

LangGraph Store is auto-provisioned by the runtime alongside the checkpointer — InMemoryStore in `langgraph dev`, Postgres-backed in `langgraph up`. No code changes needed.

---

## Human-in-the-Loop

`HumanInTheLoopMiddleware` is on the agent, configured to interrupt only on `duckdb_execute` calls — read queries and web calls pass through without approval. Decision options: approve, edit, reject. The interrupt bubbles up through the agent's checkpointer automatically.

The CLI runner (`hitl/channels/cli.py`) handles the full interrupt → approve / edit / reject loop when running outside langgraph dev:

```python
from agents.supervisor.graph import make_graph
from hitl.channels.cli import run_with_hitl

graph = make_graph()
result = run_with_hitl(graph, "What is the latest on fusion energy?", thread_id="thread-1")
```

---

## Evaluations + CI

> **Running the evals? See [`evals/README.md`](evals/README.md)** — a step-by-step guide for
> setup and reading results. This section covers the design.

### Datasets

`evals/datasets/v1/` holds JSONL datasets (one per LangSmith dataset):

| Dataset | Examples | Covers |
|---|---|---|
| `ops-v1` | 116 | The QA test suite — hierarchy/aggregation, resource use, yield loss, thresholds, root-cause, trends, financials, anti-hallucination, exec summaries |
| `supervisor-v1` / `research-v1` | few | Legacy placeholder buckets (pre-single-agent); ignore |

`ops-v1` is generated from the QA team's questions and is graded against the June-14 dataset
they were authored on (loaded into the gold DB). Each example:
```json
{"inputs": {"messages": [{"role": "user", "content": "question"}]}, "outputs": {"answer": "reference answer"}, "metadata": {"task": "suite3_I"}}
```
`outputs.answer` is the reference used by `correctness_evaluator`; omit it (`{}`) for questions
with no known answer (they're graded by relevance only).

### Evaluators

Three evaluators run on every dataset:

| Evaluator | File | Needs model | Needs reference answer | What it checks |
|---|---|---|---|---|
| `string_contains_evaluator` | `string_match.py` | No — pure code | Yes — `outputs.answer` | Reference answer text appears in AI response |
| `relevance_evaluator` | `llm_judge.py` | Yes — LLM judge | No | Is the response relevant to the question at all |
| `correctness_evaluator` | `llm_judge.py` | Yes — LLM judge | Yes — `outputs.answer` | AI response vs reference answer (semantic) |

`string_contains_evaluator` uses `StringEvaluator` from `langsmith.evaluation` with a plain grading function — no API calls, instant, free. It checks whether the reference answer string appears literally in the AI response.

The two LLM judges use prebuilt prompts (`CORRECTNESS_PROMPT`, `ANSWER_RELEVANCE_PROMPT`) from `openevals.prompts` via `create_llm_as_judge`. They use `settings.summarization_model` as the judge model.

Examples with an empty/`PLACEHOLDER` `answer` are skipped by `correctness`/`string_contains` (`score=None`) and excluded from the gate average — they're graded by `relevance` only.

The eval runner drives the agent asynchronously on one shared event loop (`run_evals.py`),
since the agent's middleware requires the async model-call path.

### Running evals

```bash
python scripts/upload_datasets.py                 # once — push datasets to LangSmith
python -m evals.run_evals --dataset ops-v1        # run, print results
python -m evals.run_evals --dataset ops-v1 --gate # exit 1 if avg score < 0.70
```

Eval runs are recorded in LangSmith under `LANGSMITH_PROJECT`. **Step-by-step setup and how to
read the results: [`evals/README.md`](evals/README.md).**

### Dataset upload (one-time)

Datasets must be uploaded to LangSmith before CI can use them:

```bash
python scripts/upload_datasets.py
```

Re-running is safe — appends to an existing dataset rather than replacing it.

### CI pipeline

Two workflow files:

**`ci.yml`** — runs on every push and PR, no API calls, no token cost:

| Stage | Job | What runs |
|---|---|---|
| 1 | `lint` | `ruff check` + graph import smoke test |
| 2 | `test` | `pytest tests/` (unit tests, no API calls) |

**`evals.yml`** — runs evals against LangSmith, costs tokens, NOT triggered on push:

| Trigger | When |
|---|---|
| Manual (`workflow_dispatch`) | Run from GitHub Actions UI before releases; optionally pass a single `--dataset` name |

Running evals only manually is standard practice — full E2E evals call real LLMs and are too expensive to run on every commit. The `--gate` flag is available to fail a run below a score threshold, but it is not wired into deployment. Requires GitHub repository secrets:

| Secret | Purpose |
|---|---|
| `LANGSMITH_API_KEY` | Fetch datasets + log results to LangSmith |
| `ANTHROPIC_API_KEY` | Model calls during eval runs (swap for Groq/Mistral key if needed) |

Set these in **Settings → Secrets and variables → Actions** on the repo.

---

## Roadmap / next steps

Features intentionally deferred for time. The architecture already accommodates each — notes
below are the intended implementation path, not open research.

### Conversation memory (multi-turn chat)

Today each `/api/chat` call is answered in isolation — the gateway passes a `thread_id` (already
wired from the frontend through `chat.py`) but `make_graph()` attaches no checkpointer, so there
is nothing to persist/reload a thread. `langgraph dev` auto-injects one; the FastAPI gateway does
not.

**Setup:** pass a checkpointer when building the agent in `agents/supervisor/graph.py`:
```python
from langgraph.checkpoint.memory import InMemorySaver
return create_agent(..., checkpointer=InMemorySaver())   # in-process; resets on restart
```
For durable threads across restarts, run under `langgraph up` (Postgres) or wire a Postgres
saver. No frontend change needed — the `thread_id` round-trip already exists.

### Show the SQL / citations

Return the query the agent ran alongside the answer, so every number is traceable to a source —
reinforces the "grounded, no hallucination" property. **Setup:** have the DuckDB tool record the
executed SQL (e.g. onto run state or a returned field) and include it in the `/api/chat`
response; render it under the chat bubble as a collapsible "Show query".

### Streaming responses

The gateway returns one complete response. To stream the final answer token-by-token: add a
`/api/chat/stream` endpoint using `graph.astream_events(...)` wrapped in a FastAPI
`StreamingResponse` (SSE), filtered to the final model call; the frontend reads the stream and
appends chunks. ~half a day; the tool phase stays a spinner (only the answer streams).

### API authentication

Endpoints are currently open. For a single frontend, a shared **API key** is sufficient.
**Setup:** add `API_KEY` to `settings.py` + `.env`; add a FastAPI dependency that checks an
`X-API-Key` header (constant-time compare via `hmac.compare_digest`) and apply it to the `/api`
routers (leave `/health` open). Enforce only when `API_KEY` is set, so dev/CI/evals are
unaffected. The frontend then sends the header. Use HTTPS in production; note a browser-held key
is only semi-secret (move to JWT + login if real per-user accounts are needed).

### Deeper time-series data

The current dataset is a single-day snapshot, so "this week / trend / vs yesterday" questions
have no history to compute against. **Setup:** run `sensor_stream.py` across multiple days (or
generate dated partitions) and rebuild the gold layer — the `sensor_data_*.json` wildcard and
`MAX(timestamp)` windowing already handle multi-day data. Enables real KPI deltas (currently
returned as `0.0`).

### Additional MCP tools

`tools/mcp_client.py` ships empty. Wiring an MCP server (filesystem, another database, an
external API) would extend the agent's reach — see [MCP tools](#mcp-tools-toolsmcp_clientpy).

---

## Architecture notes

**`create_agent` is a LangGraph graph**

`create_agent` from `langchain.agents` returns a compiled `LangGraph StateGraph` internally. That is why `langgraph dev` can serve it — it IS a LangGraph graph, it just doesn't require you to build the nodes/edges manually.

**Pass model as string, not pre-instantiated**

```python
# Correct
create_agent(model=settings.backend_model, ...)

# Avoid
create_agent(model=init_chat_model(settings.backend_model), ...)
```

`create_agent` calls `init_chat_model()` internally and binds tools to the model in the right order. Passing an already-instantiated model object causes LangSmith to fail serializing the graph structure. Pass the model name string; let `create_agent` own instantiation.

**Checkpointer**

`langgraph dev` / Agent Server injects its own checkpointer automatically. Do not pass one to `create_agent` when serving via the dev server. For direct CLI use, pass `checkpointer=MemorySaver()` to `create_agent`.

**`LANGSMITH_TRACING`**

Set `LANGSMITH_TRACING=true`. Earlier versions of `langsmith`/`langchain` had a bug where enabling this alongside `langgraph dev` caused a `maximum recursion depth exceeded` error (two tracers conflicting). Fixed in `langchain>=1.3.2`.

---

## Troubleshooting

**`ModuleNotFoundError` when running `langgraph dev`**

`langgraph` CLI is using a different Python than where your packages are installed. Install `langgraph-cli[inmem]` into the same venv as your project, then run `langgraph dev` with the venv active.

**`401 Unauthorized` from provider API**

API key in `.env` is missing, wrong, or was rotated. Check the key matches the provider set in `BACKEND_MODEL`.

**`ValueError: graph includes a custom checkpointer`**

Passed `checkpointer=` to `create_agent` while also running via `langgraph dev`. Remove the checkpointer argument — the dev server injects its own.

**Graph import slow (>5s warning in logs)**

`create_agent(...)` called at module level. Move it inside `_get_agent()` with a `global` so it only runs on first use.
