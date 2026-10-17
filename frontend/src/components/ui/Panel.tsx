import type { ReactNode } from "react";
import Icon, { type IconName } from "./Icon";

/** White panel with a thin border. With `title` it gets a header row (title left, actions right). */
export function Panel({
  id,
  title,
  icon,
  actions,
  className = "",
  bodyClassName = "p-3",
  children,
}: {
  id?: string;
  title?: ReactNode;
  icon?: IconName;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  const titleId = id ? `${id}-title` : undefined;
  return (
    <section id={id} className={`nis-panel ${className}`} aria-labelledby={title ? titleId : undefined}>
      {title && (
        <div className="flex min-h-[2.75rem] flex-wrap items-center justify-between gap-2 border-b border-nis-line px-3 py-1.5">
          <h2 id={titleId} className="flex items-center gap-2 text-lg font-bold text-nis-text">
            {icon && <Icon name={icon} className="text-accent-600" />}
            {title}
          </h2>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/** 11 px bold uppercase gray label ("IČP", "ODBORNOSŤ"). */
export function FieldLabel({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return htmlFor ? (
    <label htmlFor={htmlFor} className="nis-label block">
      {children}
    </label>
  ) : (
    <div className="nis-label">{children}</div>
  );
}

/** Label above value, as in the NIS account detail. */
export function Field({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <FieldLabel>{label}</FieldLabel>
      <div className="mt-0.5 text-base text-nis-text">{children}</div>
    </div>
  );
}

/** Scroll wrapper + dense table (`nis-table`). Rows can add `nis-row-*` classes. */
export function DataTable({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="nis-table">{children}</table>
    </div>
  );
}

/** Loading / empty / error text inside panels. */
export function Muted({ children }: { children: ReactNode }) {
  return <p className="text-base text-nis-muted">{children}</p>;
}

/** Full-page error with a retry button. */
export function ErrorState({
  message,
  retryLabel,
  onRetry,
}: {
  message: ReactNode;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className="nis-panel nis-row-danger flex flex-wrap items-center gap-3 px-3 py-2.5">
      <Icon name="crossCircle" className="text-nis-red" />
      <span className="text-nis-text">{message}</span>
      <button type="button" onClick={onRetry} className="nis-btn-secondary ml-auto">
        {retryLabel}
      </button>
    </div>
  );
}
