"""Health endpoint: reports the state of every dependency explicitly."""

from __future__ import annotations

import httpx
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
    if settings.fhir_backend == "iris":
        try:
            from app.fhir_store.iris import IrisFhirStore

            return {"status": "ok", "backend": "iris", "patients": IrisFhirStore().count("Patient")}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "backend": "iris", "detail": type(exc).__name__}
    if settings.fhir_backend != "local":
        return {"status": "error", "backend": settings.fhir_backend, "detail": "backend not available"}
    fhir_dir = settings.raw_dir / "fhir"
    if not fhir_dir.exists():
        return {"status": "error", "backend": "local", "detail": "dataset not extracted"}
    return {"status": "ok", "backend": "local", "patients": sum(1 for _ in fhir_dir.glob("PAC-*.json"))}


def _probe_orthanc(rest: str) -> bool:
    try:
        return httpx.get(f"{rest}/system", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        return False


def _probe_cfind(ae: str) -> bool:
    """A real study-level C-FIND for a patient that does not exist: proves the IRIS -> DICOM -> Orthanc path."""
    from app.exchange.dicom import default_client

    try:
        default_client().find(ae, "HEALTH-PROBE", None, None)
        return True
    except Exception:  # noqa: BLE001 - any failure means the path is down
        return False


def _check_pacs() -> dict:
    """Simulated PACS (Orthanc, one per AE) and the C-FIND path. Informational: a failure only degrades
    the health, because the availability check falls back to the FHIR hospitals / dataset flag."""
    settings = get_settings()
    if settings.availability_adapter != "dicom":
        return {"status": "skipped", "adapter": settings.availability_adapter, "simulated": True}
    try:
        from app.exchange.dicom import nodes

        pacs = nodes()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "adapter": "dicom", "detail": type(exc).__name__}
    orthanc = {node.ae: _probe_orthanc(node.rest) for node in pacs.values()}
    first = next(iter(pacs.values()))
    cfind = _probe_cfind(first.ae) if orthanc[first.ae] else False
    status = "ok" if cfind and all(orthanc.values()) else "error"
    return {"status": status, "adapter": "dicom", "client": settings.dicom_client, "orthanc": orthanc,
            "cfind": cfind, "simulated": True,
            **({} if status == "ok" else {"detail": "fallback to FHIR hospitals / dataset flag"})}


def _check_llm() -> dict:
    settings = get_settings()
    if not settings.api_key:
        return {"status": "error", "detail": "API_KEY is not set"}
    return {"status": "ok", "model": settings.llm_model_extract, "note": "configured, not probed"}


@router.get("/health")
def health() -> JSONResponse:
    checks = {"database": _check_db(), "fhir_store": _check_fhir(), "pacs": _check_pacs(), "llm": _check_llm()}
    required_ok = checks["database"]["status"] == "ok" and checks["fhir_store"]["status"] == "ok"
    optional_ok = checks["llm"]["status"] == "ok" and checks["pacs"]["status"] in ("ok", "skipped")
    overall = "ok" if required_ok and optional_ok else "degraded" if required_ok else "error"
    return JSONResponse(status_code=200 if required_ok else 503, content={"status": overall, **checks})
