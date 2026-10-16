"""Health endpoint: reports the state of every dependency explicitly."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.app_db.session import get_engine
from app.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


def _check_db() -> dict:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": type(exc).__name__}


def _check_fhir() -> dict:
    settings = get_settings()
    if settings.fhir_backend != "local":
        return {"status": "error", "backend": settings.fhir_backend, "detail": "backend not available"}
    fhir_dir = settings.raw_dir / "fhir"
    if not fhir_dir.exists():
        return {"status": "error", "backend": "local", "detail": "dataset not extracted"}
    return {"status": "ok", "backend": "local", "patients": sum(1 for _ in fhir_dir.glob("PAC-*.json"))}


def _check_llm() -> dict:
    settings = get_settings()
    if not settings.api_key:
        return {"status": "error", "detail": "API_KEY is not set"}
    return {"status": "ok", "model": settings.llm_model_extract, "note": "configured, not probed"}


@router.get("/health")
def health() -> JSONResponse:
    checks = {"database": _check_db(), "fhir_store": _check_fhir(), "llm": _check_llm()}
    required_ok = checks["database"]["status"] == "ok" and checks["fhir_store"]["status"] == "ok"
    overall = "ok" if required_ok and checks["llm"]["status"] == "ok" else "degraded" if required_ok else "error"
    return JSONResponse(status_code=200 if required_ok else 503, content={"status": overall, **checks})
