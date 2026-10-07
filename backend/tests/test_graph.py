"""Graph-level tests: thread memory, HITL interrupt/resume, history rewriting — no API calls.

The real graph and middleware stack run against a scripted fake model.
"""
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import Command

from agents.supervisor.graph import build_graph, guardrail, history_delta
from tests.conftest import table_rows
from tests.fakes import scripted_model, tool_call

CONFIG = {"configurable": {"thread_id": "t1"}}


# --- history_delta (B1) --------------------------------------------------------

def _msgs(*ids):
    return [HumanMessage(content=i, id=i) for i in ids]


def test_history_delta_returns_only_appended_messages():
    before = _msgs("a", "b")
    after = before + _msgs("c", "d")
    assert [m.id for m in history_delta(before, after)] == ["c", "d"]


def test_history_delta_replaces_history_when_rewritten():
    # SummarizationMiddleware: old messages replaced by a summary + kept tail.
    before = _msgs("a", "b", "c")
    after = _msgs("summary", "c", "new")
    delta = history_delta(before, after)
    assert isinstance(delta[0], RemoveMessage) and delta[0].id == REMOVE_ALL_MESSAGES
    assert [m.id for m in delta[1:]] == ["summary", "c", "new"]


# --- guardrail per-turn reset ---------------------------------------------------

def test_guardrail_resets_verify_budget_each_turn():
    state = {"messages": [HumanMessage(content="next question")], "verify_attempts": 1}
    assert guardrail(state)["verify_attempts"] == 0


# --- full graph with checkpointer (B2) -------------------------------------------

async def test_thread_remembers_previous_turns(no_cost_routing, ops_db):
    model = scripted_model(AIMessage("First answer."), AIMessage("Second answer."))
    graph = build_graph(checkpointer=InMemorySaver(), model=model)

    await graph.ainvoke({"messages": [HumanMessage("first question")]}, CONFIG)
    result = await graph.ainvoke({"messages": [HumanMessage("second question")]}, CONFIG)

    texts = [m.text for m in result["messages"]]
    assert texts == ["first question", "First answer.", "second question", "Second answer."]
    # The model saw the earlier turn when answering the second.
    assert "first question" in [m.text for m in model.calls[-1]]


async def test_write_pauses_for_approval_then_executes(no_cost_routing, ops_db):
    model = scripted_model(
        tool_call("duckdb_execute", {"statement": "INSERT INTO t VALUES (7)"}),
        AIMessage("Inserted."),
    )
    graph = build_graph(checkpointer=InMemorySaver(), model=model)

    paused = await graph.ainvoke({"messages": [HumanMessage("insert 7")]}, CONFIG)
    request = paused["__interrupt__"][0].value
    assert request["action_requests"][0]["args"] == {"statement": "INSERT INTO t VALUES (7)"}
    assert table_rows(ops_db) == []  # nothing ran before approval

    done = await graph.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), CONFIG)
    assert done["messages"][-1].text == "Inserted."
    assert table_rows(ops_db) == [(7,)]


async def test_rejected_write_never_executes(no_cost_routing, ops_db):
    model = scripted_model(
        tool_call("duckdb_execute", {"statement": "INSERT INTO t VALUES (7)"}),
        AIMessage("Understood, nothing was changed."),
    )
    graph = build_graph(checkpointer=InMemorySaver(), model=model)

    await graph.ainvoke({"messages": [HumanMessage("insert 7")]}, CONFIG)
    done = await graph.ainvoke(
        Command(resume={"decisions": [{"type": "reject", "message": "not today"}]}), CONFIG
    )
    assert done["messages"][-1].text == "Understood, nothing was changed."
    assert table_rows(ops_db) == []
