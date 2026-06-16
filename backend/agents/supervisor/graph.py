from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agents.research.graph import research_agent_tool
from agents.supervisor.nodes import build_supervisor_nodes
from agents.supervisor.state import SupervisorState

_tools = [research_agent_tool]

call_model, should_continue = build_supervisor_nodes(_tools)

builder = StateGraph(SupervisorState)
builder.add_node("call_model", call_model)
builder.add_node("tools", ToolNode(_tools))

builder.set_entry_point("call_model")
builder.add_conditional_edges(
    "call_model",
    should_continue,
    {"tools": "tools", END: END},
)
builder.add_edge("tools", "call_model")

# Checkpointer injected automatically by LangGraph API (langgraph dev / Agent Server).
# For direct Python use (hitl/channels/cli.py), pass checkpointer=InMemorySaver() at call site.
graph = builder.compile()
