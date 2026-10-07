from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware


def get_prompt_caching_middleware() -> AnthropicPromptCachingMiddleware:
    """Anthropic prompt caching — reduces cost on repeated calls with the same system prompt.

    Adds cache_control blocks to the system message, tool definitions, and the most recent
    user message so the full conversation history can be cached and reused across calls.
    Cache TTL: 5 minutes (refreshed on each cache hit).

    Only effective when using an Anthropic model. No-op for Groq / Mistral.
    Placed innermost so it wraps the actual model call after all other middleware has run.
    """
    return AnthropicPromptCachingMiddleware(ttl="5m")
