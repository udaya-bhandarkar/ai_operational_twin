"""POST /api/chat — forward a user message to the supervisor LangGraph agent.

Request  : {"message": str, "thread_id": str | null, "view": str | null}
Response : {"reply": str}
thread_id persists conversation state across turns (LangGraph checkpointer).
"""
import uuid
from typing import Any

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

router = APIRouter(prefix="/api")

_graph: Any = None


def _get_graph() -> Any:
    global _graph
    if _graph is None:
        from agents.supervisor.graph import make_graph
        _graph = make_graph()
    return _graph


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    view: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())
    # Async invoke: some agent middleware only implements the async model-call hook.
    result = await _get_graph().ainvoke(
        {"messages": [HumanMessage(content=req.message)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = result.get("messages", [])
    reply = messages[-1].content if messages else ""
    return {"reply": reply, "thread_id": thread_id}
