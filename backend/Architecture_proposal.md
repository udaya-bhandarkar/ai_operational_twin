---
  RAIC Backend — Architecture Proposal (Revised)

  Author role: Principal Software Architect
  Phase: Architecture Planning — no implementation code
  Source of truth: docs/requirements.md, docs/non_goals.md, docs/feature_inventory.md, docs/product_brief.md,
  docs/architecture_task.md

  ---
  1. Architecture Overview

  Single-process, modular multi-agent LLM platform organized around three consumer concerns that must never leak into one
  another:

  ┌─────────────────────┬────────────────────────┬──────────────────────────────────────┐
  │      Consumer       │      Entry point       │             What it sees             │
  ├─────────────────────┼────────────────────────┼──────────────────────────────────────┤
  │ Backend Runtime     │ orchestrator/runner.py │ Everything below the API layer       │
  ├─────────────────────┼────────────────────────┼──────────────────────────────────────┤
  │ Frontend / QA UI    │ api/ only              │ contracts/ types + API responses     │
  ├─────────────────────┼────────────────────────┼──────────────────────────────────────┤
  │ Evaluation Pipeline │ evals/runner.py        │ Orchestrator directly, never via API │
  └─────────────────────┴────────────────────────┴──────────────────────────────────────┘

  Every shared type definition lives in contracts/. Every component that crosses a consumer boundary uses only contracts/
  types — not internal models.

  ┌────────────────────────────────────────────────────────────────┐
  │   CLI                    API (REST + SSE)                      │  ← Consumer interfaces
  └────────────┬──────────────────┬───────────────────────────────┘
               │                  │
  ┌────────────▼──────────────────▼───────────────────────────────┐
  │                     Orchestrator Runner                        │  ← Runtime coordination
  └──┬──────────┬──────────────┬──────────────┬───────────────────┘
     │          │              │              │
     ▼          ▼              ▼              ▼
  Agents    Tool Layer     State Mgr     HITL Handler
     │          │              │              │
     ▼          ▼              ▼              ▼
  Providers  Tool Servers  Storage       Approval Channels
     │
     ▼
  contracts/   ← bottom of stack, no upstream imports

  ---
  2. Major Components and Responsibilities

  2.1 contracts/ — Shared Type Definitions

  Bottom of the dependency stack. Imported by every layer. Contains no logic — only data definitions (dataclasses or
  Pydantic models).

  ┌─────────────┬─────────────────────────────────────────────────────────────────┐
  │   Module    │                            Contains                             │
  ├─────────────┼─────────────────────────────────────────────────────────────────┤
  │ tool.py     │ ToolDefinition, ToolRequest, ToolResult                         │
  ├─────────────┼─────────────────────────────────────────────────────────────────┤
  │ provider.py │ Message, LLMResponse, StreamChunk, StopReason                   │
  ├─────────────┼─────────────────────────────────────────────────────────────────┤
  │ state.py    │ Thread, Run, Checkpoint, InterruptState, RunStatus              │
  ├─────────────┼─────────────────────────────────────────────────────────────────┤
  │ approval.py │ ApprovalRequest, ApprovalDecision, DecisionType                 │
  ├─────────────┼─────────────────────────────────────────────────────────────────┤
  │ events.py   │ RunEvent, ToolCallEvent, ApprovalEvent, StreamEvent, ErrorEvent │
  ├─────────────┼─────────────────────────────────────────────────────────────────┤
  │ evals.py    │ EvalCase, EvalResult, EvalReport, ScorerType                    │
  └─────────────┴─────────────────────────────────────────────────────────────────┘

  Rule: No module outside contracts/ defines its own wire-format types. All serialization crosses boundaries using
  contracts/ types only.

  ---
  2.2 agents/ — Agent Logic

  Base contract: receive AgentTask → return AgentResult (both from contracts/).
  Agents are stateless computation units. State lives in state/.

  Supervisor Agent
  - Receives raw user task
  - Produces SubtaskPlan: ordered list of (subtask, target_agent)
  - Synthesizes final output from specialist results
  - Owns no tools

  Research Agent
  - Domain: information gathering
  - Allowed tools declared in permissions.yaml: web_search, web_fetch
  - Returns structured research output

  Ops/Files Agent
  - Domain: filesystem operations
  - Allowed tools declared in permissions.yaml: read_file, write_file, list_directory
  - All write operations flagged approval_required: true

  Extension rule: new agent = new subdirectory + agent.py + permissions.yaml + prompts/system.txt. Zero changes to existing
  code.

  ---
  2.3 tools/ — Tool Servers and Permission Enforcement

  Agents never import tool implementations. All tool calls route through ToolRegistry.dispatch().

  Permission manifest (per agent, per tool):

  # agents/ops/permissions.yaml
  tools:
    read_file:
      allowed: true
      approval_required: false
      allowed_operations: [read]
    write_file:
      allowed: true
      approval_required: true
      allowed_operations: [write, create]
      risk_level: medium
    list_directory:
      allowed: true
      approval_required: false

  Tool execution path:
  Agent emits ToolRequest (name, params, agent_id)
    └─► ToolRegistry.dispatch()
          ├─► PermissionsManager.check(agent_id, tool_name)
          │     ├── denied → raise ToolPermissionError (logged, surfaced to agent)
          │     ├── approval_required → emit ApprovalRequest → pause execution
          │     └── allowed → continue
          └─► ToolServer.execute(params) → ToolResult

  Every ToolDefinition declares: name, description, input_schema, output_schema, risk_level, allowed_agents.

  ---
  2.4 providers/ — LLM Provider Adapters

  Agents call ProviderClient interface. Never import Anthropic or OpenAI SDKs directly.

  Interface:
  - generate(messages, tools, config) → LLMResponse
  - stream(messages, tools, config) → AsyncIterator[StreamChunk]
  - count_tokens(messages) → int

  Each adapter normalizes: message format, tool-call format, streaming chunks, error codes, stop reasons.

  ProviderFactory.create(config) → ProviderClient — provider selected at startup via config. Switching = one config change.

  ---
  2.5 state/ — Persistence Layer

  Identity model:

  ┌───────────────┬────────────────────────┬───────────────────────────────────────────────────────────┐
  │      ID       │         Scope          │                         Lifecycle                         │
  ├───────────────┼────────────────────────┼───────────────────────────────────────────────────────────┤
  │ thread_id     │ Conversation / session │ Stable for the life of a conversation. Survives restarts. │
  ├───────────────┼────────────────────────┼───────────────────────────────────────────────────────────┤
  │ run_id        │ Single invocation      │ New run per call, per resume. A thread has many runs.     │
  ├───────────────┼────────────────────────┼───────────────────────────────────────────────────────────┤
  │ checkpoint_id │ State snapshot         │ Created after each agent step and each tool call.         │
  ├───────────────┼────────────────────────┼───────────────────────────────────────────────────────────┤
  │ interrupt_id  │ Paused state           │ Present only when a run is waiting for HITL approval.     │
  └───────────────┴────────────────────────┴───────────────────────────────────────────────────────────┘

  Thread state contains:
  - thread_id, run_id
  - conversation_history — ordered messages
  - agent_outputs — map of step_id → AgentResult
  - stream_event_history — ordered log of all RunEvent items in this run (required for replay)
  - interrupt_state — present when paused: ApprovalRequest + context + checkpoint reference
  - run_metadata — start time, config snapshot, cost, latency, token usage so far

  Pluggable backends: StorageBackend ABC with SQLite (dev), Postgres (prod), Memory (tests).

  Resume: load Thread by thread_id + latest checkpoint_id, reconstruct RunContext, re-enter Orchestrator at last completed
  step, restore stream_event_history for replay.

  ---
  2.6 hitl/ — Human-in-the-Loop

  Pattern: Interrupt → Checkpoint → Notify → Wait → Resume

  1. PermissionsManager flags tool approval_required
  2. HITLHandler.pause() called — emits ApprovalRequest, suspends coroutine
  3. StateManager.checkpoint() — run safely serialized, interrupt_state written
  4. HITLHandler.notify(request) — sends to approval channel
  5. Execution suspends
  6. Human acts via CLI (raic approve <id>) or API (POST /approvals/{id}/approve)
  7. HITLHandler.resume(decision) — decision types: Approve, Reject, Modify(new_params)
  8. On Approve/Modify: execute tool, continue
  9. On Reject: return ToolResult(success=False, rejected=True), agent handles gracefully

  All approval events emitted as ApprovalEvent (from contracts/events.py) and logged.

  Approval channels: channels/cli.py (current), channels/api.py (future webhook/HTTP).

  ---
  2.7 orchestrator/ — Runtime Loop

  Owns execution flow only. Coordinates all components without containing their logic.

  RunContext carries: thread_id, run_id, config, ProviderClient, ToolRegistry, StateManager, HITLHandler, observability
  references.

  runner.py run loop:
  1. Create RunContext, initialize thread in StateManager
  2. Call Supervisor agent
  3. For each subtask in SubtaskPlan: route to specialist, await AgentResult
  4. Checkpoint after each step
  5. On ApprovalRequest: delegate to HITLHandler, suspend, resume on decision
  6. Emit RunEvent for each significant action
  7. Return final output, mark run complete

  ---
  2.8 api/ — External Interface Layer

  Exposes the runtime to frontend clients, QA tooling, and remote approval actors. Imports only orchestrator/ and state/.
  Uses only contracts/ types in request/response bodies.

  Routes:

  ┌────────┬─────────────────────────────────────┬──────────────────────────────────────┐
  │ Method │                Path                 │               Purpose                │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ POST   │ /runs                               │ Create and start a new run           │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ GET    │ /runs/{run_id}                      │ Run status and metadata              │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ GET    │ /threads/{thread_id}                │ Thread state and history             │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ GET    │ /threads/{thread_id}/events         │ SSE stream of RunEvent items         │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ GET    │ /threads/{thread_id}/checkpoints    │ List checkpoints for replay/debug    │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ GET    │ /threads/{thread_id}/stream-history │ Full replay of event stream (for QA) │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ POST   │ /approvals/{approval_id}/approve    │ Approve a pending action             │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ POST   │ /approvals/{approval_id}/reject     │ Reject a pending action              │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ POST   │ /approvals/{approval_id}/modify     │ Approve with modified params         │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ POST   │ /threads/{thread_id}/resume         │ Resume a paused thread               │
  ├────────┼─────────────────────────────────────┼──────────────────────────────────────┤
  │ GET    │ /approvals/pending                  │ List all pending approval requests   │
  └────────┴─────────────────────────────────────┴──────────────────────────────────────┘

  Streaming: Server-Sent Events (SSE). Each RunEvent from contracts/events.py is emitted as a typed SSE event. Frontend
  subscribes to /threads/{thread_id}/events for live updates.

  Consumer isolation rule: frontend never calls orchestrator/, agents/, or tools/ directly. All access through api/. QA
  tooling inspects threads, checkpoints, and event streams via api/ only.

  ---
  2.9 observability/ — Logging, Tracing, Metrics

  Imported by every layer. Imports nothing from the system.

  Structured logging — every significant event emits a JSON log entry:
  {
    "timestamp": "...",
    "thread_id": "...",
    "run_id": "...",
    "step_id": "...",
    "event_type": "tool_call|agent_result|approval_request|...",
    "agent": "...",
    "provider": "...",
    "data": {},
    "cost_usd": 0.0,
    "latency_ms": 0,
    "input_tokens": 0,
    "output_tokens": 0
  }

  OpenTelemetry traces — one root span per run_id, child spans per agent step and tool call. Backend-agnostic (Jaeger,
  Honeycomb, Datadog).

  Metrics tracked:

  ┌────────────────────┬──────────────────────────────────────────────────────┐
  │       Metric       │                      Dimensions                      │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Token usage        │ per run, per agent, per provider, per model          │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Cost (USD)         │ per run, per agent, per provider                     │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Latency            │ per run, per agent step, per tool call, per LLM call │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Tool call count    │ per tool, per agent, per run                         │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Tool failure rate  │ per tool                                             │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Approval wait time │ per approval, per agent, per tool                    │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Approval decision  │ approve/reject/modify rate                           │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Eval pass rate     │ per suite, per agent, per dataset version            │
  ├────────────────────┼──────────────────────────────────────────────────────┤
  │ Eval cost          │ per suite                                            │
  └────────────────────┴──────────────────────────────────────────────────────┘

  Failure monitoring: every unhandled exception captured with full thread_id/run_id/step_id context.

  ---
  3. Data Flow (End-to-End)

  User: raic run "research X and save report to output/report.md"
    │
    ▼
  CLI → Orchestrator.create_run(task, config)
          └─► StateManager.create_thread(thread_id, run_id)
          └─► ObservabilityTracer.start_span(run_id)
    │
    ▼
  SupervisorAgent.run(AgentTask)
      └─► ProviderClient.generate(messages + tools)
      └─► SubtaskPlan: [research_subtask → ResearchAgent, write_subtask → OpsAgent]
    │
    ▼
  [Step 1] ResearchAgent.run(research_subtask)
      └─► ProviderClient.generate(...)
      └─► emit ToolRequest: web_search("X")
      └─► ToolRegistry.dispatch("research_agent", "web_search", params)
            └─► PermissionsManager → allowed
            └─► WebToolServer.execute(params) → ToolResult
      └─► ProviderClient.generate([..., tool_result])
      └─► returns AgentResult(research_data)
    │
    ▼
  StateManager.checkpoint()
  emit RunEvent(type=agent_step_complete, step=1, agent=research)
    │
    ▼
  [Step 2] OpsAgent.run(write_subtask)
      └─► emit ToolRequest: write_file("output/report.md", content)
      └─► ToolRegistry.dispatch("ops_agent", "write_file", params)
            └─► PermissionsManager → approval_required
            └─► HITLHandler.pause()
                  └─► StateManager.checkpoint() [interrupt_state written]
                  └─► emit ApprovalEvent(type=pending, approval_id=...)
                  └─► [via CLI] "OpsAgent wants to write output/report.md. Approve? [y/n/m]"
    │
    ▼                                    ← execution suspended here
  User approves: raic approve <id>
    │
    ▼
  HITLHandler.resume(Approve)
      └─► emit ApprovalEvent(type=approved, ...)
      └─► FilesystemToolServer.execute(params) → ToolResult
      └─► OpsAgent resumes → returns AgentResult(file_written)
    │
    ▼
  StateManager.checkpoint() [interrupt_state cleared]
    │
    ▼
  SupervisorAgent synthesizes → returns final AgentResult
    │
    ▼
  StateManager.mark_run_complete(run_id)
  emit RunEvent(type=run_complete)
  ObservabilityTracer.end_span()
    │
    ▼
  CLI streams final output to user

  ---
  4. Repository Structure

  raic/
  │
  ├── .github/
  │   └── workflows/
  │       ├── ci.yml              # Lint + type check + unit tests + integration tests
  │       ├── eval.yml            # Eval suite (on PR + nightly)
  │       └── deploy.yml          # Staging deploy + smoke tests + manual prod gate
  │
  ├── contracts/                  # ← Shared types. No logic. Imported by all layers.
  │   ├── tool.py                 # ToolDefinition, ToolRequest, ToolResult
  │   ├── provider.py             # Message, LLMResponse, StreamChunk, StopReason
  │   ├── state.py                # Thread, Run, Checkpoint, InterruptState, RunStatus
  │   ├── approval.py             # ApprovalRequest, ApprovalDecision, DecisionType
  │   ├── events.py               # RunEvent, ToolCallEvent, ApprovalEvent, StreamEvent
  │   └── evals.py                # EvalCase, EvalResult, EvalReport
  │
  ├── agents/                     # Agent logic. Imports contracts/ and providers/ only.
  │   ├── base.py                 # AbstractAgent, AgentTask, AgentResult
  │   ├── supervisor/
  │   │   ├── agent.py
  │   │   ├── router.py           # SubtaskPlan routing
  │   │   └── prompts/
  │   │       └── system.txt
  │   ├── research/
  │   │   ├── agent.py
  │   │   ├── permissions.yaml    # Tool permission manifest for this agent
  │   │   └── prompts/
  │   │       └── system.txt
  │   └── ops/
  │       ├── agent.py
  │       ├── permissions.yaml
  │       └── prompts/
  │           └── system.txt
  │
  ├── tools/                      # Tool servers. No agent imports.
  │   ├── base.py                 # ToolServer (ABC), ToolRegistry
  │   ├── permissions.py          # PermissionsManager
  │   ├── web/
  │   │   └── server.py           # web_search, web_fetch
  │   └── filesystem/
  │       └── server.py           # read_file, write_file, list_directory
  │
  ├── providers/                  # LLM adapters. No agent or tool imports.
  │   ├── base.py                 # ProviderClient (ABC)
  │   ├── factory.py              # ProviderFactory.create(config)
  │   ├── anthropic/
  │   │   └── client.py
  │   └── openai/
  │       └── client.py
  │
  ├── state/                      # Persistence. Imports contracts/ only.
  │   ├── manager.py              # StateManager
  │   └── backends/
  │       ├── base.py             # StorageBackend (ABC)
  │       ├── sqlite.py
  │       ├── postgres.py
  │       └── memory.py           # Tests only
  │
  ├── hitl/                       # Human-in-the-loop. Imports contracts/ and state/.
  │   ├── handler.py              # HITLHandler (pause / notify / resume)
  │   └── channels/
  │       ├── base.py             # ApprovalChannel (ABC)
  │       ├── cli.py
  │       └── api.py              # Future: webhook / HTTP callback
  │
  ├── orchestrator/               # Runtime loop. Coordinates all inner packages.
  │   ├── runner.py               # Main run loop
  │   └── context.py              # RunContext
  │
  ├── api/                        # ← External interface. Imports orchestrator/ and state/.
  │   ├── app.py                  # App definition (FastAPI / Starlette)
  │   ├── routes/
  │   │   ├── runs.py             # POST /runs, GET /runs/{run_id}
  │   │   ├── threads.py          # GET /threads/{id}, /events, /checkpoints, /stream-history
  │   │   └── approvals.py        # POST /approvals/{id}/approve|reject|modify, GET /pending
  │   └── streaming.py            # SSE emitter
  │
  ├── observability/              # Cross-cutting. Imported by all. Imports nothing from system.
  │   ├── logger.py               # Structured JSON logger
  │   ├── tracer.py               # OpenTelemetry setup
  │   └── metrics.py              # Cost, latency, tokens, tool calls, approvals
  │
  ├── config/
  │   ├── schema.py               # Config dataclasses (validated at startup)
  │   ├── loader.py               # Merge: env vars + YAML + CLI args
  │   └── environments/
  │       ├── dev.yaml
  │       ├── staging.yaml
  │       └── prod.yaml
  │
  ├── cli/                        # Local CLI. Imports orchestrator/ and state/.
  │   ├── main.py                 # Entry point: raic
  │   └── commands/
  │       ├── run.py              # raic run "<task>"
  │       ├── eval.py             # raic eval [--suite <name>]
  │       ├── approve.py          # raic approve <approval_id>
  │       └── resume.py           # raic resume <thread_id>
  │
  ├── evals/                      # ← Evaluation pipeline. Imports orchestrator/ directly.
  │   ├── runner.py               # EvalRunner
  │   ├── scorers/
  │   │   ├── base.py             # Scorer (ABC)
  │   │   ├── exact_match.py
  │   │   ├── contains.py
  │   │   └── llm_judge.py
  │   ├── datasets/
  │   │   ├── v1/                 # Dataset versioning enforced from day one
  │   │   │   ├── research_agent.jsonl
  │   │   │   ├── ops_agent.jsonl
  │   │   │   └── end_to_end.jsonl
  │   │   └── README.md           # Dataset schema docs
  │   ├── cases/
  │   │   ├── research_agent_evals.py
  │   │   ├── ops_agent_evals.py
  │   │   └── end_to_end_evals.py
  │   └── reports/                # Generated outputs — gitignored
  │
  ├── tests/
  │   ├── unit/
  │   │   ├── agents/
  │   │   ├── tools/
  │   │   ├── providers/
  │   │   ├── state/
  │   │   └── hitl/
  │   └── integration/
  │       ├── test_orchestrator.py
  │       ├── test_hitl_flow.py
  │       └── test_checkpoint_resume.py
  │
  ├── docs/
  │   ├── requirements.md
  │   ├── non_goals.md
  │   ├── feature_inventory.md
  │   ├── product_brief.md
  │   ├── architecture_task.md
  │   └── architecture_decisions.md
  │
  ├── scripts/
  │   ├── setup_dev.sh
  │   ├── run_evals.sh
  │   └── smoke_test.sh
  │
  ├── pyproject.toml
  ├── .env.example
  ├── .gitignore
  ├── CLAUDE.md
  └── README.md

  Dependency rules (enforced by linter):

  contracts/       → nothing
  observability/   → nothing from system
  providers/       → contracts/
  tools/           → contracts/
  state/           → contracts/
  hitl/            → contracts/, state/
  agents/          → contracts/, providers/
  orchestrator/    → agents/, tools/, state/, hitl/, contracts/, observability/
  api/             → orchestrator/, state/, contracts/
  cli/             → orchestrator/, state/, contracts/
  evals/           → orchestrator/, contracts/   (isolated — never api/)

  ---
  5. ADR Recommendations

  ADR-001: contracts/ as dependency root

  Decision: All shared wire-format types live in contracts/. No layer defines its own request/response types.

  Reasoning: Prevents three copies of "what does a ToolResult look like" drifting apart. The API, runtime, and eval pipeline
  all speak the same language without coupling their implementations. Contracts become the de facto API specification.

  Alternatives: Shared types defined in the layer that "owns" them (e.g., ToolResult defined in tools/). All consumers
  import from tools/.

  Tradeoffs: contracts/ is a central change point. A breaking change in contracts/ affects all layers simultaneously.
  Acceptable — that is the correct behavior for a type system change.

  ---
  ADR-002: api/ as the only public interface

  Decision: Frontend, QA tooling, and remote approval actors interact only with api/. They never import orchestrator/,
  agents/, or tools/.

  Reasoning: Without this boundary, frontend changes can accidentally couple to internal implementation details. QA tooling
  built against orchestrator/ internals breaks on every refactor. The api/ surface is narrow, versioned, and stable.

  Alternatives: Let consumers import internal packages directly.

  Tradeoffs: Adds one serialization boundary (internal types → contracts types → HTTP). Correct tradeoff — the boundary
  catches mismatches at compile/type-check time rather than at runtime.

  ---
  ADR-003: Thread ID and Run ID are distinct, both persisted

  Decision: thread_id identifies a conversation (stable across all runs). run_id identifies a single invocation (new per
  start and per resume). Both stored on every event, log line, and checkpoint.

  Reasoning: Required for LangGraph Studio compatibility (see Section 8). Required for QA: "show me all runs for thread X"
  vs "show me exactly what happened in run Y". Required for debugging: interrupt, modify, resume creates a new run_id on the
  same thread_id.

  Alternatives: Single ID per execution.

  Tradeoffs: Every log line and checkpoint carries both IDs — minor overhead, major debuggability benefit.

  ---
  ADR-004: Stream event history persisted per run

  Decision: Every RunEvent emitted during a run is appended to the thread's stream_event_history. Accessible via GET
  /threads/{thread_id}/stream-history.

  Reasoning: Replay is required for QA (reproduce exact agent behavior). Debugging is required for developers (what exactly
  happened in step 3 before the approval). Without persisted history, these are impossible after the run ends.

  Alternatives: Stream-only (no persistence), reconstruct from checkpoints.

  Tradeoffs: Storage cost per run. Mitigated by configurable retention policy — keep history for N days, then prune.

  ---
  ADR-005: Supervisor/Worker over peer-to-peer

  Decision: Supervisor owns task decomposition and routing. Specialists have no knowledge of each other.

  Reasoning: Single mental model. Traceable. New specialists require no changes to existing agents. Peer-to-peer creates
  implicit coupling — any agent can call any agent, impossible to audit.

  Tradeoffs: Supervisor is a logical bottleneck. Mitigated by checkpointing — re-enterable from checkpoint if supervisor
  fails mid-run.

  ---
  ADR-006: MCP-style tool server isolation

  Decision: Agents never import tool implementations. All tool calls route through ToolRegistry.dispatch().

  Reasoning: Single permission enforcement point. Tools mockable in tests without touching agent code. Permission manifest
  per agent is auditable and reviewable. Mirrors MCP protocol — future migration to actual MCP servers requires only
  replacing ToolServer implementations.

  Tradeoffs: One indirection layer. Worth it for safety, testability, and future compatibility.

  ---
  ADR-007: Interrupt/Resume HITL over blocking prompts

  Decision: On approval_required, execution pauses. Checkpoint + interrupt_state written. Resume via
  HITLHandler.resume(decision).

  Reasoning: Approval may take minutes or hours. Blocking a live coroutine is not production-viable. Checkpoint-then-resume
  supports CLI and async channels (webhook, API) without changing agent code.

  Tradeoffs: Resume requires checkpoint load. Adds one code path per tool execution. Worth it — without this, HITL only
  works in synchronous CLI sessions.

  ---
  ADR-008: Tool permission manifests are per-agent YAML files

  Decision: Each agent directory contains permissions.yaml declaring: allowed tools, approval_required flag per tool,
  allowed_operations, risk_level.

  Reasoning: Permissions as code — reviewable in PRs, versioned in git, auditable without reading Python. Adding a new tool
  to an agent is a one-line YAML change, not a code change.

  Alternatives: Permissions hardcoded in PermissionsManager, or declared as Python decorators.

  Tradeoffs: YAML must be validated at startup. Mitigated by schema validation in config/loader.py.

  ---
  ADR-009: Offline eval harness with versioned JSONL datasets

  Decision: Evals are separate from unit tests. evals/runner.py drives them. Datasets stored as JSONL under
  evals/datasets/v1/. Dataset version is part of every EvalReport.

  Reasoning: Agent behavior is probabilistic and context-dependent — unit tests cannot cover it. Offline evals with fixed,
  versioned datasets give reproducible regression signal. Versioning datasets prevents silent dataset drift breaking
  historical comparisons.

  Alternatives: Online evals only, using production traffic.

  Tradeoffs: Datasets go stale relative to production. Mitigated by: version tagging, quarterly review process, regression
  gate in CI.

  ---
  ADR-010: Monorepo, single deployable

  Decision: All packages in one repository. One Python application. No microservices.

  Reasoning: Non-goal explicitly prohibits premature microservices. Single repo enables atomic changes across
  agent/tool/provider boundaries. Single deployable means no distributed systems complexity at this stage.

  Tradeoffs: Scales cleanly to ~10 engineers. Beyond that, package boundaries already drawn make service extraction
  straightforward.

  ---
  6. Evaluation Architecture

  Eval consumer isolation

  Evals consume orchestrator/ directly. They never go through api/. They use a test storage backend
  (state/backends/memory.py) and a test provider (cached/mocked). They produce EvalReport objects (from contracts/evals.py).

  Eval types

  ┌──────────────────┬────────────────────────────────┬─────────────────┬─────────────────┐
  │       Type       │             Scope              │    Frequency    │    Provider     │
  ├──────────────────┼────────────────────────────────┼─────────────────┼─────────────────┤
  │ Unit evals       │ Single agent, single turn      │ Every PR        │ Mock/cached     │
  ├──────────────────┼────────────────────────────────┼─────────────────┼─────────────────┤
  │ Agent evals      │ Multi-turn agent behavior      │ Every PR        │ Mock/cached     │
  ├──────────────────┼────────────────────────────────┼─────────────────┼─────────────────┤
  │ End-to-end evals │ Full workflow, all agents      │ Daily + release │ Real (budgeted) │
  ├──────────────────┼────────────────────────────────┼─────────────────┼─────────────────┤
  │ Regression evals │ Known-good cases don't regress │ Every PR        │ Mock/cached     │
  └──────────────────┴────────────────────────────────┴─────────────────┴─────────────────┘

  Eval case structure (JSONL)

  {
    "id": "research_001",
    "dataset_version": "v1",
    "agent": "research",
    "input": {"task": "Find current population of Japan"},
    "expected": {"contains": ["125", "million"], "not_contains": ["China"]},
    "scorer": "contains",
    "tags": ["research", "smoke"],
    "max_cost_usd": 0.01,
    "max_latency_ms": 5000
  }

  Scorers

  ┌─────────────┬──────────────────────────────────────────────────────┐
  │   Scorer    │                     When to use                      │
  ├─────────────┼──────────────────────────────────────────────────────┤
  │ exact_match │ Deterministic outputs: IDs, structured data          │
  ├─────────────┼──────────────────────────────────────────────────────┤
  │ contains    │ Output must include specific facts/phrases           │
  ├─────────────┼──────────────────────────────────────────────────────┤
  │ llm_judge   │ Open-ended quality: tone, completeness, accuracy     │
  ├─────────────┼──────────────────────────────────────────────────────┤
  │ custom      │ Per-case callable registered at eval definition time │
  └─────────────┴──────────────────────────────────────────────────────┘

  llm_judge uses temperature=0, fixed seed, explicit rubric. Runs are repeatable.

  Eval runner behavior

  1. Load dataset(s) by tag, agent, or version
  2. For each case: construct RunContext with test provider + memory backend
  3. Run orchestrator, collect AgentResult
  4. Score with case scorer → EvalResult
  5. Aggregate: pass rate, avg score, cost, latency per agent and dataset version
  6. Compare to stored baseline (stored as CI artifact, not in repo)
  7. Write EvalReport to evals/reports/ (JSON + HTML)
  8. If regression > threshold on any agent: exit nonzero → blocks CI

  Baselines

  - Stored as artifacts in CI, not committed to repo
  - Updated explicitly via raic eval --update-baseline (requires manual approval in CI)
  - Every EvalReport records: dataset version, provider, model, run timestamp

  Cost control in evals

  - Unit/agent evals: mock provider — zero cost
  - End-to-end evals: real provider, max_cost_usd per case enforced by runner
  - Global eval_budget_usd in config — runner aborts suite if exceeded

  ---
  7. CI/CD Architecture

  Pipeline

  Stage 1 — Static checks (no LLM calls, ~60s)
    ├── ruff / flake8 lint
    ├── mypy type check
    ├── dependency rule check (contracts/ import graph)
    └── pytest tests/unit/

  Stage 2 — Integration tests (mocked provider, ~3min)
    └── pytest tests/integration/
        Covers: orchestrator flow, HITL pause/resume, checkpoint recovery

  Stage 3 — Eval regression gate (~5-10min depending on suite)
    ├── raic eval --tags smoke (subset, mock provider)
    ├── Compare to stored baseline
    └── Block merge if regression > 5% on any agent

  Stage 4 — Staging deploy (after merge to main)
    ├── Build artifact
    ├── Deploy to staging environment
    ├── Run scripts/smoke_test.sh (real provider, limited budget)
    └── Block prod promotion on failure

  Stage 5 — Production (manual gate)
    ├── Explicit human approval required
    ├── Deploy to prod
    └── Post-deploy smoke tests

  Quality gates

  ┌───────────────────────┬───────────────────────────────────────┐
  │         Gate          │                Blocks                 │
  ├───────────────────────┼───────────────────────────────────────┤
  │ Stage 1 failure       │ PR merge                              │
  ├───────────────────────┼───────────────────────────────────────┤
  │ Stage 2 failure       │ PR merge                              │
  ├───────────────────────┼───────────────────────────────────────┤
  │ Stage 3 regression    │ PR merge                              │
  ├───────────────────────┼───────────────────────────────────────┤
  │ Stage 4 smoke failure │ Prod promotion                        │
  ├───────────────────────┼───────────────────────────────────────┤
  │ Stage 5               │ Prod deploy (requires human approval) │
  └───────────────────────┴───────────────────────────────────────┘

  Environment configuration

  ┌───────────────────┬─────────────────────┬───────────┬───────────┐
  │      Setting      │         dev         │  staging  │   prod    │
  ├───────────────────┼─────────────────────┼───────────┼───────────┤
  │ Storage backend   │ SQLite              │ Postgres  │ Postgres  │
  ├───────────────────┼─────────────────────┼───────────┼───────────┤
  │ Provider          │ Mock / Anthropic    │ Anthropic │ Anthropic │
  ├───────────────────┼─────────────────────┼───────────┼───────────┤
  │ HITL channel      │ CLI                 │ CLI + API │ API       │
  ├───────────────────┼─────────────────────┼───────────┼───────────┤
  │ Log format        │ Human-readable      │ JSON      │ JSON      │
  ├───────────────────┼─────────────────────┼───────────┼───────────┤
  │ HITL auto-approve │ Optional (dev flag) │ Off       │ Off       │
  ├───────────────────┼─────────────────────┼───────────┼───────────┤
  │ Eval budget       │ Unlimited           │ $1.00/run │ N/A       │
  └───────────────────┴─────────────────────┴───────────┴───────────┘

  Secrets management

  - API keys via environment variables only — never in YAML
  - .env.example documents all required vars
  - CI uses GitHub Actions environment secrets
  - No secrets in code, no secrets in git

  ---
  8. LangGraph / Agent Chat UI Compatibility Assumptions

  This section documents design decisions made specifically to preserve compatibility with LangGraph-based tooling (e.g.,
  LangGraph Studio, Agent Chat UIs) and general agent UI patterns.

  ---
  8.1 Thread and Run Identity

  LangGraph assumption: state is keyed by thread_id. A thread represents a persistent conversation. Multiple runs
  (invocations) can occur within one thread.

  Architecture decision: Our Thread model has exactly this shape. thread_id is stable and persisted. run_id is
  per-invocation. Both IDs appear on every event, log line, and checkpoint.

  Implication: Any LangGraph-compatible UI can identify and display threads by thread_id and navigate individual run history
  by run_id without changes to our state model.

  ---
  8.2 Checkpoint Interface

  LangGraph assumption: checkpointers implement get(config), put(config, checkpoint), list(config).

  Architecture decision: our StorageBackend ABC exposes semantically equivalent operations. The interface is not identical
  to LangGraph's BaseCheckpointSaver, but the operations map directly: get_checkpoint(thread_id, checkpoint_id),
  put_checkpoint(thread_id, checkpoint), list_checkpoints(thread_id).

  Implication: A LangGraph-compatible saver adapter can be added to state/backends/ without modifying any core logic. This
  is deferred — but the interface gap is small by design.

  ---
  8.3 Interrupt / Resume Semantics

  LangGraph assumption: interrupt() suspends execution at a node boundary. Resume is triggered via Command(resume=value).

  Architecture decision: our HITLHandler.pause() / HITLHandler.resume(ApprovalDecision) is semantically equivalent.
  Execution suspends at a tool boundary. Resume reloads checkpoint and continues.

  Implication: the interrupt/resume pattern is compatible with LangGraph's human-in-the-loop model. A LangGraph UI that
  expects interrupt_before/interrupt_after semantics can be mapped to our approval_required permission flag.

  ---
  8.4 Streaming Event Shape

  LangGraph assumption: Agent Chat UIs expect a stream of typed events. Common types: on_chain_start, on_chain_end,
  on_tool_start, on_tool_end, on_chat_model_stream, on_chat_model_end.

  Architecture decision: our contracts/events.py defines typed RunEvent variants. api/streaming.py emits these as SSE
  events. The type names do not match LangGraph's names verbatim.

  Implication: a thin adapter in api/streaming.py can remap our event types to LangGraph-compatible names if needed. The
  event data is already structurally compatible (agent name, step info, tool name, message content, stop reason). This
  adapter is deferred but the data is present.

  ---
  8.5 Persistence Requirements for UI

  LangGraph Studio assumption: the UI can: list threads, inspect thread state, view checkpoint history, replay event
  streams, trigger resume.

  Architecture decision: all of these are exposed via api/:
  - GET /threads/{thread_id} — full thread state
  - GET /threads/{thread_id}/checkpoints — checkpoint list with metadata
  - GET /threads/{thread_id}/stream-history — full persisted event replay
  - POST /threads/{thread_id}/resume — resume from interrupt

  stream_event_history is persisted per run (see ADR-004) specifically to support this replay requirement.

  ---
  8.6 State Schema Serialization

  LangGraph assumption: state must be serializable (JSON). TypedDict-based state schemas.

  Architecture decision: contracts/state.py types are Pydantic models (or dataclasses with __dict__ serialization). All
  state written to storage backend is JSON-serializable. No unserializable Python objects (no functions, no class instances)
  stored in checkpoints.

  Implication: directly compatible. A LangGraph-style state schema can be adopted at implementation time with no
  architectural changes required.

  ---
  8.7 What is Not Compatible (and Why)

  - LangGraph graph definition format (nodes, edges, conditional edges): our supervisor/worker routing is implemented in
  Python logic inside supervisor/router.py, not as a declarative graph. Migration to a LangGraph graph definition is
  possible but not required — the runtime behavior is equivalent.
  - LangGraph-specific tool binding format: our provider adapters normalize tool definitions to each provider's native
  format. LangGraph uses its own tool-binding layer. Integration would require adapting tool definitions at the provider
  adapter layer, not in agent code.

  These gaps are acceptable at this architecture phase. Both can be closed via thin adapters without modifying core logic.

  ---
  9. Risks and Tradeoffs

    ## Risks and Tradeoffs
|
    ### Supervisor as Single Logical Bottleneck
    **Severity:** Medium

    **Risk**
    - The supervisor coordinates all work and can become a bottleneck as workflows become more complex.

    **Mitigation**
    - Checkpoint after every supervisor step.
    - Allow execution to resume from any checkpoint.
    - Keep supervisor responsibilities focused on orchestration rather than execution.

    ---

    ### Tool Server Running In-Process (No Sandboxing)
    **Severity:** High

    **Risk**
    - Tool execution shares the same process as the application.
    - Bugs or unsafe operations can affect system stability.

    **Mitigation**
    - Enforce permission manifests through `PermissionsManager`.
    - Require HITL approval for write operations.
    - Defer subprocess or container isolation to a production-hardening phase.

    ---

    ### Contracts Layer as a Central Change Point
    **Severity:** Medium

    **Risk**
    - Changes to shared contracts can impact multiple layers simultaneously.

    **Mitigation**
    - Treat contract breakage as intentional and visible.
    - Use type checking and CI validation to detect violations immediately.
    - Require contract changes to be reviewed carefully.

    ---

    ### Checkpoint Storage Growth
    **Severity:** Medium

    **Risk**
    - Frequent checkpointing can increase storage requirements over time.

    **Mitigation**
    - Use configurable retention policies.
    - Remove runs older than a configured threshold.
    - Prune non-interrupt checkpoints after successful completion.

    ---

    ### LLM Judge Non-Determinism
    **Severity:** Medium

    **Risk**
    - Evaluation results may vary across runs.

    **Mitigation**
    - Use `temperature=0`.
    - Use fixed evaluation prompts.
    - Average results across multiple runs.
    - Prefer deterministic scorers whenever possible.

    ---

    ### HITL Indefinite Blocking
    **Severity:** Medium

    **Risk**
    - Workflows may stall indefinitely waiting for approval.

    **Mitigation**
    - Define timeout policies for approval requests.
    - Support configurable default-deny behavior.
    - Expose pending approvals through monitoring and APIs.

    ---

    ### Evaluation Dataset Staleness
    **Severity:** Medium

    **Risk**
    - Evaluation datasets may stop reflecting real-world usage.

    **Mitigation**
    - Version datasets from the start.
    - Record dataset versions in evaluation reports.
    - Review and refresh datasets regularly.

    ---

    ### API Layer Becoming a God Layer
    **Severity:** Low

    **Risk**
    - API endpoints may accumulate business logic and orchestration behavior.

    **Mitigation**
    - Restrict API responsibilities to request handling and response formatting.
    - Keep orchestration inside workflow/orchestrator layers.
    - Enforce dependency rules through architecture tests.

    ---

    ## Architectural Tradeoffs

    ### Supervisor + Specialist Agents

    **Benefits**
    - Clear separation of responsibilities.
    - Easy to add new specialists.
    - Better maintainability.

    **Costs**
    - Increased orchestration complexity.
    - More components to monitor and debug.

    ---

    ### Dedicated Contracts Layer

    **Benefits**
    - Strong boundaries between modules.
    - Easier refactoring.
    - Better type safety.

    **Costs**
    - Additional maintenance overhead.
    - More upfront design effort.

    ---

    ### Workflow Layer Separate from Agents

    **Benefits**
    - Keeps agents focused on reasoning.
    - Keeps workflows focused on coordination.
    - Improves testability.

    **Costs**
    - Additional files and abstractions.

    ---

    ### Persistent Checkpoints

    **Benefits**
    - Recovery from failures.
    - HITL support.
    - Thread replay and debugging.
    - Frontend integration support.

    **Costs**
    - Storage overhead.
    - Retention management requirements.

    ---

    ### Thin Provider Abstraction

    **Benefits**
    - Easier provider switching.
    - Reduced vendor lock-in.
    - Cleaner agent code.

    **Costs**
    - Adapter maintenance.

    ---

    ### Explicit API Layer

    **Benefits**
    - Cleaner frontend integration.
    - Better QA tooling support.
    - Stable external interface.

    **Costs**
    - Additional layer to maintain.

    ---

    ### Evaluation-First Architecture

    **Benefits**
    - Detects regressions early.
    - Improves reliability.
    - Encourages measurable quality.

    **Costs**
    - Longer CI runtimes.
    - Ongoing dataset maintenance.

  ---
  10. Migration Guidance for Future Implementation

  Phase order (each phase leaves system runnable)

  Phase 1 — Foundation
  contracts/ → config/ → observability/logger.py → providers/base.py + anthropic/client.py → state/models.py +
  backends/memory.py → agents/base.py

  Phase 2 — Core runtime
  tools/base.py + registry.py + permissions.py → hitl/models.py + handler.py + channels/cli.py → orchestrator/context.py +
  runner.py → agents/supervisor/ + agents/research/ → cli/commands/run.py

  At end of Phase 2: raic run "<task>" works end-to-end.

  Phase 3 — Persistence and safety
  state/backends/sqlite.py → cli/commands/resume.py + cli/commands/approve.py → tools/filesystem/server.py + agents/ops/ →
  full HITL flow with checkpoint/resume

  At end of Phase 3: HITL approval works. Runs survive restarts.

  Phase 4 — External interface
  api/app.py + api/routes/ + api/streaming.py → observability/tracer.py + metrics.py

  At end of Phase 4: Frontend and QA tooling can connect.

  Phase 5 — Evaluations and CI
  evals/runner.py + scorers/ + initial datasets → evals/cases/ → CI eval gate → .github/workflows/

  Phase 6 — Production hardening
  state/backends/postgres.py → providers/openai/client.py → hitl/channels/api.py → staging + prod deploy pipeline

  ---
  Assumptions

  1. Python / asyncio — assumed. Streaming output requires async I/O.
  2. Anthropic as default provider — first adapter implemented. OpenAI is Phase 6.
  3. FastAPI or Starlette for api/ — assumed for SSE support. Not locked in until Phase 4.
  4. Single-machine deployment — no distributed state. Postgres assumed single-node initially.
  5. No real-time streaming to end users via WebSocket (yet) — SSE sufficient for Phase 4. WebSocket deferred.
  6. LangGraph compatibility is design-influencing, not a hard dependency — architecture preserves compatibility but does not require LangGraph to be installed or used.