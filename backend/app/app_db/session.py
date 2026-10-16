"""SQLite engine and session lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.app_db.models import Base
from app.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if "sqlite" in url else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


def init_db(url: str | None = None) -> Engine:
    """(Re)initialise the global engine and create tables."""
    global _engine, _factory
    _engine = make_engine(url or get_settings().app_db_url)
    Base.metadata.create_all(_engine)
    _factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or init_db()


@contextmanager
def session_scope() -> Iterator[Session]:
    if _factory is None:
        init_db()
    assert _factory is not None
    session = _factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed on success."""
    with session_scope() as session:
        yield session
