import { useState } from "react";
import { cs } from "../i18n/cs";
import type { RequiredItem } from "../services/api-types";
import { getCoordinator, requestsApi, setCoordinator, useAction } from "../services/requestsApi";
import ActionDialog, { CoordinatorField } from "./ActionDialog";
import SimulaceTag from "./SimulaceTag";
import { Button } from "./ui";

type Dialog = "approve" | "waive" | "reply" | "call" | "delivery" | null;

const OPEN_STATES = new Set(["SENT", "REMINDER_SENT", "VOICE_ESCALATED", "HUMAN_ESCALATED", "ACKNOWLEDGED", "NEEDS_INFO"]);
const DELIVERABLE = new Set([...OPEN_STATES, "RECEIVED"]);
const OTHER_MODALITY: Record<string, string> = { CT: "MR", MR: "CT", PET: "CT" };

/** Per-item request actions; hidden in presentation mode by the caller. Simulated steps carry the tag. */
export default function ItemActions({
  caseId,
  item,
  requestsAvailable,
  onShowRequest,
}: {
  caseId: string;
  item: RequiredItem;
  requestsAvailable: boolean;
  onShowRequest: (requestId: string) => void;
}) {
  const [dialog, setDialog] = useState<Dialog>(null);
  const [coordinator, setName] = useState(getCoordinator());
  const [reason, setReason] = useState("");
  const [reply, setReply] = useState<string>(cs.actions.replyPresets[0]);
  const [outcome, setOutcome] = useState("accepted");
  const [wrong, setWrong] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const req = item.request;
  const state = req?.state;
  const done = (r: { requestId?: string; state?: string } | undefined) => {
    setDialog(null);
    if (r?.requestId && r.state) setMessage(cs.actions.done(r.requestId, cs.requestState[r.state as keyof typeof cs.requestState] ?? r.state));
  };

  const create = useAction(() => requestsApi.createDrafts(caseId));
  const approve = useAction(() => requestsApi.approve(req!.id, coordinator.trim()));
  const waive = useAction(() => requestsApi.waive(item.id, caseId, reason.trim(), coordinator.trim()));
  const sendReply = useAction(() => requestsApi.reply(req!.id, reply.trim()));
  const call = useAction(() => requestsApi.call(req!.id, outcome));
  const deliver = useAction(() =>
    requestsApi.delivery(req!.id, wrong ? { modality: OTHER_MODALITY[item.modality] ?? "RTG" } : {}),
  );
  const active = { approve, waive, reply: sendReply, call, delivery: deliver }[dialog ?? "approve"];
  const close = () => {
    setDialog(null);
    active.reset();
  };

  const named = coordinator.trim().length >= 2;
  const remember = () => setCoordinator(coordinator);

  if (item.waiver) {
    return null;
  }

  const missing = item.state === "missing" || item.availability === "not_found" || item.availability === "not_in_pacs";
  const canCreate = requestsAvailable && missing && item.state !== "ok" && (!req || state === "CANCELLED");

  return (
    <div className="flex min-w-[11rem] flex-col items-start gap-1">
      <div className="flex flex-wrap gap-1">
        {canCreate && (
          <Button icon="plus" className="!px-2 !py-0.5 text-sm" disabled={create.isPending} onClick={() => create.mutate(undefined)}>
            {create.isPending ? cs.actions.working : cs.actions.createRequests}
          </Button>
        )}
        {state === "DRAFTED" && (
          <Button variant="primary" icon="check" className="!px-2 !py-0.5 text-sm" onClick={() => setDialog("approve")}>
            {cs.actions.approve}
          </Button>
        )}
        {state && OPEN_STATES.has(state) && (
          <Button icon="mail" className="!px-2 !py-0.5 text-sm" onClick={() => setDialog("reply")}>
            {cs.actions.reply}
          </Button>
        )}
        {state === "VOICE_ESCALATED" && (
          <Button icon="phone" className="!px-2 !py-0.5 text-sm" onClick={() => setDialog("call")}>
            {cs.actions.call}
          </Button>
        )}
        {state && DELIVERABLE.has(state) && (
          <Button icon="inbox" className="!px-2 !py-0.5 text-sm" onClick={() => setDialog("delivery")}>
            {cs.actions.delivery}
          </Button>
        )}
        {item.state !== "ok" && (
          <Button variant="ghost" icon="flag" className="!px-2 !py-0.5 text-sm" onClick={() => setDialog("waive")}>
            {cs.actions.waive}
          </Button>
        )}
        {req && (
          <Button variant="ghost" icon="document" className="!px-2 !py-0.5 text-sm" onClick={() => onShowRequest(req.id)}>
            {cs.actions.show}
          </Button>
        )}
      </div>
      {(state && (OPEN_STATES.has(state) || DELIVERABLE.has(state))) || canCreate ? <SimulaceTag /> : null}
      {create.isError && <span role="alert" className="text-xs text-nis-red">{create.error.message}</span>}
      {message && <span className="text-xs text-nis-muted" role="status">{message}</span>}

      {dialog === "approve" && (
        <ActionDialog
          title={`${cs.actions.approveTitle} ${req?.id ?? ""}`}
          hint={cs.actions.approveHint}
          simulated
          submitLabel={cs.actions.approve}
          canSubmit={named}
          busy={approve.isPending}
          error={approve.error?.message}
          onClose={close}
          onSubmit={() => {
            remember();
            approve.mutate(undefined, { onSuccess: done });
          }}
        >
          <CoordinatorField value={coordinator} onChange={setName} />
        </ActionDialog>
      )}
      {dialog === "waive" && (
        <ActionDialog
          title={cs.actions.waiveTitle}
          hint={cs.actions.waiveHint}
          submitLabel={cs.actions.waive}
          canSubmit={named && reason.trim().length >= 3}
          busy={waive.isPending}
          error={waive.error?.message}
          onClose={close}
          onSubmit={() => {
            remember();
            waive.mutate(undefined, { onSuccess: () => setDialog(null) });
          }}
        >
          <CoordinatorField value={coordinator} onChange={setName} />
          <label className="block">
            <span className="nis-label block">{cs.actions.waiveReason}</span>
            <textarea
              className="nis-input mt-1 h-20 w-full"
              required
              minLength={3}
              value={reason}
              placeholder={cs.actions.waiveReasonPlaceholder}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
        </ActionDialog>
      )}
      {dialog === "reply" && (
        <ActionDialog
          title={`${cs.actions.replyTitle} – ${req?.id ?? ""}`}
          hint={cs.actions.replyHint}
          simulated
          submitLabel={cs.actions.send}
          canSubmit={reply.trim().length > 0}
          busy={sendReply.isPending}
          error={sendReply.error?.message}
          onClose={close}
          onSubmit={() => sendReply.mutate(undefined, { onSuccess: done })}
        >
          <div className="flex flex-wrap gap-1">
            {cs.actions.replyPresets.map((p) => (
              <Button key={p} variant={reply === p ? "primary" : "secondary"} className="!px-2 !py-0.5 text-sm" onClick={() => setReply(p)}>
                {p}
              </Button>
            ))}
          </div>
          <label className="block">
            <span className="nis-label block">{cs.actions.replyFree}</span>
            <textarea className="nis-input mt-1 h-20 w-full" value={reply} onChange={(e) => setReply(e.target.value)} />
          </label>
        </ActionDialog>
      )}
      {dialog === "call" && (
        <ActionDialog
          title={cs.actions.callTitle}
          hint={cs.actions.callHint}
          simulated
          canSubmit
          busy={call.isPending}
          error={call.error?.message}
          onClose={close}
          onSubmit={() => call.mutate(undefined, { onSuccess: done })}
        >
          <fieldset className="space-y-1">
            {Object.entries(cs.actions.callOutcomes).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2">
                <input type="radio" name="outcome" value={k} checked={outcome === k} onChange={() => setOutcome(k)} />
                {label}
              </label>
            ))}
          </fieldset>
        </ActionDialog>
      )}
      {dialog === "delivery" && (
        <ActionDialog
          title={cs.actions.deliveryTitle}
          hint={cs.actions.deliveryHint}
          simulated
          canSubmit
          busy={deliver.isPending}
          error={deliver.error?.message}
          onClose={close}
          onSubmit={() => deliver.mutate(undefined, { onSuccess: done })}
        >
          <fieldset className="space-y-1">
            <label className="flex items-center gap-2">
              <input type="radio" name="delivery" checked={!wrong} onChange={() => setWrong(false)} />
              {cs.actions.deliveryCorrect}
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="delivery" checked={wrong} onChange={() => setWrong(true)} />
              {cs.actions.deliveryWrong}
            </label>
          </fieldset>
        </ActionDialog>
      )}
    </div>
  );
}
