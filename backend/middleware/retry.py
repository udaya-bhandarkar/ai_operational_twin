"""
Retry middleware for both create_agent agents (deepagents) and StateGraph nodes.

Phase 1: ModelRetryMiddleware (deepagents) on research agent.
         .with_retry() on supervisor's bound model (StateGraph has no middleware param).
Phase 2+: ToolRetryMiddleware added for API tools (web_search, web_fetch).
"""

from langchain.agents.middleware import ModelRetryMiddleware


def get_retry_middleware(
    max_retries: int = 3,
    backoff_factor: float = 1.5,
) -> list:
    """Return middleware list for create_agent() agents."""
    return [
        ModelRetryMiddleware(
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            on_failure="continue",
        )
    ]


def configure_model_retry(model, stop_after_attempt: int = 3):
    """Wrap a bound LangChain model with retry for use in StateGraph nodes."""
    return model.with_retry(
        stop_after_attempt=stop_after_attempt,
        wait_exponential_jitter=True,
    )
