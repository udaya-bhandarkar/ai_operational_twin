"""Proactive model-call rate limiting — the "waiting system".

A single agent turn (especially a DB question routed to the ops agent) fans out into many
model calls in quick succession: list tables -> get schema -> write SQL -> run query ->
summarise. On a rate-limited provider (Mistral free tier ~1 req/s) that burst trips HTTP 429.

This middleware paces calls *before* they happen: it blocks (sleeps) until a token is free,
so calls are spread under the provider limit instead of failing and retrying. The limiter is
a single module-level instance shared across every agent (supervisor + ops + research), so
pacing is global — the supervisor's calls and the ops agent's calls draw from one budget.

Complements ModelRetryMiddleware: throttling prevents most 429s up front; retry still covers
genuinely transient failures.
"""
from langchain.agents.middleware import AgentMiddleware
from langchain_core.rate_limiters import InMemoryRateLimiter

from config.settings import settings

# check_every_n_seconds: how often a blocked caller re-checks for a free token (responsiveness).
# max_bucket_size=1: no burst allowance — calls are spaced evenly at requests_per_second.
_limiter = InMemoryRateLimiter(
    requests_per_second=max(settings.model_requests_per_second, 0.01),
    check_every_n_seconds=0.1,
    max_bucket_size=1,
)


class RateLimitMiddleware(AgentMiddleware):
    """Block before each model call until the shared rate limiter grants a token.

    Implements both sync and async hooks so it works on `graph.invoke` (evals) and
    `graph.ainvoke` (API chat) without the async-only NotImplementedError pitfall.
    """

    def wrap_model_call(self, request, handler):
        _limiter.acquire(blocking=True)
        return handler(request)

    async def awrap_model_call(self, request, handler):
        await _limiter.aacquire(blocking=True)
        return await handler(request)


def get_rate_limit_middleware() -> list:
    """Return the throttle middleware, or nothing when disabled (rps <= 0)."""
    if settings.model_requests_per_second <= 0:
        return []
    return [RateLimitMiddleware()]
