import pathlib

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool

from config.settings import settings
from middleware.rate_limit import get_rate_limit_middleware
from middleware.retry import get_model_retry, get_ops_limits
from tools.duckdb import (
    duckdb_execute,
    duckdb_list_tables,
    duckdb_query,
    duckdb_query_checker,
    duckdb_schema,
)

_system_prompt = (pathlib.Path(__file__).parent / "prompts" / "system.txt").read_text()
_tools = [duckdb_list_tables, duckdb_schema, duckdb_query_checker, duckdb_query, duckdb_execute]
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        # Middleware order (outer → inner):
        # ModelCallLimitMiddleware — counts logical calls (outside retry)
        # ToolCallLimitMiddleware(duckdb_execute) — caps write operations per run
        # ModelRetryMiddleware — retries model failures
        # HumanInTheLoopMiddleware — innermost, closest to tool execution
        _agent = create_agent(
            model=settings.backend_model,
            tools=_tools,
            system_prompt=_system_prompt,
            middleware=[
                *get_ops_limits(),
                get_model_retry(),
                *get_rate_limit_middleware(),
                HumanInTheLoopMiddleware(
                    interrupt_on={
                        "duckdb_execute": {
                            "allowed_decisions": ["approve", "edit", "reject"],
                            "description": "Review write statement before execution",
                        },
                        "duckdb_query": False,
                        "duckdb_list_tables": False,
                        "duckdb_schema": False,
                        "duckdb_query_checker": False,
                    }
                ),
            ],
        )
    return _agent


@tool
def ops_agent_tool(query: str) -> str:
    """Ops specialist. Use for reading or writing to the operational database (DuckDB).
    Accepts natural-language requests. Write operations pause for human approval automatically."""
    result = _get_agent().invoke({"messages": [{"role": "user", "content": query}]})
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        return last.content if hasattr(last, "content") else str(last)
    return "Ops agent returned no result."
