"""Chat endpoints — forward user messages to the agent graph, with HITL approvals.

POST /api/chat
    Request  : {"message": str, "thread_id": str | null, "view": str | null}
    Response : {"reply": str, "thread_id": str, "status": "complete" | "awaiting_approval",
                "approval": {...} | null}

POST /api/chat/resume
    Request  : {"thread_id": str, "decisions": [{"type": "approve" | "edit" | "reject",
                                                "args": {...} | null, "message": str | null}]}
    Response : same shape as /api/chat

thread_id keys the conversation in the checkpointer, so follow-up messages see prior turns.
When the agent wants to run a database write, the run pauses and the response comes back with
status "awaiting_approval" and the pending actions; the client answers with one decision per
action via /api/chat/resume. A thread that is awaiting approval rejects new messages (409).
"""
import asyncio
import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

logger = logging.getLogger("api.chat")

router = APIRouter(prefix="/api")

_graph_lock = asyncio.Lock()


async def _get_graph(request: Request) -> Any:
    """Build the graph once per app, bound to the app's checkpointer (see api/app.py lifespan)."""
    state = request.app.state
    if getattr(state, "graph", None) is None:
        async with _graph_lock:
            if getattr(state, "graph", None) is None:
                from agents.supervisor.graph import build_graph
                state.graph = build_graph(checkpointer=state.checkpointer)
    return state.graph


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    view: str | None = None


class Decision(BaseModel):
    type: Literal["approve", "edit", "reject"]
    args: dict[str, Any] | None = None  # edit: replacement tool arguments
    message: str | None = None  # reject: reason shown to the agent


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[Decision]


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def _pending_approval(graph: Any, thread_id: str) -> dict | None:
    """The HITL request this thread is paused on, or None."""
    snapshot = await graph.aget_state(_config(thread_id))
    return snapshot.interrupts[0].value if snapshot.interrupts else None


def _describe(actions: list[dict]) -> str:
    lines = ["Approval required before running:"]
    for a in actions:
        args = ", ".join(f"{k}={v!r}" for k, v in a.get("args", {}).items())
        lines.append(f"- {a['name']}({args})")
    return "\n".join(lines)


def _to_response(result: dict, thread_id: str) -> dict:
    interrupts = result.get("__interrupt__") or []
    if interrupts:
        actions = interrupts[0].value.get("action_requests", [])
        return {
            "reply": _describe(actions),
            "thread_id": thread_id,
            "status": "awaiting_approval",
            "approval": {"actions": actions},
        }
    messages = result.get("messages", [])
    return {
        "reply": messages[-1].text if messages else "",
        "thread_id": thread_id,
        "status": "complete",
        "approval": None,
    }


async def _run(graph: Any, payload: Any, thread_id: str) -> dict:
    try:
        result = await graph.ainvoke(payload, config=_config(thread_id))
    except Exception:
        # Full detail goes to the server log; the client gets a safe, generic error.
        logger.exception("Agent run failed (thread_id=%s)", thread_id)
        raise HTTPException(status_code=500, detail="The agent failed to answer. Please retry.")
    return _to_response(result, thread_id)


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    graph = await _get_graph(request)
    thread_id = req.thread_id or str(uuid.uuid4())
    if await _pending_approval(graph, thread_id):
        raise HTTPException(
            status_code=409,
            detail="This conversation is waiting for an approval decision — "
            "answer it via /api/chat/resume first.",
        )
    return await _run(graph, {"messages": [HumanMessage(content=req.message)]}, thread_id)


@router.post("/chat/resume")
async def resume(req: ResumeRequest, request: Request):
    graph = await _get_graph(request)
    pending = await _pending_approval(graph, req.thread_id)
    if not pending:
        raise HTTPException(status_code=409, detail="No approval is pending for this thread.")

    actions = pending.get("action_requests", [])
    if len(req.decisions) != len(actions):
        raise HTTPException(
            status_code=422,
            detail=f"Expected {len(actions)} decision(s), got {len(req.decisions)}.",
        )
    allowed = {c["action_name"]: c["allowed_decisions"] for c in pending.get("review_configs", [])}

    decisions = []
    for decision, action in zip(req.decisions, actions):
        if decision.type not in allowed.get(action["name"], []):
            raise HTTPException(
                status_code=422, detail=f"'{decision.type}' is not allowed for {action['name']}."
            )
        if decision.type == "approve":
            decisions.append({"type": "approve"})
        elif decision.type == "edit":
            if decision.args is None:
                raise HTTPException(status_code=422, detail="An edit decision needs 'args'.")
            # The tool name is fixed to the one under review — an edit cannot switch tools.
            decisions.append(
                {"type": "edit", "edited_action": {"name": action["name"], "args": decision.args}}
            )
        else:
            reject = {"type": "reject"}
            if decision.message:
                reject["message"] = decision.message
            decisions.append(reject)

    return await _run(graph, Command(resume={"decisions": decisions}), req.thread_id)
