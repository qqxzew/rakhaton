import { cs } from "../i18n/cs";
import type { ReadinessState } from "../services/api-types";
import { Icon, READINESS_ICON, READINESS_TONE, Tag } from "./ui";

export function ReadinessIcon({ state, size }: { state: ReadinessState; size?: number | string }) {
  return <Icon name={READINESS_ICON[state]} size={size} strokeWidth={2.2} />;
}

/** Solid status tag: icon + label (never color alone). */
export function ReadinessTag({ state }: { state: ReadinessState }) {
  return (
    <Tag tone={READINESS_TONE[state]} icon={READINESS_ICON[state]}>
      {cs.readiness[state]}
    </Tag>
  );
}

/** Icon + label + reason; state is never conveyed by color alone. */
export default function ReadinessBadge({ state, reason }: { state: ReadinessState; reason: string }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-readiness={state}>
      <ReadinessTag state={state} />
      <span className="text-base text-nis-text">{reason}</span>
    </span>
  );
}
