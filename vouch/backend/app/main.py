"""
FastAPI entry point.

Boots the app, opens the DB, and mounts the router in api/routes.py - the Trust API's `POST /verify`
plus the repricer's REST surface. CORS is wide open for the demo (tighten before any real deploy).
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
from app.api.trust_routes import trust_router  # noqa: E402

# The repricer's REST surface plus /verify (the dashboard proxy and tests hit these on the root app).
app.include_router(routes.router)
app.include_router(trust_router)

# The Trust API as a STANDALONE product, with its own OpenAPI docs at /trust/docs showing ONLY
# /verify - a developer integrating it never has to wade past the repricer's endpoints.
trust_api = FastAPI(
    title="Vouch Trust API",
    version="1.0.0",
    description="Stateless verification for scraped data. POST rows, get a verdict "
                "(PASS / REVIEW / FAIL + confidence + brief). No database, no writes.",
)
trust_api.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
trust_api.include_router(trust_router)
app.mount("/trust", trust_api)
