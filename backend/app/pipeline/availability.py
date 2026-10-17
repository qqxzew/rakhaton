"""PACS availability. The dataset flag is a simulation of a real PACS query (QIDO-RS / C-FIND)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.pipeline.schemas import Availability, OpenIssue, PriorReference, RequiredItem, Study


class AvailabilityAdapter(ABC):
    @abstractmethod
    def check(self, study: Study | None, reference: PriorReference | None) -> Availability:
        """Availability of one required study. `study` is the matched internal study, if any."""

    def enrich(self, items: list[RequiredItem]) -> tuple[list[RequiredItem], list[OpenIssue]]:
        """Hook after build_items: adapters that learned more (e.g. which hospital holds a study) add it here."""
        return items, []


class DatasetFlagAdapter(AvailabilityAdapter):
    """Reads the PACS availability flag from the dataset's ImagingStudy extension."""

    def check(self, study: Study | None, reference: PriorReference | None) -> Availability:
        if study is None:
            return "not_found"
        if study.source == "received":
            return "available"
        return {"yes": "available", "no": "not_in_pacs"}.get(study.pacs_flag, "unknown")


def default_adapter() -> AvailabilityAdapter:
    """Adapter chosen by AVAILABILITY_ADAPTER (default dicom with the IRIS FHIR backend, else dataset_flag)."""
    from app.config import get_settings

    settings = get_settings()
    if settings.availability_adapter == "dicom":
        from app.pipeline.availability_dicom import DicomAvailabilityAdapter

        return DicomAvailabilityAdapter()

    if settings.availability_adapter == "fhir_hospitals" and settings.fhir_backend == "iris":
        from app.pipeline.availability_fhir import FhirHospitalAdapter

        return FhirHospitalAdapter()
    return DatasetFlagAdapter()
