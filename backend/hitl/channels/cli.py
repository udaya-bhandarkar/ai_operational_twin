"""CLI HITL channel — chat with the agent in a terminal and answer write approvals.

Runs the graph with an in-memory checkpointer, prints each node's new messages, and when the
agent pauses on a write (HumanInTheLoopMiddleware), prompts for approve / edit / reject per
pending action before resuming.

Usage:
    python -m hitl.channels.cli "What is the capital of France?"
    python -m hitl.channels.cli            # interactive: one thread, multiple questions

The graph has async nodes (and async-only middleware), so everything runs on asyncio.
"""
import argparse
import asyncio
import json
import sys

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


async def run_with_hitl(user_message: str, thread_id: str = "cli", graph=None) -> dict:
    """Run one user turn to completion, prompting for approvals. Returns the final state."""
    if graph is None:
        from agents.supervisor.graph import build_graph
        graph = build_graph(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": thread_id}}
    payload: dict | Command = {"messages": [HumanMessage(content=user_message)]}

    while True:
        async for update in graph.astream(payload, config=config, stream_mode="updates"):
            _print_update(update)

        snapshot = await graph.aget_state(config)
        if not snapshot.interrupts:
            return snapshot.values

        request = snapshot.interrupts[0].value
        allowed = {c["action_name"]: c["allowed_decisions"] for c in request["review_configs"]}
        decisions = [
            _prompt_decision(action, allowed.get(action["name"], []))
            for action in request["action_requests"]
        ]
        payload = Command(resume={"decisions": decisions})


def _print_update(update: dict) -> None:
    for node, output in update.items():
        if not isinstance(output, dict):
            continue  # e.g. the __interrupt__ entry
        for msg in output.get("messages", []):
            if getattr(msg, "type", None) == "remove":
                continue
            for call in getattr(msg, "tool_calls", None) or []:
                print(f"[{node}] tool call -> {call['name']}({json.dumps(call['args'])})")
            if msg.text:
                print(f"[{node}] {msg.type}: {msg.text}")


def _prompt_decision(action: dict, allowed: list[str]) -> dict:
    print("\n--- Approval required ---")
    print(f"Tool:  {action['name']}")
    print(f"Args:  {json.dumps(action['args'], indent=2, default=str)}")
    print(f"Choices: {' / '.join(allowed)}")

    while True:
        choice = input("Decision: ").strip().lower()
        if choice.startswith("a") and "approve" in allowed:
            return {"type": "approve"}
        if choice.startswith("e") and "edit" in allowed:
            raw = input("Replacement args as JSON: ").strip()
            try:
                args = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON: {e}")
                continue
            return {"type": "edit", "edited_action": {"name": action["name"], "args": args}}
        if choice.startswith("r") and "reject" in allowed:
            reason = input("Rejection reason (optional): ").strip()
            return {"type": "reject", "message": reason} if reason else {"type": "reject"}
        print(f"Please choose one of: {', '.join(allowed)}")


async def _main(question: str | None) -> None:
    from agents.supervisor.graph import build_graph

    graph = build_graph(checkpointer=InMemorySaver())
    if question:
        await run_with_hitl(question, graph=graph)
        return
    print("Interactive chat — empty line to quit.")
    while (question := input("\nYou: ").strip()):
        await run_with_hitl(question, graph=graph)


if __name__ == "__main__":
    # Answers may contain non-ASCII (₹, €, emoji); Windows consoles default to cp1252.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="?", help="ask once and exit (omit for interactive)")
    asyncio.run(_main(parser.parse_args().question))
