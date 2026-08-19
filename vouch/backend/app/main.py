"""
FastAPI entry point.

Phase 1: expand api/routes.py with the endpoints the dashboard needs:
    GET  /products
    GET  /proposals?status=pending|held
    POST /proposals/{id}/approve
    POST /proposals/{id}/reject
    GET  /heal-events
For now this boots and serves /health so Phase 0's check passes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Vouch", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten for anything beyond the demo
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "vouch"}


from app.api import routes  # noqa: E402  (imported after app creation by design)

app.include_router(routes.router)
