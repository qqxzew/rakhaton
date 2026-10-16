import { cs } from "../i18n/cs";
import type { ReadinessCounts, ReadinessState } from "../services/api-types";
import { ReadinessIcon } from "./ReadinessBadge";

const TEXT: Record<ReadinessState, string> = {
  ready: "text-green-900",
  attention: "text-amber-900",
  not_ready: "text-red-900",
};

/** Icon + label (+ optional reason) on one line; state is never conveyed by color alone. */
export function ReadinessLabel({ state, reason }: { state: ReadinessState; reason?: string | null }) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${TEXT[state]}`} data-readiness={state}>
      <ReadinessIcon state={state} />
      <span className="font-semibold">{cs.readiness[state]}</span>
      {reason ? (
        <>
          <span aria-hidden="true">–</span>
          <span>{reason}</span>
        </>
      ) : null}
    </span>
  );
}

const ORDER: ReadinessState[] = ["not_ready", "attention", "ready"];

/** "Nepřipraveno 2 · Vyžaduje pozornost 1" – only non-zero states. */
export function CountsText({ counts }: { counts: ReadinessCounts }) {
  const parts = ORDER.filter((s) => counts[s] > 0).map((s) => `${cs.readiness[s]} ${counts[s]}`);
  return <span>{parts.length ? parts.join(" · ") : cs.common.none}</span>;
}
