"""PACS availability. The dataset flag is a simulation of a real PACS query (QIDO-RS / C-FIND)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.pipeline.schemas import Availability, PriorReference, Study


class AvailabilityAdapter(ABC):
    @abstractmethod
    def check(self, study: Study | None, reference: PriorReference | None) -> Availability:
        """Availability of one required study. `study` is the matched internal study, if any."""


class DatasetFlagAdapter(AvailabilityAdapter):
    """Reads the PACS availability flag from the dataset's ImagingStudy extension."""

    def check(self, study: Study | None, reference: PriorReference | None) -> Availability:
        if study is None:
            return "not_found"
        if study.source == "received":
            return "available"
        return {"yes": "available", "no": "not_in_pacs"}.get(study.pacs_flag, "unknown")
