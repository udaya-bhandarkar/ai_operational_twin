# General-Purpose AI Agent — Backend

A general-purpose, tool-using AI agent built on **LangGraph** and **LangChain**, with
human-in-the-loop approvals, durable conversation threads, defense-in-depth tool security,
provider-agnostic model selection, and LangSmith tracing/evals.

- **Graph:** a custom LangGraph `StateGraph` places deterministic nodes (input guardrail,
  numeric grounding check) around an agentic `create_agent` core.
- **Tools:** web search + safe web fetch; an optional SQL toolset over any DuckDB database
  (reads free, writes gated by human approval); MCP client for external tool servers.
- **Interfaces:** FastAPI gateway (`/api/chat`, `/api/chat/resume`), terminal CLI, and
  LangGraph Studio via `langgraph dev`.

> **Status:** active rebuild toward an explicit LangGraph architecture (subgraphs,
> `interrupt()`, parallel fan-out, streaming). See [`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md)
> for the roadmap and [`docs/KNOWN_BUGS.md`](docs/KNOWN_BUGS.md) for open issues.
>
> **Origin:** this began as an MVP agent for a specific operational dataset. Domain-specific
> code, docs and eval sets were removed or archived in [`docs/archive/mvp/`](docs/archive/mvp/).

---

## Quick start

```bash
cd backend
uv venv .venv --python 3.11
.venv\Scripts\activate                     # Windows; source .venv/bin/activate elsewhere
uv pip install -e ".[dev,tavily]" "langgraph-cli[inmem]"
cp .env.example .env                       # then set a provider key + BACKEND_MODEL
```

Run it one of three ways:

```bash
python -m hitl.channels.cli "What changed in the latest Python release?"   # terminal
python -m api.app                                                            # HTTP API on :8000
langgraph dev                                                                # LangGraph Studio
```

Optional extras: `.[groq]`, `.[mistral]`, `.[tavily]` (web search), `.[mcp]` (MCP tools),
`.[all-providers]`.

> Install `langgraph-cli` into the same venv as the project — a CLI from another Python
> (e.g. Anaconda base) won't see the project packages (`ModuleNotFoundError`).

---

## Architecture

```
START → guardrail → agent → verify → END
          │           ▲       │
          └→ END       └───────┘   (one bounded retry if figures aren't grounded)
```

| Node | Kind | Role |
|---|---|---|
| `guardrail` | deterministic | Rejects empty / oversized input and attempts to spoof the untrusted-content markers. Resets the per-turn retry budget. Un-promptable. |
| `agent` | agentic | `create_agent` + middleware stack + configured tools. Returns only the history delta (`history_delta`), or a full replacement when summarization rewrote history. |
| `verify` | deterministic | Numeric grounding: figures in the answer must appear in this turn's tool output. Ungrounded → one corrective retry, then surface. |

**Why one agent, not supervisor + sub-agents.** The project started as a supervisor routing to
specialist sub-agents. Each sub-agent is its own reasoning loop, so every question paid for two
loops (~2× model calls), tripping rate limits and double-summarising results. Collapsing to one
agent with all tools attached halved the calls. Multi-agent patterns return in the rebuild where
they earn their cost (parallel fan-out, isolated specialists) — benchmarked against this baseline.

**Configuration-driven toolset.** `_toolset()` in `graph.py` attaches web tools always, and the
SQL toolset plus its prompt section (`prompts/sql.txt`) only when `DUCKDB_PATH` is set.

---

## Tools

| Tool | Kind | Notes |
|---|---|---|
| `web_search` | read | Tavily; returns a helpful message when `TAVILY_API_KEY` is unset |
| `web_fetch` | read | SSRF-guarded, 1 MB streamed cap, HTML → visible text, 8k-char output |
| `duckdb_list_tables` / `duckdb_schema` | read | Schema discovery (allowlisted, parameterized) |
| `duckdb_query` | read | Query statements only; 100-row cap |
| `duckdb_query_checker` | validation | Classify + validate a statement before a write |
| `duckdb_execute` | **write** | DML/DDL only; **pauses for human approval** |
| MCP tools | varies | `tools/mcp_client.py` — ships empty; add servers to `MCP_SERVERS` |

SQL tools are attached only when `DUCKDB_PATH` points at a DuckDB file.

---

## Security

Defense-in-depth aligned with the **OWASP Top 10 for LLM Applications**:

- **Text-to-SQL hardening** (`tools/duckdb.py`) — statements are classified by **AST**
  (`sqlglot`) against **allowlists**: a read only if it is a known query type
  (SELECT/UNION/DESCRIBE/SHOW/…), a write only if known DML/DDL; anything else (`COPY`,
  `ATTACH`, `INSTALL`, `SET`, `PRAGMA`, …) is refused. CTE-wrapped writes
  (`WITH t AS (…) DELETE …`) are caught; multi-statement payloads are rejected.
- **Hardened DB connections** (`db/connection.py`) — DuckDB external access disabled and
  configuration locked on every connection: SQL cannot read local files (`read_text('.env')`),
  write them (`COPY … TO`), attach databases or install extensions. Reads use `read_only=True`.
- **Indirect prompt-injection defense** (`tools/web.py`) — web content wrapped in
  `<<<EXTERNAL_CONTENT>>>` markers labelled untrusted; marker spoofing stripped; the guardrail
  rejects user input containing the markers; the system prompt forbids following embedded
  instructions.
- **SSRF protection** (`tools/web.py`) — http(s) only; every redirect hop must resolve
  exclusively to public IPs (loopback, private, link-local incl. cloud metadata
  `169.254.169.254`, reserved, multicast and IPv4-mapped IPv6 are refused).
- **Human approval for state changes** — writes interrupt the graph until a human approves,
  edits or rejects; edits cannot switch the tool under review.
- **Output checks** — API-key pattern blocking (PII middleware) and numeric grounding.

Residual risks are tracked in [`docs/KNOWN_BUGS.md`](docs/KNOWN_BUGS.md) (e.g. DNS rebinding,
no API auth yet).

---

## Middleware stack

```
PIIMiddleware (api_key block)              — outermost
ModelCallLimit (15) + ToolCallLimit (duckdb_execute=3, web_search=5)
ModelRetryMiddleware (rate-limit-aware)
SummarizationMiddleware (80% context, keep 6)
dev_cost_router                            — budget model in dev
RateLimitMiddleware                        — paces calls under provider RPM
HumanInTheLoopMiddleware                   — interrupts on duckdb_execute
AnthropicPromptCachingMiddleware           — innermost
```

- **Retry** (`middleware/retry.py`) retries only rate-limit / transient errors (429, 5xx,
  overloaded, timeout) with 5 → 60 s backoff; auth / bad-request errors surface immediately.
  Call limits sit outside retry so retries don't consume the budget.
- **Rate limiting** (`middleware/rate_limit.py`) — a shared `InMemoryRateLimiter` paces model
  calls *before* they happen (`MODEL_REQUESTS_PER_SECOND`, 0 disables).
- **Summarization** (`middleware/summarization.py`) — compresses history at 80% of the model's
  context, keeping the 6 latest messages; uses `SUMMARIZATION_MODEL`.
- **Cost routing** (`middleware/dynamic_model.py`) — in `BACKEND_ENV=dev`, routes to
  `SUMMARIZATION_MODEL` when it is a cheaper model from the same provider.
- **Prompt caching** (`middleware/caching.py`) — Anthropic cache breakpoints (5-min TTL); no-op
  for other providers.
- **Prompts** — `agents/supervisor/prompts/system.txt` (general) + `sql.txt` (when a DB is set).

---

## API

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/chat` | `{message, thread_id?}` | `{reply, thread_id, status, approval}` |
| POST | `/api/chat/resume` | `{thread_id, decisions: [...]}` | same shape |
| GET | `/health` | — | `{status}` |

- Reuse `thread_id` for follow-ups — threads persist in the checkpointer.
- `status: "complete"` → answer in `reply`. `status: "awaiting_approval"` → the agent wants to
  run a state-changing tool; `approval.actions` lists the pending calls and `reply` holds a
  readable summary.
- Resume with one decision per action: `{"type": "approve"}`,
  `{"type": "edit", "args": {...}}` (tool name stays fixed), or `{"type": "reject", "message"?}`.
- `409` — new message on a thread awaiting approval, or resume with nothing pending.
  `422` — wrong number of decisions / disallowed decision / edit without args.
  `500` — agent failure (generic message; details in server log).

CORS: `CORS_ORIGINS` / `CORS_ORIGIN_REGEX`; any localhost origin is allowed when `BACKEND_ENV=dev`.

---

## Persistence & memory

- **API gateway** — `api/app.py` opens an `AsyncSqliteSaver` for the app's lifetime
  (`CHECKPOINT_DB`, default `backend/.state/checkpoints.sqlite`, git-ignored; `:memory:` for
  ephemeral). Threads and paused approvals survive restarts.
- **CLI** — in-memory checkpointer per process.
- **`langgraph dev` / `langgraph up`** — the runtime injects its own checkpointer (in-memory /
  Postgres), so `make_graph()` (the `langgraph.json` entrypoint) compiles without one;
  `build_graph(checkpointer=...)` is used everywhere else.
- **History compression** — when `SummarizationMiddleware` rewrites history inside the agent,
  `history_delta` replaces the outer persisted history to match, so long threads stay bounded.

---

## Human-in-the-loop

`HumanInTheLoopMiddleware` interrupts on `duckdb_execute`; reads and web calls pass through.
The interrupt pauses the outer graph with the thread checkpointed until a decision arrives:

- **API** — `awaiting_approval` response, then `/api/chat/resume`.
- **CLI** — prompts approve / edit / reject per pending action:

```bash
python -m hitl.channels.cli "Add a row to the tasks table"   # one question
python -m hitl.channels.cli                                   # interactive thread
```

---

## Configuration

Settings live in `config/settings.py` (Pydantic), read from `backend/.env` over per-environment
yaml defaults (`config/environments/<BACKEND_ENV>.yaml`).

| Variable | Default | Purpose |
|---|---|---|
| `BACKEND_MODEL` | `anthropic:claude-opus-4-8` | Main model. `anthropic:` / `groq:` prefix, none = Mistral |
| `ANTHROPIC_API_KEY` / `GROQ_API_KEY` / `MISTRAL_API_KEY` | — | Key matching `BACKEND_MODEL` (startup warns if missing) |
| `SUMMARIZATION_MODEL` | = `BACKEND_MODEL` | Cheaper same-provider model: summarization + dev routing |
| `BACKEND_ENV` | `dev` | `dev` enables localhost CORS + budget routing |
| `TAVILY_API_KEY` | — | Web search |
| `DUCKDB_PATH` | — | DuckDB file for the SQL toolset; empty disables it |
| `CHECKPOINT_DB` | `backend/.state/checkpoints.sqlite` | API thread store; `:memory:` for ephemeral |
| `MODEL_REQUESTS_PER_SECOND` | `2.0` | Model-call pacing; `0` disables |
| `CORS_ORIGINS` / `CORS_ORIGIN_REGEX` | — | Allowed browser origins |
| `LANGSMITH_API_KEY` / `LANGSMITH_TRACING` / `LANGSMITH_PROJECT` | — | Tracing + evals |

Switching models needs no code change — set `BACKEND_MODEL`, e.g.
`anthropic:claude-haiku-4-5`, `groq:llama-3.3-70b-versatile`, `mistral-large-latest`.

---

## Testing, evals & CI

- **Unit + integration tests** (`tests/`, no API calls): SQL classification and DB lockdown,
  SSRF and HTML extraction, guardrail / verify, thread memory, HITL approve / edit / reject,
  API status codes. A scripted fake chat model (`tests/fakes.py`) drives the real graph and
  middleware stack. Run: `pytest`.
- **Evals** (`evals/`) — LangSmith `evaluate()` with code + LLM-judge evaluators; every
  `evals/datasets/<name>.jsonl` becomes a LangSmith dataset (`scripts/upload_datasets.py`).
  **Being rebuilt for the general agent** — the MVP's domain datasets are archived; see
  [`evals/README.md`](evals/README.md).
- **CI** (`.github/workflows/ci.yml`) — ruff + graph import smoke test + pytest on every push/PR.
  `evals.yml` runs the eval gate manually (`workflow_dispatch`) — it costs tokens.

---

## Project structure

```
backend/
├── langgraph.json              # make_graph entrypoint for langgraph dev / Studio
├── pyproject.toml
├── .env.example
├── agents/supervisor/
│   ├── graph.py                # StateGraph: guardrail → agent → verify; build_graph / make_graph
│   └── prompts/                # system.txt (general) + sql.txt (when DUCKDB_PATH is set)
├── api/
│   ├── app.py                  # FastAPI app, lifespan (checkpointer), CORS
│   └── chat.py                 # /api/chat + /api/chat/resume
├── config/                     # settings.py + environments/{dev,staging,prod}.yaml
├── db/connection.py            # hardened DuckDB connections
├── hitl/channels/cli.py        # terminal chat with approval prompts
├── middleware/                 # pii, retry + limits, rate_limit, summarization, dynamic_model, caching
├── tools/                      # web.py, duckdb.py, mcp_client.py
├── evals/                      # run_evals.py, evaluators/, datasets/ (rebuild pending)
├── scripts/upload_datasets.py
├── tests/                      # pytest suite + fakes.py (scripted model)
└── docs/                       # IMPROVEMENTS.md, KNOWN_BUGS.md, archive/mvp/
```

---

## Notes & troubleshooting

- **`create_agent` is a LangGraph graph** — LangChain's prebuilt agent compiles to a LangGraph
  `StateGraph`; this project wraps it in a hand-built outer graph.
- **`ValueError: graph includes a custom checkpointer`** under `langgraph dev` — the runtime
  injects its own; use `make_graph()` there and `build_graph(checkpointer=...)` elsewhere.
- **`401` from the provider** — key missing or doesn't match `BACKEND_MODEL`'s provider.
- **`429` / slow replies on free tiers** — expected; calls are paced and retried. Raise
  `MODEL_REQUESTS_PER_SECOND` on paid tiers.
