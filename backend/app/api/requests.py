"""Request loop endpoints (T081, T082). The lifecycle runs in the IRIS production; this only calls it.

After every action the case readiness is recomputed from the stored check result, the coordinator's waivers
and the request states in the production (`app.requests.overlay`), and the overview caches are cleared.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import cache as api_cache
from app.api.cases import get_fhir_store, get_llm
from app.api.errors import DependencyUnavailable, NotFoundError, ValidationFailed
from app.app_db.models import AutopilotPolicy, Case, CaseResult, IssueAck, ItemWaiver, Meeting, utcnow
from app.app_db.session import get_db as _db_dependency
from app.config import today
from app.exchange.hospitals import HospitalError, make_client, provider, request
from app.exchange.mhd import DeliveryRequest, provide_document_bundle
from app.fhir_store.base import FhirStore
from app.llm.client import StructuredLlm
from app.ml.predict import prediction_for_request
from app.pipeline.run import run_case_check
from app.pipeline.schemas import CaseCheckResult, RequiredItem
from app.requests.overlay import DONE_STATES, confirm_key, refresh_case, requests_for_case
from app.requests.production_client import ProductionClient, ProductionError, get_client, sync_files, visual_trace_url

router = APIRouter(prefix="/api", tags=["requests"])

# A waiver cancels the item's request unless it already ended.
_ENDED = {"VERIFIED", "CLOSED", "CANCELLED", "REJECTED", "WRONG_RECIPIENT"}


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


class WaiveBody(BaseModel):
    reason: str = Field(min_length=3, max_length=400)
    coordinator: str = Field(min_length=1, max_length=100)
    case_id: str | None = None


class AckBody(BaseModel):
    coordinator: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=400)


class NightlyBody(BaseModel):
    days: int = Field(default=2, ge=0, le=14)


class AutopilotBody(BaseModel):
    enabled: bool
    coordinator: str = Field(default="", max_length=100)


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


def _refresh(db: Session, client: ProductionClient, case_ids: set[str]) -> None:
    """Recompute readiness of the given cases and of every other case of the same patients (item ids and
    therefore requests are shared between cases of one patient)."""
    cases = [c for c in (db.get(Case, i) for i in case_ids if i) if c is not None]
    patients = {c.patient_id for c in cases}
    if patients:
        cases += [c for c in db.scalars(select(Case).where(Case.patient_id.in_(patients))).all()
                  if c.id not in case_ids]
    for case in cases:
        refresh_case(db, case, client)
    db.commit()
    api_cache.invalidate()


def _after_request(db: Session, client: ProductionClient, request_id: str, result: dict) -> dict:
    """Readiness follows the request: reload its case and recompute."""
    try:
        data = client.get(request_id) or {}
    except ProductionError:
        data = {}
    _refresh(db, client, {data.get("caseId", "")})
    return result


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


def draft_missing(db: Session, case: Case, client: ProductionClient) -> list[dict]:
    """Draft one request per missing, not waived item that has no live request yet (nothing is sent)."""
    overlaid, existing = refresh_case(db, case, client)
    if overlaid is None:
        return []
    out = []
    for item in overlaid.items:
        if item.state != "missing" or item.waived:
            continue
        prev = (existing or {}).get(item.id)
        if prev is not None and prev.get("state") != "CANCELLED":
            continue
        out.append(_guard(lambda i=item: client.submit("DRAFT", "", draft_payload(case, i), "system")))
    return out


# --- autopilot: a standing approval policy ----------------------------------------------------------


def _autopilot_view(policy: AutopilotPolicy | None) -> dict:
    if policy is None or not policy.enabled:
        return {"enabled": False, "actor": policy.actor if policy else "",
                "changed_at": policy.changed_at.isoformat(timespec="seconds") if policy else None}
    return {"enabled": True, "actor": policy.actor, "changed_at": policy.changed_at.isoformat(timespec="seconds")}


def autopilot_actor(db: Session) -> str | None:
    """Actor string for automatic approvals, or None while autopilot is off."""
    policy = db.get(AutopilotPolicy, 1)
    if policy is None or not policy.enabled:
        return None
    return f"autopilot (zapnul {policy.actor})"


def auto_approve(db: Session, client: ProductionClient, request_ids: list[str]) -> list[str]:
    """Approve DRAFTED requests under the autopilot policy, through the same production call as a click.
    Requests whose holding site is unknown stay drafted for a human. Returns the approved request ids."""
    actor = autopilot_actor(db)
    if actor is None:
        return []
    approved = []
    for request_id in request_ids:
        data = _guard(lambda r=request_id: client.get(r)) or {}
        if data.get("state") != "DRAFTED":
            continue
        site = (data.get("provider") or {}).get("id") or ""
        if site in ("", "unknown") or provider(site) is None:
            continue
        _guard(lambda r=request_id: client.submit("APPROVE", r, {"approvedBy": actor}, actor))
        approved.append(request_id)
    return approved


@router.get("/autopilot")
def get_autopilot(db: Session = Depends(_db_dependency)) -> dict:
    return _autopilot_view(db.get(AutopilotPolicy, 1))


@router.put("/autopilot")
def set_autopilot(body: AutopilotBody, db: Session = Depends(_db_dependency),
                  client: ProductionClient = Depends(production)) -> dict:
    """Switch the autopilot on or off. Enabling needs the coordinator's name (it is the approval record)
    and approves the drafts that already wait for a known hospital."""
    name = body.coordinator.strip()
    if body.enabled and len(name) < 2:
        raise ValidationFailed("Pro zapnutí autopilota zadejte jméno koordinátora")
    policy = db.get(AutopilotPolicy, 1)
    if policy is None:
        policy = AutopilotPolicy(id=1)
        db.add(policy)
    policy.enabled = body.enabled
    policy.actor = name or policy.actor
    policy.changed_at = utcnow()
    db.commit()
    approved: list[str] = []
    if body.enabled:
        approved = auto_approve(db, client, _guard(lambda: client.draft_ids([])))
        if approved:
            rows = _guard(lambda: client.list(""))
            _refresh(db, client, {r.get("caseId", "") for r in rows if r.get("requestId") in approved})
    api_cache.invalidate()
    return {**_autopilot_view(policy), "auto_approved": len(approved)}


@router.post("/cases/{case_id}/requests")
def create_drafts(case_id: str, db: Session = Depends(_db_dependency),
                  client: ProductionClient = Depends(production)) -> list[dict]:
    case, _ = _case_result(db, case_id)
    out = draft_missing(db, case, client)
    new = [d.get("requestId", "") for d in out if "existuje" not in str(d.get("note", ""))]
    approved = set(auto_approve(db, client, [r for r in new if r]))
    for d in out:
        d["auto_approved"] = d.get("requestId") in approved
    _refresh(db, client, {case_id})
    return out


@router.get("/cases/{case_id}/requests")
def case_requests(case_id: str, db: Session = Depends(_db_dependency),
                  client: ProductionClient = Depends(production)) -> list[dict]:
    case = db.get(Case, case_id)
    if case is None:
        return _guard(lambda: client.list(case_id))
    return list(_guard(lambda: requests_for_case(client, case)).values())


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


@router.get("/requests/{request_id}/audio/{message_id}")
def request_audio(request_id: str, message_id: int, client: ProductionClient = Depends(production)) -> Response:
    """The Czech voice message (ElevenLabs mp3) of a simulated call, if the production produced one."""
    data = _guard(lambda: client.get(request_id))
    if data is None or not any(m.get("id") == message_id and m.get("hasAudio") for m in data.get("messages", [])):
        raise NotFoundError("Hlasová zpráva není k dispozici")
    audio = _guard(lambda: client.audio(message_id))
    if not audio:
        raise NotFoundError("Hlasová zpráva není k dispozici")
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/requests/approve-all")
def approve_all(body: ApproveAllBody, db: Session = Depends(_db_dependency),
                client: ProductionClient = Depends(production)) -> dict:
    case_ids = body.case_ids
    if case_ids:
        # Requests are shared between cases of one patient; include the sibling cases.
        patients = {c.patient_id for c in (db.get(Case, i) for i in case_ids) if c is not None}
        case_ids = sorted(set(case_ids) | {c.id for c in db.scalars(
            select(Case).where(Case.patient_id.in_(patients))).all()}) if patients else case_ids
    ids = _guard(lambda: client.draft_ids(case_ids))
    done = [_guard(lambda i=i: client.submit("APPROVE", i, {"approvedBy": body.coordinator}, body.coordinator))
            for i in ids]
    rows = _guard(lambda: client.list(""))
    approved = {d.get("requestId") for d in done}
    _refresh(db, client, {r.get("caseId", "") for r in rows if r.get("requestId") in approved})
    return {"approved": len(done), "requests": [d.get("requestId") for d in done]}


@router.post("/requests/{request_id}/approve")
def approve(request_id: str, body: ApproveBody, db: Session = Depends(_db_dependency),
            client: ProductionClient = Depends(production)) -> dict:
    out = _guard(lambda: client.submit("APPROVE", request_id, {"approvedBy": body.coordinator}, body.coordinator))
    return _after_request(db, client, request_id, out)


@router.post("/requests/{request_id}/simulate-reply")
def simulate_reply(request_id: str, body: ReplyBody, db: Session = Depends(_db_dependency),
                   client: ProductionClient = Depends(production)) -> dict:
    out = _guard(lambda: client.submit("REPLY", request_id, {"text": body.text}, "provider-sim"))
    return _after_request(db, client, request_id, out)


@router.post("/requests/{request_id}/simulate-call")
def simulate_call(request_id: str, body: CallBody, db: Session = Depends(_db_dependency),
                  client: ProductionClient = Depends(production)) -> dict:
    out = _guard(lambda: client.submit("CALL_OUTCOME", request_id, {"outcome": body.outcome}, "provider-sim"))
    return _after_request(db, client, request_id, out)


def _full_date(value: str) -> str:
    """The requested date as a day: month precision -> the 15th, year precision -> 15 June."""
    if len(value) == 7:
        return f"{value}-15"
    if len(value) == 4:
        return f"{value}-06-15"
    return value[:10]


@router.post("/requests/{request_id}/simulate-delivery")
def simulate_delivery(request_id: str, body: DeliveryBody, db: Session = Depends(_db_dependency),
                      client: ProductionClient = Depends(production)) -> dict:
    """Simulated delivery. With a seeded hospital study, the hospital POSTs an ITI-65 bundle to Motol and the
    production finds it; otherwise the delivered study is described directly. Fields given in the body
    override the requested values (a deliberately wrong study for the demo)."""
    data = _guard(lambda: client.get(request_id))
    if data is None:
        raise NotFoundError("Žádost nebyla nalezena")
    case, result = _case_result(db, data["caseId"])
    item = next((i for i in result.items if i.id == data["itemId"]), None)
    given = {k: v for k, v in body.model_dump().items() if v}
    if item is not None and item.provider_study_ref:
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
    if given or item is None or not item.provider_study_ref:
        target = str(data.get("targetDate") or "")
        if not target and not given.get("date"):
            raise ValidationFailed("Žádost nemá požadované datum, zadejte datum doručené studie")
        payload = {"modality": data.get("modality") or "", "date": _full_date(target) if target else "",
                   "region": str(data.get("regions") or "").split(",")[0]}
        payload.update(given)
    else:
        payload = {}
    out = _guard(lambda: client.submit("DELIVERY", request_id, payload, "provider-sim"))
    return _after_request(db, client, request_id, out)


@router.post("/items/{item_id}/waive")
def waive_item(item_id: str, body: WaiveBody, db: Session = Depends(_db_dependency),
               client: ProductionClient = Depends(production)) -> dict:
    """Coordinator waives a required item (who, when, why). A live request of the item is cancelled."""
    case = _case_for_item(db, item_id, body.case_id)
    waiver = db.get(ItemWaiver, (case.id, item_id))
    if waiver is None:
        waiver = ItemWaiver(case_id=case.id, item_id=item_id, reason=body.reason, actor=body.coordinator,
                            waived_at=utcnow())
        db.add(waiver)
    else:
        waiver.reason, waiver.actor, waiver.waived_at = body.reason, body.coordinator, utcnow()
    db.commit()
    cancelled = None
    cancel_error = None
    try:
        live = requests_for_case(client, case).get(item_id)
        if live is not None and live.get("state") not in _ENDED:
            client.submit("CANCEL", live["requestId"], {"reason": body.reason}, body.coordinator)
            cancelled = live["requestId"]
    except ProductionError as exc:
        cancel_error = str(exc)[:200]
    _refresh(db, client, {case.id})
    return {"case_id": case.id, "item_id": item_id, "waived": True, "reason": waiver.reason,
            "actor": waiver.actor, "waived_at": waiver.waived_at.isoformat(timespec="seconds"),
            "cancelled_request": cancelled, "cancel_error": cancel_error,
            "readiness": case.readiness, "readiness_reason": case.readiness_reason}


@router.post("/cases/{case_id}/issues/{issue_key}/acknowledge")
def acknowledge_issue(case_id: str, issue_key: str, body: AckBody, db: Session = Depends(_db_dependency),
                      client: ProductionClient = Depends(production)) -> dict:
    """Coordinator acknowledges an open issue (who, when, note); it then no longer blocks readiness."""
    case = db.get(Case, case_id)
    if case is None:
        raise NotFoundError("Případ nenalezen")
    ack = db.get(IssueAck, (case_id, issue_key))
    if ack is None:
        ack = IssueAck(case_id=case_id, issue_key=issue_key, note=body.note, actor=body.coordinator,
                       acked_at=utcnow())
        db.add(ack)
    else:
        ack.note, ack.actor, ack.acked_at = body.note, body.coordinator, utcnow()
    db.commit()
    _refresh(db, client, {case_id})
    return {"case_id": case_id, "issue_key": issue_key, "acknowledged": True, "actor": ack.actor,
            "readiness": case.readiness, "readiness_reason": case.readiness_reason}


@router.post("/cases/{case_id}/items/{item_id}/confirm")
def confirm_delivery(case_id: str, item_id: str, body: AckBody, db: Session = Depends(_db_dependency),
                     client: ProductionClient = Depends(production)) -> dict:
    """Coordinator confirms a delivered and automatically verified study; only then the item counts as ok."""
    case = _case_for_item(db, item_id, case_id)
    req = requests_for_case(client, case).get(item_id) if client is not None else None
    if req is None or req.get("state") not in DONE_STATES:
        raise ValidationFailed("Studie zatím nebyla doručena a ověřena")
    key = confirm_key(item_id)
    ack = db.get(IssueAck, (case_id, key))
    if ack is None:
        ack = IssueAck(case_id=case_id, issue_key=key, note=body.note, actor=body.coordinator,
                       acked_at=utcnow())
        db.add(ack)
    else:
        ack.note, ack.actor, ack.acked_at = body.note, body.coordinator, utcnow()
    db.commit()
    _refresh(db, client, {case_id})
    return {"case_id": case_id, "item_id": item_id, "confirmed": True, "actor": ack.actor,
            "readiness": case.readiness, "readiness_reason": case.readiness_reason}


def _case_for_item(db: Session, item_id: str, case_id: str | None) -> Case:
    candidates = [db.get(Case, case_id)] if case_id else [
        r.case for r in db.scalars(select(CaseResult)).all()]
    for case in candidates:
        if case is None or case.result is None:
            continue
        if any(i.get("id") == item_id for i in (case.result.result or {}).get("items", [])):
            return case
    raise NotFoundError("Položka nebyla nalezena")


# --- demo controls (time is simulated; nothing is sent without approval) -------------------------


@router.post("/demo/advance-time")
def advance_time(body: AdvanceBody, db: Session = Depends(_db_dependency),
                 client: ProductionClient = Depends(production)) -> dict:
    """Simulated time: moves the production clock and runs the reminder and escalation timers once."""
    out = _guard(lambda: client.advance_time(body.hours))
    api_cache.invalidate()
    return out


def _window_cases(db: Session, days: int) -> list[Case]:
    start = today()
    meetings = db.scalars(select(Meeting).where(Meeting.date >= start,
                                                Meeting.date <= start + timedelta(days=days))).all()
    return [c for m in sorted(meetings, key=lambda m: (m.date, m.time)) for c in m.cases]


@router.post("/demo/nightly-run")
def nightly_run(body: NightlyBody | None = None, db: Session = Depends(_db_dependency),
                client: ProductionClient = Depends(production), store: FhirStore = Depends(get_fhir_store),
                llm: StructuredLlm = Depends(get_llm)) -> dict:
    """The nightly job (T-2 days): re-check the cases of meetings in the next N days and draft a request
    for every missing item. Drafts wait for a coordinator's approval; nothing is sent here."""
    days = (body or NightlyBody()).days
    cases = _window_cases(db, days)
    case_ids = [c.id for c in cases]
    autopilot_on = autopilot_actor(db) is not None
    db.close()
    per_meeting: dict[str, dict] = {}
    failed = 0
    created_total = 0
    auto_total = 0
    from app.app_db.session import session_scope

    for case_id in case_ids:
        if run_case_check(case_id, store, llm) is None:
            failed += 1
        with session_scope() as s:
            case = s.get(Case, case_id)
            created = draft_missing(s, case, client)
            new = [d for d in created if "existuje" not in str(d.get("note", ""))]
            created_total += len(new)
            auto = auto_approve(s, client, [d.get("requestId", "") for d in new if d.get("requestId")])
            auto_total += len(auto)
            refresh_case(s, case, client)
            m = case.meeting
            entry = per_meeting.setdefault(m.id, {"meeting_id": m.id, "label": m.label, "date": m.date.isoformat(),
                                                  "time": m.time, "cases": 0, "drafts_created": 0, "auto_approved": 0})
            entry["cases"] += 1
            entry["drafts_created"] += len(new)
            entry["auto_approved"] += len(auto)
    api_cache.invalidate()
    pending = _guard(lambda: client.draft_ids(case_ids)) if case_ids else []
    # Drafts left from earlier runs (for example created before autopilot was switched on).
    with session_scope() as s:
        swept = auto_approve(s, client, pending)
        if swept:
            auto_total += len(swept)
            rows = _guard(lambda: client.list(""))
            _refresh(s, client, {r.get("caseId", "") for r in rows if r.get("requestId") in set(swept)})
    pending = [r for r in pending if r not in set(swept)]
    api_cache.invalidate()
    return {"window": {"from": today().isoformat(), "to": (today() + timedelta(days=days)).isoformat()},
            "cases_checked": len(case_ids), "failed": failed, "drafts_created": created_total,
            "drafts_pending": len(pending), "auto_approved": auto_total, "autopilot": autopilot_on,
            "meetings": list(per_meeting.values()), "simulated": True}


@router.get("/demo/summary")
def demo_summary(days: int = 7, db: Session = Depends(_db_dependency),
                 client: ProductionClient = Depends(production)) -> dict:
    """Pending drafts of cases in the dashboard window (the "Schválit vše" banner)."""
    case_ids = [c.id for c in _window_cases(db, max(0, min(days, 31)))]
    try:
        pending = client.draft_ids(case_ids) if case_ids else []
    except ProductionError as exc:
        return {"available": False, "reason": str(exc)[:200], "drafts_pending": 0, "case_ids": case_ids}
    return {"available": True, "drafts_pending": len(pending), "requests": pending, "case_ids": case_ids,
            "simulated": True}
