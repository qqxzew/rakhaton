"""GET /api/stats: figures from the FHIR SQL Builder projection."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.stats.projection import load_stats

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats() -> dict:
    try:
        return load_stats()
    except Exception as exc:  # noqa: BLE001 - driver raises plain exceptions
        raise HTTPException(
            status_code=503,
            detail=f"SQL projection unavailable ({type(exc).__name__}); run scripts/sql_projection_setup.py",
        ) from exc
