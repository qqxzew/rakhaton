"""FastAPI application."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import agent, cases, health, hooks, meetings, ml, patients, search, stats, system
from app.api import requests as requests_api
from app.api.errors import register_error_handlers
from app.api.system import warm_native
from app.app_db.repositories import ensure_meetings
from app.app_db.session import get_engine, init_db, session_scope
from app.config import REPO_ROOT, today
from app.iris_resources import close_resources
from app.logging import configure_logging
from app.stats.projection import sql_pool_enabled, warm_pool


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()
    with session_scope() as db:
        ensure_meetings(db, today())
    if sql_pool_enabled():
        await asyncio.gather(asyncio.to_thread(warm_pool), asyncio.to_thread(warm_native))
    try:
        yield
    finally:
        close_resources()
        get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="PACS Komparátor", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(meetings.router)
    app.include_router(patients.router)
    app.include_router(cases.router)
    app.include_router(agent.router)
    app.include_router(stats.router)
    app.include_router(hooks.router)
    app.include_router(ml.router)
    app.include_router(requests_api.router)
    app.include_router(search.router)
    app.include_router(system.router)
    _serve_frontend(app)
    return app


def _serve_frontend(app: FastAPI) -> None:
    """Cloud deployment: serve the built frontend (frontend/dist) from the same origin as /api."""
    dist = REPO_ROOT / "frontend" / "dist"
    if os.environ.get("SERVE_FRONTEND") != "1" or not (dist / "index.html").is_file():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(dist / "index.html")


app = create_app()
