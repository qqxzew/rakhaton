"""Typed pipeline models. Dates stay in the patient's own (dataset-shifted) frame."""

from __future__ import annotations

import re
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Availability = Literal["available", "not_in_pacs", "unknown", "not_found"]
ItemState = Literal["ok", "attention", "missing"]
Readiness = Literal["not_ready", "attention", "ready"]
PacsFlag = Literal["yes", "no", "unknown"]
IssueType = Literal["low_confidence", "date_typo", "conflict", "time_gap", "no_priors", "data"]


class QuoteError(ValueError):
    """The quote is not an exact (whitespace-insensitive) part of the source text."""


_WS = re.compile(r"\s+")


def locate_quote(source: str, quote: str) -> tuple[int, int] | None:
    """Span of the quote in the source. Whitespace runs may differ; characters may not."""
    quote = quote.strip()
    if not quote:
        return None
    start = source.find(quote)
    if start >= 0:
        return start, start + len(quote)
    norm_chars: list[str] = []
    index_map: list[int] = []
    prev_space = False
    for i, ch in enumerate(source):
        if ch.isspace():
            if prev_space:
                continue
            norm_chars.append(" ")
            prev_space = True
        else:
            norm_chars.append(ch)
            prev_space = False
        index_map.append(i)
    norm_source = "".join(norm_chars)
    norm_quote = _WS.sub(" ", quote)
    pos = norm_source.find(norm_quote)
    if pos < 0:
        return None
    end = pos + len(norm_quote) - 1
    return index_map[pos], index_map[end] + 1


class Evidence(BaseModel):
    """Source of an AI-derived fact: document id, exact quoted span and confidence."""

    doc_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    @classmethod
    def from_source(cls, doc_id: str, quote: str, confidence: float, source_text: str) -> Evidence:
        span = locate_quote(source_text, quote)
        if span is None:
            raise QuoteError("quote is not part of the source text")
        return cls(doc_id=doc_id, quote=source_text[span[0]:span[1]], confidence=confidence)

    def verify_against(self, source_text: str) -> bool:
        return source_text.find(self.quote) >= 0


class PartialDate(BaseModel):
    """A date with year, month or day precision, e.g. '2025-03' for a month-only citation."""

    year: int
    month: int | None = None
    day: int | None = None

    @model_validator(mode="after")
    def _check(self) -> PartialDate:
        if self.day is not None and self.month is None:
            raise ValueError("day requires month")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError("month out of range")
        if self.day is not None:
            Date(self.year, self.month or 1, self.day)
        return self

    @property
    def precision(self) -> Literal["day", "month", "year"]:
        return "day" if self.day else "month" if self.month else "year"

    @property
    def iso(self) -> str:
        if self.day:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.month:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"

    @classmethod
    def from_iso(cls, text: str) -> PartialDate:
        parts = [int(p) for p in text.split("-")]
        return cls(year=parts[0], month=parts[1] if len(parts) > 1 else None,
                   day=parts[2] if len(parts) > 2 else None)

    def as_date(self) -> Date:
        return Date(self.year, self.month or 1, self.day or 1)

    def end_date(self) -> Date:
        if self.day:
            return self.as_date()
        if self.month:
            nxt = Date(self.year + (self.month == 12), self.month % 12 + 1, 1)
            return Date.fromordinal(nxt.toordinal() - 1)
        return Date(self.year, 12, 31)


class SourceDoc(BaseModel):
    id: str
    kind: Literal["radiology_report", "clinical_note", "mdt", "other"]
    date: Date | None
    text: str
    department: str | None = None
    type_label: str | None = None


class Study(BaseModel):
    id: str
    patient_id: str
    date: Date
    modality: str
    regions: list[str] = Field(default_factory=list)
    site: str | None = None
    source: Literal["internal", "received"] = "internal"
    pacs_flag: PacsFlag = "unknown"
    pacs_source: str | None = None
    report_id: str | None = None
    headline: str | None = None


class PriorReference(BaseModel):
    id: str
    patient_id: str
    from_report_id: str
    from_report_date: Date | None = None
    modality: str
    regions: list[str] = Field(default_factory=list)
    ref_date: PartialDate | None = None
    ref_date_text: str | None = None
    site_text: str | None = None
    evidence: Evidence
    date_valid: bool = True
    flags: list[str] = Field(default_factory=list)
    matched_study_id: str | None = None
    # Vector Search proposal for a reference without a date (low confidence, never a confirmed match).
    proposed_study_id: str | None = None
    proposed_report_id: str | None = None
    proposed_score: float | None = None

    @property
    def low_confidence(self) -> bool:
        return self.evidence.confidence < 0.5


class PlannedExam(BaseModel):
    id: str
    patient_id: str
    modality: str
    regions: list[str] = Field(default_factory=list)
    date: Date | None = None
    relative_text: str | None = None
    site_text: str | None = None
    kind: Literal["imaging", "mdt", "rt_planning"] = "imaging"
    source_doc_id: str
    source_doc_date: Date | None = None
    evidence: Evidence
    corrected_by_coordinator: bool = False
    # "ris": an order from the simulated RIS (HL7 ORM^O01 -> FHIR ServiceRequest), "text": extracted from notes.
    source: Literal["text", "ris", "coordinator"] = "text"


class TreatmentMilestones(BaseModel):
    first_systemic: Date | None = None
    last_systemic: Date | None = None
    first_surgery: Date | None = None
    first_radiotherapy: Date | None = None
    first_treatment: Date | None = None
    used: list[str] = Field(default_factory=list)


class Timeline(BaseModel):
    patient_id: str
    studies: list[Study] = Field(default_factory=list)
    documents: list[SourceDoc] = Field(default_factory=list)
    mdt_dates: list[Date] = Field(default_factory=list)
    treatment: TreatmentMilestones = Field(default_factory=TreatmentMilestones)
    diagnoses: list[str] = Field(default_factory=list)
    sex: str | None = None
    birth_year: int | None = None
    birth_band: str | None = None  # k-anonymized patients only have a range such as "1940-1944"


class RequiredItem(BaseModel):
    id: str
    rule_ids: list[str]
    reasons: list[str]
    modality: str
    regions: list[str] = Field(default_factory=list)
    target_date: PartialDate | None = None
    study_id: str | None = None
    reference_id: str | None = None
    availability: Availability
    state: ItemState
    holding_site_id: str | None = None
    holding_site_name: str | None = None
    holding_site_basis: Literal["stated", "text_near_date"] | None = None
    evidence: Evidence | None = None
    low_confidence: bool = False
    date_valid: bool = True
    waived: bool = False
    note: str | None = None
    # Set by FhirHospitalAdapter: how the holding hospital was found and its ImagingStudy there.
    located_by: str | None = None
    provider_study_ref: str | None = None
    # Set for items proposed by Vector Search (undated reference): the similar report and its cosine score.
    proposed_report_id: str | None = None
    similarity_score: float | None = None
    simulated: bool = True


class OpenIssue(BaseModel):
    type: IssueType
    text: str
    item_id: str | None = None
    acknowledged: bool = False
    ack_note: str | None = None

    @property
    def key(self) -> str:
        import hashlib

        return hashlib.sha1(f"{self.type}|{self.text}".encode()).hexdigest()[:16]


class CaseCheckResult(BaseModel):
    patient_id: str
    reference_date: Date | None = None
    planned_exam: PlannedExam | None = None
    timeline: Timeline
    references: list[PriorReference] = Field(default_factory=list)
    items: list[RequiredItem] = Field(default_factory=list)
    open_issues: list[OpenIssue] = Field(default_factory=list)
    readiness: Readiness = "not_ready"
    readiness_reason: str = ""
    notes: list[str] = Field(default_factory=list)
