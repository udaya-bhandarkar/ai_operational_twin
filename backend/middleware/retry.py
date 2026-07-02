from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
)


def get_model_retry() -> ModelRetryMiddleware:
    """Retry failed model calls with exponential backoff.

    on_failure="continue" returns an AIMessage with the error instead of raising,
    so the agent can surface the failure gracefully rather than crashing.
    Placed inside ModelCallLimitMiddleware so retries don't inflate the call count.
    """
    return ModelRetryMiddleware(
        max_retries=3,
        backoff_factor=2.0,
        initial_delay=1.0,
        max_delay=60.0,
        jitter=True,
        on_failure="continue",
    )


def get_supervisor_limits() -> list:
    """Call limits for the supervisor agent.

    run_limit=10: supervisor is a routing agent — it should never need more than
    a handful of model calls per run (analyse → route → synthesise).
    10 is a generous ceiling that stops infinite loops without restricting normal use.
    """
    return [
        ModelCallLimitMiddleware(run_limit=10, exit_behavior="end"),
    ]


def get_ops_limits() -> list:
    """Call limits for the ops agent.

    ModelCallLimit run_limit=15: ops agent runs multiple tool steps
    (list_tables → schema → checker → query/execute), each requiring a model call.
    15 covers realistic multi-step DB workflows.

    ToolCallLimit on duckdb_execute run_limit=3: prevents the same write statement
    firing repeatedly if the agent loops. exit_behavior="continue" blocks the tool
    call and tells the model it hit the limit — model can then decide to stop cleanly.
    """
    return [
        ModelCallLimitMiddleware(run_limit=15, exit_behavior="end"),
        ToolCallLimitMiddleware(
            tool_name="duckdb_execute",
            run_limit=3,
            exit_behavior="continue",
        ),
    ]


def get_research_limits() -> list:
    """Call limits for the research agent.

    ToolCallLimit on web_search run_limit=5: Tavily charges per search.
    5 searches per run is enough for thorough research without runaway spend.
    exit_behavior="continue" blocks further searches and lets the model synthesise
    from what it already found.
    """
    return [
        ToolCallLimitMiddleware(
            tool_name="web_search",
            run_limit=5,
            exit_behavior="continue",
        ),
    ]
