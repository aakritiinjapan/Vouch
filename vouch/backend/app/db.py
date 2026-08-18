"""SQLite engine + session. Call init_db() once on startup."""

from __future__ import annotations

from sqlmodel import SQLModel, Session, create_engine

from app.config import settings

engine = create_engine(settings.database_url, echo=False,
                       connect_args={"check_same_thread": False})


def init_db() -> None:
    import app.models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
