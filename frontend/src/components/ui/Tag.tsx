import type { ReactNode } from "react";
import type { ItemState, ReadinessState, RequestState } from "../../services/api-types";
import Icon, { type IconName } from "./Icon";

export type TagTone = "slate" | "blue" | "teal" | "green" | "amber" | "red" | "gray" | "outline";

const TONE: Record<TagTone, string> = {
  slate: "bg-nis-slate text-white",
  blue: "bg-accent-600 text-white",
  teal: "bg-nis-teal text-white",
  green: "bg-nis-green text-white",
  amber: "bg-nis-amber text-nis-text",
  red: "bg-nis-red text-white",
  gray: "bg-[#e3e8ef] text-nis-ink",
  outline: "border border-nis-line bg-white text-nis-ink",
};

/** Small solid NIS tag ("Ukončená", "Schválená"); also used as a field label in record headers. */
export function Tag({
  tone = "slate",
  icon,
  upper = false,
  title,
  className = "",
  children,
}: {
  tone?: TagTone;
  icon?: IconName;
  upper?: boolean;
  title?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-[3px] px-1.5 py-px text-xs font-bold leading-[1.35rem] ${
        upper ? "uppercase tracking-wide" : ""
      } ${TONE[tone]} ${className}`}
    >
      {icon && <Icon name={icon} size="1.15em" strokeWidth={2.4} />}
      {children}
    </span>
  );
}

/** Status tag placed at the right end of a row; same as Tag but never uppercase. */
export function StatusTag(props: { tone: TagTone; icon?: IconName; title?: string; children: ReactNode }) {
  return <Tag {...props} />;
}

/** NIS record header pair: dark label tag followed by its value ("DG C61 …"). */
export function TagField({
  label,
  tone = "slate",
  children,
}: {
  label: string;
  tone?: TagTone;
  children: ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Tag tone={tone} upper className="text-2xs">
        {label}
      </Tag>
      <span className="text-base font-medium text-nis-text">{children}</span>
    </span>
  );
}

// ---- tone maps shared by readiness, items and requests ----

export const READINESS_TONE: Record<ReadinessState, TagTone> = {
  ready: "green",
  attention: "amber",
  not_ready: "red",
};

export const READINESS_ICON: Record<ReadinessState, IconName> = {
  ready: "checkCircle",
  attention: "warning",
  not_ready: "crossCircle",
};

/** Pastel row background by readiness (class names from index.css). */
export const READINESS_ROW: Record<ReadinessState, string> = {
  ready: "nis-row-ready",
  attention: "nis-row-attention",
  not_ready: "nis-row-danger",
};

/** Request state tag colors: gray = not sent yet, blue = in flight, teal = approved/acknowledged, green = done. */
export const REQUEST_TONE: Record<RequestState, TagTone> = {
  DETECTED: "gray",
  DRAFTED: "gray",
  APPROVED: "teal",
  SENT: "blue",
  REMINDER_SENT: "amber",
  VOICE_ESCALATED: "amber",
  HUMAN_ESCALATED: "red",
  ACKNOWLEDGED: "teal",
  RECEIVED: "blue",
  VERIFIED: "green",
  CLOSED: "slate",
  REJECTED: "red",
  NEEDS_INFO: "amber",
  WRONG_RECIPIENT: "red",
  CANCELLED: "slate",
};

export const ITEM_ROW: Record<ItemState, string> = {
  ok: "nis-row-ready",
  attention: "nis-row-attention",
  missing: "nis-row-danger",
};
