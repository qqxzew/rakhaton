import { cs } from "../i18n/cs";
import type { ReadinessCounts, ReadinessState } from "../services/api-types";
import { ReadinessIcon } from "./ReadinessBadge";

const TEXT: Record<ReadinessState, string> = {
  ready: "text-nis-green",
  attention: "text-[#9a6b00]",
  not_ready: "text-nis-red",
};

/** Icon + label (+ optional reason) on one line; state is never conveyed by color alone. */
export function ReadinessLabel({ state, reason }: { state: ReadinessState; reason?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5" data-readiness={state}>
      <span className={`inline-flex items-center gap-1 ${TEXT[state]}`}>
        <ReadinessIcon state={state} />
        <span className="font-medium">{cs.readiness[state]}</span>
      </span>
      {reason ? (
        <>
          <span aria-hidden="true" className="text-nis-muted">
            –
          </span>
          <span className="text-nis-text">{reason}</span>
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
