# AI Operational Twin — Preliminary Report
**Prepared for:** Nikola (report writing)
**Prepared by:** Saad Bin Waqas
**Status:** Preliminary — covers backend implementation complete to date

---

## 1. Executive Summary

The AI Operational Twin is a software platform that uses multiple cooperating AI agents to answer questions about an organisation's operational data. A user can ask questions in plain English — the system decides whether to search the web for information, query a live database, or both — and returns a synthesised answer.

The platform was built with safety and control as primary concerns: any operation that modifies data requires explicit human approval before it is executed. It is provider-agnostic (supports Anthropic, Groq, and Mistral AI models), fully observable through LangSmith tracing, and ships with an automated evaluation and CI pipeline that prevents regressions when the system is updated.

The backend is fully functional and ready for integration with a frontend dashboard and production deployment infrastructure.

---

## 2. Problem Statement

Modern organisations generate large volumes of operational data but lack tools that allow non-technical staff to interact with that data conversationally. Existing solutions require writing SQL queries or navigating complex dashboards.

At the same time, AI systems that can write to databases introduce risk: an autonomous system making unchecked changes to operational data could cause serious harm.

The project addresses both problems:
1. Allow users to ask questions in plain English and receive answers derived from live operational data and external research sources.
2. Ensure that any AI action that modifies data requires a human to explicitly approve it before execution.

---

## 3. Project Objectives

The objectives, drawn from the product brief, were:

| Objective | Status |
|---|---|
| Support multiple AI agents with different responsibilities | ✅ Complete |
| Support tool usage through a clean abstraction layer | ✅ Complete |
| Support multiple LLM providers (Anthropic, Groq, Mistral) | ✅ Complete |
| Support human-in-the-loop approval for sensitive actions | ✅ Complete |
| Support persistent conversation memory and checkpoints | ✅ Complete |
| Support evaluation-driven development | ✅ Complete |
| Support CI/CD with automated quality gates | ✅ Complete |
| Production deployment infrastructure | 🔲 Planned (next phase) |

---

## 4. Solution Architecture

The system follows a **supervisor + specialists** pattern. A central orchestrating agent (the Supervisor) receives the user's message, decides which specialist is best suited to handle it, delegates the work, and synthesises the response.

```
User
  │
  ▼
Supervisor Agent
  ├── Research Agent  ──► Web Search (Tavily) + Web Fetch
  └── Ops Agent       ──► Operational Database (DuckDB)
                              ↑
                        Human approval required
                        for any write operation
```

**Key architectural decisions:**

- **Agent-as-tool pattern:** Each specialist is wrapped as a tool that the supervisor can call. This means adding a new specialist in future requires no changes to the supervisor.
- **Middleware stack:** A layered middleware system handles cross-cutting concerns (safety, fault tolerance, memory, cost control) separately from agent logic.
- **Provider-agnostic:** The model provider is a single configuration setting. Switching from Anthropic to Groq, for example, requires one line change in the config file.
- **LangGraph runtime:** The entire system runs on LangGraph, which manages conversation state, checkpointing, and the human-in-the-loop interrupt mechanism.

---

## 5. System Components

### 5.1 Data Layer

**DuckDB Operational Database**

An embedded analytical database that stores operational data. Five tools expose the database to the Ops Agent:

| Tool | What it does |
|---|---|
| List tables | Shows all tables in the database |
| Show schema | Shows column names, types, and sample rows |
| Query checker | Validates SQL and classifies it as read or write |
| Read query | Executes SELECT queries; capped at 100 rows |
| Write query | Executes INSERT/UPDATE/DELETE — requires human approval first |

The database file is created automatically on first use. No manual database setup is required.

**MCP Tool Server Integration**

The system includes a connection point for external tool servers following the Model Context Protocol (MCP) standard. This allows additional data sources or services to be connected without modifying agent code. Currently configured as empty — ready to plug in.

### 5.2 AI Layer

**Supervisor Agent**

The central orchestrator. It receives user messages, decides routing, calls specialists, and writes the final response. It carries the full middleware stack.

**Research Agent**

Handles questions that require external knowledge — web search and article retrieval. Uses Tavily for search and direct HTTP fetch for page content. If the Tavily API key is not configured, it returns a clear message rather than crashing.

**Ops Agent**

Handles questions about the operational database. Reads data freely; write operations pause and wait for human approval before executing.

**Middleware Stack (on the Supervisor)**

The middleware is a set of layers applied to every AI call, from outermost to innermost:

| Layer | Purpose |
|---|---|
| PII filter | Blocks API keys and sensitive patterns in both incoming and outgoing messages |
| Call limit | Stops runaway loops — supervisor is capped at 10 model calls per request |
| Retry | Automatically retries failed API calls up to 3 times |
| Memory | Injects the AGENTS.md routing rules into the system prompt on every call |
| Summarisation | Compresses conversation history when it gets too long (at 80% of the token limit), keeping the 6 most recent messages |
| Dev cost router | In development mode, routes calls to a cheaper model to reduce cost |
| Prompt caching | Caches the system prompt on Anthropic's servers to reduce cost on repeated calls |

**Configuration System**

Environment-specific configuration files (dev / staging / prod) set sensible defaults per environment. A `.env` file overrides any default. The system supports three AI providers out of the box; switching providers is a one-line change.

### 5.3 Dashboard / Observability Layer

**LangSmith Studio**

Every agent call, tool call, intermediate step, and token count is traced automatically in LangSmith. The LangGraph Studio UI (accessible via `langgraph dev`) provides a live graph visualisation and allows interactive testing of the supervisor directly in the browser.

This serves as the current operational dashboard. A dedicated frontend UI is planned for a future phase.

---

## 6. Implementation Process

The system was built incrementally in four stages:

**Stage 1 — Core agent skeleton**
Established the supervisor + research agent structure, LangGraph integration, provider-agnostic model configuration, LangSmith tracing, and the CLI runner for local testing.

**Stage 2 — Real tools, safety, and fault tolerance**
Added real web search (Tavily), the Ops Agent with DuckDB tools, the human-in-the-loop approval mechanism, PII filtering, and fault tolerance middleware (retry, call limits).

**Stage 3 — Persistence, memory, and context management**
Added durable conversation persistence (Postgres via `langgraph up`), AGENTS.md memory injection, conversation summarisation, Anthropic prompt caching, dynamic cost routing, MCP integration, and environment-specific configuration files.

**Stage 4 — Evaluations and CI**
Added three JSONL evaluation datasets (11 examples total), three evaluators (substring check, exact match, LLM-as-judge), an evaluation runner with a pass/fail gate, and a 3-stage GitHub Actions CI pipeline.

---

## 7. Testing & Validation

### Unit Tests

`tests/` contains two unit test files that run without any API calls:

- **test_evaluators.py** — verifies that the substring and exact-match evaluators return correct scores across 11 cases (match, no match, case sensitivity, empty inputs, null outputs)
- **test_config.py** — verifies that the Settings system correctly defaults `SUMMARIZATION_MODEL` to `BACKEND_MODEL` when not set, and that other config defaults are correct

### Evaluation Suite

Three datasets stored as JSONL files and uploaded to LangSmith:

| Dataset | Examples | What it tests |
|---|---|---|
| supervisor-v1 | 5 | Correct routing between research and ops; response synthesis |
| research-v1 | 3 | Factual retrieval on industrial topics (SCADA, anomaly detection, KPIs) |
| ops-v1 | 3 | Read-only database queries (list tables, schema, overview) |

Each example specifies an input question and expected content in the response. The evaluators check whether the AI's answer contains the expected content. A second evaluator (LLM-as-judge) uses a separate AI model to rate correctness on a 0–1 scale.

### CI Pipeline

Three sequential stages run automatically on every code push:

| Stage | What runs | When |
|---|---|---|
| 1 — Lint | Code style check (ruff) + import smoke test | Every push and pull request |
| 2 — Unit tests | pytest (no API calls, runs in seconds) | After lint passes |
| 3 — Eval gate | Full eval run against LangSmith datasets; fails if average score < 70% | Push to main branch only |

Stage 3 acts as a regression gate — it blocks a code change from reaching the main branch if it causes the system's eval scores to drop below the threshold.

---

## 8. Results

- A fully functional multi-agent backend that can answer questions combining web research and live database queries
- Human-in-the-loop approval confirmed working: write operations pause and wait for approval before executing
- Provider switching confirmed: system runs on Anthropic, Groq, and Mistral by changing one config value
- Conversation persistence confirmed: threads survive server restarts when running `langgraph up`
- Full observability: every request is traced end-to-end in LangSmith with token counts, latency, and intermediate steps
- CI pipeline operational: lint, unit tests, and eval gate run automatically on every push
- Evaluation datasets uploaded to LangSmith and eval runner verified working

---

## 9. Limitations

**No production deployment yet**
The system runs in development mode (`langgraph dev`) and staging mode (`langgraph up` with Docker). Production deployment infrastructure (hosting, scaling, auth, monitoring alerts) is planned for the next phase.

**No frontend dashboard**
The current user interface is LangGraph Studio (a developer tool) and a CLI runner. A purpose-built dashboard for end users has not been built yet.

**Small evaluation datasets**
The eval datasets contain 11 examples total. This is sufficient for a regression gate but not for statistically robust benchmarking. Datasets should be expanded as the system matures.

**Ops eval depends on database content**
The ops evaluation examples test database queries against the live operational database. If the database is empty or missing, some eval examples may produce less informative results (though they will not crash).

**No fine-tuning or prompt versioning**
The system uses off-the-shelf models with prompt files stored on disk. Systematic prompt versioning and A/B testing of prompts are not yet implemented.

---

## 10. Future Improvements

**Phase 5 — Production deployment**
Containerise the backend, set up hosted infrastructure, add authentication, configure production monitoring and alerting, and establish a deployment pipeline.

**Frontend dashboard**
Build a user-facing interface that allows non-technical users to interact with the system without needing LangGraph Studio or a CLI.

**Expanded evaluations**
Grow the evaluation datasets, add latency and cost tracking per eval run, and introduce multi-turn conversation test cases.

**Prompt versioning**
Implement version control for system prompts so changes to prompts can be tracked, rolled back, and A/B tested.

**Additional specialist agents**
The architecture supports adding new specialists without changing the supervisor. Future specialists could handle report generation, anomaly alerting, or integration with external operational systems (SCADA, ERP, etc.).

**CompositeBackend memory routing**
The system is architected to support cross-thread persistent memory through LangGraph Store. A future upgrade would route memory through a CompositeBackend for more sophisticated long-term memory across sessions.

---

## 11. Conclusion

The AI Operational Twin backend delivers a working, safe, and extensible multi-agent AI platform. The core requirements — multi-agent orchestration, tool use, human approval for sensitive actions, provider flexibility, conversation persistence, observability, evaluations, and CI — are all implemented and verified.

The system is designed so that each major concern (agents, tools, middleware, config, evals) lives in its own module. Adding a new agent, a new tool, or a new AI provider requires minimal changes and does not touch unrelated parts of the system.

The immediate next step is production deployment infrastructure (Phase 5), followed by a user-facing frontend dashboard.
