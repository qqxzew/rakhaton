// Request workflow, nightly run, agent chat and evaluation (all actions run in the IRIS production).
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import type { RequestState } from "./api-types";
import { SystemApiError, type Prediction } from "./systemApi";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = (await res.json()) as { message?: string; detail?: unknown };
      message = body.message ?? (typeof body.detail === "string" ? body.detail : message);
    } catch {
      // non-JSON error body
    }
    throw new SystemApiError(res.status, message);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown = {}) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });
const enc = encodeURIComponent;

export interface ActionResult {
  ok?: boolean;
  requestId?: string;
  state?: RequestState;
  note?: string;
  sessionId?: string;
}

export interface HistoryEntry {
  ts: string;
  actor: string;
  from: string;
  to: string;
  note: string;
  sessionId?: string;
}

export type MessageKind = "email" | "reminder" | "voice_call" | "call_outcome" | "reply" | "delivery";

export interface RequestMessage {
  id: number;
  ts: string;
  kind: MessageKind | string;
  direction: string;
  channel: string;
  subject: string;
  body: string;
  class?: string;
  quote?: string;
  method?: string;
  hasAudio?: boolean;
}

export interface RequestDetail {
  requestId: string;
  caseId: string;
  itemId: string;
  state: RequestState;
  modality?: string;
  targetDate?: string;
  regions?: string;
  provider?: { id?: string; name?: string; email?: string; route?: string };
  deadline?: string;
  approvedBy?: string;
  approvedAt?: string;
  attempts?: number;
  nextActionAt?: string;
  fhirTaskId?: string;
  note?: string;
  replyClass?: string;
  verifyReason?: string;
  updatedAt?: string;
  history: HistoryEntry[];
  messages: RequestMessage[];
  visualTrace?: string[];
  prediction?: Prediction | null;
}

export interface NightlyResult {
  window: { from: string; to: string };
  cases_checked: number;
  failed: number;
  drafts_created: number;
  drafts_pending: number;
  meetings: { meeting_id: string; label: string; date: string; time: string; cases: number; drafts_created: number }[];
}

export interface DemoSummary {
  available: boolean;
  reason?: string;
  drafts_pending: number;
  case_ids: string[];
}

export interface WaiveResult {
  cancelled_request: string | null;
  cancel_error: string | null;
  readiness: string;
}

export interface ChatResult {
  answer: string;
  tools_called: { name?: string; tool?: string; args?: unknown; arguments?: unknown }[];
  sources: string[];
  refused: boolean;
  mode: string;
}

export interface EvalResult {
  available: boolean;
  reason?: string;
  label?: string;
  reports?: number | null;
  silver_citations?: number | null;
  recall_pct?: number | null;
  date_accuracy_given_modality_pct?: number | null;
  in_dataset_pct?: number | null;
  naive_latest_same_modality_pct?: number | null;
}

export const requestsApi = {
  createDrafts: (caseId: string) => post<ActionResult[]>(`/cases/${enc(caseId)}/requests`),
  get: (id: string) => call<RequestDetail>(`/requests/${enc(id)}`),
  approve: (id: string, coordinator: string) => post<ActionResult>(`/requests/${enc(id)}/approve`, { coordinator }),
  approveAll: (coordinator: string, caseIds: string[]) =>
    post<{ approved: number; requests: string[] }>("/requests/approve-all", { coordinator, case_ids: caseIds }),
  reply: (id: string, text: string) => post<ActionResult>(`/requests/${enc(id)}/simulate-reply`, { text }),
  call: (id: string, outcome: string) => post<ActionResult>(`/requests/${enc(id)}/simulate-call`, { outcome }),
  delivery: (id: string, body: { modality?: string; date?: string; region?: string }) =>
    post<ActionResult>(`/requests/${enc(id)}/simulate-delivery`, body),
  waive: (itemId: string, caseId: string, reason: string, coordinator: string) =>
    post<WaiveResult>(`/items/${enc(itemId)}/waive`, { reason, coordinator, case_id: caseId }),
  acknowledge: (caseId: string, key: string, coordinator: string, note = "") =>
    post<{ readiness: string; readiness_reason: string }>(
      `/cases/${enc(caseId)}/issues/${enc(key)}/acknowledge`, { coordinator, note }),
  nightly: () => post<NightlyResult>("/demo/nightly-run", { days: 2 }),
  summary: () => call<DemoSummary>("/demo/summary?days=7"),
  advance: (hours: number) => post<{ offsetSeconds?: number; now?: string; ticked?: unknown[] }>("/demo/advance-time", { hours }),
  chat: (caseId: string, question: string) => post<ChatResult>("/agent/chat", { case_id: caseId, question }),
  evaluation: () => call<EvalResult>("/system/eval"),
  audioUrl: (id: string, messageId: number) => `/api/requests/${enc(id)}/audio/${messageId}`,
};

/** Everything that shows readiness or request state. */
export function invalidateAll(qc: QueryClient) {
  for (const key of ["dashboard", "schedule-dates", "day", "meeting", "case", "system", "request", "demo-summary"]) {
    void qc.invalidateQueries({ queryKey: [key] });
  }
}

export function useAction<A, R>(fn: (args: A) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSettled: () => invalidateAll(qc) });
}

export function useRequestDetail(id: string | null) {
  return useQuery({
    queryKey: ["request", id],
    queryFn: () => requestsApi.get(id as string),
    enabled: !!id,
    refetchInterval: 5_000,
  });
}

export function useDemoSummary() {
  return useQuery({ queryKey: ["demo-summary"], queryFn: requestsApi.summary, refetchInterval: 15_000 });
}

export function useEvaluation() {
  return useQuery({ queryKey: ["system", "eval"], queryFn: requestsApi.evaluation, staleTime: 60_000 });
}

const COORDINATOR_KEY = "pacs.coordinator";

export function getCoordinator(): string {
  try {
    return localStorage.getItem(COORDINATOR_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setCoordinator(name: string) {
  try {
    localStorage.setItem(COORDINATOR_KEY, name.trim());
  } catch {
    // storage disabled
  }
}

export function isPresentation(): boolean {
  return document.documentElement.classList.contains("presentation");
}
