"""API tests for /api/chat and /api/chat/resume — real graph, scripted model, no API calls."""
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agents.supervisor.graph import build_graph
from api.app import app
from config.settings import settings
from tests.conftest import table_rows
from tests.fakes import scripted_model, tool_call


@pytest.fixture
def client_with(no_cost_routing, ops_db, monkeypatch):
    """Factory: a TestClient whose graph uses the given scripted replies."""
    monkeypatch.setattr(settings, "checkpoint_db", ":memory:")
    clients = []

    def make(*replies):
        client = TestClient(app)
        client.__enter__()  # runs lifespan → app.state.checkpointer
        app.state.graph = build_graph(
            checkpointer=app.state.checkpointer, model=scripted_model(*replies)
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)
    app.state.graph = None


def _write_then(answer: str) -> tuple:
    return tool_call("duckdb_execute", {"statement": "INSERT INTO t VALUES (7)"}), AIMessage(answer)


def test_chat_completes_and_keeps_thread(client_with):
    client = client_with(AIMessage("One."), AIMessage("Two."))
    first = client.post("/api/chat", json={"message": "q1"}).json()
    assert first["status"] == "complete" and first["reply"] == "One."

    second = client.post(
        "/api/chat", json={"message": "q2", "thread_id": first["thread_id"]}
    ).json()
    assert second["reply"] == "Two."
    state = app.state.graph.get_state({"configurable": {"thread_id": first["thread_id"]}})
    assert [m.text for m in state.values["messages"]] == ["q1", "One.", "q2", "Two."]


def test_write_requires_approval_then_resumes(client_with, ops_db):
    client = client_with(*_write_then("Inserted."))
    paused = client.post("/api/chat", json={"message": "insert 7"}).json()
    assert paused["status"] == "awaiting_approval"
    assert paused["approval"]["actions"][0]["name"] == "duckdb_execute"
    assert "INSERT INTO t VALUES (7)" in paused["reply"]  # readable even for old clients
    assert table_rows(ops_db) == []

    done = client.post(
        "/api/chat/resume",
        json={"thread_id": paused["thread_id"], "decisions": [{"type": "approve"}]},
    ).json()
    assert done["status"] == "complete" and done["reply"] == "Inserted."
    assert table_rows(ops_db) == [(7,)]


def test_edit_decision_runs_edited_statement(client_with, ops_db):
    client = client_with(*_write_then("Inserted 8 instead."))
    paused = client.post("/api/chat", json={"message": "insert 7"}).json()
    client.post(
        "/api/chat/resume",
        json={
            "thread_id": paused["thread_id"],
            "decisions": [{"type": "edit", "args": {"statement": "INSERT INTO t VALUES (8)"}}],
        },
    )
    assert table_rows(ops_db) == [(8,)]


def test_new_message_blocked_while_awaiting_approval(client_with):
    client = client_with(*_write_then("Inserted."))
    paused = client.post("/api/chat", json={"message": "insert 7"}).json()
    r = client.post("/api/chat", json={"message": "hello?", "thread_id": paused["thread_id"]})
    assert r.status_code == 409


def test_resume_validates_request(client_with):
    client = client_with(*_write_then("Inserted."))
    r = client.post("/api/chat/resume", json={"thread_id": "nope", "decisions": []})
    assert r.status_code == 409  # nothing pending

    paused = client.post("/api/chat", json={"message": "insert 7"}).json()
    r = client.post(
        "/api/chat/resume",
        json={"thread_id": paused["thread_id"], "decisions": [{"type": "approve"}] * 2},
    )
    assert r.status_code == 422  # one action, two decisions
    r = client.post(
        "/api/chat/resume",
        json={"thread_id": paused["thread_id"], "decisions": [{"type": "edit"}]},
    )
    assert r.status_code == 422  # edit without args


def test_agent_failure_returns_safe_500(client_with):
    client = client_with()  # no scripted replies → the run raises
    app.state.graph = _ExplodingGraph(app.state.graph)
    r = client.post("/api/chat", json={"message": "q"})
    assert r.status_code == 500
    assert r.json()["detail"] == "The agent failed to answer. Please retry."


class _ExplodingGraph:
    def __init__(self, graph):
        self._graph = graph

    async def aget_state(self, config):
        return await self._graph.aget_state(config)

    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("secret internal detail")
