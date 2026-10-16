import { cs } from "../i18n/cs";
import type { RequestRef, RequestState } from "../services/api-types";
import { formatDateTime } from "./format";

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
    return <span className="text-slate-600">{cs.items.noRequest}</span>;
  }
  const step = STEP_INDEX[request.state];
  const total = cs.requestSteps.length;

  return (
    <div>
      <div className="font-semibold">{cs.requestState[request.state]}</div>
      <div className="text-xs text-slate-600">
        {request.id} · {formatDateTime(request.updated_at)}
      </div>
      {step !== null && (
        <ol className="mt-1 flex gap-1" aria-label={`${step + 1} / ${total}`}>
          {cs.requestSteps.map((name, i) => (
            <li
              key={name}
              title={name}
              className={`h-2 w-6 rounded-sm ${
                i < step ? "bg-accent-600" : i === step ? "bg-accent-600 ring-2 ring-accent-500 ring-offset-1" : "bg-slate-200"
              }`}
            >
              <span className="sr-only">{name}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
