"""HTTP response/request models. Kept in sync by hand with frontend/src/services/api-types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReadinessState = Literal["ready", "attention", "not_ready"]
Availability = Literal["available", "not_in_pacs", "unknown", "not_found"]
ItemState = Literal["ok", "attention", "missing"]
TimelineKind = Literal["study", "referenced", "treatment", "mdt"]
IssueType = Literal["low_confidence", "date_typo", "conflict", "time_gap", "verification_failed", "data"]


class ErrorBody(BaseModel):
    code: str
    message: str


class MeetingView(BaseModel):
    id: str
    label: str
    date: str
    time: str


class CaseSummary(BaseModel):
    id: str
    meeting: MeetingView
    readiness: ReadinessState
    reason: str
    date_offset_days: int


class Diagnosis(BaseModel):
    code: str
    text: str


class PatientView(BaseModel):
    id: str
    display_name: str
    sex: str
    age_band: str
    diagnoses: list[Diagnosis]


class PlannedExamView(BaseModel):
    modality: str
    regions: list[str]
    date: str | None
    site: str | None
    quote: str | None
    source_doc_id: str | None
    confidence: float | None
    source: Literal["text", "ris", "coordinator"] = "text"


class TimelineEntry(BaseModel):
    kind: TimelineKind
    date: str
    modality: str | None
    regions: list[str]
    label: str
    availability: Availability | None
    study_id: str | None
    doc_id: str | None


class HoldingSite(BaseModel):
    id: str
    name: str


class EvidenceView(BaseModel):
    quote: str
    doc_id: str
    confidence: float


class RequestRef(BaseModel):
    id: str
    state: str
    updated_at: str
    provider_name: str | None = None
    approved_by: str | None = None


class WaiverView(BaseModel):
    reason: str
    actor: str
    waived_at: str


class ProposedMatch(BaseModel):
    study_id: str
    report_id: str
    score: float
    simulated: bool = False


class RequiredItemView(BaseModel):
    id: str
    reasons: list[str]
    modality: str
    regions: list[str]
    target_date: str | None
    target_date_precision: Literal["day", "month", "year"] | None = None
    availability: Availability
    state: ItemState
    holding_site: HoldingSite | None
    holding_site_basis: Literal["stated", "text_near_date"] | None = None
    evidence: EvidenceView | None
    request: RequestRef | None = None
    waiver: WaiverView | None = None
    simulated: bool = True
    note: str | None = None
    proposed_match: ProposedMatch | None = None


class OpenIssueView(BaseModel):
    type: IssueType
    text: str


class CaseDetail(BaseModel):
    case: CaseSummary
    patient: PatientView
    planned_exam: PlannedExamView | None
    timeline: list[TimelineEntry]
    items: list[RequiredItemView]
    open_issues: list[OpenIssueView]
    simulated: bool = True
    shifted: bool = True
    check_status: str = "done"
    notes: list[str] = Field(default_factory=list)
    requests_available: bool = True


class SourceDocumentView(BaseModel):
    doc_id: str
    kind: str
    date: str
    text: str


class PlannedExamPatch(BaseModel):
    modality: str = Field(min_length=1, max_length=16)
    regions: list[str] = Field(default_factory=list, max_length=10)
    date: str | None = None
    coordinator: str | None = Field(default=None, max_length=100)


class CaseCreate(BaseModel):
    patient_id: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=200)
    group_id: str = Field(min_length=1, max_length=32)
    meeting_id: str = Field(min_length=1, max_length=64)


class DiagnosisGroupView(BaseModel):
    id: str
    label: str


class ReadinessCounts(BaseModel):
    ready: int = 0
    attention: int = 0
    not_ready: int = 0


class MeetingSummary(BaseModel):
    id: str
    label: str
    date: str
    time: str
    readiness: ReadinessState
    reason: str
    case_count: int
    counts: ReadinessCounts
    eligible_groups: list[str]
    accepts_registrations: bool


class CaseRow(BaseModel):
    id: str
    patient_id: str
    display_name: str
    diagnosis: str | None
    readiness: ReadinessState
    reason: str
    check_status: str


class MeetingDetail(MeetingSummary):
    cases: list[CaseRow]


class DayView(BaseModel):
    date: str
    readiness: ReadinessState | None
    reason: str | None
    counts: ReadinessCounts
    meetings: list[MeetingDetail]


class DashboardDay(BaseModel):
    date: str
    readiness: ReadinessState | None
    reason: str | None
    meetings: list[MeetingSummary]


class DashboardTotals(BaseModel):
    meetings: int
    cases: int
    counts: ReadinessCounts


class Dashboard(BaseModel):
    start: str
    end: str
    days: list[DashboardDay]
    totals: DashboardTotals
    readiness: ReadinessState | None
    reason: str | None


class ScheduleDate(BaseModel):
    date: str
    readiness: ReadinessState
    reason: str
    meeting_count: int
    case_count: int


class EligibleMeeting(BaseModel):
    id: str
    label: str
    date: str
    time: str


class PatientSearchResult(BaseModel):
    id: str
    display_name: str
    sex: str
    age_band: str
    diagnoses: list[Diagnosis]
    suggested_group: str
    has_imaging: bool
    has_documents: bool
