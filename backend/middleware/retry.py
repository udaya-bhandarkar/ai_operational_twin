from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
)

# Error signatures worth retrying: provider rate limits (HTTP 429) and transient server
# errors (5xx / overloaded / timeout). Matched on the exception text so it stays
# provider-agnostic (Mistral / Anthropic / Groq raise different exception classes).
_RETRYABLE_MARKERS = (
    "429",
    "rate limit",
    "rate_limited",
    "overloaded",
    "timeout",
    "timed out",
    "502",
    "503",
    "504",
    "temporarily unavailable",
)


def _should_retry(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def get_model_retry() -> ModelRetryMiddleware:
    """Retry failed model calls, waiting out rate limits with long exponential backoff.

    Pairs with RateLimitMiddleware (proactive pacing). When a 429 slips through anyway,
    this waits progressively longer (5s → 10 → 20 → 40 → 60) for the provider's window to
    reset, rather than hammering. `retry_on` restricts retries to rate-limit / transient
    errors — non-retryable failures (bad request, auth) surface immediately instead of
    burning attempts.

    on_failure="continue" returns an AIMessage with the error instead of raising, so the
    agent surfaces the failure gracefully. Placed inside ModelCallLimitMiddleware so
    retries don't inflate the call count.
    """
    return ModelRetryMiddleware(
        max_retries=5,
        retry_on=_should_retry,
        backoff_factor=2.0,
        initial_delay=5.0,
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
