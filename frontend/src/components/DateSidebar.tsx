import { NavLink } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useScheduleDates } from "../services/api";
import { formatDayMonth, weekdayShort } from "./format";
import { ReadinessLabel } from "./ReadinessLabel";

/** Only scheduled dates (next eight weeks), each with its aggregate readiness. NIS side-list style. */
export default function DateSidebar() {
  const { data, isLoading, error } = useScheduleDates();

  return (
    <aside
      className="nis-panel flex max-h-[calc(100vh-4.5rem)] w-60 shrink-0 flex-col self-start overflow-hidden lg:sticky lg:top-[4rem]"
      aria-label={cs.sidebar.title}
    >
      <h2 className="nis-label border-b border-nis-line px-3 py-2.5">{cs.sidebar.title}</h2>
      <div className="overflow-y-auto">
        {isLoading && <p className="px-3 py-2 text-nis-muted">{cs.app.loading}</p>}
        {error && (
          <p role="alert" className="px-3 py-2 text-nis-red">
            {cs.common.error}: {error.message}
          </p>
        )}
        {data && data.length === 0 && <p className="px-3 py-2 text-nis-muted">{cs.sidebar.empty}</p>}
        <ul>
          {data?.map((d) => (
            <li key={d.date} className="border-b border-nis-line last:border-b-0">
              <NavLink
                to={`/dny/${d.date}`}
                aria-label={cs.sidebar.ariaDate(weekdayShort(d.date), formatDayMonth(d.date), cs.readiness[d.readiness])}
                title={d.reason}
                className={({ isActive }) =>
                  `block border-l-[3px] px-3 py-1.5 hover:bg-accent-50 ${
                    isActive ? "border-accent-600 bg-accent-50" : "border-transparent"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="flex items-baseline justify-between gap-2">
                      <span className={`font-bold ${isActive ? "text-accent-600" : "text-nis-text"}`}>
                        {weekdayShort(d.date)} {formatDayMonth(d.date)}
                      </span>
                      <span className="text-xs text-nis-muted">{cs.sidebar.meetings(d.meeting_count)}</span>
                    </span>
                    <span className="block text-sm">
                      <ReadinessLabel state={d.readiness} />
                    </span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
