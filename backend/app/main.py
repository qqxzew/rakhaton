"""FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import cases, health
from app.api import requests as requests_api
from app.api.errors import register_error_handlers
from app.app_db.session import init_db
from app.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="PACS Komparátor", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(cases.router)
    app.include_router(requests_api.router)
    return app


app = create_app()
