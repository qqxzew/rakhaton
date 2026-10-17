// Types and hooks for the system screens (worklist, hospitals, IRIS integration map).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { RequestState } from "./api-types";

export class SystemApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

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

const enc = encodeURIComponent;

/** Every section can be unavailable (IRIS or a part of it unreachable). */
export interface Availability {
  available: boolean;
  reason?: string | null;
}

export type StateGroup = "approval" | "sent" | "escalated" | "received" | "verified" | "closed";
export type Urgency = "danger" | "attention" | "ready" | "info" | "normal";

export interface Prediction {
  late_probability: number | null;
  expected_hours: number | null;
  simulated: boolean;
  model?: string;
}

export interface WorklistRow {
  request_id: string;
  case_id: string | null;
  patient_id: string | null;
  display_name: string | null;
  meeting: { id: string; label: string; date: string; time: string } | null;
  days_to_mdt: number | null;
  modality: string | null;
  regions: string[];
  target_date: string | null;
  shifted: boolean;
  provider: { id: string | null; name: string | null; route: string | null };
  state: RequestState;
  state_group: StateGroup;
  updated_at: string | null;
  attempts: number;
  prediction: Prediction | null;
  urgency: Urgency;
}

export interface Worklist extends Availability {
  today?: string;
  requests: WorklistRow[];
  counts?: Partial<Record<StateGroup, number>>;
  ml_available?: boolean;
}

export interface Provider {
  id: string;
  name: string;
  aliases: string[];
  email: string | null;
  phone: string | null;
  hours: string | null;
  preferred_channel: string | null;
  exchange_route: string | null;
  fhir_base: string | null;
  kind: "home" | "simulated_endpoint" | "registry" | "unknown";
  fhir_studies: number | null;
  fhir_error: string | null;
  open_requests: number;
  verified: number;
  total_requests: number;
  expected_hours: Record<string, number | null>;
}

export interface Hospitals extends Availability {
  requests_available: boolean;
  requests_reason: string | null;
  ml_available: boolean;
  providers: Provider[];
}

export interface FhirOverview extends Availability {
  base?: string;
  metadata_url?: string;
  portal_url?: string;
  fhir_ui_url?: string;
  resources?: { label: string; resource_type: string; count: number }[];
  hospitals?: {
    id: string;
    name: string;
    base: string;
    counts: Record<string, number>;
    available: boolean;
    reason?: string;
  }[];
}

export interface ProductionOverview extends Availability {
  name?: string;
  running?: boolean;
  namespace?: string;
  config_url?: string;
  messages_url?: string;
  items?: { name: string; class_name: string; enabled: boolean; category: string | null; kind: string }[];
  messages?: {
    id: number;
    time: string | null;
    source: string | null;
    target: string | null;
    body_class: string | null;
    session_id: number | null;
    status: string;
    visual_trace_url: string | null;
  }[];
}

export interface MlOverview extends Availability {
  source: string;
  models: {
    model: string;
    kind: string;
    predicts: string;
    trained_model?: string;
    metrics: Record<string, number>;
  }[];
}

export interface SqlStats {
  source: string;
  studies: {
    total: number;
    per_modality: Record<string, number>;
    in_pacs: number;
    not_in_pacs: number;
    pacs_unknown: number;
  };
  open_tasks: { total: number; per_state: Record<string, number> };
  cited_priors: { total: number; undated: number; not_found: number };
  requests_per_hospital: Record<string, number>;
  planned_exams_per_modality: Record<string, number>;
}

export interface SqlOverview extends Availability {
  schema?: string;
  stats?: SqlStats;
}

export interface McpOverview extends Availability {
  server: string;
  transports: string[];
  tools: { name: string; description: string; required: string[] }[];
}

export interface CasePatient {
  patient_id: string;
  case_id: string;
  display_name: string;
}

export interface VectorResult extends Availability {
  query?: string;
  table?: string;
  elapsed_ms?: number;
  hits: {
    source_type: string;
    id: string;
    patient_id: string | null;
    date: string | null;
    modality: string | null;
    score: number;
    snippet: string | null;
  }[];
}

export interface Hl7Result extends Availability {
  message_type?: string;
  ack?: string;
  accepted?: boolean;
  placer_order?: string;
  service_request?: string | null;
  segments?: string[];
  messages_url?: string;
}

export interface CFindResult extends Availability {
  ae?: string;
  client?: string;
  elapsed_ms?: number;
  matches?: { study_date: string | null; modality: string | null; accession: string | null }[];
}

export const systemApi = {
  worklist: (): Promise<Worklist> => call("/worklist"),
  hospitals: (): Promise<Hospitals> => call("/hospitals"),
  fhir: (): Promise<FhirOverview> => call("/system/fhir"),
  production: (): Promise<ProductionOverview> => call("/system/production?top=10"),
  ml: (): Promise<MlOverview> => call("/system/ml"),
  sql: (): Promise<SqlOverview> => call("/system/sql"),
  mcp: (): Promise<McpOverview> => call("/system/mcp"),
  patients: (): Promise<{ patients: CasePatient[] }> => call("/system/patients"),
  vectorSearch: (q: string, patientId: string, includeText: boolean): Promise<VectorResult> =>
    call(
      `/system/vector-search?q=${enc(q)}&top=5&include_text=${includeText}` +
        (patientId ? `&patient_id=${enc(patientId)}` : ""),
    ),
  hl7Orm: (body: { patient_id: string; modality: string; days: number }): Promise<Hl7Result> =>
    call("/system/hl7-orm", { method: "POST", body: JSON.stringify(body) }),
  cfind: (body: { patient_id: string; node: string; modality?: string }): Promise<CFindResult> =>
    call("/system/dicom-cfind", { method: "POST", body: JSON.stringify(body) }),
  approveAll: (coordinator: string): Promise<{ approved: number; requests: string[] }> =>
    call("/requests/approve-all", { method: "POST", body: JSON.stringify({ coordinator }) }),
};

export function useWorklist() {
  return useQuery({ queryKey: ["system", "worklist"], queryFn: systemApi.worklist, refetchInterval: 10_000 });
}

export function useHospitals() {
  return useQuery({ queryKey: ["system", "hospitals"], queryFn: systemApi.hospitals, refetchInterval: 30_000 });
}

export function useSystemSection<T>(key: string, fn: () => Promise<T>, refetchMs: number | false = false) {
  return useQuery({ queryKey: ["system", key], queryFn: fn, refetchInterval: refetchMs });
}

export function useCasePatients() {
  return useQuery({ queryKey: ["system", "patients"], queryFn: systemApi.patients, staleTime: 60_000 });
}

export function useApproveAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (coordinator: string) => systemApi.approveAll(coordinator),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["system"] });
      void qc.invalidateQueries({ queryKey: ["case"] });
    },
  });
}
