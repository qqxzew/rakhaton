import { Link, useParams } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useDay } from "../services/api";
import { formatDayMonth, weekdayShort } from "../components/format";
import { ReadinessLabel } from "../components/ReadinessLabel";

export default function DayView() {
  const { date = "" } = useParams<{ date: string }>();
  const { data, isLoading, error, refetch } = useDay(date);

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

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <p>
        <Link className="text-accent-700 underline" to="/">
          {cs.day.back}
        </Link>
      </p>
      <h1 className="text-3xl font-bold">{cs.day.title(weekdayShort(data.date), formatDayMonth(data.date))}</h1>
      {data.meetings.length === 0 && <p className="text-lg">{cs.day.noMeetings}</p>}

      {data.meetings.map((m) => (
        <section key={m.id} id={m.id} className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-2xl font-bold">
              {m.time} {m.label}
            </h2>
            <Link
              to={`/pridat?meeting=${encodeURIComponent(m.id)}&group=${encodeURIComponent(m.eligible_groups[0] ?? "")}`}
              className="rounded-lg border-2 border-accent-600 px-3 py-1 font-semibold text-accent-700 hover:bg-accent-50"
            >
              {cs.day.addToMeeting}
            </Link>
          </div>
          <div className="mt-1">
            <ReadinessLabel state={m.readiness} reason={m.reason} />
          </div>

          {m.cases.length === 0 ? (
            <p className="mt-3 text-slate-700">{cs.day.noPatients}</p>
          ) : (
            <table className="mt-3 w-full text-left">
              <thead>
                <tr className="border-b border-slate-300 text-sm text-slate-600">
                  <th className="py-1 pr-3">{cs.day.patient}</th>
                  <th className="py-1 pr-3">{cs.day.diagnosis}</th>
                  <th className="py-1">{cs.day.status}</th>
                </tr>
              </thead>
              <tbody>
                {m.cases.map((c) => (
                  <tr key={c.id} className="border-b border-slate-100">
                    <td className="py-2 pr-3">
                      <Link
                        to={`/cases/${c.id}`}
                        title={`${cs.header.pseudonym}: ${c.patient_id}`}
                        className="font-semibold text-accent-700 underline"
                      >
                        {c.display_name}
                      </Link>
                    </td>
                    <td className="py-2 pr-3">{c.diagnosis ?? cs.common.unknown}</td>
                    <td className="py-2">
                      <ReadinessLabel state={c.readiness} reason={c.reason} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ))}
    </div>
  );
}
