import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { cs } from "../i18n/cs";
import SimulaceTag from "../components/SimulaceTag";
import { formatDate, formatDayMonth, regionsText, weekdayShort } from "../components/format";
import {
  Button,
  DataTable,
  ErrorState,
  Icon,
  Muted,
  Panel,
  PillTabs,
  REQUEST_TONE,
  SectionHeader,
  StatusTag,
} from "../components/ui";
import { useApproveAll, useWorklist, type StateGroup, type Urgency, type WorklistRow } from "../services/systemApi";

const t = cs.system.worklist;
type Filter = "all" | StateGroup;
const GROUPS: StateGroup[] = ["approval", "sent", "escalated", "received", "verified"];

const ROW: Record<Urgency, string> = {
  danger: "nis-row-danger",
  attention: "nis-row-attention",
  ready: "nis-row-ready",
  info: "nis-row-info",
  normal: "",
};

/** "2026-10-25 06:36:31" -> "25. 10. 2026 06:36" */
function eventTime(value: string | null): string {
  if (!value) return cs.common.none;
  const m = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/.exec(value);
  return m ? `${formatDate(m[1])} ${m[2]}` : formatDate(value);
}

function studyDate(iso: string | null): string {
  if (!iso) return cs.common.none;
  const month = /^(\d{4})-(\d{2})$/.exec(iso);
  return month ? `${month[2]}/${month[1]}` : formatDate(iso);
}

export default function Worklist() {
  const { data, isLoading, error, refetch } = useWorklist();
  const [filter, setFilter] = useState<Filter>("all");
  const [coordinator, setCoordinator] = useState("");
  const approve = useApproveAll();
  const rows = useMemo(() => data?.requests ?? [], [data]);
  const shown = filter === "all" ? rows : rows.filter((r) => r.state_group === filter);
  const drafts = rows.filter((r) => r.state === "DRAFTED").length;

  if (isLoading) return <p className="nis-panel p-4 text-nis-muted">{cs.app.loading}</p>;
  if (error || !data) {
    return (
      <ErrorState
        message={`${cs.common.error}: ${error?.message ?? ""}`}
        retryLabel={cs.common.retry}
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="space-y-3">
      <SectionHeader icon="inbox" title={t.title} subtitle={t.subtitle}>
        <SimulaceTag />
      </SectionHeader>

      {!data.available && (
        <p role="alert" className="nis-panel nis-row-danger px-3 py-2.5">
          {cs.system.unavailable}: {data.reason}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <PillTabs<Filter>
          label={t.filterLabel}
          value={filter}
          onChange={setFilter}
          tabs={[
            { id: "all", label: t.all, count: rows.length },
            ...GROUPS.map((g) => ({ id: g, label: t.groups[g], count: data.counts?.[g] ?? 0 })),
            ...(data.counts?.closed ? [{ id: "closed" as const, label: t.groups.closed, count: data.counts.closed }] : []),
          ]}
        />
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (coordinator.trim() && drafts > 0) approve.mutate(coordinator.trim());
          }}
        >
          <label htmlFor="wl-coordinator" className="sr-only">
            {t.coordinator}
          </label>
          <input
            id="wl-coordinator"
            className="nis-input w-48"
            placeholder={t.coordinatorPlaceholder}
            value={coordinator}
            onChange={(e) => setCoordinator(e.target.value)}
          />
          <Button
            type="submit"
            variant="primary"
            icon="check"
            title={t.approveHint}
            disabled={!coordinator.trim() || drafts === 0 || approve.isPending}
          >
            {approve.isPending ? t.approving : t.approveAll(drafts)}
          </Button>
        </form>
      </div>

      {approve.isSuccess && (
        <p role="status" className="nis-panel nis-row-ready px-3 py-2">
          {t.approved(approve.data.approved)}
        </p>
      )}
      {approve.isError && (
        <p role="alert" className="nis-panel nis-row-danger px-3 py-2">
          {cs.common.error}: {approve.error.message}
        </p>
      )}

      <Panel
        bodyClassName=""
        title={
          <>
            {t.title}
            <span className="text-base font-normal text-nis-muted">({shown.length})</span>
          </>
        }
        icon="list"
        actions={
          <span className="flex items-center gap-2 text-sm text-nis-muted">
            <Icon name="chart" />
            {data.ml_available === false ? t.mlUnavailable : t.mlNote}
            <SimulaceTag />
          </span>
        }
      >
        {rows.length === 0 || shown.length === 0 ? (
          <div className="p-3">
            <Muted>{rows.length === 0 ? t.empty : t.emptyFilter}</Muted>
          </div>
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>{t.request}</th>
                <th>{t.patient}</th>
                <th>{t.mdt}</th>
                <th>{t.daysToMdt}</th>
                <th>{t.study}</th>
                <th>{t.hospital}</th>
                <th>{t.state}</th>
                <th>{t.updated}</th>
                <th className="text-right">{t.late}</th>
                <th className="text-right">{t.expected}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <Row key={r.request_id} r={r} />
              ))}
            </tbody>
          </DataTable>
        )}
      </Panel>
    </div>
  );
}

function Row({ r }: { r: WorklistRow }) {
  const navigate = useNavigate();
  const open = r.case_id ? () => navigate(`/cases/${encodeURIComponent(r.case_id as string)}`) : undefined;
  const late = r.prediction?.late_probability;
  const hours = r.prediction?.expected_hours;
  return (
    <tr className={`${ROW[r.urgency]} ${open ? "cursor-pointer hover:brightness-[0.97]" : ""}`} onClick={open}>
      <td className="whitespace-nowrap font-medium">
        {r.case_id ? (
          <Link
            to={`/cases/${encodeURIComponent(r.case_id)}`}
            className="text-accent-600 hover:underline"
            title={t.openCase}
            onClick={(e) => e.stopPropagation()}
          >
            {r.request_id}
          </Link>
        ) : (
          r.request_id
        )}
      </td>
      <td>
        {r.display_name ? (
          <>
            <div className="font-medium text-nis-text">{r.display_name}</div>
            <div className="whitespace-nowrap text-xs text-nis-muted">{r.patient_id}</div>
          </>
        ) : (
          <span className="text-nis-muted">{t.noCase}</span>
        )}
      </td>
      <td className="whitespace-nowrap">
        {r.meeting ? (
          <>
            <div>
              {weekdayShort(r.meeting.date)} {formatDayMonth(r.meeting.date)} {r.meeting.time}
            </div>
            <div className="text-xs text-nis-muted">{r.meeting.label}</div>
          </>
        ) : (
          cs.common.none
        )}
      </td>
      <td className="whitespace-nowrap font-medium">{r.days_to_mdt == null ? cs.common.none : t.days(r.days_to_mdt)}</td>
      <td>
        <div className="font-medium text-nis-text">
          {r.modality ?? cs.common.none} · {regionsText(r.regions)}
        </div>
        <div className="text-xs text-nis-muted" title={r.shifted ? t.shifted : undefined}>
          {studyDate(r.target_date)}
          {r.shifted && " *"}
        </div>
      </td>
      <td>
        <div>{r.provider.name ?? cs.common.none}</div>
        {r.provider.route && <div className="text-xs text-nis-muted">{r.provider.route}</div>}
      </td>
      <td>
        <StatusTag tone={REQUEST_TONE[r.state] ?? "gray"}>{cs.requestState[r.state] ?? r.state}</StatusTag>
      </td>
      <td className="whitespace-nowrap text-sm">{eventTime(r.updated_at)}</td>
      <td className="whitespace-nowrap text-right">
        {late == null ? (
          cs.common.none
        ) : (
          <span className={late >= 0.5 ? "font-bold text-nis-red" : ""}>{Math.round(late * 100)} %</span>
        )}
      </td>
      <td className="whitespace-nowrap text-right">{hours == null ? cs.common.none : t.hours(hours)}</td>
    </tr>
  );
}
