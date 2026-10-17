"""Planned exam from the simulated RIS (IRIS Stage D3).

The HL7 feed writes ORM^O01 orders as FHIR ServiceRequests tagged `urn:pacs-comparator:hl7-source|ORM^O01`.
A live order is a structured fact and wins over a plan extracted from note text. RIS dates are calendar
dates, the pipeline works in the patient's shifted frame, so the order keeps its lead time
(occurrence - authoredOn) counted from the patient's latest document date.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.fhir_store.base import FhirStore, Resource
from app.logging import get_logger
from app.pipeline.normalize import clean_regions, normalize_modality
from app.pipeline.schemas import Evidence, PlannedExam

log = get_logger(__name__)

RIS_TAG_SYSTEM = "urn:pacs-comparator:hl7-source"
RIS_TAG_CODE = "ORM^O01"
RIS_QUOTE = "Objednávka ze simulovaného RIS (HL7 ORM^O01)"
_DICOM_TO_OURS = {"PT": "PET", "CR": "RTG", "DX": "RTG", "US": "SONO", "MG": "MAMO", "NM": "SCINT"}


def _is_ris_order(res: Resource) -> bool:
    tags = (res.get("meta") or {}).get("tag") or []
    return any(t.get("system") == RIS_TAG_SYSTEM and t.get("code") == RIS_TAG_CODE for t in tags)


def _day(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _modality(res: Resource) -> str:
    code = res.get("code") or {}
    raw = next((c.get("code") for c in code.get("coding") or [] if c.get("code")), None) or code.get("text")
    raw = str(raw or "").upper()
    return normalize_modality(_DICOM_TO_OURS.get(raw, raw))


def ris_orders(store: FhirStore, patient_id: str) -> list[Resource]:
    """Active RIS orders of the patient, newest first (by authoredOn)."""
    found = store.search("ServiceRequest", {"subject": f"Patient/{patient_id}"})
    active = [r for r in found if _is_ris_order(r) and r.get("status", "active") == "active"]
    return sorted(active, key=lambda r: str(r.get("authoredOn") or ""), reverse=True)


def planned_from_ris(store: FhirStore, patient_id: str, latest_doc: date | None) -> PlannedExam | None:
    """The newest active RIS order as the planned exam, or None (also on any store error)."""
    try:
        orders = ris_orders(store, patient_id)
    except Exception as exc:  # noqa: BLE001 - the RIS is optional; text extraction stays the fallback
        log.warning("RIS order lookup failed", extra={"fields": {"error": type(exc).__name__}})
        return None
    for res in orders:
        modality = _modality(res)
        if modality in ("UNKNOWN", "OTHER"):
            continue
        authored = _day(res.get("authoredOn"))
        occurrence = _day(res.get("occurrenceDateTime") or (res.get("occurrencePeriod") or {}).get("start"))
        exam_date = None
        if occurrence is not None and latest_doc is not None:
            lead = (occurrence - authored).days if authored else 0
            exam_date = latest_doc + timedelta(days=max(lead, 0))
        performer = next((p.get("display") for p in res.get("performer") or [] if p.get("display")), None)
        return PlannedExam(
            id=f"RIS-{res.get('id')}", patient_id=patient_id, modality=modality,
            regions=clean_regions([b.get("text") for b in res.get("bodySite") or [] if b.get("text")]),
            date=exam_date, site_text=performer, kind="imaging",
            source_doc_id=f"ServiceRequest/{res.get('id')}", source_doc_date=latest_doc,
            evidence=Evidence(doc_id=f"ServiceRequest/{res.get('id')}", quote=RIS_QUOTE, confidence=1.0),
            source="ris",
        )
    return None
