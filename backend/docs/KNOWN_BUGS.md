# Known Bugs & Issues — Backend

Open items first, ordered by severity; fixed items are logged at the end. Each open entry:
where, what breaks, suggested fix. First compiled in a code review on 2026-09-28.

---

## Open — correctness

### B4. `verify` node — false positives and a persistent fake user message
- **Where:** `agents/supervisor/graph.py` (`verify`)
- **What:** (a) Derived figures (sums, differences, unit conversions) never appear verbatim in
  tool output, so correct answers get flagged, costing an extra model round trip. (b) The
  correction is appended as a `HumanMessage`, so it becomes permanent thread history (the
  checkpointer persists it) and looks like a message the user sent.
- **Fix:** (a) Tolerate figures derivable as sum/difference of corpus figures, or restrict the
  check to figures presented as retrieved values. (b) Put the correction in a separate state
  key (or a `SystemMessage`) consumed by the next agent call and cleared afterwards. The
  rebuild may replace this node with a grader node anyway.

### B6. DuckDB lock / configuration conflicts
- **Where:** `db/connection.py`, `tools/duckdb.py`
- **What:** DuckDB permits one writer *process* per file — if another process holds the write
  lock, every `read_only=True` connect fails. Within one process, a read-write connection
  (`duckdb_execute`) cannot be opened while read-only connections to the same file are open
  ("different configuration" error). All connections now share one hardened config, but the
  read-only vs read-write split remains.
- **Fix:** One shared connection (or pool) per process with per-request cursors, or route
  writes through a single owner. Add a concurrency test.

### B7. `.env` resolution depends on the working directory
- **Where:** `config/settings.py` (`dotenv_values(".env")`, `env_file=".env"`)
- **What:** `load_dotenv` uses an absolute path, but these two resolve relative to CWD, and a
  relative `DUCKDB_PATH` resolves against wherever the process was launched.
- **Fix:** Use the absolute backend path everywhere; resolve relative paths against the backend
  dir in a validator.

---

## Open — security

### S3. API has no auth or request rate limit — ⚠️ PARTIAL
_Done: chat errors return a generic 500 (detail logged server-side)._
- **Where:** `api/chat.py`, `api/app.py`
- **Fix:** API key (constant-time compare) or JWT dependency on `/api` routes; per-client rate
  limit.

### S4. DNS rebinding in `web_fetch` (residual)
- **Where:** `tools/web.py` (`check_url` → connect)
- **What:** The host is resolved and checked, then httpx resolves it again to connect; a
  hostile DNS server can answer differently the second time.
- **Fix:** Connect to the vetted IP (custom transport pinning the resolved address, with SNI /
  Host header preserved).

---

## Open — hygiene

- Unused settings: `hitl_enabled`, `hitl_channel`, `eval_budget_usd` (only asserted in tests).
- `tools/mcp_client.py:get_mcp_tools` is never called — MCP tools are not wired into the agent.
- Stale naming: folder `agents/supervisor/` and graph name `supervisor` in `langgraph.json` —
  it is a single general agent (rename during the rebuild).
- `AnthropicPromptCachingMiddleware` is added unconditionally; warns on every call with
  non-Anthropic models.
- `dev_cost_router` is async-only → forces `ainvoke` everywhere (root cause of the background
  event-loop workaround in `evals/run_evals.py`).
- No lockfile (`uv.lock`); loose `>=` pins, so CI is not reproducible.
- `.github/workflows/evals.yml` comment says nightly, but only `workflow_dispatch` is set.
- `pyproject.toml` package name is still `ai-operational-twin-backend`.

## Open — evals (deferred rebuild)

- No datasets yet — the MVP sets are archived (`docs/archive/mvp/eval-datasets/`).
- `string_contains` requires the whole reference string verbatim — fails on formatting
  (`14585.16` vs `14,585.16`). Replace with numeric extraction + tolerance.
- Judge model defaults to the agent's own model (self-grading bias).
- Gate averages relevance + correctness together — easy relevance masks weak correctness.
  Gate per metric, per dataset, against a baseline experiment.

---

## Fixed log

| ID | Issue | Fix |
|---|---|---|
| B1 | Agent node sliced history by length; broke when summarization rewrote history | `history_delta`: append → new tail; rewrite → `RemoveMessage(REMOVE_ALL_MESSAGES)` + full history. Note: "mount as subgraph" was tested and does **not** propagate removals. |
| B2 | No checkpointer on the API; no thread memory; HITL interrupts ignored | SQLite checkpointer in API lifespan; `awaiting_approval` status; `/api/chat/resume`; 409 while paused. Also: `verify_attempts` now reset per turn. |
| B3 | deepagents `MemoryMiddleware` injected ~1k tokens of irrelevant memory guidelines per call | AGENTS.md merged into `system.txt`; middleware + `deepagents` dependency removed |
| B5 | CLI broken (`.bound`, sync stream over async nodes, old interrupt format) | Async rewrite; `python -m hitl.channels.cli` |
| S1 | Agent SQL could read/write local files (`read_text`, `COPY`, `ATTACH`, `INSTALL`) | External access off + config locked on all connections; allowlist classification |
| S2 | SSRF in `web_fetch` | Public-IP check per redirect hop, byte cap, text-only, HTML → text |
| — | Deprecated `@app.on_event` | FastAPI `lifespan` |
| — | Empty evaluators, clutter files, stale `CLAUDE.md`, multi-agent leftovers in docstrings, domain-specific prompt / API / datasets | Removed, rewritten or archived in the generalization pass |
