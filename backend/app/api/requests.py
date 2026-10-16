"""Request loop endpoints (T081, T082). The lifecycle runs in the IRIS production; this only calls it."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.errors import DependencyUnavailable, NotFoundError, ValidationFailed
from app.app_db.models import Case
from app.app_db.session import get_db as _db_dependency
from app.exchange.hospitals import HospitalError, make_client, provider, request
from app.exchange.mhd import DeliveryRequest, provide_document_bundle
from app.ml.predict import prediction_for_request
from app.pipeline.schemas import CaseCheckResult, RequiredItem
from app.requests.production_client import ProductionClient, ProductionError, get_client, sync_files, visual_trace_url

router = APIRouter(prefix="/api", tags=["requests"])


def production() -> ProductionClient:
    return get_client()


class ApproveBody(BaseModel):
    coordinator: str = Field(min_length=1, max_length=100)


class ApproveAllBody(ApproveBody):
    case_ids: list[str] | None = None


class ReplyBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class CallBody(BaseModel):
    outcome: str = Field(pattern="^(accepted|call_back|refused|no_answer)$")


class DeliveryBody(BaseModel):
    modality: str | None = None
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    region: str | None = None


class AdvanceBody(BaseModel):
    hours: float = Field(gt=0, le=24 * 30)


def _guard(call):
    try:
        return call()
    except ProductionError as exc:
        raise DependencyUnavailable(str(exc)) from exc


def _case_result(db: Session, case_id: str) -> tuple[Case, CaseCheckResult]:
    case = db.get(Case, case_id)
    if case is None or case.result is None:
        raise NotFoundError("Případ nebyl nalezen nebo nemá výsledek kontroly")
    return case, CaseCheckResult.model_validate(case.result.result)


def draft_payload(case: Case, item: RequiredItem) -> dict:
    """Minimum data only (rule 8): no patient name, no free text; the patient id stays in the production
    for the FHIR Task and never goes into messages."""
    site = provider(item.holding_site_id or "") or provider("unknown") or {}
    return {
        "itemId": item.id, "caseId": case.id, "patientId": case.patient_id,
        "providerId": site.get("id", item.holding_site_id or "unknown"),
        "providerName": site.get("name", item.holding_site_name or "Neznámé pracoviště"),
        "providerEmail": site.get("email", ""), "providerPhone": site.get("phone", ""),
        "providerRoute": site.get("exchange_route", "ePACS"),
        "studyRef": item.provider_study_ref or "", "modality": item.modality,
        "regions": ",".join(item.regions), "targetDate": item.target_date.iso if item.target_date else "",
        "deadline": (case.meeting.date - timedelta(days=1)).isoformat(),
    }


@router.post("/cases/{case_id}/requests")
def create_drafts(case_id: str, db: Session = Depends(_db_dependency),
                  client: ProductionClient = Depends(production)) -> list[dict]:
    """Draft a request for every missing, not waived item (nothing is sent before approval)."""
    case, result = _case_result(db, case_id)
    out = []
    for item in result.items:
        if item.state == "missing" and not item.waived:
            out.append(_guard(lambda i=item: client.submit("DRAFT", "", draft_payload(case, i), "system")))
    return out


@router.get("/cases/{case_id}/requests")
def case_requests(case_id: str, client: ProductionClient = Depends(production)) -> list[dict]:
    return _guard(lambda: client.list(case_id))


@router.get("/requests/{request_id}")
def get_request(request_id: str, client: ProductionClient = Depends(production)) -> dict:
    data = _guard(lambda: client.get(request_id))
    if data is None:
        raise NotFoundError("Žádost nebyla nalezena")
    sessions = [s for s in data.get("sessionIds", "").split(",") if s]
    data["visualTrace"] = [visual_trace_url(s) for s in sessions]
    _guard(lambda: sync_files(data, client))
    data["prediction"] = prediction_for_request(data)  # D5 hook (T088)
    return data


@router.post("/requests/approve-all")
def approve_all(body: ApproveAllBody, client: ProductionClient = Depends(production)) -> dict:
    ids = _guard(lambda: client.draft_ids(body.case_ids))
    done = [_guard(lambda i=i: client.submit("APPROVE", i, {"approvedBy": body.coordinator}, body.coordinator))
            for i in ids]
    return {"approved": len(done), "requests": [d.get("requestId") for d in done]}


@router.post("/requests/{request_id}/approve")
def approve(request_id: str, body: ApproveBody, client: ProductionClient = Depends(production)) -> dict:
    return _guard(lambda: client.submit("APPROVE", request_id, {"approvedBy": body.coordinator}, body.coordinator))


@router.post("/requests/{request_id}/simulate-reply")
def simulate_reply(request_id: str, body: ReplyBody, client: ProductionClient = Depends(production)) -> dict:
    return _guard(lambda: client.submit("REPLY", request_id, {"text": body.text}, "provider-sim"))


@router.post("/requests/{request_id}/simulate-call")
def simulate_call(request_id: str, body: CallBody, client: ProductionClient = Depends(production)) -> dict:
    return _guard(lambda: client.submit("CALL_OUTCOME", request_id, {"outcome": body.outcome}, "provider-sim"))


@router.post("/requests/{request_id}/simulate-delivery")
def simulate_delivery(request_id: str, body: DeliveryBody, db: Session = Depends(_db_dependency),
                      client: ProductionClient = Depends(production)) -> dict:
    """The simulated hospital POSTs an ITI-65 bundle to Motol; the production finds and verifies it."""
    data = _guard(lambda: client.get(request_id))
    if data is None:
        raise NotFoundError("Žádost nebyla nalezena")
    case, result = _case_result(db, data["caseId"])
    item = next((i for i in result.items if i.id == data["itemId"]), None)
    if item is None or not item.provider_study_ref:
        raise ValidationFailed("Položka nemá simulovaného poskytovatele, který by studii doručil")
    hospital = provider(item.holding_site_id or "")
    http = make_client()
    try:
        study = request(http, "GET", item.provider_study_ref).json()
        study_date = date.fromisoformat(str(study["started"])[:10])
        provide_document_bundle(hospital, DeliveryRequest(
            request_id=request_id, patient_id=case.patient_id, modality=item.modality, study_date=study_date,
            provider_study_ref=item.provider_study_ref), client=http)
    except HospitalError as exc:
        raise DependencyUnavailable(f"Doručení se nepodařilo: {exc}") from exc
    payload = {k: v for k, v in body.model_dump().items() if v}
    return _guard(lambda: client.submit("DELIVERY", request_id, payload, "provider-sim"))


@router.post("/demo/advance-time")
def advance_time(body: AdvanceBody, client: ProductionClient = Depends(production)) -> dict:
    """Simulated time: moves the production clock and runs the reminder and escalation timers once."""
    return _guard(lambda: client.advance_time(body.hours))
