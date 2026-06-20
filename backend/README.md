# AI Operational Twin — Backend

Multi-agent LLM system built on LangGraph / LangChain / LangSmith.

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
uv pip install -e ".[all-providers,tavily]"
uv pip install "langgraph-cli[inmem]"
```

Or install only the provider you need:

```bash
uv pip install -e .              # Anthropic only (default)
uv pip install -e ".[groq]"      # adds langchain-groq
uv pip install -e ".[mistral]"   # adds langchain-mistralai
uv pip install -e ".[tavily]"    # adds tavily web search
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

---

## Project Structure

```
backend/
├── langgraph.json              # Graph entrypoint (points to make_graph factory)
├── pyproject.toml              # Dependencies
├── .env.example                # Environment variable template
│
├── config/
│   └── settings.py             # Pydantic Settings — reads from .env
│
├── agents/
│   ├── supervisor/             # Orchestrator: routes to specialists, synthesises results
│   │   ├── graph.py            # make_graph() factory — create_agent with all specialist tools
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
│   └── duckdb.py               # 5 DuckDB tools (list, schema, checker, query, execute)
│
├── middleware/
│   ├── pii.py                  # PIIMiddleware — API key blocking (input + output)
│   └── retry.py                # ModelRetryMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
│
└── hitl/
    └── channels/
        └── cli.py              # CLI runner: streams graph, handles interrupts
```

---

## Phase 1 — Core Graph

Phase 1 establishes the full multi-agent skeleton end-to-end. Every subsequent phase adds to this foundation without restructuring it.

### What is built

**Supervisor agent**

Built with `create_agent` from `langchain.agents`. Receives the user message, decides which specialist to call, invokes it as a tool, synthesises the result. `create_agent` builds a LangGraph `StateGraph` internally — `langgraph dev` can serve it directly via the `make_graph` factory in `langgraph.json`.

**Research agent (agent-as-tool pattern)**

A specialist for web search and information retrieval. Also built with `create_agent`, then wrapped in a `@tool` so the supervisor can call it like any other tool. Internally it runs its own model + tool-calling loop against `web_search` and `web_fetch`.

```
supervisor
  └── research_agent_tool  (@tool that calls...)
        └── research agent  (create_agent with...)
              ├── web_search  (stub in Phase 1)
              └── web_fetch   (stub in Phase 1)
```

**Provider-agnostic model**

Pass the model name as a string directly to `create_agent`. Switching providers is one `.env` change — no code changes.

**HITL infrastructure**

`hitl/channels/cli.py` has a full interrupt → approve / edit / reject loop ready for Phase 2's `HumanInTheLoopMiddleware`.

**LangSmith tracing**

Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`. Traces appear in LangSmith Studio automatically.

### What is NOT in Phase 1

| Feature | Phase |
|---|---|
| Real web search (Tavily) | 2 |
| Ops agent (DuckDB read/write) | 2 |
| HITL approval on tool calls | 2 |
| PII middleware | 2 |
| Postgres checkpointer | 3 |
| MCP server integration | 3 |
| Summarization + prompt caching | 3 |
| Dynamic model selection | 3 |
| Evaluations + CI gate | 4 |
| Production deployment | 5 |

---

## Phase 2 — Web Search, Ops Agent, HITL, PII

### What is built

**Real web search (Tavily) with graceful degradation**

`tools/web.py` calls the Tavily API if `TAVILY_API_KEY` is set. If the key is missing, `web_search` returns a clear message instead of crashing:

```
[web_search] No results — TAVILY_API_KEY is not set.
Add it to .env and run: uv pip install -e ".[tavily]"
```

To enable real search:

```bash
uv pip install -e ".[tavily]"
# then in .env:
TAVILY_API_KEY=tvly-...
```

`web_fetch` uses `httpx` and truncates responses at 8 000 chars to protect the context window.

**Ops agent — DuckDB read/write**

`agents/ops/graph.py` is a specialist for the operational DuckDB database. It has five tools split by operation type:

| Tool | Type | Purpose |
|---|---|---|
| `duckdb_list_tables` | read | List all tables |
| `duckdb_schema` | read | Column definitions + 3 sample rows |
| `duckdb_query_checker` | validation | Validate SQL + classify as read or write |
| `duckdb_query` | read | Execute SELECT; rejects mutations; capped at 100 rows |
| `duckdb_execute` | write | Execute INSERT/UPDATE/DELETE/DROP/CREATE/ALTER; requires HITL approval |

The checker returns `"OK — read query"` or `"OK — write query"` so the agent knows which execution tool to call next. `duckdb_query` hard-rejects mutation keywords. `duckdb_execute` hard-rejects SELECT.

Database path: `DUCKDB_PATH` in `.env` (default: `data/operational.duckdb`). DuckDB creates the file on first connect — no manual setup needed.

**HITL on write operations**

`HumanInTheLoopMiddleware` is on the ops agent (not the supervisor). It interrupts only on `duckdb_execute` — reads pass through without approval. Decision options: approve, edit, reject. Interrupt bubbles up through the supervisor's checkpointer automatically.

**PII middleware**

`middleware/pii.py` uses `PIIMiddleware` from `langchain.agents.middleware` on the supervisor:

- `PIIMiddleware("api_key", detector=r"sk-...", strategy="block", apply_to_input=True, apply_to_output=True)` — blocks `sk-...` API key patterns in both directions

Email middleware is intentionally omitted. Redacting emails on input breaks legitimate requests ("draft an email to x@y.com"), and the ops agent may need to return emails from database query results.

Requires `langchain>=1.3.2` for `apply_to_output` support.

**Fault tolerance middleware**

`middleware/retry.py` provides three protection layers. Each agent has its own independent middleware stack — limits and retry counters are not shared between agents.

| Middleware | Supervisor | Research | Ops |
|---|---|---|---|
| `ModelRetryMiddleware(max_retries=3)` | yes | yes | yes |
| `ModelCallLimitMiddleware(run_limit=10/15)` | 10 | — | 15 |
| `ToolCallLimitMiddleware(web_search, run_limit=5)` | — | yes | — |
| `ToolCallLimitMiddleware(duckdb_execute, run_limit=3)` | — | — | yes |

**Isolation:** the supervisor's `ModelCallLimit(10)` only counts the supervisor's own model calls. When the supervisor calls `ops_agent_tool` or `research_agent_tool`, those are tool calls from the supervisor's perspective — the subagent's internal model calls are counted by the subagent's own limit independently.

**Middleware order:** `ModelCallLimitMiddleware` sits outside `ModelRetryMiddleware` on every agent. If the limit were inside the retry wrapper, a single transient API failure would burn retry attempts against the call budget — 3 retries on one bad response would consume 3 of the 10 allowed calls. With limit outside, retries are invisible to the counter: one logical call counts as one regardless of how many retry attempts happen internally.

**Lazy agent initialization**

`create_agent(...)` is called inside `_get_agent()` with a module-level `global`, not at import time. This prevents slow startup — `langgraph dev` imports all modules at boot, and creating agents at import time adds ~5s per agent to startup.

### Updated structure

```
backend/
├── tools/
│   ├── web.py          # Tavily + httpx (graceful degradation)
│   └── duckdb.py       # 5 tools: list, schema, checker, query (read), execute (write+HITL)
├── agents/
│   └── ops/            # NEW — DuckDB specialist with HumanInTheLoopMiddleware
├── middleware/
│   ├── pii.py          # API key blocking on supervisor
│   └── retry.py        # NEW — ModelRetryMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
└── config/
    └── settings.py     # + tavily_api_key, duckdb_path
```

### Install Phase 2 deps

```bash
uv pip install -e .            # picks up duckdb + httpx from core deps
uv pip install -e ".[tavily]"  # optional — only needed for real web search
```

---

## Using the CLI runner directly

```python
from agents.supervisor.graph import make_graph
from hitl.channels.cli import run_with_hitl

graph = make_graph()
result = run_with_hitl(graph, "What is the latest on fusion energy?", thread_id="thread-1")
```

---

## Switching models

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

## Architecture notes

**`create_agent` is a LangGraph graph**

`create_agent` from `langchain.agents` returns a compiled `LangGraph StateGraph` internally. That is why `langgraph dev` can serve it — it IS a LangGraph graph, it just doesn't require you to build the nodes/edges manually.

**Pass model as string, not pre-instantiated**

```python
# Correct
create_agent(model=settings.backend_model, ...)

# Avoid — pre-instantiated model attaches extra metadata
# that LangSmith's serializer can't walk cleanly
create_agent(model=init_chat_model(settings.backend_model), ...)
```

**Checkpointer**

`langgraph dev` / Agent Server injects its own checkpointer automatically. Do not pass one to `create_agent` when serving via the dev server. For direct CLI use, pass `checkpointer=MemorySaver()` to `create_agent`.

**Lazy agent initialization**

Subagents (`research`, `ops`) use a `_get_agent()` pattern — `create_agent` runs on first tool call, not at import. Calling `create_agent` at module level adds startup time because `langgraph dev` imports all graph modules before serving.

**LANGSMITH_TRACING**

Set `LANGSMITH_TRACING=true`. Earlier versions of `langsmith`/`langchain` had a bug where enabling this alongside `langgraph dev` caused a `maximum recursion depth exceeded` error (two tracers conflicting). This is fixed in `langchain>=1.3.2`.

---

## Troubleshooting

**`python-dotenv could not parse statement at line N`**

Non-ASCII characters in `.env` comment lines (`→`, `──`). Replace with ASCII (`->`, `-`).

**`ModuleNotFoundError` when running `langgraph dev`**

`langgraph` CLI is using a different Python than where your packages are installed. Install `langgraph-cli[inmem]` into the same venv as your project, then run `langgraph dev` with the venv active.

**`401 Unauthorized` from provider API**

API key in `.env` is missing, wrong, or was rotated. Check the key matches the provider set in `BACKEND_MODEL`.

**`ValueError: graph includes a custom checkpointer`**

Passed `checkpointer=` to `create_agent` while also running via `langgraph dev`. Remove the checkpointer argument — the dev server injects its own.

**Graph import slow (>5s warning in logs)**

`create_agent(...)` called at module level. Move it inside `_get_agent()` with a `global` so it only runs on first use.
