import { Link } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useDashboard } from "../services/api";
import { formatDayMonth, weekdayShort } from "../components/format";
import { CountsText, ReadinessLabel } from "../components/ReadinessLabel";

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useDashboard();

  if (isLoading) return <p className="p-6 text-lg">{cs.app.loading}</p>;
  if (error || !data) {
    return (
      <div className="p-6" role="alert">
        <p className="text-lg text-red-800">
          {cs.common.error}: {error?.message}
        </p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="mt-2 rounded border-2 border-accent-600 px-3 py-1 font-semibold text-accent-700"
        >
          {cs.common.retry}
        </button>
      </div>
    );
  }

  const { totals } = data;
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <h1 className="text-3xl font-bold">
        {cs.dashboard.title(formatDayMonth(data.start), formatDayMonth(data.end))}
      </h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5" data-testid="summary-tiles">
        <Tile label={cs.dashboard.totalMeetings} value={totals.meetings} />
        <Tile label={cs.dashboard.totalCases} value={totals.cases} />
        <Tile label={cs.readiness.not_ready} value={totals.counts.not_ready} state="not_ready" />
        <Tile label={cs.readiness.attention} value={totals.counts.attention} state="attention" />
        <Tile label={cs.readiness.ready} value={totals.counts.ready} state="ready" />
      </div>

      {totals.meetings === 0 && <p className="text-lg">{cs.dashboard.emptyWindow}</p>}

      <ol className="space-y-3">
        {data.days.map((day) => (
          <li key={day.date} className="rounded-xl border border-slate-300 bg-white p-3 shadow-sm">
            <h2 className="text-xl font-bold">
              <Link className="text-accent-700 underline" to={`/dny/${day.date}`}>
                {weekdayShort(day.date)} {formatDayMonth(day.date)}
              </Link>
            </h2>
            {day.meetings.length === 0 ? (
              <p className="mt-1 text-slate-600">{cs.dashboard.noMeetings}</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {day.meetings.map((m) => (
                  <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-1">
                    <Link className="font-semibold text-accent-700 underline" to={`/dny/${day.date}#${m.id}`}>
                      {m.time} {m.label}
                    </Link>
                    <ReadinessLabel state={m.readiness} reason={m.reason} />
                    <span className="text-slate-700">{cs.dashboard.patients(m.case_count)}</span>
                    {m.case_count > 0 && (
                      <span className="text-sm text-slate-700">
                        {cs.dashboard.meetingCounts}: <CountsText counts={m.counts} />
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

const TILE: Record<string, string> = {
  ready: "border-green-600 bg-green-50",
  attention: "border-amber-600 bg-amber-50",
  not_ready: "border-red-600 bg-red-50",
};

function Tile({ label, value, state }: { label: string; value: number; state?: string }) {
  return (
    <div className={`rounded-xl border-2 p-3 ${state ? TILE[state] : "border-slate-300 bg-white"}`}>
      <div className="text-3xl font-bold">{value}</div>
      <div className="font-medium">{label}</div>
    </div>
  );
}
