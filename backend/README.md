# AI Operational Twin — Backend

Multi-agent LLM system built on LangGraph / LangChain / LangSmith. A supervisor agent orchestrates two specialists — one for web research, one for querying and writing to an operational DuckDB database — with human-in-the-loop approval on write operations, a full middleware stack, and a CI eval gate.

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
├── AGENTS.md                   # Supervisor memory: routing rules, write-safety, response style
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
│   ├── supervisor/             # Orchestrator: routes to specialists, synthesises results
│   │   ├── graph.py            # make_graph() — full middleware stack
│   │   └── prompts/system.txt
│   ├── research/               # Research specialist: web search and fetch
│   │   ├── graph.py            # lazy create_agent + @tool wrapper exposed to supervisor
│   │   └── prompts/system.txt
│   └── ops/                    # Ops specialist: DuckDB read/write
│       ├── graph.py            # lazy create_agent + @tool wrapper + HumanInTheLoopMiddleware
│       └── prompts/system.txt
│
├── tools/
│   ├── web.py                  # web_search (Tavily, graceful degradation), web_fetch (httpx)
│   ├── duckdb.py               # 5 DuckDB tools (list, schema, checker, query, execute)
│   └── mcp_client.py           # MultiServerMCPClient — add MCP servers here
│
├── middleware/
│   ├── pii.py                  # PIIMiddleware — API key blocking (input + output)
│   ├── retry.py                # ModelRetryMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
│   ├── context.py              # MemoryMiddleware (AGENTS.md) + AnthropicPromptCachingMiddleware
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

**Scope params** — every dashboard GET accepts `view`, `facility_id`, `department_id` (all optional). `facility_id`/`department_id` apply as exact-match filters. Waste convention: `waste_cost = estimated_power_waste_cost_inr + material_waste_cost_inr`. Windows anchor on `MAX(timestamp)` (data is a fixed snapshot, not live).

### Design decisions (resolved with designers)

All the original open items are now answered:

| # | Question | Resolution |
|---|---|---|
| 1 | `view` semantics | Dropdowns drive scoping — factory sends `facility_id`, department sends `facility_id`+`department_id`, ceo sends neither. No server-side `view` logic needed; the id filters do the work. |
| 2 | `facilities` / `departments` shape | `{facility_id, label}` and `{department_id, label, facility_id}`. `label` derived from the id (no lookup table). |
| 3 | KPI `deltas` | Frontend dropping the delta UI (no history). Field kept at `0.0` (non-breaking); real deltas become computable once data accumulates. |
| 4 / 5 | `energy_waste_cost_inr` | = `estimated_power_waste_cost_inr` (**excess** power waste, not total cost). Confirmed both sides. |
| — | Frontend `client.js` gaps | Frontend designer added `getFacilities`/`getDepartments` + sends `facility_id`/`department_id`. Done. |

### Remaining open item — split waste types (cross-team)

Data designer wants wastes reported **separately and excess-only**: electricity / **water** / material.
- `estimated_power_waste_cost_inr` (electricity, excess) ✅ exists
- `material_waste_cost_inr` (excess by nature) ✅ exists
- **water waste ❌ does not exist** — the gold layer only has `operational_water_cost_inr` (total, not excess).

Needs: (a) **data side** — add an excess-water-waste column in `build_gold_layer.py` (needs a waste threshold/rule like the 300 kW power one); (b) **frontend** — add a water-waste KPI card. Until both land, the API exposes electricity + material waste only.

### Known blocker

`/api/chat` returns `401 Unauthorized` when the provider key in `.env` is invalid/rotated. The dashboard endpoints need no key. Fix by setting a valid key for whatever `BACKEND_MODEL` points at (see [Troubleshooting](#troubleshooting)).

---

## Agents

### Supervisor

Built with `create_agent` from `langchain.agents`. Receives the user message, decides which specialist to call, invokes it as a tool, synthesises the result. `create_agent` builds a LangGraph `StateGraph` internally — `langgraph dev` can serve it directly via the `make_graph` factory in `langgraph.json`.

The supervisor carries the full middleware stack (see [Middleware](#middleware)).

### Research agent

Specialist for web search and information retrieval. Built with `create_agent`, then wrapped in a `@tool` so the supervisor can call it like any other tool. Internally it runs its own model + tool-calling loop against `web_search` and `web_fetch`.

```
supervisor
  └── research_agent_tool  (@tool that calls...)
        └── research agent  (create_agent with...)
              ├── web_search  (Tavily)
              └── web_fetch   (httpx)
```

### Ops agent

Specialist for the operational DuckDB database. Also wrapped as a `@tool` for the supervisor. Carries `HumanInTheLoopMiddleware` — interrupts only on `duckdb_execute` (write operations). Read queries pass through without approval.

```
supervisor
  └── ops_agent_tool  (@tool that calls...)
        └── ops agent  (create_agent with HumanInTheLoopMiddleware)
              ├── duckdb_list_tables
              ├── duckdb_schema
              ├── duckdb_query_checker
              ├── duckdb_query      (read — no HITL)
              └── duckdb_execute    (write — HITL interrupt)
```

**Lazy initialization:** both subagents use a `_get_agent()` pattern — `create_agent` runs on first tool call, not at import time. This prevents slow startup; `langgraph dev` imports all graph modules before serving.

---

## Tools

### Web tools (`tools/web.py`)

`web_search` calls the Tavily API if `TAVILY_API_KEY` is set. If the key is missing it returns a clear message instead of crashing:

```
[web_search] No results — TAVILY_API_KEY is not set.
Add it to .env and run: uv pip install -e ".[tavily]"
```

`web_fetch` uses `httpx` and truncates responses at 8 000 chars to protect the context window.

### DuckDB tools (`tools/duckdb.py`)

Five tools split by operation type:

| Tool | Type | Purpose |
|---|---|---|
| `duckdb_list_tables` | read | List all tables |
| `duckdb_schema` | read | Column definitions + 3 sample rows |
| `duckdb_query_checker` | validation | Validate SQL + classify as read or write |
| `duckdb_query` | read | Execute SELECT; rejects mutations; capped at 100 rows |
| `duckdb_execute` | write | Execute INSERT/UPDATE/DELETE/DROP/CREATE/ALTER; requires HITL approval |

The checker returns `"OK — read query"` or `"OK — write query"` so the agent knows which execution tool to call next. `duckdb_query` hard-rejects mutation keywords. `duckdb_execute` hard-rejects SELECT.

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

### Supervisor middleware stack

```
PIIMiddleware (api_key block)              — outermost
ModelCallLimitMiddleware (10 calls)
ModelRetryMiddleware (3 retries)
MemoryMiddleware (AGENTS.md)              — injects memory into system prompt
SummarizationMiddleware (80%, keep 6)     — compress history before model call
dev_cost_router                           — swaps model per env
RateLimitMiddleware                       — paces model calls under provider RPM
AnthropicPromptCachingMiddleware          — innermost; caches prompt before model call
```

### PII (`middleware/pii.py`)

`PIIMiddleware("api_key", detector=r"sk-...", strategy="block", apply_to_input=True, apply_to_output=True)` blocks `sk-...` API key patterns in both directions.

Email middleware is intentionally omitted. Redacting emails on input breaks legitimate requests ("draft an email to x@y.com"), and the ops agent may need to return emails from database query results.

### Fault tolerance (`middleware/retry.py`)

Each agent has its own independent middleware stack — limits and retry counters are not shared.

| Middleware | Supervisor | Research | Ops |
|---|---|---|---|
| `ModelRetryMiddleware(max_retries=3)` | yes | yes | yes |
| `ModelCallLimitMiddleware` | 10 | — | 15 |
| `ToolCallLimitMiddleware(web_search, run_limit=5)` | — | yes | — |
| `ToolCallLimitMiddleware(duckdb_execute, run_limit=3)` | — | — | yes |

`ModelCallLimitMiddleware` sits outside `ModelRetryMiddleware`. If the limit were inside the retry wrapper, a single transient failure would burn retry attempts against the call budget. With limit outside, retries are invisible to the counter.

**Rate-limit-aware retry.** `get_model_retry()` uses `retry_on` to retry **only** rate-limit / transient errors (429, 5xx, overloaded, timeout — matched on exception text, provider-agnostic), with long backoff (5 → 10 → 20 → 40 → 60 s, up to 5 attempts) to wait out the provider's window. Non-retryable failures (bad request, auth) surface immediately instead of burning attempts. Works with `RateLimitMiddleware` (proactive pacing) so a multi-call DB question completes on a free tier rather than failing with 429.

### Rate limiting (`middleware/rate_limit.py`)

Proactive throttle — the "waiting system" for provider rate limits. A single agent turn
(especially a DB question) fans into many rapid model calls; on a rate-limited provider
(e.g. Mistral free tier ~1 req/s) that burst returns HTTP 429.

`RateLimitMiddleware` blocks before each model call until a shared `InMemoryRateLimiter`
grants a token, spacing calls under the limit. One module-level limiter is shared across all
agents (supervisor + ops + research), so pacing is global. Implements both sync and async
hooks (works on `graph.invoke` and `graph.ainvoke`). Placed **inside** `ModelRetryMiddleware`
so retries are paced too. Tune with `MODEL_REQUESTS_PER_SECOND` (0 disables).

Paired with the retry middleware's rate-limit-aware backoff (below), a multi-step DB question
completes on a free tier instead of failing with 429 — at the cost of latency (calls are
serialized at the configured rate). Raise the rate on paid tiers / Anthropic for faster chat.

### Memory (`middleware/context.py`)

`MemoryMiddleware` from `deepagents.middleware` loads `AGENTS.md` into the system prompt on each run via `FilesystemBackend` (real disk paths). Teaches the supervisor routing conventions, write-safety rules, and response style.

`FilesystemBackend` is created at module level (not inside `make_graph()`) so its `Path.resolve()` call runs synchronously at import time, not inside the async ASGI event loop.

Add more sources by passing additional paths:

```python
from middleware.context import get_memory_middleware
get_memory_middleware("./AGENTS.md", "./agents/ops/AGENTS.md")
```

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

`HumanInTheLoopMiddleware` is on the ops agent only (not the supervisor). It interrupts on `duckdb_execute` calls — read queries pass through without approval. Decision options: approve, edit, reject. The interrupt bubbles up through the supervisor's checkpointer automatically.

The CLI runner (`hitl/channels/cli.py`) handles the full interrupt → approve / edit / reject loop when running outside langgraph dev:

```python
from agents.supervisor.graph import make_graph
from hitl.channels.cli import run_with_hitl

graph = make_graph()
result = run_with_hitl(graph, "What is the latest on fusion energy?", thread_id="thread-1")
```

---

## Evaluations + CI

### Datasets

`evals/datasets/v1/` contains three JSONL datasets:

| Dataset | Examples | Covers |
|---|---|---|
| `supervisor-v1` | 5 | Routing to ops/research + response synthesis |
| `research-v1` | 3 | Factual retrieval (SCADA, anomaly detection, KPIs) |
| `ops-v1` | 3 | Read-only DB queries (list tables, schema, overview) |

Each example format:
```json
{"inputs": {"messages": [{"role": "user", "content": "question"}]}, "outputs": {"answer": "reference answer"}, "metadata": {"task": "..."}}
```

The `outputs.answer` field is the reference answer used by `correctness_evaluator`. Fill these in with real expected answers before running the eval gate. Questions are placeholders — replace with real domain questions from the team.

### Evaluators

Three evaluators run on every dataset. **The evaluation infrastructure is final; the dataset Q&A pairs are not — they are placeholders until the team submits real questions and reference answers.**

| Evaluator | File | Needs model | Needs reference answer | What it checks |
|---|---|---|---|---|
| `string_contains_evaluator` | `string_match.py` | No — pure code | Yes — `outputs.answer` | Reference answer text appears in AI response |
| `relevance_evaluator` | `llm_judge.py` | Yes — LLM judge | No | Is the response relevant to the question at all |
| `correctness_evaluator` | `llm_judge.py` | Yes — LLM judge | Yes — `outputs.answer` | AI response vs reference answer (semantic) |

`string_contains_evaluator` uses `StringEvaluator` from `langsmith.evaluation` with a plain grading function — no API calls, instant, free. It checks whether the reference answer string appears literally in the AI response.

The two LLM judges use prebuilt prompts (`CORRECTNESS_PROMPT`, `ANSWER_RELEVANCE_PROMPT`) from `openevals.prompts` via `create_llm_as_judge`. They use `settings.summarization_model` as the judge model.

Examples with `"PLACEHOLDER"` in the `answer` field are skipped (`score=None`) and excluded from the gate average — so CI is not blocked by unfilled datasets.

### Running evals

```bash
python -m evals.run_evals                          # run, print results
python -m evals.run_evals --gate                   # exit 1 if avg score < 0.70
python -m evals.run_evals --dataset supervisor-v1  # single dataset
```

Eval runs are recorded in LangSmith under `LANGSMITH_PROJECT`.

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

The eval gate fails if average score across all evaluators drops below 70%. Running evals only on schedule/manually is standard practice in production — full E2E evals are too expensive to run on every commit. Requires GitHub repository secrets:

| Secret | Purpose |
|---|---|
| `LANGSMITH_API_KEY` | Fetch datasets + log results to LangSmith |
| `ANTHROPIC_API_KEY` | Model calls during eval runs (swap for Groq/Mistral key if needed) |

Set these in **Settings → Secrets and variables → Actions** on the repo.

---

## Designer questions — all answered

Original list is in `QUESTIONS_FOR_DESIGNERS.md` (repo root). Resolutions:

**Frontend designer**
1. Shapes — assumption confirmed; actual contract is the mock: `{facility_id, label}` / `{department_id, label, facility_id}`. ✅
2. `view` — dropdowns pick facility (factory view) and facility→department (department view); client sends the ids. ✅
3. `client.js` — designer added the missing fns + scope params. ✅
4. `deltas` — being removed (no history); field kept neutral for now. ✅
5. `energy_waste` — = wasted power (excess). ✅

**Data designer**
6. DB path — confirmed `data/database/operational_twin.db`. ✅
7. Names — no lookup table; dashboard shows friendly labels (backend derives `label` from id). ✅
8. Wastes — separate + excess-only. Electricity + material done; **water waste still needs a gold-layer column** (see [remaining open item](#remaining-open-item--split-waste-types-cross-team)). ⚠️
9. Refresh — data keeps arriving (multiple sensor files). `as_of`/windows anchor on `MAX(timestamp)` — already correct. Rebuild the gold DB to ingest new files. ✅
10. Existing queries — the gold-layer SQL in `build_gold_layer.py` is the source; gateway reads `gold_operational_metrics` directly. ✅

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

**`LangChainDeprecationWarning: FilesystemBackend virtual_mode default will change`**

Pass `virtual_mode=False` explicitly to `FilesystemBackend`. The default is changing in deepagents 0.6.0. `virtual_mode=False` is correct here — no virtual path routing is used, sources are real disk paths relative to `root_dir`.
