from typing import Callable

from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain.chat_models import init_chat_model

from config.settings import settings


def _provider(model_str: str) -> str:
    """Extract provider prefix, e.g. 'anthropic' from 'anthropic:claude-opus-4-8'."""
    return model_str.split(":")[0] if ":" in model_str else "mistral"


# Only route if user explicitly set a cheaper model (different from backend_model).
# When SUMMARIZATION_MODEL is unset it defaults to BACKEND_MODEL — routing to the same
# model is pointless, so skip. Also skip if providers differ (cross-provider key issue).
_routing_enabled = (
    settings.summarization_model != settings.backend_model
    and _provider(settings.summarization_model) == _provider(settings.backend_model)
)

# Lazy-initialized on first call to avoid init_chat_model() running at import time,
# which loads heavy provider libraries and causes slow graph startup warnings.
_budget_model = None
_budget_model_loaded = False


@wrap_model_call
async def dev_cost_router(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    """Route to a budget model in dev; use configured model in staging/prod.

    Provider-agnostic — works with Anthropic, Groq, or Mistral.
    Set SUMMARIZATION_MODEL in .env to a cheap model from the same provider as BACKEND_MODEL.
    No-op if SUMMARIZATION_MODEL is from a different provider or not configured.
    Switch to staging/prod behaviour locally by setting BACKEND_ENV=staging in .env.
    """
    global _budget_model, _budget_model_loaded
    if not _budget_model_loaded:
        if _routing_enabled:
            _budget_model = init_chat_model(settings.summarization_model)
        _budget_model_loaded = True
    if settings.backend_env == "dev" and _budget_model is not None:
        request = request.override(model=_budget_model)
    return await handler(request)
