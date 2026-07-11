---
RAIC Backend — Architecture Proposal (LangChain Ecosystem Revision)

Author role: Principal Software Architect
Phase: Architecture Planning — no implementation code
Source of truth: requirements.md + LangChain/LangGraph/LangSmith documentation (live, via MCP)
Prior proposal: SUPERSEDED — previous design predated LangChain adoption decision

LangChain docs consulted:
  - LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
  - Multi-agent subagents: https://docs.langchain.com/oss/python/langchain/multi-agent/subagents
  - HITL middleware: https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant
  - LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
  - LangGraph checkpointers: https://docs.langchain.com/oss/python/langgraph/checkpointers
  - Subgraph persistence: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
  - Memory overview: https://docs.langchain.com/oss/python/concepts/memory
  - MCP integration: https://docs.langchain.com/oss/python/langchain/mcp
  - LangSmith evaluation: https://docs.langchain.com/langsmith/evaluation
  - LangSmith deployment: https://docs.langchain.com/oss/python/langgraph/deploy
  - Agent Server / LangGraph CLI: https://docs.langchain.com/langsmith/cli
  - Cost tracking: https://docs.langchain.com/langsmith/cost-tracking
  - Streaming: https://docs.langchain.com/oss/python/langgraph/streaming
  - Middleware (prebuilt): https://docs.langchain.com/oss/python/langchain/middleware/built-in
  - Middleware (custom): https://docs.langchain.com/oss/python/langchain/middleware/custom
  - Execution environment / sandboxes: https://docs.langchain.com/oss/python/deepagents/sandboxes
  - Context management: https://docs.langchain.com/oss/python/deepagents/harness
  - Planning/delegation: https://docs.langchain.com/oss/python/langchain/agents#planning-and-delegation
  - Fault tolerance: https://docs.langchain.com/oss/python/langchain/agents#fault-tolerance
  - Guardrails / PII: https://docs.langchain.com/oss/python/langchain/guardrails
  - Dynamic model selection: https://docs.langchain.com/oss/python/langchain/models#dynamic-model-selection
  - Structured output errors: https://docs.langchain.com/oss/python/langchain/structured-output#error-handling-strategies

---

1. Architecture Overview

This system is a production-ready multi-agent LLM platform built on the LangChain ecosystem.
Each product in the stack has a specific, non-overlapping responsibility:

+------------------+-----------------------------------------------+---------------------------+
| Product          | Role in this system                           | Key docs reference        |
+------------------+-----------------------------------------------+---------------------------+
| LangChain        | Agent abstractions, model integrations,       | oss/python/langchain      |
|                  | tool definitions, create_agent()              |                           |
+------------------+-----------------------------------------------+---------------------------+
| LangGraph        | Orchestration runtime: StateGraph, durable    | oss/python/langgraph      |
|                  | execution, HITL interrupts, checkpointing,    |                           |
|                  | streaming, subgraphs                          |                           |
+------------------+-----------------------------------------------+---------------------------+
| LangSmith        | Observability (auto-tracing), evaluation      | langsmith/                |
|                  | harness, dataset management, production       |                           |
|                  | deployment (Agent Server)                     |                           |
+------------------+-----------------------------------------------+---------------------------+
| langchain-mcp-   | Loads external MCP servers as LangChain       | oss/python/langchain/mcp  |
| adapters         | tools; interceptors bridge MCP with LangGraph |                           |
+------------------+-----------------------------------------------+---------------------------+
| openevals        | Prebuilt LLM-as-judge evaluators              | langsmith/openevals       |
+------------------+-----------------------------------------------+---------------------------+

System boundary diagram:

+--------------------------------------------------------------+
|  Entry points: CLI  |  Agent Server API  |  LangGraph Studio |
+--------+------------------+-----------------------------------+
         |                  |
+--------v------------------v-----------------------------------+
|              LangGraph StateGraph (Supervisor)                |
|   Compiled graph + checkpointer + store + streaming           |
+----+----------+----------+----------------------------------+--+
     |          |          |
     v          v          v
 Research    Ops/Files   [future specialists]
  subgraph   subgraph       subgraph
     |          |
     v          v
 LangChain tools (web, filesystem, MCP servers)
     |
     v
 HumanInTheLoopMiddleware (on interrupt_on tools)
     |
     v
 LangSmith (auto-traces all runs, costs, tokens)

---

2. Major Components

2.1 LangGraph Supervisor Graph

The central orchestrator is a LangGraph StateGraph.

Source:
  "In the subagents architecture, a central main agent (often referred to as a supervisor)
  coordinates subagents by calling them as tools. The main agent decides which subagent to
  invoke, what input to provide, and how to combine results. Subagents are stateless—they
  don't remember past interactions, with all conversation memory maintained by the main agent."
  — https://docs.langchain.com/oss/python/langchain/multi-agent/subagents

Design decisions derived from docs:

  - Supervisor is a LangGraph StateGraph compiled with a checkpointer (required for HITL and
    thread persistence).
  - Each specialist is a subgraph created via create_agent() or a raw StateGraph. The supervisor
    calls specialists as tools.
  - Subagents compiled with checkpointer=None (default): each invocation starts fresh, inherits
    the parent's checkpointer for interrupt support. This is the recommended default for
    multi-agent systems where subagents handle independent requests.
    — https://docs.langchain.com/oss/python/langgraph/use-subgraphs#subgraph-persistence
  - Context isolation: each subagent invocation receives a clean context window, preventing
    context bloat in the supervisor's conversation history.

State type:

  Supervisor maintains MessagesState (or a custom TypedDict extending it) containing:
  - messages: Annotated[list, add_messages]    — conversation history, auto-reduced
  - agent_outputs: dict                        — results keyed by step/agent
  - run_metadata: dict                         — cost, latency, token accumulators

Specialist agents (Phase 1+):

  - ResearchAgent    — web_search, web_fetch tools
  - OpsAgent         — read_file, write_file, list_directory tools (write ops require HITL)
  - [extensible: new agent = new subgraph + system prompt + tool list]

---

2.2 Tool System

Source: https://docs.langchain.com/oss/python/langchain/tools

Tools are defined using the @tool decorator or StructuredTool from langchain_core.tools.
They are passed directly to create_agent() or bound to the StateGraph's model.

Tool categories:

  - Web tools: web_search (Tavily/SerpAPI), web_fetch
  - Filesystem tools: read_file, write_file, list_directory
  - MCP tools: any external MCP server loaded via langchain-mcp-adapters

MCP integration:

  Source: https://docs.langchain.com/oss/python/langchain/mcp

  langchain-mcp-adapters converts MCP servers into standard LangChain tools:
  - MultiServerMCPClient loads one or more MCP servers (stdio or HTTP/SSE)
  - Returns a list of BaseTool objects usable by any LangChain agent
  - Tool interceptors bridge MCP execution with LangGraph runtime context (store, agent state)
  - Agent Server exposes the deployed LangGraph graphs as MCP tools via /mcp endpoint, enabling
    other agents or clients to call this system as an MCP server

Permission enforcement:

  Per-tool HITL approval is handled by HumanInTheLoopMiddleware (see section 2.3).
  There is no separate PermissionsManager class — the middleware IS the permission layer.
  Risk classification lives in tool metadata (tags: ["requires_approval", "risk:medium"]).

---

2.3 Human-in-the-Loop

Source: https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant

LangChain provides built-in HumanInTheLoopMiddleware for tool-level approval.
LangGraph provides interrupt() for node-level pauses.

Approved pattern for this system — tool-level HITL via middleware:

  1. HumanInTheLoopMiddleware configured on agents with sensitive tools:
       middleware=[HumanInTheLoopMiddleware(interrupt_on={"write_file": True})]
  2. Checkpointer on supervisor (required): execution state serialized at interrupt point.
  3. Supervisor streams events; caller collects Interrupt objects.
  4. Human receives interrupt with: tool name, args, description_prefix.
  5. Human submits decision keyed by interrupt.id via Command(resume={interrupt.id: decision}).
  6. Decision types (from docs):
       - {"decisions": [{"type": "approve"}]}
       - {"decisions": [{"type": "edit", "edited_action": modified_args}]}
       - {"decisions": [{"type": "reject"}]}
  7. Execution resumes from checkpoint, tool executes (or not) based on decision.

Key doc constraint:
  "We add a checkpointer only to the top-level agent. This is required to pause and resume
  execution."
  — https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant

Approval channels:
  - Phase 1: CLI (iterate over streamed interrupt events, prompt user inline)
  - Phase 3+: API endpoint on Agent Server — POST /threads/{thread_id}/runs/{run_id}/resume
              with Command payload (Agent Server exposes this natively)

---

2.4 Provider Abstraction

Source: LangChain init_chat_model()

LangChain's init_chat_model() is the recommended provider abstraction layer.

  model = init_chat_model("anthropic:claude-opus-4-8")
  # Switch provider: init_chat_model("openai:gpt-5")
  # Switch: one config string change

This replaces any hand-rolled ProviderClient ABC. The langchain_anthropic and langchain_openai
packages normalize message format, tool-call format, streaming, error codes, and stop reasons
automatically. init_chat_model() is configurable at runtime — the model string comes from
config/settings.py and is injectable for testing (pass a mock ChatModel).

Default model: claude-opus-4-8 via langchain_anthropic.

---

2.5 State Management and Persistence

Source:
  https://docs.langchain.com/oss/python/langgraph/persistence
  https://docs.langchain.com/oss/python/langgraph/checkpointers

LangGraph provides two complementary persistence systems:

A) Checkpointers — thread-scoped (short-term memory):

  "Checkpointers persist a thread's graph state as checkpoints. Use them for short-term,
  thread-scoped memory, including conversation continuity, human-in-the-loop workflows,
  time travel, and fault tolerance."

  Backend progression:
  +------------------+-------------------------------+------------------------------------+
  | Environment      | Backend                       | How                                |
  +------------------+-------------------------------+------------------------------------+
  | Tests            | InMemorySaver                 | from langgraph.checkpoint.memory   |
  | Dev (local)      | InMemorySaver or SqliteSaver  | via langgraph dev                  |
  | Staging/Prod     | AsyncPostgresSaver            | Agent Server manages automatically |
  +------------------+-------------------------------+------------------------------------+

  Thread identity model (aligned with LangGraph):
  - thread_id: stable conversation ID, set in config["configurable"]["thread_id"]
  - Each graph invocation = one run within the thread
  - State checkpoint created after every super-step
  - Time travel: rewind to any prior checkpoint via Agent Server API

B) Store — cross-thread (long-term memory):

  "Stores persist application-defined data outside the graph state. Use them for long-term,
  cross-thread memory, including user preferences, facts, and shared knowledge."

  Used for: user-level context, shared knowledge, preferences that persist across sessions.
  Injected into graph nodes via RunnableConfig or as an injected dependency.
  Agent Server provisions a BaseStore automatically for deployed graphs.

---

2.6 Observability and Tracing

Source: https://docs.langchain.com/langsmith/observability

LangSmith provides automatic tracing for all LangChain and LangGraph calls.
Zero instrumentation code required in this codebase — set two env vars:

  LANGSMITH_TRACING=true
  LANGSMITH_API_KEY=...

Every graph invocation, agent step, tool call, LLM call, token count, and latency is captured
automatically and linked by thread_id/run_id.

Cost tracking:
  LangChain-wrapped models automatically track token usage and compute cost.
  Cost appears in LangSmith traces per LLM call, per run, per thread.
  Source: https://docs.langchain.com/langsmith/cost-tracking

Additional instrumentation:
  - @traceable decorator for non-LangChain functions (custom pre/post-processing)
  - t.log_inputs() / t.log_outputs() for pytest-based eval tracing
  - LangSmith Engine: monitors traces, detects failure patterns, proposes fixes

Trace structure for multi-agent:
  - One root trace per supervisor run (keyed by thread_id + run_id)
  - Child spans per specialist invocation, per tool call, per LLM call
  - Interrupt events visible as trace nodes with decision outcomes
  - All traces linked by thread_id for cross-run inspection

No custom observability/logger.py, tracer.py, or metrics.py — LangSmith replaces all of these.

---

2.7 Evaluations

Source:
  https://docs.langchain.com/langsmith/evaluation
  https://docs.langchain.com/langsmith/evaluation-concepts

LangSmith is the evaluation harness. No custom eval runner needed.

Evaluation flow:

  1. Dataset: JSONL examples in evals/datasets/v1/ — inputs + reference_outputs.
     Uploaded to LangSmith via client.create_dataset() / client.create_examples().
  2. Target function: wraps the supervisor graph invocation.
  3. Evaluators: scoring functions passed to client.evaluate().
  4. Experiment: results stored in LangSmith, visible in UI with pass rate, avg score, cost,
     latency per example.
  5. Regression comparison: compare experiment against stored baseline.

Evaluator types (from LangSmith docs):

  +-------------+--------------------------------------------------+----------------------+
  | Type        | When to use                                      | Implementation       |
  +-------------+--------------------------------------------------+----------------------+
  | exact_match | Deterministic outputs                            | Custom code function |
  | contains    | Output must include facts/phrases                | Custom code function |
  | llm_judge   | Open-ended quality: tone, accuracy, completeness | openevals library    |
  | pairwise    | Compare two model versions head-to-head          | LangSmith UI/SDK     |
  | human       | Annotation queues for ground truth labeling      | LangSmith UI         |
  +-------------+--------------------------------------------------+----------------------+

openevals library provides prebuilt LLM-as-judge evaluators (CORRECTNESS_PROMPT, etc.)
that integrate directly with client.evaluate().

Offline vs online:
  - Offline: client.evaluate() against versioned datasets — runs in CI, blocks on regression
  - Online: evaluators configured in LangSmith UI run automatically on production traces

Eval datasets are versioned (v1/, v2/ folders) from day one. Dataset version recorded
on every EvalReport for reproducible regression comparison.

---

2.8 Deployment

Source:
  https://docs.langchain.com/oss/python/langgraph/deploy
  https://docs.langchain.com/langsmith/cli
  https://docs.langchain.com/langsmith/deployment-quickstart

The deployment unit is a langgraph.json file (not a hand-written Dockerfile):

  {
    "dependencies": ["."],
    "graphs": {
      "supervisor": "./agents/supervisor/graph.py:graph"
    },
    "env": ".env"
  }

langgraph.json declares:
  - dependencies: packages to install (reads pyproject.toml automatically)
  - graphs: graph IDs mapped to compiled graph objects
  - env: secrets file
  - checkpointer TTL, store index, auth handlers, webhooks (optional)

Local development:

  langgraph dev
    → Starts local Agent Server on port 8123
    → Connects to LangGraph Studio for visual debugging
    → Uses InMemorySaver (no Postgres needed locally)
    → Hot-reload on file changes
    → LANGSMITH_TRACING sends all local traces to LangSmith

  langgraph up
    → Full local stack with Postgres checkpointing (Docker required)
    → For staging-parity testing

Production (LangSmith Cloud):
  → Connect GitHub repository to LangSmith
  → Every push to main triggers build + deploy
  → Agent Server provisions: threads, runs, store, checkpointer (Postgres-backed), auth, API
  → Exposes REST + SSE API, /mcp endpoint, /a2a endpoint automatically
  → Traces auto-sent to LangSmith project named after deployment
  → Scale, HA, and infrastructure managed by platform

Self-hosted alternative:
  → langgraph up with --postgres-uri for managed Postgres
  → Docker image: langchain/langgraph-api
  → Kubernetes deployment supported (langgraph/kubernetes docs)

Environment configuration:

  +------------------+--------------------+--------------------+--------------------+
  | Setting          | dev                | staging            | prod               |
  +------------------+--------------------+--------------------+--------------------+
  | Checkpointer     | InMemorySaver      | Postgres (Agent    | Postgres (Agent    |
  |                  |                    | Server)            | Server)            |
  | Model            | claude-opus-4-8    | claude-opus-4-8    | claude-opus-4-8    |
  | HITL channel     | CLI                | API                | API                |
  | Tracing          | LangSmith          | LangSmith          | LangSmith          |
  | Eval runs        | mock/cached        | real (budgeted)    | N/A                |
  +------------------+--------------------+--------------------+--------------------+

---

3. Repository Structure

backend/
│
├── langgraph.json              ← Platform config. Declares graphs, deps, env, checkpointer TTL
│
├── pyproject.toml              ← Dependencies: langgraph, langchain, langchain-anthropic,
│                                 langchain-mcp-adapters, langsmith, openevals, pytest
│
├── .env.example                ← ANTHROPIC_API_KEY, LANGSMITH_API_KEY, LANGSMITH_TRACING,
│                                 BACKEND_MODEL, BACKEND_ENV
│
├── config/
│   ├── settings.py             ← Pydantic Settings: model name, env, HITL config, eval budget
│   └── environments/
│       ├── dev.yaml
│       ├── staging.yaml
│       └── prod.yaml
│
├── agents/
│   ├── supervisor/
│   │   ├── graph.py            ← Compiled StateGraph (entry point declared in langgraph.json)
│   │   ├── state.py            ← SupervisorState TypedDict extending MessagesState
│   │   ├── nodes.py            ← Graph node functions (call_model, route_to_specialist)
│   │   └── prompts/
│   │       └── system.txt
│   ├── research/
│   │   ├── graph.py            ← create_agent(model, tools=[web_search, web_fetch])
│   │   ├── state.py            ← ResearchState TypedDict
│   │   └── prompts/
│   │       └── system.txt
│   └── ops/
│       ├── graph.py            ← create_agent(..., middleware=[HumanInTheLoopMiddleware(...)])
│       ├── state.py            ← OpsState TypedDict
│       └── prompts/
│           └── system.txt
│
├── tools/
│   ├── web.py                  ← @tool web_search, web_fetch
│   ├── filesystem.py           ← @tool read_file, write_file, list_directory
│   └── mcp_client.py           ← MultiServerMCPClient config; loads MCP servers as tools
│
├── middleware/
│   ├── pii.py                  ← PIIMiddleware config (email, api_key, custom detectors)
│   ├── retry.py                ← ModelRetryMiddleware + ToolRetryMiddleware config
│   ├── dynamic_model.py        ← @wrap_model_call for cost-tier / conversation-length routing
│   └── tool_errors.py          ← @wrap_tool_call for runtime tool error → ToolMessage handling
│
├── hitl/
│   └── channels/
│       └── cli.py              ← CLI HITL channel: iterates stream, prompts user, sends Command
│
├── evals/
│   ├── datasets/
│   │   └── v1/                 ← JSONL files: research_agent.jsonl, ops_agent.jsonl,
│   │       └── README.md         end_to_end.jsonl. Schema: {id, input, expected, tags}
│   ├── evaluators/
│   │   ├── exact_match.py      ← Code evaluator functions
│   │   ├── contains.py
│   │   └── llm_judge.py        ← openevals create_llm_as_judge() wrappers
│   └── run_evals.py            ← client.evaluate() harness; loads datasets, runs experiments
│
├── tests/
│   ├── unit/
│   │   ├── agents/             ← Test graph nodes in isolation with mock ChatModel
│   │   ├── tools/
│   │   └── hitl/
│   └── integration/
│       ├── test_supervisor.py  ← Full graph run with InMemorySaver
│       ├── test_hitl_flow.py   ← Interrupt → Command(resume) flow
│       └── test_checkpoint.py  ← Thread resume from checkpoint
│
└── scripts/
    ├── upload_datasets.py      ← Push evals/datasets/ to LangSmith
    └── smoke_test.sh

Dependency rules:

  config/          → nothing (Pydantic Settings reads env vars)
  tools/           → langchain_core only
  middleware/      → langchain, langchain_anthropic (for PIIMiddleware, retry, caching)
  agents/          → tools/, config/, middleware/, langchain, langgraph, deepagents
  hitl/            → langgraph.types (Command, interrupt)
  evals/           → agents/, langsmith, openevals
  tests/           → all (with InMemorySaver injected, mock middleware)

---

4. Agent Responsibilities

4.1 Supervisor Agent

  Responsibility: task decomposition, specialist routing, result synthesis.
  Owns no domain tools. Calls specialists as tools.

  Graph structure:
    __start__ → call_model → [route_to_specialist | END]
    route_to_specialist → [research_tool | ops_tool] → call_model (loop)

  State: MessagesState + SubtaskPlan + AgentOutputs
  System prompt: defines routing logic, specialist descriptions, output format

4.2 Research Agent

  Responsibility: information gathering.
  Tools: web_search, web_fetch, (MCP tools as configured)
  No HITL — read-only operations.
  Subgraph: create_agent(model, tools=[web_search, web_fetch], system_prompt=...)
  Checkpointer: None (per-invocation; inherits parent)

4.3 Ops/Files Agent

  Responsibility: filesystem operations.
  Tools: read_file, write_file, list_directory
  HITL: write_file and list_directory(write=True) require approval.
    middleware=[HumanInTheLoopMiddleware(interrupt_on={"write_file": True, ...})]
  Checkpointer: None (per-invocation; interrupts bubble to supervisor's checkpointer)

4.4 Extension rule (from requirements: "adding new agents should require minimal code changes"):

  New agent = new directory under agents/ + graph.py + state.py + system.txt
  Register as a tool in supervisor/nodes.py (one line: add to tools list)
  Zero changes to existing agents, tools, or graph structure.

---

5. Tool Boundaries

All tools are standard LangChain BaseTool instances. No custom registry or dispatcher.

Tool safety contract:
  - Read-only tools: no approval required. Direct execution.
  - Write/mutate tools: tagged with metadata {"requires_approval": True}
    and passed to HumanInTheLoopMiddleware(interrupt_on={tool_name: True}).
  - Tools never import agent internals. Agent logic never imports tool implementations.

MCP tool isolation:
  - MCP servers run as separate processes (stdio) or remote HTTP endpoints
  - langchain-mcp-adapters loads their tool schemas at startup
  - Tool interceptors (from langchain MCP docs) bridge MCP execution with LangGraph store/context
    when tools need runtime state (e.g. user ID, session data)
  - Agent Server can expose the deployed LangGraph graph as an MCP server (/mcp endpoint),
    allowing other systems to call it as a tool

---

6. State and Memory Design

Short-term memory (thread-scoped, per LangGraph docs):

  Maintained by the checkpointer attached to the supervisor graph.
  Updated after every super-step (node execution).
  Contains: full message history, agent outputs, interrupt state.
  Accessed by thread_id via config["configurable"]["thread_id"].

  Key behavior:
    - Thread resumes automatically from last checkpoint when thread_id is reused
    - Interrupt state persists in checkpoint until Command(resume=...) is sent
    - Time travel: Agent Server exposes GET /threads/{id}/history to list checkpoints

Long-term memory (cross-thread, per LangGraph docs):

  Maintained by LangGraph Store (BaseStore).
  Namespaced by user/agent/topic. Survives across threads.
  Used for: user preferences, remembered facts, agent-level learned context.
  Injected into graph nodes via RunnableConfig or typed InjectedStore.

Memory summary / context compression (if needed):

  LangChain trim_messages() or summarize_messages() to reduce token consumption in
  long-running threads. Applied at start of call_model node when messages exceed threshold.

---

7. Evaluation Plan

Source: https://docs.langchain.com/langsmith/evaluation

Dataset management:
  - Datasets stored in evals/datasets/v1/ as JSONL
  - Schema: {"id": str, "input": dict, "expected": dict, "tags": list[str]}
  - Uploaded to LangSmith via upload_datasets.py script
  - Dataset version tracked: every EvalReport records dataset name + version

Evaluator types used:

  Unit/agent evals (every PR):
    - exact_match: structured output fields
    - contains: required facts/entities present in output
    - llm_judge via openevals: quality, tone, completeness
    All use mock model (ChatModel with fixed responses) — zero real API cost.

  End-to-end evals (daily + pre-release):
    - Full supervisor graph with real model
    - max_cost_usd enforced per example via experiment configuration
    - Global eval budget in config/settings.py (eval_budget_usd)

Experiment runner (run_evals.py):

  client.evaluate(
      target_fn,          # wraps graph.invoke()
      data=dataset_name,
      evaluators=[exact_match_eval, contains_eval, judge_eval],
      experiment_prefix="supervisor-v2",
      max_concurrency=4,
  )

Regression gate:
  - CI compares experiment pass_rate against stored baseline
  - Baseline stored as LangSmith experiment (referenced by experiment_id in CI env var)
  - Block merge if regression > 5% on any scorer

Online evaluators:
  - Configured in LangSmith UI on production tracing project
  - Run on every production trace: safety check, format validation, quality heuristics
  - Failing traces automatically surfaced in LangSmith for annotation

---

8. CI/CD Plan

All stages defined in .github/workflows/.

Stage 1 — Static (no LLM calls, ~60s):
  - ruff lint
  - mypy type check
  - pytest tests/unit/ (mock model, InMemorySaver)

Stage 2 — Integration (~3min):
  - pytest tests/integration/ (InMemorySaver, mock model)
  - Covers: full graph flow, HITL interrupt/resume, checkpoint recovery

Stage 3 — Eval regression gate (~5-10min):
  - python evals/run_evals.py --tags smoke (mock model, subset)
  - Compare against baseline experiment in LangSmith
  - Block merge if regression > 5%

Stage 4 — Staging deploy (after merge to main):
  - langgraph deploy (LangSmith Cloud) or docker build + push
  - Run scripts/smoke_test.sh against staging deployment (real model, limited budget)
  - Block prod promotion on failure

Stage 5 — Production (manual gate):
  - Explicit human approval in GitHub Actions environment
  - Promote staging image/revision to production
  - Post-deploy smoke tests

Quality gates:

  +-------------------+-----------------------------+
  | Gate              | Blocks                      |
  +-------------------+-----------------------------+
  | Stage 1 failure   | PR merge                    |
  | Stage 2 failure   | PR merge                    |
  | Stage 3 regression| PR merge                    |
  | Stage 4 failure   | Prod promotion              |
  | Stage 5           | Prod deploy (requires human)|
  +-------------------+-----------------------------+

Secrets:
  - ANTHROPIC_API_KEY, LANGSMITH_API_KEY — GitHub Actions environment secrets
  - Never in YAML, never in code, never in git

---

9. Risks and Tradeoffs

9.1 LangSmith dependency for observability and deployment

  Risk: vendor lock-in on LangSmith for tracing and deployment.
  Severity: Medium.
  Mitigation:
    - LangGraph is MIT-licensed open source; self-hostable without LangSmith
    - LangSmith tracing uses OTEL-compatible export; can swap backend
    - Deployment via langgraph up works with any Postgres without LangSmith Cloud
  Tradeoff: accepting LangSmith as the observability platform eliminates the need to build
  and maintain a custom observability layer. Worth it for teams < 20 engineers.

9.2 HumanInTheLoopMiddleware is a LangChain abstraction over LangGraph interrupt()

  Risk: middleware behavior may not cover all HITL patterns (batch approval, timeout, webhook).
  Severity: Medium.
  Mitigation:
    - Middleware is composable; direct use of interrupt() + Command is always available
    - Agent Server REST API supports async resume via POST with Command payload
    - Timeout policies can be implemented as a wrapper on resume handler

9.3 Subagent context isolation means no shared memory between specialists mid-run

  Risk: Research output must be passed explicitly to Ops agent via supervisor state.
  Severity: Low.
  Mitigation:
    - Supervisor state (agent_outputs dict) carries results between steps
    - This is the documented pattern; docs note "subagents are stateless"

9.4 InMemorySaver loses state on process restart

  Risk: dev interrupts not survived across restarts.
  Severity: Low in dev, not acceptable in prod.
  Mitigation: Prod uses Postgres-backed checkpointer via Agent Server. Enforced by environment.

9.5 LangGraph graph schema changes break in-flight checkpoints

  Risk: deploying a new graph version with changed state shape breaks existing thread checkpoints.
  Severity: Medium.
  Mitigation:
    - Use checkpointer.serde.allowed_json_modules for controlled deserialization
    - Version graphs in langgraph.json (graph IDs act as versions)
    - Drain in-flight threads before deploying breaking schema changes

9.6 MCP server availability

  Risk: MCP server process crash breaks all tools from that server.
  Severity: Medium.
  Mitigation:
    - Tool interceptors can implement retry with backoff
    - langchain-mcp-adapters supports reconnect
    - Agent Server health checks via /ok endpoint

---

10. ADR-Style Decisions

ADR-001: LangGraph StateGraph as the orchestration runtime

  Decision: Use LangGraph StateGraph for both supervisor and specialist agents.
  Source: https://docs.langchain.com/oss/python/langgraph/overview
  Reasoning: LangGraph is purpose-built for agent orchestration — durable execution, HITL,
  streaming, checkpointing. Building these from scratch (prior architecture) duplicates what
  LangGraph already provides and is tested at scale (Klarna, Uber, JPMorgan per docs).
  Alternatives: custom orchestrator/runner.py (prior design). Rejected — reinvents the wheel.

ADR-002: Supervisor calls subagents as tools (not subgraphs with direct edges)

  Decision: Specialist agents are wrapped as tools and bound to the supervisor's model.
  Source: https://docs.langchain.com/oss/python/langchain/multi-agent/subagents
  Reasoning: Docs describe this as the canonical subagents architecture. Enables context
  isolation (each subagent runs in a clean context window). Supervisor retains all memory.
  Alternatives: supervisor/worker with shared state (LangGraph multi-agent network). Deferred —
  more complex to reason about, and context isolation is a feature not a limitation.

ADR-003: Checkpointer only on supervisor graph

  Decision: Specialist subgraphs compiled with checkpointer=None (default).
  Source: https://docs.langchain.com/oss/python/langgraph/use-subgraphs#subgraph-persistence
  Reasoning: Docs state per-invocation (None) is "the right choice for most applications,
  including multi-agent systems where subagents handle independent requests." Adds interrupt
  support via parent checkpointer without per-subagent state accumulation.
  Alternatives: per-thread persistence on subagents. Deferred — only needed if subagents
  require multi-turn memory independent of supervisor.

ADR-004: HumanInTheLoopMiddleware for tool approval

  Decision: Use LangChain's built-in HumanInTheLoopMiddleware instead of a custom HITL handler.
  Source: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
  Reasoning: Middleware pattern integrates with LangGraph's interrupt/resume mechanism natively.
  Supports approve, edit, reject decision types out of the box. No custom pause/resume logic.
  Alternatives: raw interrupt() node in StateGraph. Available as escape hatch for non-tool HITL.

ADR-005: init_chat_model() for provider abstraction

  Decision: Use LangChain's init_chat_model() instead of a custom ProviderClient ABC.
  Reasoning: init_chat_model("anthropic:claude-opus-4-8") normalizes message format, tool
  calling, streaming, and error handling across providers. Switching providers = one config
  string. Custom ProviderClient ABC duplicates this and requires adapter maintenance per provider.
  Alternatives: custom ABC (prior design). Rejected — unnecessary duplication of LangChain core.

ADR-006: LangSmith for all observability and tracing

  Decision: Use LangSmith auto-tracing (LANGSMITH_TRACING=true) instead of custom logger/tracer.
  Reasoning: LangGraph/LangChain auto-emit structured traces to LangSmith with zero code.
  Token counts, costs, latency, tool calls, agent steps all captured. Custom observability/
  logger.py, tracer.py, metrics.py would replicate a fraction of this with more maintenance.
  Alternatives: custom OpenTelemetry tracer (prior design). Available via OTEL export from
  LangSmith for Jaeger/Datadog/Honeycomb compatibility.

ADR-007: LangSmith evaluate() + openevals as evaluation harness

  Decision: Use langsmith.Client.evaluate() with openevals for all evals.
  Source: https://docs.langchain.com/langsmith/evaluation
  Reasoning: Native integration between evaluation runs and LangSmith traces. Experiment
  comparison, regression detection, and online evaluators built into the platform.
  openevals provides production-quality LLM-as-judge evaluators without reinvention.
  Alternatives: custom evals/runner.py (prior design). Rejected — duplicates LangSmith's eval
  infrastructure. Custom evaluator functions still live in evals/evaluators/ and are passed
  to client.evaluate() — implementation code stays in repo, harness does not.

ADR-008: langgraph.json + Agent Server for deployment

  Decision: Deploy via langgraph.json + LangSmith Agent Server (cloud or self-hosted).
  Source: https://docs.langchain.com/oss/python/langgraph/deploy
  Reasoning: Agent Server provisions threads, runs, store, checkpointer, auth, webhooks,
  /mcp endpoint, and scaling automatically. A hand-written Dockerfile + docker-compose +
  FastAPI app (prior design) duplicates all of this. langgraph dev enables local dev with
  LangGraph Studio visual debugger.
  Alternatives: custom FastAPI app (prior design). Not needed until the system requires
  custom routes beyond what Agent Server provides. Custom routes can be added via custom
  middleware in langgraph.json if needed.

ADR-009: langchain-mcp-adapters for external tool servers

  Decision: Integrate external tools via langchain-mcp-adapters (MultiServerMCPClient).
  Source: https://docs.langchain.com/oss/python/langchain/mcp
  Reasoning: Converts MCP servers into standard BaseTool instances; no custom ToolServer ABC.
  Tool interceptors handle runtime context (store, agent state) bridging at the MCP layer.
  Alternatives: custom ToolServer ABC + ToolRegistry (prior design). Rejected — MCP is the
  standard; adapters handle the conversion. Direct tool definition (@tool decorator) still
  used for simple in-process tools.

ADR-010: No custom contracts/ layer

  Decision: No shared type definitions package. LangGraph state TypedDicts + Pydantic models
  used locally per agent.
  Reasoning: LangGraph's MessagesState and TypedDict state schemas are the effective "contracts"
  between components. The Agent Server REST API is the external interface contract. A custom
  contracts/ package would duplicate and diverge from LangGraph's type system.
  Tradeoffs: individual agent states are not centrally documented. Mitigated by: typed state
  classes per agent, mypy strict checking, LangGraph state schema validation at compile time.

---

11. Phase Implementation Order

Each phase leaves the system runnable.

Phase 1 — Core Graph (runnable with langgraph dev):
  - pyproject.toml + langgraph.json + .env.example
  - config/settings.py (model, env, HITL, eval budget)
  - agents/supervisor/graph.py (StateGraph, call_model node, tool routing, stream_mode wired)
  - agents/supervisor/state.py (MessagesState + summary field for future summarization)
  - agents/research/graph.py (create_agent with web_search stub)
  - tools/web.py (stub tools)
  - middleware/retry.py (ModelRetryMiddleware on all agents from day 1)
  - hitl/channels/cli.py (CLI HITL: iterates stream events, prompts user, sends Command)
  Result: langgraph dev → supervisor routes to research, streaming visible, retries wired

Phase 2 — Tools + HITL + Guardrails:
  - tools/filesystem.py (real read_file, write_file, list_directory)
  - agents/ops/graph.py (create_agent + HumanInTheLoopMiddleware + FilesystemMiddleware)
  - Real web tools (Tavily integration)
  - middleware/pii.py (PIIMiddleware on supervisor — email redact, api_key block)
  - middleware/tool_errors.py (@wrap_tool_call for ops tool runtime errors)
  - CLI HITL full approve/edit/reject loop
  - stream_mode="tools" to show tool args to CLI before interrupt fires
  Result: full multi-agent flow with HITL, guardrails, error handling end-to-end

Phase 3 — Persistence + MCP + Context Management:
  - langgraph up (Postgres checkpointer locally)
  - tools/mcp_client.py (MultiServerMCPClient)
  - LangGraph Store + CompositeBackend routing
  - MemoryMiddleware + SummarizationMiddleware on supervisor
  - AnthropicPromptCachingMiddleware (prompt cost reduction)
  - middleware/dynamic_model.py (@wrap_model_call — basic cost-tier routing)
  - config/environments/ fully wired
  Result: threads survive restarts; context managed; prompt cache active

Phase 4 — Evaluations + CI:
  - evals/datasets/v1/ (initial JSONL sets)
  - evals/evaluators/ (exact_match, contains, llm_judge via openevals)
  - evals/run_evals.py (ToolStrategy with handle_errors on structured eval outputs)
  - scripts/upload_datasets.py
  - .github/workflows/ci.yml (Stages 1-3 including eval regression gate)
  Result: CI eval gate blocks regressions on merge

Phase 5 — Production:
  - LangSmith Cloud deployment (connect GitHub repo)
  - .github/workflows/deploy.yml (Stages 4-5)
  - Staging + prod environment configs
  - Online evaluators configured in LangSmith UI
  - LangSmith trace masking (regex redaction before storage)
  Result: production deployment with full observability + trace-level PII protection

Phase 6 — Hardening:
  - todoListMiddleware on supervisor (complex multi-step task planning)
  - SubAgentMiddleware for parallel research delegation
  - ModelFallbackMiddleware (provider redundancy)
  - Modal/Daytona sandbox backend on ops agent (code execution)
  - Custom auth in langgraph.json
  - Webhook-based HITL channel
  - Content moderation custom middleware (if multi-tenant)
  - Dynamic model via user context (user-selectable model string)

---

12. Prior Architecture — What Changed and Why

The previous Architecture_proposal.md predated the decision to standardize on LangChain.
The following components are superseded:

+----------------------------------+------------------------------------------+
| Prior design component           | LangChain replacement                    |
+----------------------------------+------------------------------------------+
| contracts/ (custom types)        | LangGraph TypedDict state + MessagesState|
| ProviderClient ABC               | init_chat_model()                        |
| orchestrator/runner.py           | LangGraph StateGraph                     |
| hitl/handler.py + channels/      | HumanInTheLoopMiddleware + Command       |
| state/backends/base.py (ABC)     | LangGraph Checkpointer interface         |
| state/backends/duckdb.py         | AsyncPostgresSaver (Agent Server)        |
| state/backends/memory.py         | InMemorySaver                            |
| observability/logger.py          | LangSmith auto-tracing                   |
| observability/tracer.py          | LangSmith OTEL export                    |
| evals/runner.py                  | langsmith.Client.evaluate()              |
| api/app.py + api/routes/         | Agent Server built-in API                |
| Dockerfile + docker-compose.yml  | langgraph.json + langgraph dev/up        |
+----------------------------------+------------------------------------------+

Any Phase 1 implementation files written against the prior architecture should be deleted
before Phase 1 of this architecture is implemented.

---

Assumptions

1. Python 3.11+. Required by langgraph-cli.
2. Anthropic as default provider (langchain_anthropic). OpenAI available via init_chat_model switch.
3. LangSmith account required for tracing and eval. Free tier sufficient for development.
4. LangSmith Cloud for production deployment. Self-hosted Agent Server is the alternative if
   data residency or air-gap requirements exist (see langsmith/self-hosted.mdx).
5. Tavily API key for web_search tool (or swap for SerpAPI/DuckDuckGo via config).
6. No real-time WebSocket to end users — SSE via Agent Server sufficient.
7. MCP servers run as local stdio processes in dev; HTTP/SSE endpoints in prod.
8. deepagents package available — required for FilesystemMiddleware, SummarizationMiddleware,
   SkillsMiddleware, MemoryMiddleware, SubAgentMiddleware, todoListMiddleware, sandbox backends.
9. DuckDB: no native LangChain integration (not in vector store or checkpointer list). If analytics
   queries over structured data are needed, implement as a @tool using standalone duckdb package.
   LangSmith data export can be queried with DuckDB, but that is an ops tool, not an agent tool.

---

13. Streaming

Source: https://docs.langchain.com/oss/python/langgraph/streaming

LangGraph graphs expose .stream() (sync) and .astream() (async). Stream mode was MISSING from the
original proposal. It is essential for user-facing applications.

Available stream modes:

+----------+--------------------------------------------------------------------+
| Mode     | What is streamed                                                   |
+----------+--------------------------------------------------------------------+
| values   | Full graph state snapshot after each super-step                    |
| updates  | Only the state diffs after each step (preferred for most UIs)      |
| messages | LLM token-by-token output + metadata (required for chat streaming) |
| custom   | Developer-emitted events via get_stream_writer() inside a node     |
| tools    | Tool lifecycle events (on_tool_start, on_tool_end, on_tool_error)  |
| debug    | All internal events; use for debugging only                        |
+----------+--------------------------------------------------------------------+

Multiple modes can be combined: stream_mode=["updates", "messages", "custom"]

Subgraph streaming: pass subgraphs=True to receive tokens from specialist agents too.
Each event includes chunk["ns"] (namespace) identifying which subgraph emitted it.
Events from a subagent have a namespace containing "tools:".

Implementation notes:
  - Supervisor graph: stream updates + messages + custom to client
  - Custom events: nodes emit progress via get_stream_writer() (e.g. "researching topic X...")
  - CLI: iterate sync stream; Agent Server: SSE stream out of box (no extra work)
  - langgraph dev: Studio UI visualizes all stream modes live

Phase impact: streaming is wired at Phase 1 (graph compile-time zero cost). Only the caller
changes between consume-all vs stream. Ops agent tool lifecycle events via stream_mode="tools"
are useful for HITL visibility (see exact tool args before interrupt fires).

---

14. Middleware Catalog

Source: https://docs.langchain.com/oss/python/langchain/middleware/built-in
        https://docs.langchain.com/oss/python/langchain/middleware/custom

All middleware passed as list to create_agent(..., middleware=[...]). Order matters: earlier
middleware wraps later middleware. Middleware applies to the agent it is configured on.

14.1 Prebuilt middleware (from langchain.agents.middleware)

FAULT TOLERANCE:

  ModelRetryMiddleware
    Retries failed model calls (rate limits, timeouts, network errors, 5xx) with exponential
    backoff. Config: max_retries=3, backoff_factor=2.0, initial_delay=1.0, max_delay=60.0,
    jitter=True, retry_on=(Exception,), on_failure="continue"|"error"|callable.
    on_failure="continue" returns AIMessage with error instead of raising — agent can recover.
    RECOMMENDED: all agents in production.

  ToolRetryMiddleware
    Retries failed tool calls with exponential backoff.
    IMPORTANT: scope to API/network tools only, not filesystem tools.
    Config: max_retries=2, tools=["web_search", "fetch_url"], retry_on=(TimeoutError,)
    Filesystem read/write that fails should NOT be retried — surface the error.

  ModelFallbackMiddleware
    Switches to a backup model string if primary model is entirely unavailable.
    ModelFallbackMiddleware("anthropic:claude-sonnet-4-6") as fallback for primary Opus.
    Use after ModelRetryMiddleware so retries exhaust first.

HUMAN-IN-THE-LOOP / STEERING:

  HumanInTheLoopMiddleware (already in plan, also called "Steering" in docs)
    Source: docs call steering = HITL at specific decision points without restructuring the graph.
    interrupt_on={"write_file": True, "delete_file": True}
    Resume via Command(resume={interrupt_id: {"decisions": [{"type": "approve|edit|reject"}]}})

GUARDRAILS / PRIVACY:

  PIIMiddleware
    Detects and handles PII before it reaches the model or gets stored in logs.
    Built-in types: email, credit_card, ip, mac_address, url
    Custom types: regex string, compiled regex, or callable(content) → list[{text, start, end}]
    Strategies: redact ([REDACTED_EMAIL]), mask (****-1234), hash (deterministic), block (raise)
    Config: apply_to_input=True, apply_to_output=False, apply_to_tool_results=False
    With langchain>=1.3.2 and apply_to_output=True: also redacts streamed wire output.
    RECOMMENDED: add to supervisor for any user-facing deployment.
    Example: block API keys leaking out (detector=r"sk-[a-zA-Z0-9]{32}", strategy="block")
    Note: LangSmith gateway also has Presidio-based PII redaction at infrastructure level.

CONTEXT MANAGEMENT (from deepagents package):

  SummarizationMiddleware
    Auto-compresses conversation history when token threshold hit. Prevents context overflow on
    long-running threads. Uses a separate (cheaper) model for summarization.
    Alternative: manual SummarizationNode from langmem.short_term in the graph.

  MemoryMiddleware
    Loads persistent instructions from AGENTS.md files into the system prompt at startup.
    Cross-session knowledge without re-prompting the user every time.
    Sources: ["./AGENTS.md", "./agents/ops/AGENTS.md"]

  SkillsMiddleware
    On-demand domain knowledge from skill files. Only skill descriptions loaded at startup.
    Full skill file read when the agent decides it matches a task.
    Keeps context lean. Sources: ["./skills/"]

  FilesystemMiddleware
    Gives the agent a persistent workspace: read_file, write_file, edit_file, ls, glob, grep.
    Backend determines where files live (see section 15 — Execution Environment).
    Required for agents that need to read/write files across turns within a thread.

PLANNING / DELEGATION (from deepagents package):

  todoListMiddleware
    Gives the agent a todo list for multi-step task planning. Agent can create, check off,
    and update tasks. Prevents losing track of subtasks in long-running workflows.

  SubAgentMiddleware / createSubAgentMiddleware
    Delegates subtasks to named subagents running in isolated context windows.
    Subagents declared with: name, description, system_prompt, tools, model.
    Work can run in parallel. Supervisor stays focused on coordination, not execution.
    Different from "subgraph as tool" — this is explicit middleware-driven delegation.
    Requires FilesystemMiddleware + StateBackend for context passing.

PROMPT CACHING:

  AnthropicPromptCachingMiddleware (in langchain-anthropic package)
    Adds cache_control blocks to static parts of the system prompt automatically.
    Reduces cost on repeated calls with the same system prompt (5-min TTL, refreshed on hit).
    For create_deep_agent: automatically applied when using Anthropic model (zero config).
    For create_agent: add explicitly.

DYNAMIC MODEL:

  @wrap_model_call decorator (custom — see section 17)
    Swap model at runtime based on state, store, or runtime context.

14.2 Custom middleware hooks

  before_model(state) → state_update     — read/modify request before model call
  after_model(state) → state_update      — read/modify response after model call
  wrap_model_call(request, handler)       — full control: retry, short-circuit, swap model
  wrap_tool_call(request, handler)        — full control: retry, error handling, dynamic tools
  before_tool(state) → state_update      — read request before tool execution
  after_tool(state) → state_update       — read result after tool execution

14.3 Recommended middleware stack per agent

  Supervisor:
    middleware=[
        PIIMiddleware("email", strategy="redact", apply_to_input=True),
        PIIMiddleware("api_key", detector=r"sk-[a-zA-Z0-9]{32}", strategy="block"),
        ModelRetryMiddleware(max_retries=3),
        ModelFallbackMiddleware("anthropic:claude-sonnet-4-6"),
        HumanInTheLoopMiddleware(interrupt_on={"write_file": True}),
        SummarizationMiddleware(model=summarization_model, backend=backend),
        MemoryMiddleware(backend=backend, sources=["./AGENTS.md"]),
        AnthropicPromptCachingMiddleware(),
    ]

  Research agent:
    middleware=[
        ModelRetryMiddleware(max_retries=3),
        ToolRetryMiddleware(max_retries=2, tools=["web_search", "web_fetch"]),
    ]

  Ops agent:
    middleware=[
        ModelRetryMiddleware(max_retries=3),
        ToolRetryMiddleware(max_retries=2, tools=["fetch_url"]),  # NOT read_file/write_file
        HumanInTheLoopMiddleware(interrupt_on={"write_file": True, "delete_file": True}),
        FilesystemMiddleware(backend=StateBackend()),
    ]

---

15. Execution Environment

Source: https://docs.langchain.com/oss/python/langchain/agents#execution-environment
        https://docs.langchain.com/oss/python/deepagents/sandboxes
        https://docs.langchain.com/oss/python/deepagents/backends

Agents that only read/write files need FilesystemMiddleware + a backend.
Agents that execute code need a sandbox backend (adds execute shell tool).

Backend options:

+----------------------+---------------------------------------------------+-------------------------+
| Backend              | Description                                       | Use case                |
+----------------------+---------------------------------------------------+-------------------------+
| StateBackend         | Thread-scoped. Files in LangGraph state.          | Default for most agents |
|                      | Survives turns, not process restart.              |                         |
+----------------------+---------------------------------------------------+-------------------------+
| FilesystemBackend    | Local disk at specified root_dir.                 | Dev, restricted scope   |
|                      | Agent can read/write real files.                  |                         |
+----------------------+---------------------------------------------------+-------------------------+
| StoreBackend         | Durable cross-thread (LangGraph Store).           | Long-term agent memory  |
|                      | Files persist across sessions.                    | Shared knowledge        |
+----------------------+---------------------------------------------------+-------------------------+
| ContextHubBackend    | Durable in LangSmith Hub repo.                    | No separate Store infra |
+----------------------+---------------------------------------------------+-------------------------+
| CompositeBackend     | Routes different paths to different backends.     | Hybrid persistence      |
|                      | e.g. /memories/ → StoreBackend, rest → State      |                         |
+----------------------+---------------------------------------------------+-------------------------+
| Sandbox backends     | Isolated container. Adds execute tool.            | Code execution          |
| (Modal, Daytona,     | Filesys + shell. Protects host system.            | Install deps, run tests |
| Deno, local VFS)     |                                                   |                         |
+----------------------+---------------------------------------------------+-------------------------+
| LocalShellBackend    | Filesys + shell directly on host. No isolation.   | Dev only                |
+----------------------+---------------------------------------------------+-------------------------+

Recommended setup for this system:

  Phase 1-2: StateBackend (thread-scoped, zero infra)
  Phase 3+: CompositeBackend routing /memories/ → StoreBackend, rest → StateBackend
  Code execution (future): Modal or Daytona sandbox backend on ops agent

Code execution options (when needed):
  - Sandbox backends: shell commands, install packages, run CLIs, full OS filesystem
  - Interpreters: lightweight QuickJS runtime, eval tool, no shell/network, deterministic transforms

HITL interaction with exec environment:
  Ops agent with FilesystemMiddleware can stream tool lifecycle events (stream_mode="tools").
  Client sees exact write_file args BEFORE the interrupt fires — full transparency.

---

16. Context Management

Source: https://docs.langchain.com/oss/python/deepagents/harness#context-management
        https://docs.langchain.com/oss/python/langgraph/add-memory#summarize-messages

Four layers of context management, in order of application:

1. Skills — on-demand domain knowledge
   File-based skill definitions. Only descriptions loaded at startup.
   Full skill file loaded when agent needs it. Prevents bloating every call.
   Implementation: SkillsMiddleware(backend=backend, sources=["./skills/"])

2. Memory — persistent instructions
   AGENTS.md files loaded into system prompt at startup.
   Survives across sessions. User teaches agent conventions; agent applies on next run.
   Implementation: MemoryMiddleware(backend=backend, sources=["./AGENTS.md"])

3. Summarization — automatic history compression
   LangGraph approach: extend MessagesState with summary: str.
   Add summarize_conversation node that calls a cheap model, trims messages, stores summary.
   Trigger: when message count exceeds threshold (e.g. 20 messages).
   Resume path: summary injected as SystemMessage at start of next call_model node.
   Library approach: langmem.short_term.SummarizationNode (drop-in graph node).
   Middleware approach: SummarizationMiddleware from deepagents (for create_agent).
   Procedural memory: agent can update its own AGENTS.md instructions via store write.

4. Prompt caching — token cost reduction
   Anthropic: explicit cache_control blocks on static system prompt sections.
   AnthropicPromptCachingMiddleware applies automatically.
   Cache TTL: 5 min (ephemeral), 1h (specify "ttl": "1h" in cache_control).
   Cache hit visible in trace: cache_read_input_tokens vs cache_creation_input_tokens.
   OpenAI: implicit (automatic above 1024 tokens). No config needed.

Context budget (approximate for Anthropic claude-opus-4-8, 1M context):
  System prompt + cached sections: aim for < 50k tokens
  Active messages: summarize when > 20 exchanges
  Single specialist invocation: < 100k tokens (isolated context window per subagent)

---

17. Dynamic Model Selection

Source: https://docs.langchain.com/oss/python/langchain/models#dynamic-model-selection

Easy to implement. Recommended for Phase 3+.

Pattern: @wrap_model_call middleware intercepts each model call and swaps the model based on:
  - State (conversation length → use larger model for longer threads)
  - Store (user's saved preference → MODEL_MAP lookup)
  - Runtime context (cost tier, environment, user role → different model per tier)

Usage patterns for this system:

  1. Cost optimization: short conversations → claude-haiku-4-5, long → claude-opus-4-8
  2. Per-agent model: research agent uses a cheaper model for simple retrieval tasks
  3. User-selectable model: pass model string via runtime context, init_chat_model() per call
  4. Eval vs prod: eval runs use mock/cheap model; prod uses configured model

Important constraint from docs:
  Pre-bound models (with .bind_tools() already called) cannot be used with structured output
  in dynamic model selection. Initialize model instances without pre-binding; let middleware bind.

Implementation note: initialize model instances ONCE outside the middleware function to avoid
per-call overhead. Use a MODEL_MAP dict if switching between a fixed set of models.

Phase placement: basic model config in Phase 1 (single model from settings.py).
Dynamic selection middleware in Phase 3 when multi-model routing is needed.

---

18. Structured Output and Error Handling

Source: https://docs.langchain.com/oss/python/langchain/structured-output#error-handling-strategies

LangChain structured output for agents uses ToolStrategy:
  response_format=ToolStrategy(schema=MyPydanticModel, handle_errors=...)

handle_errors options:
  True (default)    — catch all errors, return default retry message
  False             — all errors raised, no retry
  "string"          — fixed retry message sent to model as tool result
  ExceptionType     — only retry on this exception class
  (Exc1, Exc2)      — only retry on these exception classes
  callable(e) → str — custom error message function per exception type

Catchable error types:
  StructuredOutputValidationError   — model returned wrong schema
  MultipleStructuredOutputsError    — model returned multiple outputs when one expected

Use cases in this system:
  - Supervisor structured routing decision → handle_errors catches malformed route
  - Research agent structured summary → retry with validation message on schema mismatch
  - Ops agent structured action plan → handle_errors=(StructuredOutputValidationError,)

Tool error handling (separate from structured output):
  wrap_tool_call middleware catches runtime tool errors and returns ToolMessage with
  descriptive error content instead of raising — model gets feedback and can retry with
  corrected input. Only handle runtime errors (bad input to tool), NOT:
    - network failures (use ToolRetryMiddleware)
    - tool implementation bugs (should bubble up)
    - schema mismatch (already handled by framework)

---

19. Guardrails

Source: https://docs.langchain.com/oss/python/langchain/guardrails
        https://docs.langchain.com/langsmith/mask-inputs-outputs

Guardrails = deterministic enforcement that runs regardless of what the model outputs.
Two layers: middleware (runtime) + LangSmith (trace storage).

Runtime guardrails via PIIMiddleware:

  +-------------+------------------------------------+------------------------------------------+
  | PII type    | Default detector                   | Strategy options                         |
  +-------------+------------------------------------+------------------------------------------+
  | email       | RFC 5322 pattern                   | redact, mask, hash, block                |
  | credit_card | Luhn-validated pattern             | redact, mask, hash, block                |
  | ip          | IPv4/IPv6 pattern                  | redact, mask, hash, block                |
  | mac_address | MAC pattern                        | redact, mask, hash, block                |
  | url         | URL pattern                        | redact, mask, hash, block                |
  | custom      | Your regex / callable              | redact, mask, hash, block                |
  +-------------+------------------------------------+------------------------------------------+

  Custom detector example: block API keys leaking through output
    PIIMiddleware("api_key", detector=r"sk-[a-zA-Z0-9]{32}", strategy="block",
                  apply_to_output=True)

Content moderation (no prebuilt middleware — custom wrap_model_call):
  Implement as a wrap_model_call hook that inspects the AIMessage after model call.
  If content violates policy, return a blocked AIMessage instead.
  Or: call a moderation API (e.g. OpenAI moderation endpoint) inside before_model hook.

LangSmith trace-level guardrails:
  - Mask inputs/outputs: rule-based regex masking before trace storage
    (langsmith/mask-inputs-outputs — environment variable or Client config)
  - Presidio integration: named entity PII redaction on trace data
  - ABAC: deny access to datasets tagged Contains-PII=true for non-authorized users
  - Conditional tracing: disable tracing entirely for zero-retention clients

Recommended guardrails for this system:
  Tier 1 (Phase 1): PIIMiddleware on supervisor (email redact, api_key block)
  Tier 2 (Phase 3): LangSmith trace masking (regex on prompt inputs before storage)
  Tier 3 (future): content moderation custom middleware if system becomes multi-tenant

---

20. Planning and Delegation

Source: https://docs.langchain.com/oss/python/langchain/agents#planning-and-delegation
        https://docs.langchain.com/oss/python/deepagents/harness#summarization-and-context-offloading

LangChain provides two complementary mechanisms:

A) todoListMiddleware — per-agent task planning
   Agent can create a todo list, check off items, update status mid-run.
   Prevents losing track of multi-step workflows within a single long run.
   Add to supervisor when tasks require more than 3-4 sequential steps.

B) SubAgentMiddleware — parallel isolated delegation
   Supervisor delegates to named subagents running in their own isolated context windows.
   Subagents defined at middleware config time: name, description, system_prompt, tools, model.
   Work can run in parallel (supervisor stays clean, subagents quarantine heavy work).
   Different from "subgraph as tool" pattern (ADR-002) — explicit middleware-driven delegation.
   Use SubAgentMiddleware when: tasks benefit from parallelism, or context isolation is critical
   (e.g. researching multiple topics simultaneously, each in a fresh context window).

Relationship between ADR-002 (subgraph-as-tool) and SubAgentMiddleware:
  Both patterns can coexist. Subgraph-as-tool is the baseline architecture.
  SubAgentMiddleware adds parallel execution and explicit task isolation on top.
  Decision tree:
    Simple sequential delegation → subgraph-as-tool (Phase 1)
    Parallel tasks or context overflow → SubAgentMiddleware (Phase 4+)

Phase placement: todoListMiddleware in Phase 2. SubAgentMiddleware in Phase 4 (hardening).

---

ADR-011: Streaming at graph level, not provider level

  Decision: Use LangGraph graph.astream() with stream_mode=["updates", "messages", "custom"]
  rather than provider-level streaming (model.stream()).
  Reasoning: Graph-level streaming aggregates events across all nodes — supervisor LLM tokens,
  specialist LLM tokens (subgraphs=True), tool lifecycle (stream_mode="tools"), and custom
  progress events. Provider-level streaming only covers one model call at a time. Agent Server
  already serves SSE from graph-level stream — zero extra work for production.

ADR-012: PIIMiddleware as the primary guardrail

  Decision: PIIMiddleware on supervisor agent for all deployments. No custom moderation layer
  in Phase 1-3.
  Source: https://docs.langchain.com/oss/python/langchain/guardrails
  Reasoning: Built-in, covers the highest-risk PII types. Custom content moderation adds
  significant latency and complexity. LangSmith trace masking covers the storage-level risk.
  Content moderation via custom wrap_model_call hook is available as Phase 4+ hardening.

ADR-013: DuckDB as the domain database; Postgres for checkpointing

  Decision: The system uses two separate database layers with distinct roles:

  1. DuckDB — domain / operational database (REQUIRED)
     All sensor data, telemetry, operational records, and structured domain data live in DuckDB.
     Agents access DuckDB exclusively via the LangChain SQL agent tool pattern — NOT via any
     native LangChain checkpointer or vector store integration (none exists for DuckDB).

     Tool pattern (4 tools, following LangChain SQL agent docs):
       @tool duckdb_list_tables()        → comma-separated list of tables
       @tool duckdb_schema(table_names)  → schema + sample rows
       @tool duckdb_query(query)         → executes SQL against DuckDB
       @tool duckdb_query_checker(query) → validates query before execution

     Guardrails on DuckDB tools:
       - System prompt: DO NOT make DML statements (INSERT, UPDATE, DELETE, DROP)
       - duckdb_query_checker always called before duckdb_query
       - HumanInTheLoopMiddleware(interrupt_on={"duckdb_query": True}) for HITL approval
         before any query execution (read or write)
       - Scoped permissions: agent DB user has read-only access by default

     Phase placement: duckdb_query tools added to ops agent in Phase 2 (tool integration).

  2. Postgres (via LangGraph Agent Server) — conversation state / checkpointing
     LangGraph thread checkpoints (short-term memory, conversation history, interrupt state)
     use AsyncPostgresSaver via Agent Server. This is the only LangGraph-native persistence
     backend for production. DuckDB is NOT used for checkpointing.

  Source: LangChain SQL agent docs (oss/python/langchain/sql-agent, oss/python/langgraph/sql-agent).
  DuckDB not listed in LangChain checkpointer or vector store integrations.
  Reasoning: DuckDB is analytically excellent for structured operational data. The @tool wrapper
  pattern gives agents full SQL access without requiring a native LangChain integration. Postgres
  handles the agent infrastructure layer (state) independently of the domain data layer (DuckDB).

ADR-014: Middleware preferred for infrastructure faults; application code for uncovered cases

  Decision: ModelRetryMiddleware + ToolRetryMiddleware + ModelFallbackMiddleware handle
  infrastructure-level faults (rate limits, 5xx, transient failures, provider outages).
  These middleware layers are preferred over application code for the cases they cover because
  they centralize retry logic, keep tools clean, and avoid duplicating boilerplate error handling.
  However, application code (try/except in agent or tool functions) is the CORRECT and EXPECTED
  fallback for any fault case not covered by existing middleware.

  Source: https://docs.langchain.com/oss/python/langchain/agents#fault-tolerance
  Docs quote: "Fault tolerance middleware handles these at the infrastructure level so your
  tools and business logic don't need try/catch around every call."

  Reasoning: The quoted docs refer specifically to the cases middleware does cover — not a
  directive to avoid application-level error handling entirely. When a fault falls outside the
  middleware catalog (e.g. DuckDB query result validation, domain-specific error codes, partial
  result handling), write application code. Middleware is the preferred layer where it fits;
  application code is the correct fallback where it doesn't.

  Scope of existing middleware (use middleware here):
    ModelRetryMiddleware  → rate limits, 5xx, timeouts on model calls
    ToolRetryMiddleware   → transient API failures on web_search, fetch_url, etc.
    ModelFallbackMiddleware → provider outage, switch to backup model

  Use application code for (middleware does NOT cover these):
    - DuckDB query result validation (wrong columns, unexpected nulls)
    - Tool output business logic errors (e.g. sensor returns out-of-range value)
    - HITL rejection handling (user rejects an action — resume or abort flow)
    - Domain exceptions that need custom recovery logic

ADR-015: Dynamic model selection deferred to Phase 3

  Decision: Phase 1 uses single configured model (init_chat_model from settings.py).
  Phase 3+ adds @wrap_model_call middleware for per-request model switching.
  Source: https://docs.langchain.com/oss/python/langchain/models#dynamic-model-selection
  Reasoning: Zero overhead in Phase 1. Middleware pattern is non-breaking — add it without
  restructuring the graph. Priority order: cost optimization (haiku vs opus by complexity),
  then user-selectable model via runtime context.

ADR-016: Structured output with handle_errors on specialist agents

  Decision: Specialist agents that return structured output use ToolStrategy with handle_errors.
  Source: https://docs.langchain.com/oss/python/langchain/structured-output#error-handling-strategies
  Reasoning: Without handle_errors, schema mismatch silently fails or raises. handle_errors
  feeds a corrective message back to the model, enabling self-repair without human intervention.
  Default handle_errors=True for most cases; custom callable for agents with complex error
  semantics (StructuredOutputValidationError vs MultipleStructuredOutputsError need different
  retry messages).

---
