"""Hook called by the IRIS production (PacsComparator.HL7.BO.BackendHook) after a ServiceRequest from the
simulated RIS has been written to FHIR: the open cases of that patient are checked again (T086)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cases import _background_check, get_fhir_store, get_llm
from app.app_db.models import Case
from app.app_db.session import get_db
from app.fhir_store.base import FhirStore
from app.llm.client import StructuredLlm

router = APIRouter(prefix="/api/hooks", tags=["hooks"])


class FhirWritten(BaseModel):
    patient_id: str
    resource_type: str
    resource_id: str


@router.post("/fhir-written", status_code=202)
def fhir_written(body: FhirWritten, tasks: BackgroundTasks, db: Session = Depends(get_db),
                 store: FhirStore = Depends(get_fhir_store), llm: StructuredLlm = Depends(get_llm)) -> dict:
    if body.resource_type != "ServiceRequest":
        return {"rechecked": 0}
    cases = db.scalars(select(Case).where(Case.patient_id == body.patient_id,
                                          Case.check_status != "running")).all()
    for case in cases:
        case.check_status = "running"
        tasks.add_task(_background_check, case.id, store, llm)
    db.commit()
    return {"rechecked": len(cases)}
