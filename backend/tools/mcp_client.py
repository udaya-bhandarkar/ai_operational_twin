"""MCP (Model Context Protocol) client — loads external tools from MCP servers.

Configure MCP_SERVERS below to connect to one or more MCP servers. Tools from all
configured servers are returned by get_mcp_tools() and can be passed directly to
create_agent(tools=...).

Supported transports:
  stdio — local subprocess (dev; no network needed)
  http  — HTTP endpoint (staging/prod)
  sse   — SSE endpoint (streaming)

To add a server: uncomment or add an entry to MCP_SERVERS, then install its package
(e.g. `npx -y @modelcontextprotocol/server-filesystem`) and restart langgraph dev.

Phase 3 ships this as infrastructure. No servers are wired by default — add them as
your use case requires.
"""

import asyncio
import concurrent.futures
import logging

logger = logging.getLogger(__name__)

# Add MCP server configs here. Key = server name (used for tool name prefixing).
# See MultiServerMCPClient docs for full connection config options.
#
# Example — filesystem server (gives agent read/write access to a local directory):
#   "filesystem": {
#       "command": "npx",
#       "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/agent-workspace"],
#       "transport": "stdio",
#   }
#
# Example — remote HTTP server:
#   "knowledge-base": {
#       "url": "http://localhost:8000/mcp",
#       "transport": "http",
#   }
MCP_SERVERS: dict = {}

_mcp_tools: list | None = None


def get_mcp_tools() -> list:
    """Return LangChain tools loaded from all configured MCP servers. Cached after first call.

    Thread-safe wrapper around the async MultiServerMCPClient.get_tools() — works in both
    sync (direct script) and async (langgraph dev / uvicorn) contexts.
    Returns an empty list if MCP_SERVERS is empty.
    """
    global _mcp_tools
    if _mcp_tools is not None:
        return _mcp_tools

    if not MCP_SERVERS:
        _mcp_tools = []
        return _mcp_tools

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(MCP_SERVERS, tool_name_prefix=True)

    async def _fetch() -> list:
        return await client.get_tools()

    try:
        _mcp_tools = asyncio.run(_fetch())
    except RuntimeError:
        # Already inside a running event loop (langgraph dev / uvicorn).
        # Offload to a thread so asyncio.run() can create its own loop there.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _fetch())
            _mcp_tools = future.result(timeout=30)

    logger.info("MCP tools loaded: %s", [t.name for t in _mcp_tools])
    return _mcp_tools
