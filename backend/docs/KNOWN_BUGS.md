# Known Bugs & Issues — Backend

Found in a code review on 2026-09-28 against the working tree (uncommitted `graph.py` hybrid
StateGraph). Ordered by severity. Each entry: where, what breaks, suggested fix.

---

## Correctness

### B1. Agent node slices history by length — breaks when summarization fires
- **Where:** `agents/supervisor/graph.py:213-216` (`agent_node`)
- **What:** The `create_agent` graph is called as a plain function (`agent.ainvoke`) and the
  node returns `result["messages"][len(state["messages"]):]`, assuming the inner agent only
  *appends*. `SummarizationMiddleware` *replaces* old messages with a summary, so the inner
  list shrinks and the slice returns the wrong messages (lost or duplicated). The outer state
  also never sees the summarization, so history keeps growing and summarization re-runs every
  turn once a checkpointer is added.
- **Fix:** Mount the compiled agent directly as a subgraph node — `add_node("agent", agent)` —
  so both graphs share the `messages` channel and its `add_messages` reducer (which understands
  `RemoveMessage`). Remove the manual slicing.

### B2. No checkpointer on the API path — no memory, HITL broken
- **Where:** `agents/supervisor/graph.py:228` (`graph.compile()`), `api/chat.py`
- **What:** `make_graph()` compiles without a checkpointer. `/api/chat` generates a
  `thread_id` but nothing persists, so every request starts a fresh conversation. When
  `duckdb_execute` triggers the HITL interrupt, `/api/chat` ignores `__interrupt__`, returns
  whatever the last message is, and there is no resume endpoint. Approvals only work in
  `langgraph dev` (which injects its own checkpointer).
- **Fix:** Compile with a checkpointer in the gateway (`AsyncPostgresSaver`; `InMemorySaver`
  for dev). Detect `__interrupt__` in the result and return it to the frontend; add
  `POST /api/chat/resume` that calls `ainvoke(Command(resume=decision), config)`.

### B3. deepagents `MemoryMiddleware` injects irrelevant, contradictory instructions — ✅ FIXED
_Fixed on branch `chore/remove-agents-md`: AGENTS.md removed (its 2 unique rules merged into
`system.txt`), middleware and `deepagents` dependency dropped._
- **Where:** `middleware/context.py:13`, used in `graph.py:87`
- **What:** Besides AGENTS.md, the middleware appends its default `MEMORY_SYSTEM_PROMPT`
  (`deepagents/middleware/memory.py:105`, ~1k tokens) on every model call. It tells the agent
  to save learnings with an `edit_file` tool the agent does not have, to ask the user rather
  than assume, and includes Slack/Google-account examples. This costs tokens on every call
  and conflicts with the system prompt's "give the data first" rules.
- **Fix:** Drop the middleware. Append AGENTS.md to the system prompt at build time (or merge
  it into `prompts/system.txt` — it largely duplicates it). If kept, pass
  `system_prompt="{agent_memory}"` to suppress the default guidelines.

### B4. `verify` node — false positives and a persistent fake user message
- **Where:** `agents/supervisor/graph.py:151-193`
- **What:** (a) Derived figures (sums, differences — which the system prompt's own example
  asks for: "₹1,758.85 above the next machine") never appear verbatim in tool output, so
  correct answers get flagged, costing an extra model round trip. (b) The correction is
  appended as a `HumanMessage`, so it becomes permanent thread history once a checkpointer
  exists, and the frontend/history will show a message the user never sent.
- **Fix:** (a) Tolerate figures derivable as sum/difference of corpus figures, or restrict the
  check to figures presented as retrieved values. (b) Put the correction in a separate state
  key (or a `SystemMessage`) consumed by the next agent call and cleared afterwards.

### B5. CLI HITL fallback uses a non-existent attribute
- **Where:** `hitl/channels/cli.py:24` — `graph.bound.compile(...)`
- **What:** `CompiledStateGraph` exposes `.builder`, not `.bound` (verify against installed
  langgraph). The fallback path for running without a checkpointer would raise
  `AttributeError`.
- **Fix:** `graph.builder.compile(checkpointer=MemorySaver())`, or have `make_graph` accept a
  `checkpointer` argument.

### B6. DuckDB lock / configuration conflicts
- **Where:** `tools/duckdb.py:36-42`, `api/db.py:25`
- **What:** DuckDB permits one writer process per file. If the data pipeline / sensor stream
  holds the write lock, every `read_only=True` connect fails. Within one process, opening a
  read-write connection (`duckdb_execute`) while read-only connections to the same file are
  open can fail with a "different configuration" error.
- **Fix:** One shared connection (or pool) per process with per-request cursors; or route
  writes through a single owner. Add a concurrency test.

### B7. `.env` resolution depends on the working directory
- **Where:** `config/settings.py:27` (`dotenv_values(".env")`), `:48` (`env_file=".env"`)
- **What:** `load_dotenv` uses an absolute path, but these two resolve relative to CWD.
  `.env.example` sets a relative `DUCKDB_PATH`, which overrides the absolute default and
  points somewhere different depending on where the process is launched.
- **Fix:** Use the same absolute backend path everywhere; resolve `duckdb_path` relative to
  the backend dir in a validator.

---

## Security

### S1. DuckDB "reads" can read/write the local filesystem — ✅ FIXED
_Fixed: `db/connection.py` (external access off + config locked on every connection),
allowlist classification in `tools/duckdb.py`. Tests in `tests/test_security.py`._
- **Where:** `tools/duckdb.py` (`classify_sql`, `_read_conn`)
- **What:** `SELECT * FROM read_text('.env')` is a valid read — passes AST classification and
  runs on the read-only connection. `COPY ... TO`, `ATTACH`, `INSTALL`/`LOAD` likely parse as
  `exp.Command` and are classified "read". Combined with indirect prompt injection via
  `web_fetch`, this is a secret-exfiltration path (PII middleware only matches `sk-...`).
- **Fix:** Connect with `config={"enable_external_access": False, "lock_configuration": True}`.
  Switch classification to an allowlist (only `Select` / `Union` / CTE-over-`Select`) instead
  of a write denylist. Add tests for each bypass.

### S2. SSRF in `web_fetch` — ✅ FIXED
_Fixed in `tools/web.py`: public-IP check per redirect hop, streamed 1 MB cap, text-only
content types, HTML→text. Residual: DNS rebinding between check and connect. Tests in
`tests/test_web.py`._
- **Where:** `tools/web.py:57-69`
- **What:** Fetches any URL — `localhost`, `169.254.169.254`, internal hosts. Body is fully
  read before the 8k truncation.
- **Fix:** Resolve DNS and reject private/loopback/link-local ranges (re-check after
  redirects); stream with a byte cap. Extract text (trafilatura/html2text) instead of returning
  raw HTML.

### S3. API has no auth, no request rate limit, raw 500s
- **Where:** `api/chat.py`, `api/app.py`
- **Fix:** API key or JWT dependency; per-client rate limit; exception handler returning a
  safe error body.

---

## Hygiene / dead code

- Unused settings: `hitl_enabled`, `hitl_channel`, `eval_budget_usd` (only asserted in tests).
- Unused functions: `middleware/retry.py:get_supervisor_limits`, `tools/mcp_client.py:get_mcp_tools`.
- Stale naming/docstrings: `agents/supervisor/`, graph name `supervisor` in `langgraph.json`,
  rate-limit docstring mentions supervisor/ops/research agents — it is a single agent now.
- `AnthropicPromptCachingMiddleware` added unconditionally; warns on every call with Mistral.
- `dev_cost_router` is async-only → forces `ainvoke` everywhere (root cause of the background
  event-loop workaround in `evals/run_evals.py`).
- `evals/evaluators/contains.py`, `exact_match.py` are empty; `evals/JsonForQA.rtf` is clutter.
- No lockfile (`uv.lock`); loose `>=` pins, so CI is not reproducible.
- `.github/workflows/evals.yml` comment says nightly, but only `workflow_dispatch` is set.
- `api/app.py` uses deprecated `@app.on_event` — move to `lifespan`.
- `CLAUDE.md` still says "architecture planning only, no code" — stale.
- `docs/IMPROVEMENTS.md` 1.7 ("sync tools block the event loop") is likely wrong: LangChain runs
  sync tools via `run_in_executor` under `ainvoke`, and FastAPI runs `def` endpoints in a
  threadpool. Measure before acting on it.

## Evals

- `string_contains` requires the whole reference string verbatim — fails on formatting
  (`14585.16 kw` vs `₹14,585.16`). Replace with numeric extraction + tolerance.
- Judge model defaults to the agent's own model (self-grading bias).
- Gate averages relevance + correctness together — easy relevance masks weak correctness.
  Gate per metric, per dataset, against a baseline experiment.
