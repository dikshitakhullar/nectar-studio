"""FastAPI application instance.

Exposes the routes described in spec §2.1, configures CORS for the studio
frontend, and creates the SQLite schema on startup.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lighting_engine import __version__
from lighting_engine.api.db import dispose_db, init_db
from lighting_engine.api.routes import generation, projects, rooms
from lighting_engine.api.schemas import HealthResponse

# Origins that are *always* allowed; the env var ``CORS_ALLOWED_ORIGINS`` (a
# comma-separated list) is concatenated on top so deploy environments can add
# their own without rebuilding.
_DEFAULT_ORIGINS: list[str] = ["http://localhost:3000"]
# `allow_origin_regex` separately matches Vercel preview URLs.
_VERCEL_REGEX = r"https://.*\.vercel\.app"


def _cors_origins() -> list[str]:
    env = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    extra: list[str] = [o.strip() for o in env.split(",") if o.strip()] if env else []
    return [*_DEFAULT_ORIGINS, *extra]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: create tables. Shutdown: dispose engine."""
    await init_db()
    try:
        yield
    finally:
        await dispose_db()


app = FastAPI(
    title="nectar-studio lighting engine",
    description=(
        "FastAPI service for the v1 lighting-design pipeline. "
        "Spec: docs/superpowers/specs/2026-06-03-v1-design.md"
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=_VERCEL_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(rooms.router)
app.include_router(generation.router)


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    """Liveness probe — returns 200 once the app is accepting requests."""
    return HealthResponse(status="ok", service="lighting-engine", version=__version__)
