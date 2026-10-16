// Mirrors the case detail view model (CLAUDE.md 11.1) plus agreed additions:
// `doc_id` on timeline entries and item evidence, `simulated` on items,
// and the source document endpoint.
// All dates are ISO "YYYY-MM-DD" strings, already shifted for presentation.

export type ReadinessState = "ready" | "attention" | "not_ready";

export type Availability = "available" | "not_in_pacs" | "unknown" | "not_found";

export type ItemState = "ok" | "attention" | "missing";

export type TimelineKind = "study" | "referenced" | "treatment" | "mdt";

export type IssueType =
  | "low_confidence"
  | "date_typo"
  | "conflict"
  | "time_gap"
  | "verification_failed"
  | "data";

export type RequestState =
  | "DETECTED"
  | "DRAFTED"
  | "APPROVED"
  | "SENT"
  | "ACKNOWLEDGED"
  | "RECEIVED"
  | "VERIFIED"
  | "CLOSED"
  | "REMINDER_SENT"
  | "VOICE_ESCALATED"
  | "HUMAN_ESCALATED"
  | "REJECTED"
  | "NEEDS_INFO"
  | "WRONG_RECIPIENT"
  | "CANCELLED";

export interface Meeting {
  id: string;
  label: string;
  date: string;
  time: string; // "HH:MM"
}

export interface CaseSummary {
  id: string;
  meeting: Meeting;
  readiness: ReadinessState;
  reason: string;
  date_offset_days: number;
}

export interface Diagnosis {
  code: string;
  text: string;
}

export interface Patient {
  id: string; // dataset pseudonym
  display_name: string; // fictional
  sex: string;
  age_band: string;
  diagnoses: Diagnosis[];
}

export interface PlannedExam {
  modality: string;
  regions: string[];
  date: string | null;
  site: string | null;
  quote: string | null;
  source_doc_id: string | null;
  confidence: number | null; // 0..1
}

export interface TimelineEntry {
  kind: TimelineKind;
  date: string;
  modality: string | null;
  regions: string[];
  label: string;
  availability: Availability | null; // null for treatment / mdt
  study_id: string | null;
  doc_id: string | null;
}

export interface HoldingSite {
  id: string;
  name: string;
}

export interface Evidence {
  quote: string;
  doc_id: string;
  confidence: number; // 0..1
}

export interface RequestRef {
  id: string;
  state: RequestState;
  updated_at: string;
}

export interface RequiredItem {
  id: string;
  reasons: string[];
  modality: string;
  regions: string[];
  target_date: string | null;
  // "month": the day is an approximation, show month and year only
  target_date_precision?: "day" | "month" | "year" | null;
  availability: Availability;
  state: ItemState;
  holding_site: HoldingSite | null;
  // "text_near_date": site read from the report text next to the cited date, not stated by the extraction
  holding_site_basis?: "stated" | "text_near_date" | null;
  evidence: Evidence | null;
  request: RequestRef | null;
  simulated: boolean;
  note?: string | null;
}

export interface OpenIssue {
  type: IssueType;
  text: string;
}

export interface CaseDetail {
  case: CaseSummary;
  patient: Patient;
  planned_exam: PlannedExam | null;
  timeline: TimelineEntry[];
  items: RequiredItem[];
  open_issues: OpenIssue[];
  simulated: boolean;
  check_status?: string;
  notes?: string[];
}

// GET /api/cases/{caseId}/documents/{docId}
export interface SourceDocument {
  doc_id: string;
  kind: string;
  date: string;
  text: string;
}

// PATCH /api/cases/{caseId}/planned-exam
export interface PlannedExamPatch {
  modality: string;
  regions: string[];
  date: string | null;
}

// Error body used by all routes
export interface ApiErrorBody {
  code: string;
  message: string;
}

// ---- Schedule and registration (GET /api/dashboard, /days, /meetings, /patients/search, POST /api/cases) ----
// Meeting dates are real calendar dates (not shifted); only patient dates inside a case are shifted.

export interface DiagnosisGroup {
  id: string;
  label: string;
}

export interface ReadinessCounts {
  ready: number;
  attention: number;
  not_ready: number;
}

export interface MeetingSummary {
  id: string;
  label: string;
  date: string;
  time: string;
  readiness: ReadinessState;
  reason: string;
  case_count: number;
  counts: ReadinessCounts;
  eligible_groups: string[];
  accepts_registrations: boolean;
}

export interface CaseRow {
  id: string;
  patient_id: string;
  display_name: string;
  diagnosis: string | null;
  readiness: ReadinessState;
  reason: string;
  check_status: string;
}

export interface MeetingDetail extends MeetingSummary {
  cases: CaseRow[];
}

export interface DayView {
  date: string;
  readiness: ReadinessState | null;
  reason: string | null;
  counts: ReadinessCounts;
  meetings: MeetingDetail[];
}

export interface DashboardDay {
  date: string;
  readiness: ReadinessState | null;
  reason: string | null;
  meetings: MeetingSummary[];
}

export interface Dashboard {
  start: string;
  end: string;
  days: DashboardDay[];
  totals: { meetings: number; cases: number; counts: ReadinessCounts };
  readiness: ReadinessState | null;
  reason: string | null;
}

export interface ScheduleDate {
  date: string;
  readiness: ReadinessState;
  reason: string;
  meeting_count: number;
  case_count: number;
}

export interface EligibleMeeting {
  id: string;
  label: string;
  date: string;
  time: string;
}

export interface PatientSearchResult {
  id: string;
  display_name: string;
  sex: string;
  age_band: string;
  diagnoses: Diagnosis[];
  suggested_group: string;
  has_imaging: boolean;
  has_documents: boolean;
}

export interface CaseCreate {
  patient_id: string;
  display_name?: string | null;
  group_id: string;
  meeting_id: string;
}
