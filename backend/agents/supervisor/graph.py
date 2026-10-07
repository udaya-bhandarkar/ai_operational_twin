"""Agent graph: a custom LangGraph StateGraph wrapping the LangChain agent.

Architecture (deterministic nodes around an agentic core — the documented reason to use a
custom StateGraph instead of create_agent alone):

    START → guardrail → agent → verify → END
              │           ▲       │
              └→ END      └───────┘  (one bounded retry when figures aren't grounded)

- guardrail (deterministic): input validation — rejects empty/oversized input and attempts to
  spoof the external-content boundary markers used by the web tools.
- agent (agentic): the existing create_agent with the full middleware stack (PII, limits,
  retry, memory, summarization, cost routing, rate limiting, HITL, prompt caching).
- verify (deterministic): numeric grounding check — money-like figures in the final answer
  must appear in this turn's tool results. Ungrounded figures trigger ONE corrective retry;
  a persistent failure is surfaced rather than looped forever.
"""
import pathlib
import re

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from config.settings import settings
from middleware.caching import get_prompt_caching_middleware
from middleware.dynamic_model import dev_cost_router
from middleware.pii import get_pii_middleware
from middleware.rate_limit import get_rate_limit_middleware
from middleware.retry import get_model_retry, get_ops_limits, get_research_limits
from middleware.summarization import get_summarization_middleware
from tools.duckdb import (
    duckdb_execute,
    duckdb_list_tables,
    duckdb_query,
    duckdb_query_checker,
    duckdb_schema,
)
from tools.web import web_fetch, web_search

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()

# Single agent: DB tools + web tools attached directly (no nested sub-agents). One reasoning
# loop instead of supervisor->sub-agent->tools, which roughly halves model calls per turn.
_tools = [
    duckdb_query,
    duckdb_query_checker,
    duckdb_list_tables,
    duckdb_schema,
    duckdb_execute,
    web_search,
    web_fetch,
]

_MAX_INPUT_CHARS = 4000
_BOUNDARY_MARKERS = ("<<<EXTERNAL_CONTENT>>>", "<<<END_EXTERNAL_CONTENT>>>")
# Figures the answer may legitimately contain without appearing in tool output:
# the waste thresholds baked into the data model (300 kW power, 25 L water).
_KNOWN_CONSTANTS = {300.0, 25.0}


class AgentState(MessagesState):
    rejected: bool
    verify_attempts: int


def _build_agent(model=None):
    """The agentic core — unchanged middleware stack from the pre-graph architecture.

    `model` overrides settings.backend_model (a model string or chat-model instance) — used by
    tests to run the full graph against a scripted fake model.

    Middleware order (outer → inner):
    PIIMiddleware              — sanitise input + output first; blocks API key leaks
    ModelCallLimit + ToolCall  — cap total model calls (15) + writes (3) + web searches (5)
    ModelRetryMiddleware       — retries rate-limit / transient failures with backoff
    SummarizationMiddleware    — compresses history at 80% token threshold
    dev_cost_router            — swaps to budget model in dev
    RateLimitMiddleware        — paces model calls under provider RPM
    HumanInTheLoopMiddleware   — interrupts on duckdb_execute (writes) for approval
    AnthropicPromptCaching     — innermost; injects cache_control just before model call
    """
    middleware = (
        get_pii_middleware()
        + get_ops_limits()
        + get_research_limits()
        + [get_model_retry()]
        + [get_summarization_middleware()]
        + [dev_cost_router]
        + get_rate_limit_middleware()
        + [
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "duckdb_execute": {
                        "allowed_decisions": ["approve", "edit", "reject"],
                        "description": "Review write statement before execution",
                    },
                }
            )
        ]
        + [get_prompt_caching_middleware()]
    )
    return create_agent(
        model=model or settings.backend_model,
        tools=_tools,
        system_prompt=_system_prompt,
        middleware=middleware,
    )


# ---------------------------------------------------------------------------
# Deterministic nodes
# ---------------------------------------------------------------------------

def guardrail(state: AgentState) -> dict:
    """Input validation before any model call. Cheap, deterministic, un-promptable."""
    last = state["messages"][-1] if state["messages"] else None
    text = last.content if isinstance(last, HumanMessage) and isinstance(last.content, str) else ""

    problem = None
    if not text.strip():
        problem = "Your message is empty — please ask a question."
    elif len(text) > _MAX_INPUT_CHARS:
        problem = f"Your message is too long ({len(text)} chars; limit {_MAX_INPUT_CHARS})."
    elif any(m in text for m in _BOUNDARY_MARKERS):
        # A user message must never contain the untrusted-content markers the web tools use —
        # that's an attempt to disguise input as (or escape from) external content.
        problem = "Your message contains reserved content markers and was rejected."

    # verify_attempts is a per-turn retry budget: reset it every turn, otherwise (with a
    # checkpointer) one retry in an early turn would disable grounding retries for the thread.
    if problem:
        return {"messages": [AIMessage(content=problem)], "rejected": True, "verify_attempts": 0}
    return {"rejected": False, "verify_attempts": 0}


_NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?!\s*%)(?![\w])")


def extract_figures(text: str) -> set[float]:
    """Money-like figures in a message: magnitude >= 10, percentages excluded."""
    figures = set()
    for whole, frac in _NUMBER_RE.findall(text):
        try:
            value = float(whole.replace(",", "") + (frac or ""))
        except ValueError:
            continue
        if value >= 10:
            figures.add(round(value, 2))
    return figures


def verify(state: AgentState) -> dict:
    """Numeric grounding check: figures in the answer must exist in this turn's tool results.

    Deterministic hallucination detector — an LLM can claim anything, but a number that
    doesn't appear in any tool output was not read from the database.
    """
    messages = state["messages"]
    answer = messages[-1]
    if not isinstance(answer, AIMessage) or not isinstance(answer.content, str):
        return {}

    # Tool outputs + the user's own question form the grounding corpus for this turn.
    corpus_figures: set[float] = set(_KNOWN_CONSTANTS)
    saw_tool_output = False
    for m in reversed(messages[:-1]):
        if isinstance(m, HumanMessage):
            if isinstance(m.content, str):
                corpus_figures |= extract_figures(m.content)
            break  # start of this turn
        if isinstance(m, ToolMessage) and isinstance(m.content, str):
            saw_tool_output = True
            corpus_figures |= extract_figures(m.content)

    if not saw_tool_output:
        return {}  # chit-chat / refusals — nothing to ground

    corpus_whole = {round(c) for c in corpus_figures}
    ungrounded = sorted(
        f for f in extract_figures(answer.content)
        # tolerate rounding to whole units either way
        if f not in corpus_figures and round(f) not in corpus_whole
    )
    if not ungrounded or state.get("verify_attempts", 0) >= 1:
        return {}

    correction = HumanMessage(
        content=(
            "[automated grounding check] These figures in your answer do not appear in the "
            f"tool results: {ungrounded}. Re-run the query and answer again using only "
            "figures read directly from the database."
        )
    )
    return {"messages": [correction], "verify_attempts": state.get("verify_attempts", 0) + 1}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def _route_after_guardrail(state: AgentState) -> str:
    return END if state.get("rejected") else "agent"


def _route_after_verify(state: AgentState) -> str:
    # verify appended a correction message → loop back to the agent once.
    return "agent" if isinstance(state["messages"][-1], HumanMessage) else END


def history_delta(before: list[AnyMessage], after: list[AnyMessage]) -> list:
    """The `messages` update that turns `before` into `after` under the add_messages reducer.

    The inner agent returns its full final history. Usually it only appended, so the update is
    just the new tail. But SummarizationMiddleware REWRITES history (old messages replaced by a
    summary), and add_messages never deletes on its own — returning only "new" messages would
    leave the outer state holding the full uncompressed history forever. When the prefix no
    longer matches, clear and replace the whole history instead.
    """
    n = len(before)
    if len(after) >= n and [m.id for m in after[:n]] == [m.id for m in before]:
        return list(after[n:])
    return [RemoveMessage(id=REMOVE_ALL_MESSAGES), *after]


def build_graph(checkpointer=None, model=None):
    """Compile the graph. `checkpointer` persists threads (memory + HITL resume).

    Leave `checkpointer` None under `langgraph dev` / Agent Server — the runtime injects its
    own and rejects a custom one. The API gateway and CLI pass theirs explicitly.
    """
    agent = _build_agent(model)

    async def agent_node(state: AgentState) -> dict:
        result = await agent.ainvoke({"messages": state["messages"]})
        return {"messages": history_delta(state["messages"], result["messages"])}

    graph = (
        StateGraph(AgentState)
        .add_node("guardrail", guardrail)
        .add_node("agent", agent_node)
        .add_node("verify", verify)
        .add_edge(START, "guardrail")
        .add_conditional_edges("guardrail", _route_after_guardrail, ["agent", END])
        .add_edge("agent", "verify")
        .add_conditional_edges("verify", _route_after_verify, ["agent", END])
    )
    return graph.compile(checkpointer=checkpointer)


def make_graph():
    """Zero-argument factory for langgraph.json (the runtime supplies the checkpointer)."""
    return build_graph()
