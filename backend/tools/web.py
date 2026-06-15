from langchain.tools import tool


@tool
def web_search(query: str) -> str:
    """Search the web for information about a topic. Returns a summary of results."""
    # Phase 1 stub — replace with Tavily integration in Phase 2
    return f"[STUB] web_search called with query: {query!r}. No real results in Phase 1."


@tool
def web_fetch(url: str) -> str:
    """Fetch and return the text content of a web page at the given URL."""
    # Phase 1 stub — replace with real HTTP fetch in Phase 2
    return f"[STUB] web_fetch called for URL: {url!r}. No real content in Phase 1."
