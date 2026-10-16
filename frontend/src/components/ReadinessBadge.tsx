import { cs } from "../i18n/cs";
import type { ReadinessState } from "../services/api-types";

const STYLE: Record<ReadinessState, string> = {
  ready: "border-green-600 bg-green-50 text-green-900",
  attention: "border-amber-600 bg-amber-50 text-amber-900",
  not_ready: "border-red-600 bg-red-50 text-red-900",
};

export function ReadinessIcon({ state }: { state: ReadinessState }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (state === "ready") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="10" />
        <path d="M7.5 12.5l3 3 6-6.5" />
      </svg>
    );
  }
  if (state === "attention") {
    return (
      <svg {...common}>
        <path d="M12 3L22 20H2L12 3z" />
        <path d="M12 10v4.5M12 17.2v.1" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="10" />
      <path d="M8.5 8.5l7 7M15.5 8.5l-7 7" />
    </svg>
  );
}

/** Icon + label + reason; state is never conveyed by color alone. */
export default function ReadinessBadge({
  state,
  reason,
}: {
  state: ReadinessState;
  reason: string;
}) {
  return (
    <div
      className={`inline-flex items-center gap-2 rounded-lg border-2 px-3 py-1.5 ${STYLE[state]}`}
      data-readiness={state}
    >
      <ReadinessIcon state={state} />
      <span className="font-bold">{cs.readiness[state]}</span>
      <span aria-hidden="true">–</span>
      <span>{reason}</span>
    </div>
  );
}
