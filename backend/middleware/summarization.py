from langchain.agents.middleware import SummarizationMiddleware

from config.settings import settings


def get_summarization_middleware() -> SummarizationMiddleware:
    """Auto-compress conversation history when context fills up.

    trigger=("fraction", 0.8): summarise when 80% of model's max input tokens used.
    keep=("messages", 6): retain 6 most recent messages verbatim after compression.
    Uses summarization_model (haiku by default) — cheap + fast, not the main model.
    """
    return SummarizationMiddleware(
        model=settings.summarization_model,
        trigger=("fraction", 0.8),
        keep=("messages", 6),
    )
