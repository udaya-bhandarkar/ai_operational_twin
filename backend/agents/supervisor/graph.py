import pathlib

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

from config.settings import settings
from middleware.context import get_memory_middleware, get_prompt_caching_middleware
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


def make_graph():
    """Factory for langgraph.json — dev server calls this to get the compiled graph."""
    # Middleware order (outer → inner):
    # PIIMiddleware              — sanitise input + output first; blocks API key leaks
    # ModelCallLimit + ToolCall  — cap total model calls (15) + writes (3) + web searches (5)
    # ModelRetryMiddleware       — retries rate-limit / transient failures with backoff
    # MemoryMiddleware           — loads AGENTS.md into system prompt on each run
    # SummarizationMiddleware    — compresses history at 80% token threshold
    # dev_cost_router            — swaps to budget model in dev
    # RateLimitMiddleware        — paces model calls under provider RPM
    # HumanInTheLoopMiddleware   — interrupts on duckdb_execute (writes) for approval
    # AnthropicPromptCaching     — innermost; injects cache_control just before model call
    middleware = (
        get_pii_middleware()
        + get_ops_limits()
        + get_research_limits()
        + [get_model_retry()]
        + [get_memory_middleware("./AGENTS.md")]
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
        model=settings.backend_model,
        tools=_tools,
        system_prompt=_system_prompt,
        middleware=middleware,
    )
