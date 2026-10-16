"""Patient picker search over the FHIR store: identifiers, diagnoses and data badges only, never report text."""

from __future__ import annotations

from weakref import WeakKeyDictionary

from fastapi import APIRouter, Depends, Query

from app.api.case_views import age_band, diagnosis_label, fictional_name
from app.api.cases import get_fhir_store
from app.api.errors import DependencyUnavailable
from app.api.schemas import Diagnosis, PatientSearchResult
from app.fhir_store.base import FhirStore, FhirStoreError
from app.scheduling.meetings import group_for_codes

router = APIRouter(prefix="/api/patients", tags=["patients"])

# Per-store memo so repeated searches do not re-read every patient bundle.
_summaries: WeakKeyDictionary[FhirStore, dict[str, PatientSearchResult]] = WeakKeyDictionary()


def _codes(store: FhirStore, patient_id: str) -> list[str]:
    return sorted({
        c["code"] for cond in store.conditions(patient_id)
        for c in cond.get("code", {}).get("coding", []) if c.get("code")
    })


def summarize(store: FhirStore, patient_id: str) -> PatientSearchResult:
    memo = _summaries.setdefault(store, {})
    if patient_id in memo:
        return memo[patient_id]
    patients = store.resources(patient_id, "Patient")
    patient = patients[0] if patients else {}
    birth = (patient.get("birthDate") or "")[:4]
    sex = patient.get("gender")
    codes = _codes(store, patient_id)
    result = PatientSearchResult(
        id=patient_id, display_name=fictional_name(patient_id, sex), sex=sex or "neznámé",
        age_band=age_band(int(birth) if birth.isdigit() else None),
        diagnoses=[Diagnosis(code=c, text=diagnosis_label(c).removeprefix(f"{c} ")) for c in codes],
        suggested_group=group_for_codes(codes),
        has_imaging=bool(store.imaging_studies(patient_id)),
        has_documents=bool(store.clinical_documents(patient_id)),
    )
    memo[patient_id] = result
    return result


@router.get("/search", response_model=list[PatientSearchResult])
def search_patients(q: str = Query("", max_length=64), group: str | None = Query(None, max_length=32),
                    limit: int = Query(20, ge=1, le=50),
                    store: FhirStore = Depends(get_fhir_store)) -> list[PatientSearchResult]:
    needle = q.strip().lower()
    found: list[PatientSearchResult] = []
    try:
        for patient_id in store.list_patient_ids():
            if needle and needle not in patient_id.lower() and not _matches_diagnosis(store, patient_id, needle):
                continue
            summary = summarize(store, patient_id)
            if group and summary.suggested_group != group:
                continue
            found.append(summary)
            if len(found) >= limit:
                break
    except FhirStoreError as exc:
        raise DependencyUnavailable("Záznamy pacientů se nepodařilo načíst") from exc
    return found


def _matches_diagnosis(store: FhirStore, patient_id: str, needle: str) -> bool:
    """A search text that looks like an ICD-10 code (e.g. `c61`) also matches the patient's diagnoses."""
    if not needle[:1].isalpha() or not needle[1:].isdigit():
        return False
    return any(code.lower().startswith(needle) for code in _codes(store, patient_id))
