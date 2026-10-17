import type { ReactNode } from "react";
import Icon, { type IconName } from "./Icon";

export interface PillTab<T extends string> {
  id: T;
  label: string;
  count?: number;
  icon?: IconName;
}

/** Blue rounded pills used as view switches or filters ("Ambulancie / Hospitalizácie / …"). */
export function PillTabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: PillTab<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(t.id)}
            className={`inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-base font-medium transition-colors ${
              active
                ? "bg-accent-600 text-white"
                : "border border-accent-100 bg-accent-50 text-accent-700 hover:border-accent-600"
            }`}
          >
            {t.icon && <Icon name={t.icon} size="1.15em" />}
            {t.label}
            {t.count !== undefined && (
              <span
                className={`min-w-[1.4rem] rounded-full px-1.5 text-xs font-bold leading-5 ${
                  active ? "bg-white text-accent-700" : "bg-accent-600 text-white"
                }`}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Read-only counter chip (summary tiles): icon + label + count bubble. */
export function StatChip({
  icon,
  iconClass = "text-accent-600",
  label,
  value,
  children,
}: {
  icon: IconName;
  iconClass?: string;
  label: string;
  value: number | string;
  children?: ReactNode;
}) {
  return (
    <div className="inline-flex h-9 items-center gap-2 rounded-full border border-nis-line bg-white pl-3 pr-1.5">
      <Icon name={icon} className={iconClass} />
      <span className="text-base text-nis-text">{label}</span>
      {children}
      <span className="min-w-[1.6rem] rounded-full bg-nis-slate px-2 text-center text-sm font-bold leading-6 text-white">
        {value}
      </span>
    </div>
  );
}
