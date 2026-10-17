"""Map derived pipeline facts to FHIR R4 resources (ServiceRequest, Observation, Provenance)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.fhir_store.base import FhirStore, Resource
from app.pipeline.schemas import CaseCheckResult, Evidence, PlannedExam, PriorReference

DCM = "http://dicom.nema.org/resources/ontology/DCM"
LOCAL = "https://rakathon.local/fhir"
QUOTE_URL = f"{LOCAL}/StructureDefinition/source-quote"
CONFIDENCE_URL = f"{LOCAL}/StructureDefinition/extraction-confidence"
SOFTWARE_NAME = "pacs-comparator-check"


def _patient_ref(patient_id: str) -> dict[str, str]:
    return {"reference": f"Patient/{patient_id}"}


def _source_ref(doc_id: str) -> str:
    # Radiology reports are DiagnosticReport resources; clinical notes are DocumentReference.
    return f"DiagnosticReport/{doc_id}" if doc_id.startswith("rep-") else f"DocumentReference/{doc_id}"


def _derived_from_ref(doc_id: str) -> dict[str, str]:
    """Observation.derivedFrom only accepts ImagingStudy, DocumentReference, ... (not DiagnosticReport).

    A radiology report `rep-<study id>` derives from its ImagingStudy; the report itself goes in `focus`.
    """
    if doc_id.startswith("rep-"):
        return {"reference": f"ImagingStudy/{doc_id.removeprefix('rep-')}"}
    return {"reference": _source_ref(doc_id)}


def planned_exam_to_service_request(exam: PlannedExam) -> Resource:
    resource: dict[str, Any] = {
        "resourceType": "ServiceRequest",
        "id": exam.id,
        "status": "active",
        "intent": "plan",
        "subject": _patient_ref(exam.patient_id),
        "code": {"text": "MDT"} if exam.kind == "mdt"
        else {"coding": [{"system": DCM, "code": exam.modality}], "text": exam.modality},
        "reasonReference": [{"reference": _source_ref(exam.source_doc_id)}],
        "extension": [
            {"url": QUOTE_URL, "valueString": exam.evidence.quote},
            {"url": CONFIDENCE_URL, "valueDecimal": exam.evidence.confidence},
        ],
    }
    # FHIR forbids empty arrays: an MDT plan or an unknown region has no bodySite.
    if exam.regions:
        resource["bodySite"] = [{"text": region} for region in exam.regions]
    if exam.date:
        resource["occurrenceDateTime"] = exam.date.isoformat()
    if exam.site_text:
        resource["performer"] = [{"display": exam.site_text}]
    return resource


def reference_to_observation(ref: PriorReference) -> Resource:
    values = [
        ("modality", ref.modality),
        ("body region", ", ".join(ref.regions)),
        ("referenced date", ref.ref_date.iso if ref.ref_date else ""),
        ("holding site", ref.site_text or ""),
    ]
    # FHIR forbids empty values: leave out components that have nothing to say.
    components = [{"code": {"text": name}, "valueString": value} for name, value in values if value]
    return {
        "resourceType": "Observation",
        "id": ref.id,
        "status": "final",
        "category": [{"coding": [{"system": f"{LOCAL}/CodeSystem/observation-category",
                                  "code": "imaging-reference"}]}],
        "code": {"text": "referenced prior study"},
        "subject": _patient_ref(ref.patient_id),
        "focus": [{"reference": _source_ref(ref.from_report_id)}],
        "derivedFrom": [_derived_from_ref(ref.from_report_id)],
        "component": components,
        "extension": [{"url": CONFIDENCE_URL, "valueDecimal": ref.evidence.confidence}],
    }


def provenance_for(target_type: str, target_id: str, evidence: Evidence, model: str,
                   recorded: datetime | None = None) -> Resource:
    when = (recorded or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "resourceType": "Provenance",
        "id": f"PROV-{target_id}",
        "target": [{"reference": f"{target_type}/{target_id}"}],
        "recorded": when,
        "agent": [{
            "type": {"text": "assembler"},
            "who": {"display": f"{SOFTWARE_NAME} / {model}"},
        }],
        "entity": [{"role": "source", "what": {"reference": _source_ref(evidence.doc_id)}}],
        "extension": [
            {"url": QUOTE_URL, "valueString": evidence.quote},
            {"url": CONFIDENCE_URL, "valueDecimal": evidence.confidence},
        ],
    }


def write_case_outputs(store: FhirStore, result: CaseCheckResult, model: str) -> list[str]:
    """Persist derived resources idempotently (deterministic ids, update in place)."""
    written: list[str] = []
    # A RIS order already is a ServiceRequest in FHIR; only text-extracted plans are written.
    if (result.planned_exam and not result.planned_exam.corrected_by_coordinator
            and result.planned_exam.source == "text"):
        exam = result.planned_exam
        store.update(planned_exam_to_service_request(exam))
        store.update(provenance_for("ServiceRequest", exam.id, exam.evidence, model))
        written += [f"ServiceRequest/{exam.id}", f"Provenance/PROV-{exam.id}"]
    for ref in result.references:
        store.update(reference_to_observation(ref))
        store.update(provenance_for("Observation", ref.id, ref.evidence, model))
        written += [f"Observation/{ref.id}", f"Provenance/PROV-{ref.id}"]
    return written
