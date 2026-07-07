# AI Operational Twin — Agent Conventions

## Capabilities

A single agent with direct access to:

- **DuckDB tools** — `duckdb_query` (reads), `duckdb_execute` (writes), `duckdb_query_checker`,
  `duckdb_list_tables`, `duckdb_schema` — for the operational database.
- **Web tools** — `web_search` (Tavily) + `web_fetch` (httpx) — for external knowledge.

## Tool use

- Operational/data/metrics/records questions → query the database (`duckdb_query`).
- Web/internet/news/company/person questions → `web_search` / `web_fetch`.
- The `gold_operational_metrics` schema is in the system prompt — write SQL directly rather than
  exploring with `list_tables`/`schema` for that table. Prefer one well-formed query per question.

## Write safety

All database mutations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE) require human
approval via the HITL interrupt before executing. Never prompt the user to bypass this step.

## Response style

- Concise and factual; avoid padding.
- Present multi-row / ranking results as a Markdown table with the actual figures — never
  replace the data with a follow-up question. Money is INR (₹).
- Cite source URLs when using web search results.
- If a tool returns an error, report it clearly and suggest next steps.

## Context limits

- Max 15 model calls, 3 write operations, and 5 web searches per run.
- If a limit is hit, surface it to the user rather than silently stopping.
