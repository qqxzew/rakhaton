import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useDashboard, useScheduleDates } from "../services/api";
import type { ScheduleDate } from "../services/api-types";
import { formatDayMonth, weekdayShort } from "./format";
import { ReadinessLabel } from "./ReadinessLabel";

/**
 * Scheduled dates with their aggregate readiness. Dates with patients and the dashboard window
 * (next 7 days) are always listed; later dates without patients are folded away so empty
 * meetings do not drown the real signals. Empty days are neutral: no readiness icon.
 */
export default function DateSidebar() {
  const { data, isLoading, error } = useScheduleDates();
  const windowEnd = useDashboard().data?.end;
  const { pathname } = useLocation();
  const [expanded, setExpanded] = useState(false);

  const isEmpty = (d: ScheduleDate) => d.case_count === 0;
  const isCollapsible = (d: ScheduleDate) =>
    isEmpty(d) && (windowEnd ? d.date > windowEnd : true) && !pathname.endsWith(`/dny/${d.date}`);
  const visible = data?.filter((d) => expanded || !isCollapsible(d)) ?? [];
  const hiddenCount = data ? data.filter(isCollapsible).length : 0;

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
          {visible.map((d) => (
            <li key={d.date} className="border-b border-nis-line last:border-b-0">
              <NavLink
                to={`/dny/${d.date}`}
                aria-label={cs.sidebar.ariaDate(
                  weekdayShort(d.date),
                  formatDayMonth(d.date),
                  isEmpty(d) ? cs.sidebar.noPatients : cs.readiness[d.readiness],
                )}
                title={d.reason}
                className={({ isActive }) =>
                  `block border-l-[3px] px-3 hover:bg-accent-50 ${isEmpty(d) ? "py-1" : "py-1.5"} ${
                    isActive ? "border-accent-600 bg-accent-50" : "border-transparent"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="flex items-baseline justify-between gap-2">
                      <span
                        className={`${isEmpty(d) ? "font-medium" : "font-bold"} ${
                          isActive ? "text-accent-600" : isEmpty(d) ? "text-nis-muted" : "text-nis-text"
                        }`}
                      >
                        {weekdayShort(d.date)} {formatDayMonth(d.date)}
                      </span>
                      <span className="text-xs text-nis-muted">
                        {isEmpty(d) ? cs.sidebar.noPatients : cs.sidebar.meetings(d.meeting_count)}
                      </span>
                    </span>
                    {!isEmpty(d) && (
                      <span className="block text-sm">
                        <ReadinessLabel state={d.readiness} />
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
        {hiddenCount > 0 && (
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
            className="block w-full border-t border-nis-line px-3 py-2 text-left text-xs font-medium text-accent-600 hover:bg-accent-50"
          >
            {expanded ? cs.sidebar.lessDays : cs.sidebar.moreDays(hiddenCount)}
          </button>
        )}
      </div>
    </aside>
  );
}
