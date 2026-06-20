import pathlib

from langchain.agents import create_agent

from agents.ops.graph import ops_agent_tool
from agents.research.graph import research_agent_tool
from config.settings import settings
from middleware.pii import get_pii_middleware
from middleware.retry import get_model_retry, get_supervisor_limits

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()
_tools = [research_agent_tool, ops_agent_tool]


def make_graph():
    """Factory for langgraph.json — dev server calls this to get the compiled graph."""
    # Middleware order (outer → inner):
    # PIIMiddleware first — sanitises input before anything else sees it
    # ModelCallLimitMiddleware — counts logical calls (outside retry so retries don't inflate count)
    # ModelRetryMiddleware — retries model failures
    middleware = get_pii_middleware() + get_supervisor_limits() + [get_model_retry()]
    return create_agent(
        model=settings.backend_model,
        tools=_tools,
        system_prompt=_system_prompt,
        middleware=middleware,
    )
