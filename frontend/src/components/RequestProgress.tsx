import { cs } from "../i18n/cs";
import type { RequestRef, RequestState } from "../services/api-types";
import { formatDateTime } from "./format";
import { REQUEST_TONE, StatusTag } from "./ui";

// Maps every state onto the 7 visible steps; side exits have no progress.
const STEP_INDEX: Record<RequestState, number | null> = {
  DETECTED: 0,
  DRAFTED: 1,
  APPROVED: 2,
  SENT: 3,
  REMINDER_SENT: 3,
  VOICE_ESCALATED: 3,
  HUMAN_ESCALATED: 3,
  ACKNOWLEDGED: 4,
  RECEIVED: 5,
  VERIFIED: 6,
  CLOSED: 6,
  REJECTED: null,
  NEEDS_INFO: null,
  WRONG_RECIPIENT: null,
  CANCELLED: null,
};

export default function RequestProgress({ request }: { request: RequestRef | null }) {
  if (!request) {
    return <span className="text-nis-muted">{cs.items.noRequest}</span>;
  }
  const step = STEP_INDEX[request.state];
  const total = cs.requestSteps.length;

  return (
    <div className="space-y-1">
      <StatusTag tone={REQUEST_TONE[request.state]}>{cs.requestState[request.state]}</StatusTag>
      <div className="text-xs text-nis-muted">
        {request.id} · {formatDateTime(request.updated_at)}
      </div>
      {request.approved_by && (
        <div className="text-xs text-nis-muted">
          {cs.requestDrawer.approvedBy}: {request.approved_by}
        </div>
      )}
      {step !== null && (
        <ol className="flex gap-0.5" aria-label={`${step + 1} / ${total}`}>
          {cs.requestSteps.map((name, i) => (
            <li
              key={name}
              title={name}
              className={`h-1.5 w-5 rounded-sm ${i <= step ? "bg-accent-600" : "bg-nis-line"}`}
            >
              <span className="sr-only">{name}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
