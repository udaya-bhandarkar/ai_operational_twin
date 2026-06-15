from typing import Any

from langgraph.graph import MessagesState


class SupervisorState(MessagesState):
    summary: str
    agent_outputs: dict[str, Any]
