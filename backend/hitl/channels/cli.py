"""
CLI HITL channel for Phase 1.

Streams the supervisor graph, prints token-level messages, and handles interrupts
by prompting the user for approve / edit / reject before resuming execution.

Usage:
    from agents.supervisor.graph import graph
    from hitl.channels.cli import run_with_hitl

    run_with_hitl(graph, "What is the boiling point of water?", thread_id="t1")
"""

import json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


def run_with_hitl(graph, user_message: str, thread_id: str) -> dict:
    # Compile with InMemorySaver when running outside LangGraph API.
    # langgraph dev / Agent Server inject their own checkpointer — don't pass one there.
    if graph.checkpointer is None:
        graph = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    current_input: dict | Command = {"messages": [{"role": "user", "content": user_message}]}

    while True:
        print()
        for chunk in graph.stream(
            current_input,
            config=config,
            stream_mode=["updates", "messages"],
            subgraphs=True,
        ):
            _print_chunk(chunk)

        state = graph.get_state(config)

        if not state.next:
            break

        interrupts = [i for task in state.tasks for i in getattr(task, "interrupts", [])]
        if not interrupts:
            break

        intr = interrupts[0]
        decision = _prompt_user(getattr(intr, "value", {}))
        current_input = Command(resume=decision)

    final_state = graph.get_state(config).values
    return final_state


def _print_chunk(chunk: tuple | dict) -> None:
    if isinstance(chunk, tuple):
        _ns, event = chunk
    else:
        event = chunk

    if isinstance(event, dict):
        for _node, node_output in event.items():
            if isinstance(node_output, dict) and "messages" in node_output:
                for msg in node_output["messages"]:
                    content = getattr(msg, "content", None)
                    role = getattr(msg, "type", "message")
                    if content:
                        print(f"[{role}]: {content}")


def _prompt_user(interrupt_value: dict) -> dict:
    print("\n--- HITL: Approval Required ---")
    tool_name = interrupt_value.get("tool_name", "unknown tool")
    tool_args = interrupt_value.get("tool_args", interrupt_value)
    print(f"Tool:  {tool_name}")
    print(f"Args:  {json.dumps(tool_args, indent=2, default=str)}")
    print("Choices: [a]pprove  [e]dit  [r]eject")

    choice = input("Decision: ").strip().lower()

    if choice.startswith("a"):
        return {"type": "approve"}
    elif choice.startswith("e"):
        raw = input("Enter replacement args as JSON: ").strip()
        return {"type": "edit", "args": json.loads(raw)}
    else:
        reason = input("Rejection reason (optional): ").strip()
        return {"type": "reject", "reason": reason}
