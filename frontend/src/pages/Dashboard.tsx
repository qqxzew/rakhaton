import { useState } from "react";
import { Link } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useDashboard } from "../services/api";
import type { DashboardDay, MeetingSummary, ReadinessState } from "../services/api-types";
import { formatDayMonth, weekdayShort } from "../components/format";
import { CountsText } from "../components/ReadinessLabel";
import NightlyBanner from "../components/NightlyBanner";
import { ReadinessTag } from "../components/ReadinessBadge";
import { ErrorState, PillTabs, READINESS_ROW, SectionHeader, StatChip } from "../components/ui";

type Filter = "all" | ReadinessState;

const STATES: ReadinessState[] = ["not_ready", "attention", "ready"];

const ICON_COLOR: Record<ReadinessState, string> = {
  ready: "text-nis-green",
  attention: "text-[#9a6b00]",
  not_ready: "text-nis-red",
};

const CARD_BORDER: Record<ReadinessState, string> = {
  ready: "border-[#b9d9a6]",
  attention: "border-[#ecd77e]",
  not_ready: "border-[#efb3b3]",
};

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useDashboard();
  const [filter, setFilter] = useState<Filter>("all");

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

  const { totals } = data;
  const meetings = data.days.flatMap((d) => d.meetings);
  const meetingCount = (s: ReadinessState) => meetings.filter((m) => m.readiness === s).length;

  return (
    <div className="space-y-3">
      <SectionHeader icon="calendar" title={cs.dashboard.title(formatDayMonth(data.start), formatDayMonth(data.end))} />

      <NightlyBanner />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <PillTabs<Filter>
          label={cs.dashboard.filterLabel}
          value={filter}
          onChange={setFilter}
          tabs={[
            { id: "all", label: cs.dashboard.filterAll, count: meetings.length },
            ...STATES.map((s) => ({ id: s, label: cs.readiness[s], count: meetingCount(s) })),
          ]}
        />
        <div className="flex flex-wrap gap-2" data-testid="summary-tiles">
          <StatChip icon="calendar" label={cs.dashboard.totalMeetings} value={totals.meetings} />
          <StatChip icon="users" label={cs.dashboard.totalCases} value={totals.cases} />
          {STATES.map((s) => (
            <StatChip
              key={s}
              icon={s === "ready" ? "checkCircle" : s === "attention" ? "warning" : "crossCircle"}
              iconClass={ICON_COLOR[s]}
              label={cs.readiness[s]}
              value={totals.counts[s]}
            />
          ))}
        </div>
      </div>

      {totals.meetings === 0 && (
        <p className="nis-panel nis-row-info px-3 py-2.5">{cs.dashboard.emptyWindow}</p>
      )}

      <div className="nis-panel overflow-x-auto">
        <ol className="grid min-w-[56rem]" style={{ gridTemplateColumns: `repeat(${data.days.length || 1}, minmax(0, 1fr))` }}>
          {data.days.map((day, i) => (
            <DayColumn key={day.date} day={day} filter={filter} first={i === 0} />
          ))}
        </ol>
      </div>
    </div>
  );
}

function DayColumn({ day, filter, first }: { day: DashboardDay; filter: Filter; first: boolean }) {
  const shown = day.meetings.filter((m) => filter === "all" || m.readiness === filter);
  const empty = day.meetings.length === 0;
  return (
    <li className={`flex min-w-0 flex-col ${first ? "" : "border-l border-nis-line"}`}>
      <h2 className="border-b border-nis-line px-2 py-2 text-center">
        <Link className="font-bold text-nis-text hover:text-accent-600" to={`/dny/${day.date}`}>
          {weekdayShort(day.date)} {formatDayMonth(day.date)}
        </Link>
      </h2>
      <div className={`flex min-h-[22rem] flex-1 flex-col gap-2 p-1.5 ${empty ? "nis-hatch" : ""}`}>
        {empty ? (
          <p className="pt-2 text-center text-sm text-nis-muted">{cs.dashboard.noMeetings}</p>
        ) : (
          shown.map((m) => <MeetingCard key={m.id} date={day.date} m={m} />)
        )}
      </div>
    </li>
  );
}

function MeetingCard({ date, m }: { date: string; m: MeetingSummary }) {
  return (
    <Link
      to={`/dny/${date}#${m.id}`}
      className={`block rounded-nis border p-2 text-sm hover:border-accent-600 ${READINESS_ROW[m.readiness]} ${CARD_BORDER[m.readiness]}`}
    >
      <div className="font-bold text-accent-600">{m.time}</div>
      <div className="font-bold leading-snug text-nis-text">{m.label}</div>
      <div className="mt-1 text-nis-ink">{cs.dashboard.patients(m.case_count)}</div>
      {m.case_count > 0 && (
        <div className="text-xs text-nis-muted">
          {cs.dashboard.meetingCounts}: <CountsText counts={m.counts} />
        </div>
      )}
      <div className="mt-1.5">
        <ReadinessTag state={m.readiness} />
      </div>
      <div className="mt-1 text-xs leading-snug text-nis-ink">{m.reason}</div>
    </Link>
  );
}
