import { useEffect, useRef, type FormEvent, type ReactNode } from "react";
import { cs } from "../i18n/cs";
import SimulaceTag from "./SimulaceTag";
import { Button } from "./ui";

/** Small modal form for one request action. */
export default function ActionDialog({
  title,
  hint,
  simulated = false,
  submitLabel,
  canSubmit = true,
  busy = false,
  error,
  onSubmit,
  onClose,
  children,
}: {
  title: string;
  hint?: string;
  simulated?: boolean;
  submitLabel?: string;
  canSubmit?: boolean;
  busy?: boolean;
  error?: string | null;
  onSubmit?: () => void;
  onClose: () => void;
  children?: ReactNode;
}) {
  const ref = useRef<HTMLFormElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("input, textarea, select, button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canSubmit && !busy) onSubmit?.();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="action-title">
      <div className="absolute inset-0 bg-nis-text/30" onClick={onClose} aria-hidden="true" />
      <form ref={ref} onSubmit={submit} className="nis-panel relative w-full max-w-lg bg-white shadow-lg">
        <div className="flex items-center gap-2 border-b border-nis-line px-4 py-2.5">
          <h2 id="action-title" className="text-lg font-bold">
            {title}
          </h2>
          {simulated && <SimulaceTag />}
        </div>
        <div className="space-y-3 p-4">
          {hint && <p className="text-sm text-nis-muted">{hint}</p>}
          {children}
          {error && (
            <p role="alert" className="nis-row-danger rounded-nis px-2 py-1 text-sm">
              {cs.common.error}: {error}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-nis-line px-4 py-2.5">
          <Button onClick={onClose}>{cs.common.cancel}</Button>
          {onSubmit && (
            <Button type="submit" variant="primary" disabled={!canSubmit || busy}>
              {busy ? cs.actions.working : submitLabel ?? cs.actions.confirm}
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

/** Text field for the coordinator name; remembered in localStorage by the caller. */
export function CoordinatorField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="nis-label block">{cs.actions.coordinator}</span>
      <input
        className="nis-input mt-1 w-full"
        value={value}
        required
        minLength={2}
        placeholder={cs.actions.coordinatorPlaceholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
