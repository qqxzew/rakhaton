import type { ReactNode } from "react";
import Icon, { type IconName } from "./Icon";

/** Page header: blue circle icon + UPPERCASE bold title, controls on the right. */
export function SectionHeader({
  icon,
  title,
  subtitle,
  children,
  as: H = "h1",
}: {
  icon: IconName;
  title: ReactNode;
  subtitle?: ReactNode;
  children?: ReactNode;
  as?: "h1" | "h2";
}) {
  return (
    <div className="flex min-h-[2.75rem] flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-600 text-white">
          <Icon name={icon} size="1.35em" />
        </span>
        <div className="min-w-0">
          <H className="text-base font-bold uppercase tracking-wide text-nis-text">{title}</H>
          {subtitle && <div className="text-sm text-nis-muted">{subtitle}</div>}
        </div>
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

/** "‹ › label" date navigation; pass undefined handlers to disable an arrow. */
export function DateNav({
  label,
  onPrev,
  onNext,
  prevLabel,
  nextLabel,
}: {
  label: ReactNode;
  onPrev?: () => void;
  onNext?: () => void;
  prevLabel: string;
  nextLabel: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <button type="button" className="nis-btn-icon" onClick={onPrev} disabled={!onPrev} aria-label={prevLabel} title={prevLabel}>
        <Icon name="chevronLeft" size="1.35em" />
      </button>
      <button type="button" className="nis-btn-icon" onClick={onNext} disabled={!onNext} aria-label={nextLabel} title={nextLabel}>
        <Icon name="chevronRight" size="1.35em" />
      </button>
      <span className="ml-1 text-lg text-nis-text">{label}</span>
    </div>
  );
}

/** Vertical separator between header control groups. */
export function HeaderDivider() {
  return <span className="mx-1 h-6 w-px bg-nis-line" aria-hidden="true" />;
}
