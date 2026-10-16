import { NavLink } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useScheduleDates } from "../services/api";
import { formatDayMonth, weekdayShort } from "./format";
import { ReadinessLabel } from "./ReadinessLabel";

/** Only scheduled dates (next eight weeks), each with its aggregate readiness. */
export default function DateSidebar() {
  const { data, isLoading, error } = useScheduleDates();

  return (
    <aside className="w-64 shrink-0 border-r border-slate-300 bg-slate-50 p-3" aria-label={cs.sidebar.title}>
      <h2 className="mb-2 text-lg font-bold">{cs.sidebar.title}</h2>
      {isLoading && <p>{cs.app.loading}</p>}
      {error && (
        <p role="alert" className="text-red-800">
          {cs.common.error}: {error.message}
        </p>
      )}
      {data && data.length === 0 && <p>{cs.sidebar.empty}</p>}
      <ul className="space-y-1">
        {data?.map((d) => (
          <li key={d.date}>
            <NavLink
              to={`/dny/${d.date}`}
              aria-label={cs.sidebar.ariaDate(weekdayShort(d.date), formatDayMonth(d.date), cs.readiness[d.readiness])}
              title={d.reason}
              className={({ isActive }) =>
                `block rounded-lg border px-2 py-1.5 hover:bg-accent-50 ${
                  isActive ? "border-accent-600 bg-accent-100" : "border-transparent"
                }`
              }
            >
              <span className="block font-semibold">
                {weekdayShort(d.date)} {formatDayMonth(d.date)}
                <span className="ml-2 text-sm font-normal text-slate-600">{cs.sidebar.meetings(d.meeting_count)}</span>
              </span>
              <span className="text-sm">
                <ReadinessLabel state={d.readiness} />
              </span>
            </NavLink>
          </li>
        ))}
      </ul>
    </aside>
  );
}
