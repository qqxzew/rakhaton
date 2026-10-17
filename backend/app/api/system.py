"""System screens: request worklist, hospital registry and the live IRIS integration map.

Read-mostly. Every section degrades to `{"available": false, "reason": ...}` when IRIS or a part of it is
unreachable, and no endpoint returns report text unless `include_text=true` is asked for explicitly.
The only write actions are simulations (HL7 ORM from the simulated RIS, a DICOM C-FIND query); nothing
here approves or sends a request (approval stays in /api/requests, hard rule 3).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import cache as api_cache
from app.api.case_views import fictional_name
from app.api.errors import ValidationFailed
from app.api.requests import production
from app.api.search import get_vector_backend
from app.app_db.models import Case
from app.app_db.session import get_db
from app.config import CONFIG_DIR, get_settings, today
from app.logging import get_logger
from app.requests.production_client import ProductionClient, visual_trace_url
from app.search.vector_store import VectorBackend

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["system"])

PRODUCTION = "PacsComparator.Production"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# State groups of the worklist filter pills.
STATE_GROUP = {
    "DETECTED": "approval", "DRAFTED": "approval",
    "APPROVED": "sent", "SENT": "sent", "ACKNOWLEDGED": "sent", "NEEDS_INFO": "sent",
    "REMINDER_SENT": "escalated", "VOICE_ESCALATED": "escalated", "HUMAN_ESCALATED": "escalated",
    "REJECTED": "escalated", "WRONG_RECIPIENT": "escalated",
    "RECEIVED": "received",
    "VERIFIED": "verified", "CLOSED": "verified",
    "CANCELLED": "closed",
}
TERMINAL = {"VERIFIED", "CLOSED", "CANCELLED", "REJECTED"}
_PROBLEM = {"HUMAN_ESCALATED", "REJECTED", "WRONG_RECIPIENT"}
_WARN = {"REMINDER_SENT", "VOICE_ESCALATED", "NEEDS_INFO"}

MOTOL_RESOURCES: list[tuple[str, str, dict[str, str]]] = [
    ("Patient", "Patient", {}),
    ("ImagingStudy", "ImagingStudy", {}),
    ("DiagnosticReport", "DiagnosticReport", {}),
    ("DocumentReference", "DocumentReference", {}),
    ("ServiceRequest", "ServiceRequest", {}),
    ("Observation (imaging-reference)", "Observation", {"category": "imaging-reference"}),
    ("Task", "Task", {}),
    ("Communication", "Communication", {}),
    ("Provenance", "Provenance", {}),
    ("AuditEvent", "AuditEvent", {}),
]
HOSPITAL_RESOURCES = ("Patient", "ImagingStudy", "DiagnosticReport")

# Ens.MessageHeader.Status
MESSAGE_STATUS = {1: "Created", 2: "Queued", 3: "Delivered", 4: "Discarded", 5: "Suspended", 6: "Deferred",
                  7: "Aborted", 8: "Error", 9: "Completed"}

# Documented in CLAUDE.md section 20 (Stage D5); used when IRIS cannot be read.
ML_FALLBACK = [
    {"model": "PacsMLLateArrival", "kind": "classification", "predicts": "ArrivedLate",
     "metrics": {"Accuracy": 0.88, "Precision": 0.62, "Recall": 0.97, "ROC-AUC": 0.97}},
    {"model": "PacsMLResponseHours", "kind": "regression", "predicts": "ResponseHours",
     "metrics": {"R2": 0.56, "RMSE": 25.9}},
]


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    return {"available": False, "reason": reason, **extra}


def _reason(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:160]}"


def _iris_origin() -> str:
    parts = urlparse(get_settings().iris_fhir_base)
    return f"{parts.scheme}://{parts.netloc}"


def _providers() -> list[dict]:
    import json

    return json.loads((CONFIG_DIR / "providers.json").read_text(encoding="utf-8"))


# --- IRIS access (one lazy connection per HTTP request; tests replace the whole class) -------------


class IrisSystem:
    """Thin read access to IRIS SQL + native API in FHIRSERVER, plus the simulated HL7 entry point."""

    def __init__(self) -> None:
        self._conn: Any = None
        self._cursor: Any = None
        self._native: Any = None

    def _connect(self) -> None:
        if self._conn is None:
            import iris

            s = get_settings()
            host = urlparse(s.iris_fhir_base).hostname or "localhost"
            self._conn = iris.createConnection(host, 1972, "FHIRSERVER", s.iris_user or "SuperUser",
                                               s.iris_password or "SYS")

    def cursor(self) -> Any:
        self._connect()
        if self._cursor is None:
            self._cursor = self._conn.cursor()
        return self._cursor

    def native(self) -> Any:
        self._connect()
        if self._native is None:
            import iris

            self._native = iris.createIRIS(self._conn)
        return self._native

    def rows(self, sql: str, params: list | None = None) -> list[tuple]:
        cur = self.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return [tuple(r) for r in cur.fetchall()]

    def production_status(self) -> dict[str, Any]:
        api = self.native()
        name = api.get("^Ens.Runtime", "Name") or ""
        running = bool(int(api.classMethodValue("Ens.Director", "IsProductionRunning") or 0))
        return {"name": str(name), "running": running}

    def production_items(self, production_name: str) -> list[tuple]:
        return self.rows("SELECT Name, ClassName, Enabled, Category FROM Ens_Config.Item WHERE Production = ? "
                         "ORDER BY ID", [production_name])

    def messages(self, top: int) -> list[tuple]:
        return self.rows(f"SELECT TOP {int(top)} ID, TimeCreated, SourceConfigName, TargetConfigName, "
                         "MessageBodyClassName, SessionId, Status FROM Ens.MessageHeader ORDER BY ID DESC")

    def ml_models(self) -> list[tuple]:
        return self.rows("SELECT MODEL_NAME, PREDICTING_COLUMN_NAME, DEFAULT_TRAINED_MODEL_NAME "
                         "FROM INFORMATION_SCHEMA.ML_MODELS")

    def ml_metrics(self) -> list[tuple]:
        return self.rows("SELECT MODEL_NAME, METRIC_NAME, METRIC_VALUE FROM INFORMATION_SCHEMA.ML_VALIDATION_METRICS "
                         "ORDER BY MODEL_NAME")

    def predict(self, provider: str, modality: str, region: str, sent: datetime, deadline: datetime) -> dict:
        from app.ml.predict import predict_request

        return predict_request(provider, modality, region, sent, deadline, "email", cursor=self.cursor())

    def send_hl7(self, message: str, port: int = 4561) -> str:
        return str(self.native().classMethodValue("PacsComparator.HL7.Api", "SendMllp", message, port))

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = self._cursor = self._native = None


def get_iris() -> Iterator[IrisSystem]:
    system = IrisSystem()
    try:
        yield system
    finally:
        system.close()


class FhirReader:
    """`_summary=count` searches and single reads on the Motol and simulated hospital FHIR endpoints."""

    def __init__(self) -> None:
        s = get_settings()
        self._client = httpx.Client(auth=(s.iris_user or "SuperUser", s.iris_password or "SYS"), timeout=15,
                                    headers={"Accept": "application/fhir+json"})

    def count(self, base: str, resource_type: str, params: dict[str, str] | None = None) -> int:
        resp = self._client.get(f"{base}/{resource_type}", params={**(params or {}), "_summary": "count"})
        resp.raise_for_status()
        return int(resp.json().get("total") or 0)

    def exists(self, base: str, resource_type: str, resource_id: str) -> bool:
        return self._client.get(f"{base}/{resource_type}/{resource_id}").status_code == 200

    def close(self) -> None:
        self._client.close()


def get_fhir() -> Iterator[FhirReader]:
    reader = FhirReader()
    try:
        yield reader
    finally:
        reader.close()


def get_stats_loader() -> Callable[[], dict]:
    from app.stats.projection import load_stats

    return load_stats


def get_cfind() -> Any:
    from app.exchange.dicom import default_client

    return default_client()


# --- helpers -----------------------------------------------------------------------------------


def _parse_day(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _shift(iso: str | None, offset: int) -> tuple[str | None, bool]:
    """Presentation shift of a patient-frame date (CLAUDE.md 8.3); month/year precision stays as written."""
    if not iso:
        return None, False
    if offset and re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
        return (date.fromisoformat(iso) + timedelta(days=offset)).isoformat(), True
    return iso, False


def _urgency(state: str, days_to_mdt: int | None, late: float | None) -> str:
    if state in _PROBLEM:
        return "danger"
    if state in ("VERIFIED", "CLOSED"):
        return "ready"
    if state == "CANCELLED":
        return "normal"
    if state in _WARN or (late is not None and late >= 0.5) or (days_to_mdt is not None and days_to_mdt <= 1):
        return "attention"
    if state in ("DETECTED", "DRAFTED"):
        return "info"
    return "normal"


def _deadline_dt(deadline: str | None, fallback: date) -> datetime:
    d = _parse_day(deadline) or fallback
    return datetime(d.year, d.month, d.day, 23, 59)


def _safe_predict(iris: IrisSystem, cache: dict, provider: str, modality: str, region: str, sent: datetime,
                  deadline: datetime) -> dict | None:
    key = (provider, modality, region.split(",")[0], sent.date(), sent.hour, deadline.date())
    if key in cache:
        return cache[key]
    if cache.get("__failed__"):
        return None
    try:
        cache[key] = iris.predict(provider, modality, region, sent, deadline)
    except Exception as exc:  # noqa: BLE001 - models optional
        log.info("prediction unavailable", extra={"fields": {"error": type(exc).__name__}})
        cache["__failed__"] = True
        return None
    return cache[key]


# --- worklist ----------------------------------------------------------------------------------


@router.get("/worklist")
def worklist(db: Session = Depends(get_db), client: ProductionClient = Depends(production),
             iris: IrisSystem = Depends(get_iris)) -> dict:
    """All requests of the production (IRIS SQL PacsComparator_Req.*) joined with cases and meetings.
    Cached for a few seconds (invalidated by every request action)."""
    return api_cache.cached(f"worklist:{id(client)}:{id(iris)}", lambda: _worklist(db, client, iris),
                            keep=lambda v: bool(v.get("available")))


def _worklist(db: Session, client: ProductionClient, iris: IrisSystem) -> dict:
    try:
        rows = client.list("")
    except Exception as exc:  # noqa: BLE001 - ProductionError or driver errors
        return _unavailable(f"Produkce IRIS není dostupná ({_reason(exc)})", requests=[])
    case_ids = {r.get("caseId") for r in rows if r.get("caseId")}
    cases = {c.id: c for c in db.scalars(select(Case).where(Case.id.in_(case_ids)))} if case_ids else {}
    now = today()
    sent_at = datetime.now().replace(minute=0, second=0, microsecond=0)
    cache: dict = {}
    out = []
    for r in rows:
        state = str(r.get("state") or "")
        case = cases.get(r.get("caseId"))
        meeting = case.meeting if case else None
        timeline = ((case.result.result or {}).get("timeline") if case and case.result else None) or {}
        offset = case.date_offset_days if case else 0
        target, shifted = _shift(r.get("targetDate"), offset)
        days_to_mdt = (meeting.date - now).days if meeting else None
        provider = r.get("provider") or {}
        prediction = None
        if state not in TERMINAL:
            prediction = _safe_predict(iris, cache, provider.get("id") or "unknown", r.get("modality") or "",
                                       r.get("regions") or "", sent_at,
                                       _deadline_dt(r.get("deadline"), meeting.date if meeting else now))
        out.append({
            "request_id": r.get("requestId"),
            "case_id": r.get("caseId"),
            "patient_id": case.patient_id if case else None,
            "display_name": (case.display_name or fictional_name(case.patient_id, timeline.get("sex")))
            if case else None,
            "meeting": {"id": meeting.id, "label": meeting.label, "date": meeting.date.isoformat(),
                        "time": meeting.time} if meeting else None,
            "days_to_mdt": days_to_mdt,
            "modality": r.get("modality") or None,
            "regions": [x for x in str(r.get("regions") or "").split(",") if x],
            "target_date": target,
            "shifted": shifted,
            "provider": {"id": provider.get("id"), "name": provider.get("name"), "route": provider.get("route")},
            "state": state,
            "state_group": STATE_GROUP.get(state, "closed"),
            "updated_at": r.get("updatedAt") or None,
            "attempts": r.get("attempts") or 0,
            "prediction": prediction,
            "urgency": _urgency(state, days_to_mdt, (prediction or {}).get("late_probability")),
            "simulated": True,
        })
    out.sort(key=lambda x: (x["days_to_mdt"] if x["days_to_mdt"] is not None else 9999,
                            x["state_group"] in ("verified", "closed"), x["request_id"] or ""))
    groups: dict[str, int] = {}
    for item in out:
        groups[item["state_group"]] = groups.get(item["state_group"], 0) + 1
    return {"available": True, "today": now.isoformat(), "requests": out, "counts": groups,
            "ml_available": not cache.get("__failed__", False), "simulated": True}


# --- hospitals ---------------------------------------------------------------------------------


@router.get("/hospitals")
def hospitals_view(client: ProductionClient = Depends(production), iris: IrisSystem = Depends(get_iris),
                   fhir: FhirReader = Depends(get_fhir)) -> dict:
    return api_cache.cached(f"hospitals:{id(client)}:{id(iris)}:{id(fhir)}",
                            lambda: _hospitals(client, iris, fhir),
                            keep=lambda v: bool(v.get("requests_available")))


def _hospitals(client: ProductionClient, iris: IrisSystem, fhir: FhirReader) -> dict:
    origin = _iris_origin()
    requests_ok = True
    reason = None
    try:
        rows = client.list("")
    except Exception as exc:  # noqa: BLE001
        rows, requests_ok, reason = [], False, f"Produkce IRIS není dostupná ({_reason(exc)})"
    sent = datetime.now().replace(minute=0, second=0, microsecond=0)
    deadline = sent + timedelta(days=3)
    cache: dict = {}
    out = []
    for p in _providers():
        pid = p["id"]
        mine = [r for r in rows if (r.get("provider") or {}).get("id") == pid]
        base = origin + p["fhir_base"].rstrip("/") if p.get("fhir_base") else None
        studies: int | None = None
        fhir_error = None
        if base:
            try:
                studies = fhir.count(base, "ImagingStudy")
            except Exception as exc:  # noqa: BLE001
                fhir_error = _reason(exc)
        predictions = {}
        if pid != "unknown":
            for modality in ("CT", "PET"):
                pred = _safe_predict(iris, cache, pid, modality, "chest", sent, deadline)
                predictions[modality] = pred["expected_hours"] if pred else None
        out.append({
            "id": pid,
            "name": p["name"],
            "aliases": p.get("aliases", []),
            "email": p.get("email") or None,
            "phone": p.get("phone") or None,
            "hours": p.get("hours") or None,
            "preferred_channel": p.get("preferred_channel"),
            "exchange_route": p.get("exchange_route"),
            "fhir_base": base,
            "kind": "home" if pid == "motol" else ("simulated_endpoint" if base else
                                                     ("unknown" if pid == "unknown" else "registry")),
            "fhir_studies": studies,
            "fhir_error": fhir_error,
            "open_requests": sum(1 for r in mine if r.get("state") not in TERMINAL),
            "verified": sum(1 for r in mine if r.get("state") in ("VERIFIED", "CLOSED")),
            "total_requests": len(mine),
            "expected_hours": predictions,
            "simulated": True,
        })
    return {"available": True, "requests_available": requests_ok, "requests_reason": reason,
            "ml_available": not cache.get("__failed__", False), "providers": out, "simulated": True}


# --- integration map ---------------------------------------------------------------------------


@router.get("/system/fhir")
def system_fhir(fhir: FhirReader = Depends(get_fhir)) -> dict:
    from app.exchange.hospitals import hospitals, motol_base

    base = motol_base()
    try:
        motol = [{"label": label, "resource_type": rt, "count": fhir.count(base, rt, params)}
                 for label, rt, params in MOTOL_RESOURCES]
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"FHIR server IRIS není dostupný ({_reason(exc)})")
    endpoints = []
    for h in hospitals():
        try:
            counts = {rt: fhir.count(h.base_url, rt) for rt in HOSPITAL_RESOURCES}
            endpoints.append({"id": h.id, "name": h.name, "base": h.base_url, "counts": counts,
                              "available": True, "simulated": True})
        except Exception as exc:  # noqa: BLE001
            endpoints.append({"id": h.id, "name": h.name, "base": h.base_url, "counts": {},
                              "available": False, "reason": _reason(exc), "simulated": True})
    origin = _iris_origin()
    return {"available": True, "base": base, "metadata_url": f"{base}/metadata", "resources": motol,
            "hospitals": endpoints,
            "portal_url": f"{origin}/csp/sys/UtilHome.csp",
            "fhir_ui_url": f"{origin}/csp/healthshare/fhirserver/fhirconfig/index.csp"}


@router.get("/system/production")
def system_production(top: int = Query(10, ge=1, le=50), iris: IrisSystem = Depends(get_iris)) -> dict:
    origin = _iris_origin()
    links = {
        "config_url": f"{origin}/csp/healthshare/fhirserver/EnsPortal.ProductionConfig.zen?PRODUCTION={PRODUCTION}",
        "messages_url": f"{origin}/csp/healthshare/fhirserver/EnsPortal.MessageViewer.zen",
    }
    try:
        status = iris.production_status()
        name = status["name"] or PRODUCTION
        items = [{"name": n, "class_name": c, "enabled": bool(e), "category": cat or None,
                  "kind": "service" if ".BS." in n else "process" if ".BP." in n else
                  "operation" if ".BO." in n else "other"}
                 for n, c, e, cat in iris.production_items(name)]
        messages = [{"id": int(i), "time": str(t)[:19] if t else None, "source": s, "target": tg,
                     "body_class": b, "session_id": int(sid) if sid is not None else None,
                     "status": MESSAGE_STATUS.get(int(st or 0), str(st)),
                     "visual_trace_url": visual_trace_url(sid, origin) if sid is not None else None}
                    for i, t, s, tg, b, sid, st in iris.messages(top)]
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"Produkce IRIS není dostupná ({_reason(exc)})", name=PRODUCTION, **links)
    return {"available": True, "name": name, "running": status["running"], "namespace": "FHIRSERVER",
            "items": items, "messages": messages, **links}


@router.get("/system/ml")
def system_ml(iris: IrisSystem = Depends(get_iris)) -> dict:
    try:
        models = iris.ml_models()
        metric_rows = iris.ml_metrics()
    except Exception as exc:  # noqa: BLE001
        return {"available": True, "source": "documented", "reason": _reason(exc), "models": ML_FALLBACK,
                "simulated": True}
    if not models:
        return {"available": True, "source": "documented", "reason": "IRIS nevrací žádný model",
                "models": ML_FALLBACK, "simulated": True}
    metrics: dict[str, dict[str, float]] = {}
    for model, name, value in metric_rows:
        # per-class rows repeat the name; the last one is the positive class (ArrivedLate = 1)
        metrics.setdefault(model, {})[str(name)] = round(float(value), 3)
    out = []
    for name, predicts, trained in models:
        m = metrics.get(name, {})
        kind = "regression" if "R2" in m or "RMSE" in m else "classification"
        keep = ("R2", "RMSE", "MSE") if kind == "regression" else ("Accuracy", "Precision", "Recall", "F-Measure",
                                                                     "ROC-AUC")
        out.append({"model": name, "kind": kind, "predicts": predicts, "trained_model": trained,
                    "metrics": {k: m[k] for k in keep if k in m}})
    return {"available": True, "source": "INFORMATION_SCHEMA.ML_VALIDATION_METRICS", "models": out,
            "simulated": True}


@router.get("/system/sql")
def system_sql(loader: Callable[[], dict] = Depends(get_stats_loader)) -> dict:
    try:
        stats = loader()
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"Projekce FHIR SQL Builder není dostupná ({_reason(exc)}); "
                            "spusťte scripts/sql_projection_setup.py")
    return {"available": True, "schema": "PacsProjection", "stats": stats}


@router.get("/system/mcp")
def system_mcp() -> dict:
    from app.agent.tools import TOOL_SPECS

    return {"available": True, "server": "app/agent/mcp_server.py (FastMCP)",
            "transports": ["stdio", "http :8115 /mcp"],
            "tools": [{"name": t["name"], "description": t["description"],
                       "required": t["parameters"].get("required", [])} for t in TOOL_SPECS]}


@router.get("/system/patients")
def system_patients(db: Session = Depends(get_db)) -> dict:
    """Patients that have a case (pickers of the simulation actions)."""
    seen: dict[str, dict] = {}
    for case in db.scalars(select(Case).order_by(Case.created_at)):
        if case.patient_id in seen:
            continue
        timeline = ((case.result.result or {}).get("timeline") if case.result else None) or {}
        seen[case.patient_id] = {"patient_id": case.patient_id, "case_id": case.id,
                                 "display_name": case.display_name or fictional_name(case.patient_id,
                                                                                     timeline.get("sex"))}
    return {"patients": list(seen.values())}


class VectorHit(BaseModel):
    source_type: str
    id: str
    patient_id: str | None = None
    date: str | None
    modality: str | None = None
    score: float
    snippet: str | None = None


@router.get("/system/vector-search")
def system_vector_search(
    q: str = Query(min_length=2, max_length=500),
    patient_id: str | None = Query(default=None, max_length=128),
    top: int = Query(5, ge=1, le=20),
    include_text: bool = False,
    backend: VectorBackend = Depends(get_vector_backend),
) -> dict:
    """IRIS Vector Search over PacsVector.ReportChunk; the snippet (max 240 chars) only with include_text."""
    pid = (patient_id or "").strip() or None
    if pid and not _SAFE_ID.match(pid):
        raise ValidationFailed("Neplatné ID pacienta")
    started = time.perf_counter()
    try:
        hits = backend.search(q, patient_id=pid, top_k=top * 4)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"Vektorové vyhledávání není dostupné ({_reason(exc)})", hits=[])
    best: dict[str, VectorHit] = {}
    for h in hits:
        if h.source_id in best:
            continue
        best[h.source_id] = VectorHit(
            source_type=h.source_type, id=h.source_id, patient_id=getattr(h, "patient_id", None),
            date=h.doc_date.isoformat() if h.doc_date else None, modality=h.modality, score=round(h.score, 4),
            snippet=(h.text[:240] + ("…" if len(h.text) > 240 else "")) if include_text else None)
    return {"available": True, "query": q, "patient_id": pid, "table": "PacsVector.ReportChunk",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "hits": [h.model_dump() for h in list(best.values())[:top]]}


class Hl7Body(BaseModel):
    patient_id: str = Field(min_length=1, max_length=128)
    modality: str = Field(default="CT", pattern="^(CT|MR|PET|RTG|SONO|MAMO|SCINT)$")
    days: int = Field(default=14, ge=0, le=365)


def _case_patient(db: Session, patient_id: str) -> None:
    if not _SAFE_ID.match(patient_id) or db.scalars(select(Case.id).where(Case.patient_id == patient_id)).first() \
            is None:
        raise ValidationFailed("Pacient nemá v aplikaci žádný případ")


@router.post("/system/hl7-orm")
def system_hl7_orm(body: Hl7Body, db: Session = Depends(get_db), iris: IrisSystem = Depends(get_iris),
                   fhir: FhirReader = Depends(get_fhir)) -> dict:
    """Simulated RIS: one ORM^O01 through the IRIS MLLP service; IRIS writes a FHIR ServiceRequest."""
    from app.exchange.hl7 import message_type
    from app.exchange.hospitals import motol_base
    from scripts.simulate_ris import ack_status, build_messages

    _case_patient(db, body.patient_id)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    message = build_messages(body.patient_id, "orm", body.modality, body.days, run_id)[0]
    try:
        ack = ack_status(iris.send_hl7(message))
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"HL7 služba IRIS není dostupná ({_reason(exc)})", simulated=True)
    sr_id = f"RIS-SIM-ORD-{run_id}"
    accepted = ack in ("AA", "CA")  # CA = commit accept (AckMode Immediate); the FHIR write follows async
    created = False
    if accepted:
        for _ in range(20):
            try:
                created = fhir.exists(motol_base(), "ServiceRequest", sr_id)
            except Exception:  # noqa: BLE001
                created = False
            if created:
                break
            time.sleep(0.5)
    return {"available": True, "message_type": message_type(message), "ack": ack, "accepted": accepted,
            "placer_order": f"SIM-ORD-{run_id}", "service_request": f"ServiceRequest/{sr_id}" if created else None,
            "segments": [s.split("|")[0] for s in message.split("\r") if s],
            "messages_url": f"{_iris_origin()}/csp/healthshare/fhirserver/EnsPortal.MessageViewer.zen",
            "simulated": True}


class CFindBody(BaseModel):
    patient_id: str = Field(min_length=1, max_length=128)
    node: str = Field(pattern="^(motol|nnh|homolka|fnm)$")
    modality: str | None = Field(default=None, pattern="^(CT|MR|PET|RTG|SONO|MAMO|SCINT)$")


@router.post("/system/dicom-cfind")
def system_dicom_cfind(body: CFindBody, db: Session = Depends(get_db), client: Any = Depends(get_cfind)) -> dict:
    """Study-level C-FIND against one simulated PACS (IRIS PACSDICOM production, pynetdicom fallback)."""
    from app.exchange.dicom import nodes

    _case_patient(db, body.patient_id)
    node = nodes().get(body.node)
    if node is None:
        raise ValidationFailed("Neznámý PACS uzel")
    used = type(client).__name__
    started = time.perf_counter()
    try:
        matches = client.find(node.ae, body.patient_id, None, body.modality)
    except Exception as exc:  # noqa: BLE001
        try:
            from app.exchange.dicom import PynetdicomCFindClient

            matches = PynetdicomCFindClient().find(node.ae, body.patient_id, None, body.modality)
            used = f"PynetdicomCFindClient (fallback: {type(exc).__name__})"
        except Exception as exc2:  # noqa: BLE001
            return _unavailable(f"DICOM C-FIND selhal ({_reason(exc2)})", ae=node.ae, simulated=True)
    return {"available": True, "ae": node.ae, "client": used,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "matches": [{"study_date": m.study_date.isoformat() if m.study_date else None, "modality": m.modality,
                         "accession": m.accession} for m in matches],
            "simulated": True}

# --- AI quality (silver standard) ------------------------------------------------------------------

EVAL_FIELDS = ("reports", "silver_citations", "recall_pct", "date_accuracy_given_modality_pct", "in_dataset_pct",
               "naive_latest_same_modality_pct")


@router.get("/system/eval")
def system_eval() -> dict:
    """Extraction quality from DATA_DIR/eval/silver.json (silver standard: citations that a regex can read
    reliably, not a manual annotation). Counts only, no report text."""
    import json

    path = get_settings().data_dir / "eval" / "silver.json"
    if not path.exists():
        return _unavailable("Vyhodnocení zatím neproběhlo (chybí eval/silver.json)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _unavailable(f"Soubor s vyhodnocením nelze přečíst ({type(exc).__name__})")
    if not isinstance(data, dict):
        return _unavailable("Soubor s vyhodnocením má neočekávaný tvar")
    out = {k: data.get(k) for k in EVAL_FIELDS}
    out.update(available=True, kind="silver", label="Silver standard (automaticky čitelné citace), ne ruční anotace")
    return out
