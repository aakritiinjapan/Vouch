"""SQLite engine + session. Call init_db() once on startup."""

from __future__ import annotations

import logging
from typing import Iterator

from sqlmodel import SQLModel, Session, create_engine

from app.config import settings

log = logging.getLogger(__name__)

engine = create_engine(settings.database_url, echo=False,
                       connect_args={"check_same_thread": False})


def init_db() -> None:
    import app.models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(engine)
    # Logged on purpose: "the API is reading a different vouch.db than the seeder wrote" is
    # invisible otherwise, and it presents as an empty dashboard rather than as an error.
    log.info("database ready at %s", settings.database_url)


def get_session() -> Session:
    """A plain Session for scripts and tests: `with get_session() as s: ...`"""
    return Session(engine)


def session_dep() -> Iterator[Session]:
    """FastAPI dependency. Separate from get_session() because Depends() needs a generator,
    while scripts/seed.py needs a context manager."""
    with Session(engine) as session:
        yield session
