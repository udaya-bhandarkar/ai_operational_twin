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
_cors_kwargs = {"allow_methods": ["GET", "POST"], "allow_headers": ["*"]}
_explicit_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _explicit_origins:
    _cors_kwargs["allow_origins"] = _explicit_origins
if settings.backend_env == "dev":
    _cors_kwargs["allow_origin_regex"] = r"http://(localhost|127\.0\.0\.1):\d+"
# Fallback so a misconfigured non-dev deploy fails safe (no origins) rather than crashing.
if "allow_origins" not in _cors_kwargs and "allow_origin_regex" not in _cors_kwargs:
    _cors_kwargs["allow_origins"] = []
app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(dashboard.router)
app.include_router(chat.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=False)
