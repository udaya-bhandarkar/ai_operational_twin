from langchain.agents.middleware import PIIMiddleware


def get_pii_middleware() -> list:
    """PII middleware for the agent.

    Blocks API key patterns on input and output.
    langchain>=1.3.2 required for apply_to_output support.

    Email middleware intentionally omitted — redacting emails in inputs breaks
    legitimate use cases (e.g. "draft an email to x@y.com"), and the agent may need to
    return emails from tool results.
    """
    return [
        PIIMiddleware(
            "api_key",
            detector=r"sk-[a-zA-Z0-9]{32,}",
            strategy="block",
            apply_to_input=True,
            apply_to_output=True,
        ),
    ]
