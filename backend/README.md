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
uv venv
.venv\Scripts\activate

pip install -e ".[all-providers]"
```

Or install only the provider you need:

```bash
pip install -e .              # Anthropic only (default)
pip install -e ".[groq]"      # adds langchain-groq
pip install -e ".[mistral]"   # adds langchain-mistralai
```

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

LangSmith (optional — traces visible in Studio UI):
```env
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=RAIC
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_TRACING=false
```

> **Note:** Keep `LANGSMITH_TRACING=false` when using `langgraph dev`. The dev server submits traces to LangSmith on its own. Setting it to `true` enables a second parallel tracer which causes a recursion error in the LangSmith client. Set it to `true` only when running agents directly outside `langgraph dev`.

> **Note:** Keep `.env` comments ASCII-only. Unicode characters (`→`, `──`) cause a `python-dotenv could not parse statement` warning.

### Run

```bash
cd backend
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
│   │   ├── graph.py            # make_graph() factory — create_agent with research tool
│   │   └── prompts/system.txt
│   └── research/               # Research specialist: web search and fetch
│       ├── graph.py            # create_agent + @tool wrapper exposed to supervisor
│       └── prompts/system.txt
│
├── tools/
│   └── web.py                  # web_search, web_fetch (Phase 1 stubs)
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
              ├── web_search  (stub)
              └── web_fetch   (stub)
```

**Stub web tools**

`web_search` and `web_fetch` return placeholder strings. They match the real signatures so Phase 2 can swap in Tavily without touching the agent code.

**Provider-agnostic model**

Pass the model name as a string directly to `create_agent`. Switching providers is one `.env` change — no code changes.

**HITL infrastructure**

`hitl/channels/cli.py` has a full interrupt → approve / edit / reject loop ready for Phase 2's `HumanInTheLoopMiddleware`.

**LangSmith tracing**

`langgraph dev` automatically submits run traces to LangSmith using `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT`. No extra instrumentation needed.

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

Provider prefix rules (learned during setup):
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

**LangSmith double-tracing**

`langgraph dev` already submits traces to LangSmith. Setting `LANGSMITH_TRACING=true` in `.env` activates a second parallel tracer (the LangChain callback system), which causes `maximum recursion depth exceeded` in the LangSmith client. Keep `LANGSMITH_TRACING=false` and let the dev server handle tracing.

---

## Troubleshooting

**`python-dotenv could not parse statement at line N`**

Non-ASCII characters in `.env` comment lines (`→`, `──`). Replace with ASCII (`->`, `-`).

**`LangSmith: maximum recursion depth exceeded`**

Two tracers running at once. Set `LANGSMITH_TRACING=false` in `.env`. The `langgraph dev` server submits traces on its own — the LangChain-level tracer is redundant and causes the conflict.

**`401 Unauthorized` from provider API**

API key in `.env` is missing, wrong, or was rotated. Check the key matches the provider set in `BACKEND_MODEL`.

**`ValueError: graph includes a custom checkpointer`**

Passed `checkpointer=` to `create_agent` while also running via `langgraph dev`. Remove the checkpointer argument — the dev server injects its own.
