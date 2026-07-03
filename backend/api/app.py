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

app = FastAPI(title="AI Operational Twin Gateway")

# Dev CORS: allow any localhost origin (Vite dev server port varies: 5173, etc.).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(chat.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=False)
