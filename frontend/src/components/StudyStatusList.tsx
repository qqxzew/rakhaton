import { useState } from "react";
import { cs } from "../i18n/cs";
import type { RequiredItem } from "../services/api-types";
import { getCoordinator, requestsApi, setCoordinator, useAction } from "../services/requestsApi";
import ActionDialog, { CoordinatorField } from "./ActionDialog";
import { formatDateTime, formatItemDate, regionsText } from "./format";
import ItemActions from "./ItemActions";
import { Button, Panel, Tag, type IconName, type TagTone } from "./ui";

/** The three states a coordinator works with; the full pipeline detail stays in "Podrobnosti". */
export type StudyStatus = "ready" | "awaiting" | "attention";
type PrimaryAction = "approve" | "confirm" | "create" | null;

const TONE: Record<StudyStatus, TagTone> = { ready: "green", awaiting: "blue", attention: "amber" };
const ICON: Record<StudyStatus, IconName> = { ready: "check", awaiting: "mail", attention: "warning" };
const ORDER: Record<StudyStatus, number> = { attention: 0, awaiting: 1, ready: 2 };
const DONE = new Set(["VERIFIED", "CLOSED"]);

/** app_db stores naive UTC timestamps; show them in the viewer's local time. */
function localFromUtc(iso: string): string {
  const d = new Date(`${iso}Z`);
  if (Number.isNaN(d.getTime())) return formatDateTime(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function modalityLabel(modality: string): string {
  if (modality === "UNKNOWN") return "Neurčeno";
  return modality === "PET" ? "PET-CT" : modality;
}

export function studyStatus(item: RequiredItem): { status: StudyStatus; text: string; action: PrimaryAction } {
  const req = item.request;
  const state = req?.state;
  const provider = req?.provider_name ?? item.holding_site?.name ?? "";

  if (item.waiver) return { status: "ready", text: cs.summary.waivedBy(item.waiver.actor, item.waiver.reason), action: null };
  if (item.confirmation)
    return {
      status: "ready",
      text: cs.summary.confirmedBy(item.confirmation.actor, localFromUtc(item.confirmation.waived_at)),
      action: null,
    };
  if (state && DONE.has(state)) return { status: "attention", text: cs.summary.deliveredConfirm(provider), action: "confirm" };
  if (item.state === "ok") return { status: "ready", text: cs.summary.inPacs, action: null };

  const requested = (extra?: string) => {
    const base = cs.summary.requested(formatDateTime(req?.approved_at ?? req?.updated_at ?? ""), cs.summary.byEmail, provider);
    return extra ? `${base} · ${extra}` : base;
  };
  switch (state) {
    case "APPROVED":
    case "SENT":
      return { status: "awaiting", text: requested(), action: null };
    case "REMINDER_SENT":
      return { status: "awaiting", text: requested(cs.summary.reminder), action: null };
    case "VOICE_ESCALATED":
      return { status: "awaiting", text: requested(cs.summary.voice), action: null };
    case "ACKNOWLEDGED":
      return { status: "awaiting", text: requested(cs.summary.acknowledged), action: null };
    case "RECEIVED":
      return { status: "attention", text: cs.summary.deliveredMismatch, action: null };
    case "REJECTED":
      return { status: "attention", text: cs.summary.rejected(provider), action: null };
    case "WRONG_RECIPIENT":
      return { status: "attention", text: cs.summary.wrongRecipient, action: null };
    case "NEEDS_INFO":
      return { status: "attention", text: cs.summary.needsInfo, action: null };
    case "HUMAN_ESCALATED":
      return { status: "attention", text: cs.summary.noAnswer, action: null };
    case "DRAFTED":
      return { status: "attention", text: cs.summary.drafted, action: "approve" };
  }
  if (item.availability === "not_in_pacs") return { status: "attention", text: cs.summary.notInPacs, action: "create" };
  if (item.availability === "not_found") return { status: "attention", text: cs.summary.notFound, action: "create" };
  return { status: "attention", text: item.note ?? cs.summary.uncertain, action: null };
}

/** Compact coordinator view: one row per required comparison study, three states, one main action. */
export default function StudyStatusList({
  caseId,
  items,
  checkStatus,
  openIssueCount,
  showDemo,
  requestsAvailable,
  onShowRequest,
  onShowDetails,
}: {
  caseId: string;
  items: RequiredItem[];
  checkStatus?: string;
  openIssueCount: number;
  showDemo: boolean;
  requestsAvailable: boolean;
  onShowRequest: (requestId: string) => void;
  onShowDetails: () => void;
}) {
  const rows = items
    .map((item) => ({ item, ...studyStatus(item) }))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || (b.item.target_date ?? "").localeCompare(a.item.target_date ?? ""));

  let body;
  if (checkStatus === "pending" || checkStatus === "running") body = <p className="p-3 text-nis-muted">{cs.summary.checking}</p>;
  else if (checkStatus === "failed") body = <p className="p-3 text-nis-red">{cs.summary.failed}</p>;
  else if (rows.length === 0) body = <p className="p-3 text-nis-muted">{cs.summary.empty}</p>;
  else
    body = (
      <ul className="divide-y divide-nis-line">
        {rows.map((r) => (
          <StudyRow
            key={r.item.id}
            caseId={caseId}
            {...r}
            showDemo={showDemo}
            requestsAvailable={requestsAvailable}
            onShowRequest={onShowRequest}
          />
        ))}
      </ul>
    );

  return (
    <Panel id="studies" icon="scan" title={cs.summary.studiesTitle} bodyClassName="">
      {body}
      {openIssueCount > 0 && (
        <button
          type="button"
          onClick={onShowDetails}
          className="block w-full border-t border-nis-line px-3 py-2 text-left text-sm text-accent-700 hover:bg-accent-50"
        >
          {cs.summary.openIssues(openIssueCount)}
        </button>
      )}
    </Panel>
  );
}

function StudyRow({
  caseId,
  item,
  status,
  text,
  action,
  showDemo,
  requestsAvailable,
  onShowRequest,
}: {
  caseId: string;
  item: RequiredItem;
  status: StudyStatus;
  text: string;
  action: PrimaryAction;
  showDemo: boolean;
  requestsAvailable: boolean;
  onShowRequest: (requestId: string) => void;
}) {
  const [dialog, setDialog] = useState<"approve" | "confirm" | null>(null);
  const [demo, setDemo] = useState(false);
  const [coordinator, setName] = useState(getCoordinator());
  const req = item.request;

  const create = useAction(() => requestsApi.createDrafts(caseId));
  const approve = useAction(() => requestsApi.approve(req!.id, coordinator.trim()));
  const confirm = useAction(() => requestsApi.confirm(caseId, item.id, coordinator.trim()));
  const active = dialog === "confirm" ? confirm : approve;
  const named = coordinator.trim().length >= 2;
  const close = () => {
    setDialog(null);
    active.reset();
  };

  return (
    <li className="px-3 py-2.5" data-study-status={status}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <div className="w-24 shrink-0 text-xl font-bold text-nis-text">{modalityLabel(item.modality)}</div>
        <div className="min-w-[10rem] flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Tag tone={TONE[status]} icon={ICON[status]}>
              {cs.summary.status[status]}
            </Tag>
            <span className="text-nis-text">{text}</span>
          </div>
          <div className="mt-0.5 text-sm text-nis-muted">
            {regionsText(item.regions)} · {formatItemDate(item.target_date, item.target_date_precision)}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {action === "approve" && requestsAvailable && (
            <Button variant="primary" icon="check" onClick={() => setDialog("approve")}>
              {cs.actions.approve}
            </Button>
          )}
          {action === "confirm" && (
            <Button variant="primary" icon="check" onClick={() => setDialog("confirm")}>
              {cs.summary.confirm}
            </Button>
          )}
          {action === "create" && requestsAvailable && (
            <Button icon="plus" disabled={create.isPending} onClick={() => create.mutate(undefined)}>
              {create.isPending ? cs.actions.working : cs.actions.createRequests}
            </Button>
          )}
          {req && (
            <Button variant="ghost" icon="document" onClick={() => onShowRequest(req.id)}>
              {cs.summary.detail}
            </Button>
          )}
          {showDemo && status !== "ready" && (
            <Button variant="ghost" icon="pulse" className="demo-only" aria-expanded={demo} onClick={() => setDemo((d) => !d)}>
              {cs.summary.simulation}
            </Button>
          )}
        </div>
      </div>
      {create.isError && <p role="alert" className="mt-1 text-sm text-nis-red">{create.error.message}</p>}
      {showDemo && demo && status !== "ready" && (
        <div className="demo-only mt-2 border-t border-dashed border-nis-line pt-2">
          <ItemActions caseId={caseId} item={item} requestsAvailable={requestsAvailable} onShowRequest={onShowRequest} />
        </div>
      )}

      {dialog && (
        <ActionDialog
          title={dialog === "confirm" ? cs.summary.confirmTitle : `${cs.actions.approveTitle} ${req?.id ?? ""}`}
          hint={dialog === "confirm" ? cs.summary.confirmHint : cs.actions.approveHint}
          simulated
          submitLabel={dialog === "confirm" ? cs.summary.confirm : cs.actions.approve}
          canSubmit={named}
          busy={active.isPending}
          error={active.error?.message}
          onClose={close}
          onSubmit={() => {
            setCoordinator(coordinator);
            active.mutate(undefined, { onSuccess: () => setDialog(null) });
          }}
        >
          <CoordinatorField value={coordinator} onChange={setName} />
        </ActionDialog>
      )}
    </li>
  );
}
