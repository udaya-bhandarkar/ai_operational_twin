import pathlib

from langchain.agents import create_agent

from agents.research.graph import research_agent_tool
from config.settings import settings

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()
_tools = [research_agent_tool]


def make_graph():
    """Factory for langgraph.json — dev server calls this to get the compiled graph."""
    return create_agent(
        model=settings.backend_model,
        tools=_tools,
        system_prompt=_system_prompt,
    )
