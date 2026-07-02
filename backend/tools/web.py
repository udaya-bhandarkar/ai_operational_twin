from langchain_core.tools import tool

from config.settings import settings


@tool
def web_search(query: str) -> str:
    """Search the web for information about a topic. Returns a summary of results."""
    if not settings.tavily_api_key:
        return (
            "[web_search] No results — TAVILY_API_KEY is not set. "
            "Add it to .env and run: uv pip install -e \".[tavily]\""
        )
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(query, max_results=5)
        results = response.get("results", [])
        if not results:
            return "[web_search] No results found."
        lines = []
        for r in results:
            lines.append(f"**{r.get('title', 'Untitled')}**")
            lines.append(r.get("url", ""))
            lines.append(r.get("content", "").strip())
            lines.append("")
        return "\n".join(lines).strip()
    except Exception as e:
        return f"[web_search] Failed: {e}"


@tool
def web_fetch(url: str) -> str:
    """Fetch and return the text content of a web page at the given URL."""
    try:
        import httpx
        response = httpx.get(url, timeout=15, follow_redirects=True)
        response.raise_for_status()
        text = response.text
        # Cap to avoid blowing context window
        if len(text) > 8000:
            text = text[:8000] + "\n\n[truncated — content exceeds 8000 chars]"
        return text
    except Exception as e:
        return f"[web_fetch] Failed to fetch {url!r}: {e}"
