import pathlib

from langchain.agents import create_agent

from agents.ops.graph import ops_agent_tool
from agents.research.graph import research_agent_tool
from config.settings import settings
from middleware.context import get_memory_middleware, get_prompt_caching_middleware
from middleware.dynamic_model import dev_cost_router
from middleware.pii import get_pii_middleware
from middleware.retry import get_model_retry, get_supervisor_limits
from middleware.summarization import get_summarization_middleware

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()
_tools = [research_agent_tool, ops_agent_tool]


def make_graph():
    """Factory for langgraph.json — dev server calls this to get the compiled graph."""
    # Middleware order (outer → inner):
    # PIIMiddleware              — sanitise input + output first; blocks API key leaks
    # ModelCallLimitMiddleware   — counts logical calls (outside retry so retries don't inflate)
    # ModelRetryMiddleware       — retries model failures with exponential backoff
    # MemoryMiddleware           — loads AGENTS.md into system prompt on each run
    # SummarizationMiddleware    — compresses history at 80% token threshold
    # dev_cost_router            — swaps to budget model in dev (inside retry = consistent per call)
    # AnthropicPromptCaching     — innermost; injects cache_control blocks just before model call
    middleware = (
        get_pii_middleware()
        + get_supervisor_limits()
        + [get_model_retry()]
        + [get_memory_middleware("./AGENTS.md")]
        + [get_summarization_middleware()]
        + [dev_cost_router]
        + [get_prompt_caching_middleware()]
    )
    return create_agent(
        model=settings.backend_model,
        tools=_tools,
        system_prompt=_system_prompt,
        middleware=middleware,
    )
