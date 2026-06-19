import pathlib

from langchain.agents import create_agent
from langchain_core.tools import tool

from config.settings import settings
from tools.web import web_fetch, web_search

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()

_agent = create_agent(
    model=settings.backend_model,
    tools=[web_search, web_fetch],
    system_prompt=_system_prompt,
)


@tool
def research_agent_tool(query: str) -> str:
    """Research specialist. Use for web lookups, fact-finding, and information retrieval.
    Accepts a natural-language question or search query. Returns a synthesised answer."""
    result = _agent.invoke({"messages": [{"role": "user", "content": query}]})
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        return last.content if hasattr(last, "content") else str(last)
    return "Research agent returned no result."
