import pathlib
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langgraph.graph import END

from config.settings import settings
from middleware.retry import configure_model_retry

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()


def build_supervisor_nodes(tools: list) -> tuple:
    """
    Factory that returns (call_model_node, should_continue_edge) closed over a
    model instance with tools bound and retry configured.

    Accepts tools as a parameter to avoid circular imports between nodes.py and graph.py.
    """
    model = configure_model_retry(
        init_chat_model(settings.backend_model).bind_tools(tools)
    )

    def call_model(state: dict) -> dict[str, Any]:
        messages = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=_system_prompt)] + messages
        response = model.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: dict) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    return call_model, should_continue
