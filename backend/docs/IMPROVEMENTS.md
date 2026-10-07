# Improvement Roadmap — General-Purpose LangGraph Agent

Goal: a general-purpose agent that demonstrates current, production-grade LangGraph engineering
— explicit orchestration, durable state, human oversight, security, evals and deployment.
Ordered by CV value × learning value. Status: ✅ done · 🔜 next · ⬜ planned.

---

## Done

### ✅ Text-to-SQL hardening (OWASP LLM Top 10)
AST classification with `sqlglot` **allowlists** (reads = known query types, writes = known
DML/DDL, everything else refused), single-statement only, allowlisted + parameterized schema
lookup, and DuckDB connections with external access disabled and configuration locked — SQL
cannot touch the filesystem (`read_text`, `COPY … TO`, `ATTACH`, `INSTALL`).
**CV:** "Hardened an LLM text-to-SQL toolset against injection, write-bypass and file
exfiltration (AST allowlists, read-only + sandboxed connections), aligned with the OWASP LLM
Top 10."

### ✅ Indirect prompt-injection + SSRF defenses for web tools
Untrusted-content boundary markers with spoof stripping; guardrail rejects marker spoofing in
user input; `web_fetch` restricted to public IPs on every redirect hop, streamed byte cap,
text-only content, HTML → visible text.
**CV:** "Implemented indirect-prompt-injection and SSRF mitigations for a tool-augmented agent."

### ✅ Hybrid StateGraph (deterministic nodes around an agentic core)
`guardrail → agent → verify` with a bounded retry edge when answer figures aren't grounded in
tool output (deterministic hallucination check).

### ✅ Durable threads + human-in-the-loop over HTTP
SQLite checkpointer in the API lifespan; `/api/chat` surfaces interrupts as
`awaiting_approval`; `/api/chat/resume` applies approve / edit / reject; correct handling of
summarization rewriting history (`history_delta`).

### ✅ Generalization
Domain prompt, dashboard API and MVP datasets removed/archived; toolset assembled from
configuration (SQL tools only when a database is configured).

---

## 🔜 Next: explicit LangGraph rebuild

Replace the `create_agent` black box with hand-built graph structure that a single prebuilt
agent cannot express. Keep today's agent as a **baseline** and benchmark against it.

```
START → guardrail → route (intent)
          ├→ research subgraph   (search → fetch → grade sources → synthesize)
          ├→ sql subgraph        (inspect schema → generate → validate[sqlglot] ─invalid→ regenerate
          │                       → execute(read-only) → grade result ─insufficient→ rewrite)
          ├→ write path          (generate → approve_write [interrupt()] → execute)
          └→ direct answer
        → synthesize (structured output) → verify → END
parallel: Send() fan-out for multi-part questions → reducer merge
```

Teaches: custom state schemas + reducers, conditional edges, cycles with retry budgets,
subgraphs, `interrupt()` / `Command(resume=…)`, `Send` fan-out, node-level `RetryPolicy` /
`CachePolicy`, streaming. Middleware equivalents must be re-homed (limits → recursion limit +
counters in state, retry → `RetryPolicy`, rate limiting → model `rate_limiter`, summarization →
a summarize node). Write the mapping up as an ADR.
**CV:** "Designed a multi-path LangGraph agent with self-correcting SQL and research subgraphs,
human approval via interrupts, and parallel fan-out; benchmarked against a single-agent baseline."

### Streaming
SSE endpoint over `graph.astream(stream_mode=["messages", "updates"])` — token streaming plus
step events ("searching…", "running SQL…").

---

## ⬜ Planned

### Evals done right (deferred step 3)
- General-agent datasets: factual QA with web, SQL over a seeded demo DB, refusal /
  injection-resistance cases, HITL scenarios.
- Numeric-tolerance matcher instead of exact substring; independent judge model; gate per
  metric against a baseline experiment; CI smoke subset with cached responses.
- **Trajectory evals** — tool choice, SQL validity rate, steps per question.
**CV:** "Built answer- and trajectory-level agent evals with a regression gate in CI."

### Long-term memory (LangGraph Store)
Cross-thread memory: user preferences and learned facts in a `Store` with semantic search,
injected per user; the agent writes memories through a tool. Distinct from thread memory.

### Multi-agent study
Supervisor vs. swarm (handoffs) vs. single agent vs. the explicit graph, benchmarked on the eval
suite for latency, cost and quality. The project's own history (supervisor collapsed to one agent
for cost) is the motivating case study.

### Agentic RAG over documents
Upload/ingest documents; hybrid retrieval (BM25 + vector), reranking, retrieval grading with
query rewriting on miss.

### Structured outputs + citations
Final answer as a validated schema (`answer`, `sources`, `sql_used`, `confidence`) so every claim
is traceable.

### Token + cost accounting
Middleware/callback recording tokens and cost per request and per thread; expose via
`/metrics`.

### Complexity-based model cascade
Cheap model classifies the request; simple → small model, complex → large. Quote eval-verified
quality parity and measured savings.

### Guardrails as policy
Pre-action authorization (per-tool / per-table policy checked before each tool call), tool risk
ratings, approval rules driven by policy rather than hardcoded tool names.

### MCP both ways
Wire real MCP servers into the client; expose the agent's own tools as an MCP server.

### Durable execution demos
Kill mid-run and resume; time-travel — fork a thread from a past checkpoint with edited state.

### Deployment + observability
Dockerfile + compose (gateway + Postgres checkpointer), health/readiness probes, API auth + rate
limiting, OpenTelemetry spans, load test with a published latency budget (p50/p95).

### Semantic caching
Cache answers by embedding similarity; measure hit rate and savings.

---

## Notes

- **LangGraph vs LangChain.** `create_agent` (LangChain v1) compiles to a LangGraph
  `StateGraph`; checkpointing, interrupts and `langgraph dev` all come from the LangGraph runtime.
  What the rebuild adds is *hand-built orchestration* — the part employers mean by "agent
  orchestration".
- **Correction to an earlier note:** "sync tools block the event loop" was likely wrong —
  LangChain runs sync tools via `run_in_executor` under `ainvoke`. Measure before claiming it.
