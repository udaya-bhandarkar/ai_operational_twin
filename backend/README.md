# AI Operational Twin — Backend

Multi-agent LLM system built on LangGraph / LangChain / LangSmith.

---

## Setup

### Prerequisites

- Python 3.11+
- A supported LLM provider API key (Anthropic, Groq, or Mistral)
- A LangSmith API key (free tier works; needed for tracing)

### Install

```bash
cd backend

# Installs all core libraries (langgraph, langchain, langchain-anthropic, deepagents, etc.)
pip install -e .
```

If you want to use Groq or Mistral instead of Anthropic, install the matching extra on top:

```bash
pip install -e ".[groq]"       # adds langchain-groq
pip install -e ".[mistral]"    # adds langchain-mistralai
pip install -e ".[all-providers]"  # adds both
```

You only need the extra for the provider you set in `BACKEND_MODEL`. The base `pip install -e .` is always required first (or replace it with one of the above — they include the base deps too).

### Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your keys. Set exactly one provider block:

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
BACKEND_MODEL=mistral:mistral-large-latest
```

Also add your LangSmith key:
```env
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
```

### Run (LangGraph dev server)

```bash
cd backend
langgraph dev
```

Opens LangGraph Studio at `http://localhost:8123`. The supervisor graph is loaded automatically from `langgraph.json`.

---

## Project Structure

```
backend/
├── langgraph.json              # Graph entrypoint + deploy config
├── pyproject.toml              # Dependencies
├── .env.example                # Environment variable template
│
├── config/
│   ├── settings.py             # Pydantic Settings — reads from .env
│   └── environments/
│       └── dev.yaml            # Dev environment defaults
│
├── agents/
│   ├── supervisor/             # Orchestrator: routes to specialists, synthesises results
│   │   ├── graph.py            # Compiled StateGraph (InMemorySaver checkpointer)
│   │   ├── nodes.py            # call_model node + should_continue edge factory
│   │   ├── state.py            # SupervisorState (MessagesState + summary + agent_outputs)
│   │   └── prompts/system.txt
│   └── research/               # Research specialist: web search and fetch
│       ├── graph.py            # create_agent (deepagents) + @tool wrapper for supervisor
│       ├── state.py            # ResearchState (placeholder for Phase 2+)
│       └── prompts/system.txt
│
├── tools/
│   └── web.py                  # web_search, web_fetch (Phase 1 stubs)
│
├── middleware/
│   └── retry.py                # ModelRetryMiddleware (create_agent) + .with_retry() (StateGraph)
│
└── hitl/
    └── channels/
        └── cli.py              # CLI runner: streams graph, handles interrupts
```

---

## Phase 1 — Core Graph

Phase 1 establishes the full multi-agent skeleton end-to-end. Every subsequent phase adds to this foundation without restructuring it.

### What is built

**Supervisor agent (StateGraph)**

A LangGraph `StateGraph` that owns the conversation and routes work to specialist agents. It receives the user's message, decides which specialist to call, invokes it as a tool, then synthesises the result into a final response. The graph loops until there are no more tool calls, then ends.

Graph flow:
```
START → call_model → [tool calls?] → tools → call_model → ... → END
```

**Research agent (deepagents `create_agent`)**

A specialist that handles web search and information retrieval. Built with deepagents' `create_agent` factory, which supports the middleware stack used in later phases. Wrapped as a `@tool` so the supervisor can call it like any other tool.

**Stub web tools**

`web_search` and `web_fetch` are `@tool` stubs that return placeholder responses. They match the real tool signatures so Phase 2 can swap in Tavily without touching the agent or graph code.

**Retry from day one**

`ModelRetryMiddleware` (deepagents) on the research agent handles rate limits, 5xx errors, and transient failures automatically. The supervisor's model uses LangChain's `.with_retry()` for the same effect. Both are configured in `middleware/retry.py`.

**Provider-agnostic model init**

All agents call `init_chat_model(settings.backend_model)`. Switching providers is one `.env` change — no code changes. Supported: Anthropic, Groq, Mistral (and any `init_chat_model`-compatible provider).

**State with future fields**

`SupervisorState` extends `MessagesState` with `summary` and `agent_outputs` fields. These are unused in Phase 1 but are in place so Phase 3 can wire `SummarizationMiddleware` and structured specialist results without a state migration.

**Streaming wired**

The CLI runner calls `graph.stream(..., stream_mode=["updates", "messages"], subgraphs=True)`. Token-level streaming from both the supervisor and the research agent is visible from the first run. No changes needed when Phase 3 adds more agents.

**HITL infrastructure**

`hitl/channels/cli.py` contains a full interrupt → approve / edit / reject loop. In Phase 1 it activates only if an interrupt fires (the research agent has none). The code is in place so Phase 2's `HumanInTheLoopMiddleware` on the ops agent works immediately with no changes to the runner.

**LangSmith tracing**

With `LANGSMITH_TRACING=true` and a valid `LANGSMITH_API_KEY`, every run is automatically traced — token counts, latency, tool calls, agent steps. No instrumentation code needed.

### What is NOT in Phase 1

| Feature | Phase |
|---|---|
| Real web search (Tavily) | 2 |
| Ops agent (file read/write) | 2 |
| HITL approval on tool calls | 2 |
| PII middleware | 2 |
| Postgres checkpointer | 3 |
| MCP server integration | 3 |
| Summarization + prompt caching | 3 |
| Dynamic model selection | 3 |
| Evaluations + CI gate | 4 |
| Production deployment | 5 |

---

## Using the CLI runner directly

```python
from agents.supervisor.graph import graph
from hitl.channels.cli import run_with_hitl

result = run_with_hitl(graph, "What is the latest on fusion energy?", thread_id="thread-1")
```

To resume a thread (conversation continues from last checkpoint):

```python
result = run_with_hitl(graph, "Can you expand on that?", thread_id="thread-1")
```

---

## Switching models at runtime

Set `BACKEND_MODEL` in `.env` to any `init_chat_model`-compatible string:

```
anthropic:claude-haiku-4-5       # cheaper, faster
groq:llama-3.1-8b-instant        # ultra-fast inference
mistral:open-mixtral-8x7b        # open weights via Mistral API
```

No code changes required.
