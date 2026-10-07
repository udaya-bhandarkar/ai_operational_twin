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


def get_call_limits() -> list:
    """Per-run call budgets for the agent.

    ModelCallLimit run_limit=15: multi-step tool work (e.g. list_tables → schema → query)
    needs a model call per step; 15 covers realistic workflows and stops runaway loops.

    ToolCallLimit on duckdb_execute run_limit=3: prevents the same write firing repeatedly if
    the agent loops.

    ToolCallLimit on web_search run_limit=5: search APIs charge per call; 5 is enough for
    thorough research without runaway spend.

    exit_behavior="continue" on tool limits blocks the call and tells the model it hit the
    limit, so it can finish from what it already has. Limits on tools that are not attached
    (e.g. SQL tools with no database configured) are inert.
    """
    return [
        ModelCallLimitMiddleware(run_limit=15, exit_behavior="end"),
        ToolCallLimitMiddleware(tool_name="duckdb_execute", run_limit=3, exit_behavior="continue"),
        ToolCallLimitMiddleware(tool_name="web_search", run_limit=5, exit_behavior="continue"),
    ]
