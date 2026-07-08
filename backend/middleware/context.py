import pathlib

from deepagents.backends import FilesystemBackend
from deepagents.middleware import MemoryMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

# Created at import time (sync) — FilesystemBackend.__init__ calls Path.resolve() → os.getcwd()
# which is a blocking call. Instantiating here avoids that running inside make_graph(),
# which is called in an async context by langgraph dev (uvicorn/blockbuster would error).
_backend = FilesystemBackend(root_dir=str(pathlib.Path(__file__).parent.parent), virtual_mode=False)


def get_memory_middleware(*sources: str) -> MemoryMiddleware:
    """Load AGENTS.md memory files into the system prompt on each agent run.

    Uses FilesystemBackend so sources are real disk paths, not virtual paths.
    root_dir is the backend/ directory; sources are relative to it.
    Files that do not exist are silently skipped.
    """
    return MemoryMiddleware(
        backend=_backend,
        sources=list(sources) if sources else ["./AGENTS.md"],
    )


def get_prompt_caching_middleware() -> AnthropicPromptCachingMiddleware:
    """Anthropic prompt caching — reduces cost on repeated calls with the same system prompt.

    Adds cache_control blocks to the system message, tool definitions, and the most recent
    user message so the full conversation history can be cached and reused across calls.
    Cache TTL: 5 minutes (refreshed on each cache hit).

    Only effective when using an Anthropic model. No-op for Groq / Mistral.
    Placed innermost so it wraps the actual model call after all other middleware has run.
    """
    return AnthropicPromptCachingMiddleware(ttl="5m")
