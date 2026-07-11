"""FastAPI gateway entrypoint.

Run:
    python -m api.app                     # serves on http://localhost:8000
    uvicorn api.app:app --reload --port 8000

Frontend points at this via VITE_API_BASE=http://localhost:8000/api
(CORS enabled below — no Vite proxy needed).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import chat, dashboard
from config.settings import settings

app = FastAPI(title="AI Operational Twin Gateway")

# CORS. Explicit origins come from CORS_ORIGINS (comma-separated) for deployed frontends.
# Any localhost origin is allowed automatically in dev (Vite port varies: 5173, 5174, ...).
# CORS_ORIGIN_REGEX allows pattern matching for platforms like Vercel that generate unique
# preview URLs per deploy (e.g. https://.*\.vercel\.app).
_cors_kwargs = {"allow_methods": ["GET", "POST"], "allow_headers": ["*"]}
_explicit_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _explicit_origins:
    _cors_kwargs["allow_origins"] = _explicit_origins
_origin_regex = settings.cors_origin_regex
if settings.backend_env == "dev":
    _dev_regex = r"http://(localhost|127\.0\.0\.1):\d+"
    _origin_regex = f"({_origin_regex})|({_dev_regex})" if _origin_regex else _dev_regex
if _origin_regex:
    _cors_kwargs["allow_origin_regex"] = _origin_regex
# Fallback so a misconfigured non-dev deploy fails safe (no origins) rather than crashing.
if "allow_origins" not in _cors_kwargs and "allow_origin_regex" not in _cors_kwargs:
    _cors_kwargs["allow_origins"] = []
app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(dashboard.router)
app.include_router(chat.router)


@app.on_event("startup")
def _check_config() -> None:
    # Fail fast with a clear message if the chat provider key is missing, rather than
    # surfacing a cryptic 401 on the first /api/chat call. Dashboard endpoints need no key.
    try:
        settings.require_provider_key()
    except RuntimeError as e:
        import logging
        logging.getLogger("api").warning("Chat disabled: %s", e)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=False)
