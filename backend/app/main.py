"""FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import cases, health, meetings, patients
from app.api.errors import register_error_handlers
from app.app_db.repositories import ensure_meetings
from app.app_db.session import init_db, session_scope
from app.config import today
from app.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()
    with session_scope() as db:
        ensure_meetings(db, today())
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="PACS Komparátor", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(meetings.router)
    app.include_router(patients.router)
    app.include_router(cases.router)
    return app


app = create_app()
