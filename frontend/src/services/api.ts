import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ApiErrorBody,
  CaseCreate,
  CaseDetail,
  Dashboard,
  DayView,
  DiagnosisGroup,
  EligibleMeeting,
  PatientSearchResult,
  PlannedExamPatch,
  ScheduleDate,
  SourceDocument,
} from "./api-types";
import { mockApi } from "./mock";

const USE_MOCK = import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === "1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let body: Partial<ApiErrorBody> = {};
    try {
      body = (await res.json()) as Partial<ApiErrorBody>;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, body.code ?? "http_error", body.message ?? res.statusText);
  }
  // recheck / patch responses are not relied upon; tolerate empty bodies
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const enc = encodeURIComponent;

export const api = {
  getCase: (caseId: string): Promise<CaseDetail> =>
    USE_MOCK ? mockApi.getCase(caseId) : request(`/cases/${enc(caseId)}`),

  getDocument: (caseId: string, docId: string): Promise<SourceDocument> =>
    USE_MOCK
      ? mockApi.getDocument(caseId, docId)
      : request(`/cases/${enc(caseId)}/documents/${enc(docId)}`),

  recheck: (caseId: string): Promise<void> =>
    USE_MOCK
      ? mockApi.recheck()
      : request(`/cases/${enc(caseId)}/recheck`, { method: "POST" }),

  patchPlannedExam: (caseId: string, patch: PlannedExamPatch): Promise<void> =>
    USE_MOCK
      ? mockApi.patchPlannedExam(caseId, patch)
      : request(`/cases/${enc(caseId)}/planned-exam`, {
          method: "PATCH",
          body: JSON.stringify(patch),
        }),
};

export const isMockMode = USE_MOCK;

// Schedule and registration always call the backend; the mock mode only covers the case detail.
export const scheduleApi = {
  dashboard: (): Promise<Dashboard> => request("/dashboard?days=7"),
  scheduleDates: (): Promise<ScheduleDate[]> => request("/schedule/dates"),
  day: (date: string): Promise<DayView> => request(`/days/${enc(date)}`),
  diagnosisGroups: (): Promise<DiagnosisGroup[]> => request("/diagnosis-groups"),
  eligibleMeetings: (group: string): Promise<EligibleMeeting[]> =>
    request(`/meetings/eligible?group=${enc(group)}`),
  searchPatients: (q: string): Promise<PatientSearchResult[]> =>
    request(`/patients/search?q=${enc(q)}`),
  createCase: (body: CaseCreate): Promise<CaseDetail> =>
    request("/cases", { method: "POST", body: JSON.stringify(body) }),
};

export const SCHEDULE_POLL_MS = 2000;

export function useDashboard() {
  return useQuery({ queryKey: ["dashboard"], queryFn: scheduleApi.dashboard, refetchInterval: 5000 });
}

export function useScheduleDates() {
  return useQuery({
    queryKey: ["schedule-dates"],
    queryFn: scheduleApi.scheduleDates,
    refetchInterval: 5000,
  });
}

/** Polls while any case of the day is still being checked. */
export function useDay(date: string) {
  return useQuery({
    queryKey: ["day", date],
    queryFn: () => scheduleApi.day(date),
    refetchInterval: (query) =>
      query.state.data?.meetings.some((m) =>
        m.cases.some((c) => c.check_status === "running" || c.check_status === "pending"),
      )
        ? SCHEDULE_POLL_MS
        : false,
  });
}

export function useDiagnosisGroups() {
  return useQuery({
    queryKey: ["diagnosis-groups"],
    queryFn: scheduleApi.diagnosisGroups,
    staleTime: Infinity,
  });
}

export function useEligibleMeetings(group: string) {
  return useQuery({
    queryKey: ["eligible-meetings", group],
    queryFn: () => scheduleApi.eligibleMeetings(group),
    enabled: group !== "",
  });
}

export function usePatientSearch(q: string) {
  return useQuery({
    queryKey: ["patient-search", q],
    queryFn: () => scheduleApi.searchPatients(q),
    staleTime: 60_000,
  });
}

export function useCreateCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CaseCreate) => scheduleApi.createCase(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["schedule-dates"] });
      void qc.invalidateQueries({ queryKey: ["day"] });
    },
  });
}

export const caseKey = (caseId: string) => ["case", caseId] as const;

/** `pollMs` > 0 refetches periodically, e.g. while a recheck is running. */
export function useCaseDetail(caseId: string, pollMs = 0) {
  return useQuery({
    queryKey: caseKey(caseId),
    queryFn: () => api.getCase(caseId),
    refetchInterval: pollMs > 0 ? pollMs : false,
  });
}

export function useSourceDocument(caseId: string, docId: string | null) {
  return useQuery({
    queryKey: ["document", caseId, docId],
    queryFn: () => api.getDocument(caseId, docId as string),
    enabled: docId !== null,
    staleTime: Infinity,
  });
}

export function useRecheck(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.recheck(caseId),
    onSettled: () => qc.invalidateQueries({ queryKey: caseKey(caseId) }),
  });
}

export function useUpdatePlannedExam(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: PlannedExamPatch) => api.patchPlannedExam(caseId, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: caseKey(caseId) }),
  });
}
