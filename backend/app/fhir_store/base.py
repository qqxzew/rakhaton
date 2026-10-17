"""FhirStore: the single interface for reading clinical facts and writing derived FHIR R4 resources.

Implementations: LocalBundleStore (file based, default) and, later, an IRIS REST adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

Resource = dict[str, Any]

# Test radiology reports uploaded from the patient view are tagged with this (system, code).
TEST_UPLOAD_TAG = ("urn:pacs-comparator:simulation", "test-upload")


def is_test_upload(resource: Resource) -> bool:
    tags = (resource.get("meta") or {}).get("tag") or []
    return any((t.get("system"), t.get("code")) == TEST_UPLOAD_TAG for t in tags)


class FhirStoreError(RuntimeError):
    pass


class PatientNotFound(FhirStoreError):
    pass


class FhirStore(ABC):
    @abstractmethod
    def list_patient_ids(self) -> list[str]:
        """All patient identifiers known to the store."""

    @abstractmethod
    def get_patient_bundle(self, patient_id: str) -> Resource:
        """A FHIR Bundle with every resource of the patient (dataset resources only)."""

    @abstractmethod
    def resources(self, patient_id: str, resource_type: str) -> list[Resource]:
        """All dataset resources of one type for a patient."""

    @abstractmethod
    def create(self, resource: Resource) -> Resource:
        """Persist a new derived resource; assigns an id when missing."""

    @abstractmethod
    def update(self, resource: Resource) -> Resource:
        """Replace a previously created derived resource (by resourceType and id)."""

    @abstractmethod
    def search(self, resource_type: str, params: dict[str, str] | None = None) -> list[Resource]:
        """Search derived resources; only exact-match parameters are required."""

    def delete(self, resource_type: str, resource_id: str) -> None:
        """Remove a resource we wrote (test uploads only)."""
        raise FhirStoreError(f"{type(self).__name__} cannot delete resources")

    def forget(self, patient_id: str) -> None:
        """Drop cached data of a patient after we wrote clinical resources for them."""
        return None

    def imaging_studies(self, patient_id: str) -> list[Resource]:
        return self.resources(patient_id, "ImagingStudy")

    def radiology_reports(self, patient_id: str) -> list[Resource]:
        return self.resources(patient_id, "DiagnosticReport")

    def clinical_documents(self, patient_id: str) -> list[Resource]:
        return self.resources(patient_id, "DocumentReference")

    def conditions(self, patient_id: str) -> list[Resource]:
        return self.resources(patient_id, "Condition")
