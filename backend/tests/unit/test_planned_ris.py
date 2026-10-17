"""Planned exam from the simulated RIS (synthetic resources only)."""

from __future__ import annotations

from datetime import date

from app.fhir_store.base import FhirStoreError
from app.fhir_store.mappers import write_case_outputs
from app.pipeline.planned_ris import RIS_QUOTE, planned_from_ris
from app.pipeline.schemas import CaseCheckResult, Timeline

RIS_TAGS = [{"system": "urn:pacs-comparator:simulation", "code": "simulated"},
            {"system": "urn:pacs-comparator:hl7-source", "code": "ORM^O01"}]


def _order(rid: str, code: str, authored: str, occurrence: str, status: str = "active", tags=None) -> dict:
    return {"resourceType": "ServiceRequest", "id": rid, "status": status, "intent": "order",
            "meta": {"tag": RIS_TAGS if tags is None else tags},
            "subject": {"reference": "Patient/PAC-TEST-0001"},
            "code": {"coding": [{"system": "http://dicom.nema.org/resources/ontology/DCM", "code": code}]},
            "bodySite": [{"text": "chest"}, {"text": "abdomen"}],
            "authoredOn": authored, "occurrenceDateTime": occurrence}


class FakeStore:
    def __init__(self, resources: list[dict], fail: bool = False) -> None:
        self.resources_ = resources
        self.fail = fail
        self.updated: list[dict] = []

    def search(self, resource_type, params=None):
        if self.fail:
            raise FhirStoreError("down")
        return [r for r in self.resources_ if r["resourceType"] == resource_type
                and r["subject"]["reference"] == params["subject"]]

    def update(self, resource):
        self.updated.append(resource)


def test_newest_active_ris_order_becomes_planned_exam_in_patient_frame():
    store = FakeStore([
        _order("RIS-OLD", "CT", "2026-10-01", "2026-10-20"),
        _order("RIS-NEW", "PT", "2026-10-10", "2026-10-24"),
        _order("RIS-CANCELLED", "MR", "2026-10-15", "2026-10-30", status="revoked"),
        _order("OURS", "MR", "2026-10-16", "2026-10-30", tags=[]),
    ])
    exam = planned_from_ris(store, "PAC-TEST-0001", date(2025, 3, 1))
    assert exam is not None and exam.source == "ris" and exam.modality == "PET"
    assert exam.regions == ["chest", "abdomen"] or set(exam.regions) == {"chest", "abdomen"}
    assert exam.date == date(2025, 3, 15)  # 14 days lead time from the latest document date
    assert exam.evidence.quote == RIS_QUOTE and exam.source_doc_id == "ServiceRequest/RIS-NEW"


def test_no_order_or_store_error_falls_back_to_text():
    assert planned_from_ris(FakeStore([]), "PAC-TEST-0001", date(2025, 3, 1)) is None
    assert planned_from_ris(FakeStore([], fail=True), "PAC-TEST-0001", date(2025, 3, 1)) is None


def test_ris_plan_is_not_written_again_as_our_service_request():
    store = FakeStore([_order("RIS-NEW", "CT", "2026-10-10", "2026-10-24")])
    exam = planned_from_ris(store, "PAC-TEST-0001", date(2025, 3, 1))
    result = CaseCheckResult(patient_id="PAC-TEST-0001", timeline=Timeline(patient_id="PAC-TEST-0001"),
                             planned_exam=exam)
    assert write_case_outputs(store, result, "test-model") == [] and store.updated == []
