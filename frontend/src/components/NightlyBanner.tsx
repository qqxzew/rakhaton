import { useState } from "react";
import { cs } from "../i18n/cs";
import {
  getCoordinator,
  requestsApi,
  setCoordinator,
  useAction,
  useAutopilot,
  useDemoSummary,
} from "../services/requestsApi";
import ActionDialog, { CoordinatorField } from "./ActionDialog";
import SimulaceTag from "./SimulaceTag";
import { Button, Icon } from "./ui";

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso}Z`); // the server stores UTC without a zone marker
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("cs-CZ", { dateStyle: "short", timeStyle: "short" });
}

/** Standing approval policy: whoever switches it on is the approval record. Stays visible in presentation mode. */
function AutopilotPanel() {
  const state = useAutopilot();
  const [name, setName] = useState(getCoordinator());
  const [message, setMessage] = useState<string | null>(null);
  const t = cs.autopilot;
  const toggle = useAction((enabled: boolean) => requestsApi.setAutopilot(enabled, name.trim()));

  const enabled = state.data?.enabled === true;
  const needName = !enabled && name.trim().length < 2;

  return (
    <section className="nis-panel flex flex-wrap items-center gap-3 px-3 py-2.5" aria-label={t.title} data-testid="autopilot-panel">
      <Icon name="pulse" className={enabled ? "text-accent-600" : "text-nis-muted"} />
      <div className="min-w-[16rem] flex-1">
        <div className="flex flex-wrap items-center gap-2 font-bold" role="status">
          {enabled ? t.on(state.data?.actor ?? "", formatWhen(state.data?.changed_at ?? null)) : t.off} <SimulaceTag />
        </div>
        <div className="text-sm text-nis-muted">{t.hint}</div>
        {message && <div className="text-sm text-nis-ink" role="status">{message}</div>}
        {toggle.error && (
          <div role="alert" className="text-sm text-nis-red">
            {cs.common.error}: {toggle.error.message}
          </div>
        )}
      </div>
      {!enabled && (
        <label className="block">
          <span className="nis-label block">{t.name}</span>
          <input
            className="nis-input mt-1 w-56"
            value={name}
            minLength={2}
            placeholder={cs.actions.coordinatorPlaceholder}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={t.toggle}
        title={needName ? t.needName : undefined}
        disabled={toggle.isPending || state.isLoading || needName}
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-bold disabled:opacity-50 ${
          enabled ? "border-accent-600 bg-accent-600 text-white" : "border-nis-line bg-white text-nis-ink"
        }`}
        onClick={() => {
          if (!enabled) setCoordinator(name);
          toggle.mutate(!enabled, {
            onSuccess: (r) => setMessage(enabled ? t.disabled : t.enabled(r.auto_approved ?? 0)),
          });
        }}
      >
        <span className={`h-2.5 w-2.5 rounded-full ${enabled ? "bg-white" : "bg-nis-muted"}`} aria-hidden />
        {t.toggle}: {enabled ? t.stateOn : t.stateOff}
      </button>
    </section>
  );
}

/** "Noční běh" banner: drafts prepared by the nightly job wait here for one approval click.
 * Hidden in presentation mode (demo-only). */
export default function NightlyBanner() {
  return (
    <>
      <AutopilotPanel />
      <NightlyControls />
    </>
  );
}

function NightlyControls() {
  const summary = useDemoSummary();
  const [approving, setApproving] = useState(false);
  const [coordinator, setName] = useState(getCoordinator());
  const [message, setMessage] = useState<string | null>(null);
  const t = cs.nightly;

  const nightly = useAction(() => requestsApi.nightly());
  const advance = useAction(() => requestsApi.advance(24));
  const approveAll = useAction(() => requestsApi.approveAll(coordinator.trim(), summary.data?.case_ids ?? []));

  const pending = summary.data?.drafts_pending ?? 0;
  const available = summary.data?.available !== false;
  const caseIds = summary.data?.case_ids ?? [];

  return (
    <section className="demo-only nis-panel flex flex-wrap items-center gap-3 px-3 py-2.5" aria-label={t.banner(pending)} data-testid="nightly-banner">
      <Icon name="pulse" className="text-accent-600" />
      <div className="min-w-[16rem] flex-1">
        <div className="flex flex-wrap items-center gap-2 font-bold">
          {available ? t.banner(pending) : t.unavailable} <SimulaceTag />
        </div>
        <div className="text-sm text-nis-muted">{t.hint}</div>
        {message && (
          <div className="text-sm text-nis-ink" role="status">
            {message}
          </div>
        )}
        {(nightly.error || advance.error || approveAll.error) && (
          <div role="alert" className="text-sm text-nis-red">
            {cs.common.error}: {(nightly.error || advance.error || approveAll.error)?.message}
          </div>
        )}
      </div>
      <Button
        variant="primary"
        icon="check"
        disabled={!available || pending === 0 || caseIds.length === 0 || approveAll.isPending}
        onClick={() => setApproving(true)}
      >
        {t.approveAll} {pending > 0 ? `(${pending})` : ""}
      </Button>
      <Button
        icon="refresh"
        disabled={nightly.isPending}
        onClick={() =>
          nightly.mutate(undefined, {
            onSuccess: (r) =>
              setMessage(
                t.result(r.cases_checked, r.drafts_created) +
                  (r.autopilot ? ` ${cs.autopilot.autoApproved(r.auto_approved ?? 0)}` : ""),
              ),
          })
        }
      >
        {nightly.isPending ? t.running : t.run}
      </Button>
      <Button
        icon="calendar"
        disabled={!available || advance.isPending}
        onClick={() =>
          advance.mutate(undefined, {
            onSuccess: (r) => setMessage(t.advanced(r.ticked?.length ?? 0)),
          })
        }
      >
        {advance.isPending ? t.advancing : t.advance}
      </Button>
      {approving && (
        <ActionDialog
          title={`${t.approveAll} (${pending})`}
          hint={cs.actions.approveHint}
          simulated
          submitLabel={t.approveAll}
          canSubmit={coordinator.trim().length >= 2}
          busy={approveAll.isPending}
          error={approveAll.error?.message}
          onClose={() => setApproving(false)}
          onSubmit={() => {
            setCoordinator(coordinator);
            approveAll.mutate(undefined, {
              onSuccess: (r) => {
                setApproving(false);
                setMessage(t.approved(r.approved));
              },
            });
          }}
        >
          <CoordinatorField value={coordinator} onChange={setName} />
        </ActionDialog>
      )}
    </section>
  );
}
