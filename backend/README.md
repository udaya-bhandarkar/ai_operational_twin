# AI Operational Twin — Backend

Multi-agent LLM system built on LangGraph / LangChain / LangSmith. A supervisor agent orchestrates two specialists — one for web research, one for querying and writing to an operational DuckDB database — with human-in-the-loop approval on write operations, a full middleware stack, and a CI eval gate.

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

Database path: `DUCKDB_PATH` in `.env` (default: `data/operational.duckdb`). DuckDB creates the file on first connect — no manual setup needed.

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

Each example: `{"inputs": {...messages...}, "outputs": {"criteria": "<word>"}, "metadata": {...}}`.

### Evaluators

| Evaluator | File | Description |
|---|---|---|
| `contains_evaluator` | `evaluators/contains.py` | Case-insensitive substring check on response |
| `exact_match_evaluator` | `evaluators/exact_match.py` | Exact string match (stripped, lowercased) |
| `correctness_evaluator` | `evaluators/llm_judge.py` | LLM-as-judge via openevals `create_llm_as_judge` |

The LLM judge uses `settings.summarization_model` with `handle_errors=True` — a failed judge call returns `score=None` rather than crashing the run. Internally openevals uses ToolStrategy (tool calling) to extract the structured score.

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

`.github/workflows/ci.yml` has three sequential stages:

| Stage | Job | What runs | When |
|---|---|---|---|
| 1 | `lint` | `ruff check` + graph import smoke test | every push / PR |
| 2 | `test` | `pytest tests/` (no API calls) | after lint |
| 3 | `eval-gate` | `evals/run_evals.py --gate` against LangSmith | push to `main` only |

Stage 3 blocks merge if average score drops below 70%. Requires GitHub repository secrets:

| Secret | Purpose |
|---|---|
| `LANGSMITH_API_KEY` | Fetch datasets + log results to LangSmith |
| `ANTHROPIC_API_KEY` | Model calls during eval runs (swap for Groq/Mistral key if needed) |

Set these in **Settings → Secrets and variables → Actions** on the repo.

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
