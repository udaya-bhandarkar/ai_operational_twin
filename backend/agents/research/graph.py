import pathlib

from langchain.agents import create_agent
from langchain_core.tools import tool

from config.settings import settings
from middleware.rate_limit import get_rate_limit_middleware
from middleware.retry import get_model_retry, get_research_limits
from tools.web import web_fetch, web_search

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()
_tools = [web_search, web_fetch]
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        # Middleware order (outer → inner):
        # ModelRetryMiddleware — retries model failures
        # ToolCallLimitMiddleware(web_search) — caps Tavily API calls per run
        _agent = create_agent(
            model=settings.backend_model,
            tools=_tools,
            system_prompt=_system_prompt,
            middleware=[get_model_retry(), *get_rate_limit_middleware(), *get_research_limits()],
        )
    return _agent


@tool
def research_agent_tool(query: str) -> str:
    """Research specialist. Use for web lookups, fact-finding, and information retrieval.
    Accepts a natural-language question or search query. Returns a synthesised answer."""
    result = _get_agent().invoke({"messages": [{"role": "user", "content": query}]})
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        return last.content if hasattr(last, "content") else str(last)
    return "Research agent returned no result."
