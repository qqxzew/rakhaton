"""Case endpoints: detail, recheck, planned-exam correction and source documents."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.case_views import build_case_detail
from app.api.errors import DependencyUnavailable, NotFoundError, ValidationFailed
from app.api.schemas import CaseCreate, CaseDetail, PlannedExamPatch, PlannedExamView, SourceDocumentView
from app.app_db.models import Case
from app.app_db.repositories import create_case
from app.app_db.session import get_db as _db_dependency
from app.config import today
from app.fhir_store.base import FhirStore, FhirStoreError, PatientNotFound
from app.fhir_store.factory import get_store
from app.llm.client import GatewayBackend, StructuredLlm
from app.pipeline.normalize import clean_regions, normalize_modality
from app.pipeline.run import run_case_check
from app.pipeline.schemas import CaseCheckResult, Timeline
from app.pipeline.timeline import decode_attachment, report_text, to_date
from app.requests.overlay import optional_client, refresh_case, waivers_for
from app.requests.production_client import ProductionClient
from app.scheduling.anchoring import shift_iso, unshift_date
from app.scheduling.eligibility import validate_registration

router = APIRouter(prefix="/api/cases", tags=["cases"])


@lru_cache
def _store() -> FhirStore:
    return get_store()


def get_fhir_store() -> FhirStore:
    return _store()


@lru_cache
def _llm() -> StructuredLlm:
    return StructuredLlm(GatewayBackend())


def get_llm() -> StructuredLlm:
    return _llm()


def _load_case(db: Session, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise NotFoundError("Případ nebyl nalezen")
    return case


def _empty_result(case: Case) -> CaseCheckResult:
    return CaseCheckResult(patient_id=case.patient_id, timeline=Timeline(patient_id=case.patient_id),
                           readiness=case.readiness, readiness_reason=case.readiness_reason)


@router.post("", response_model=CaseDetail, status_code=201)
def register_case(body: CaseCreate, tasks: BackgroundTasks, db: Session = Depends(_db_dependency),
                  store: FhirStore = Depends(get_fhir_store), llm: StructuredLlm = Depends(get_llm)) -> CaseDetail:
    patient_id = body.patient_id.strip()
    try:
        store.get_patient_bundle(patient_id)
    except PatientNotFound as exc:
        raise NotFoundError("Pacient nebyl nalezen") from exc
    except FhirStoreError as exc:
        raise DependencyUnavailable("Záznamy pacientů se nepodařilo načíst") from exc
    validate_registration(db, patient_id, body.group_id, body.meeting_id, today())
    case = create_case(db, patient_id=patient_id, meeting_id=body.meeting_id, group_id=body.group_id,
                       display_name=(body.display_name or "").strip() or None)
    db.commit()
    tasks.add_task(_background_check, case.id, store, llm)
    return build_case_detail(case, _empty_result(case))


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, db: Session = Depends(_db_dependency),
             client: ProductionClient | None = Depends(optional_client)) -> CaseDetail:
    case = _load_case(db, case_id)
    overlaid, requests = refresh_case(db, case, client)
    db.commit()
    result = overlaid or _empty_result(case)
    detail = build_case_detail(case, result, requests=requests, waivers=waivers_for(db, case.id))
    detail.requests_available = client is not None and requests is not None
    return detail


def _background_check(case_id: str, store: FhirStore, llm: StructuredLlm) -> None:
    run_case_check(case_id, store, llm)


@router.post("/{case_id}/recheck", status_code=202)
def recheck(case_id: str, tasks: BackgroundTasks, db: Session = Depends(_db_dependency),
            store: FhirStore = Depends(get_fhir_store), llm: StructuredLlm = Depends(get_llm)) -> dict:
    case = _load_case(db, case_id)
    case.check_status = "running"
    db.commit()
    tasks.add_task(_background_check, case.id, store, llm)
    return {"case_id": case.id, "check_status": "running"}


@router.patch("/{case_id}/planned-exam", response_model=PlannedExamView)
def correct_planned_exam(case_id: str, patch: PlannedExamPatch, tasks: BackgroundTasks,
                         db: Session = Depends(_db_dependency),
                         store: FhirStore = Depends(get_fhir_store),
                         llm: StructuredLlm = Depends(get_llm)) -> PlannedExamView:
    case = _load_case(db, case_id)
    modality = normalize_modality(patch.modality)
    if modality in ("UNKNOWN", "OTHER"):
        raise ValidationFailed("Neznámá modalita vyšetření")
    exam_date = None
    if patch.date:
        try:
            exam_date = date.fromisoformat(patch.date)
        except ValueError as exc:
            raise ValidationFailed("Neplatné datum") from exc
    regions = clean_regions(patch.regions)
    offset = case.date_offset_days
    if exam_date is not None:
        # The UI shows shifted dates; the pipeline works in the patient's own date frame.
        exam_date = unshift_date(exam_date, offset)
    case.planned_exam_override = {"modality": modality, "regions": regions,
                                  "date": exam_date.isoformat() if exam_date else None,
                                  "coordinator": patch.coordinator}
    case.check_status = "running"
    db.commit()
    tasks.add_task(_background_check, case.id, store, llm)
    return PlannedExamView(modality=modality, regions=regions, date=patch.date, site=None,
                           quote="Upraveno koordinátorem", source_doc_id=None, confidence=1.0)


@router.get("/{case_id}/documents/{doc_id}", response_model=SourceDocumentView)
def get_document(case_id: str, doc_id: str, db: Session = Depends(_db_dependency),
                 store: FhirStore = Depends(get_fhir_store)) -> SourceDocumentView:
    case = _load_case(db, case_id)
    try:
        reports = store.radiology_reports(case.patient_id)
        notes = store.clinical_documents(case.patient_id)
    except PatientNotFound as exc:
        raise NotFoundError("Záznamy pacienta nebyly nalezeny") from exc
    except FhirStoreError as exc:
        raise NotFoundError("Záznamy pacienta se nepodařilo načíst") from exc
    for res in reports:
        if res["id"] == doc_id:
            when = to_date(res.get("effectiveDateTime"))
            return _document_view(case, doc_id, "radiology_report", when, report_text(res))
    for res in notes:
        if res["id"] == doc_id:
            return _document_view(case, doc_id, "clinical_note", to_date(res.get("date")),
                                  decode_attachment(res))
    raise NotFoundError("Dokument nebyl nalezen")


def _document_view(case: Case, doc_id: str, kind: str, when: date | None, text: str) -> SourceDocumentView:
    shown = shift_iso(when, case.date_offset_days) if when else ""
    return SourceDocumentView(doc_id=doc_id, kind=kind, date=shown, text=text)
