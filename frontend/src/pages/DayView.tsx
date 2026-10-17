import { Link, useNavigate, useParams } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useDay, useScheduleDates } from "../services/api";
import { formatDayMonth, weekdayShort } from "../components/format";
import ReadinessBadge, { ReadinessTag } from "../components/ReadinessBadge";
import {
  ButtonLink,
  DataTable,
  DateNav,
  ErrorState,
  HeaderDivider,
  Icon,
  Panel,
  READINESS_ROW,
  SectionHeader,
} from "../components/ui";

export default function DayView() {
  const { date = "" } = useParams<{ date: string }>();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useDay(date);
  const dates = useScheduleDates().data ?? [];

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

  // previous / next scheduled date (ISO strings compare lexicographically)
  const prev = [...dates].reverse().find((d) => d.date < data.date)?.date;
  const next = dates.find((d) => d.date > data.date)?.date;

  return (
    <div className="space-y-3">
      <SectionHeader icon="users" title={`MDT · ${cs.day.title(weekdayShort(data.date), formatDayMonth(data.date))}`}>
        <DateNav
          label={cs.day.title(weekdayShort(data.date), formatDayMonth(data.date))}
          prevLabel={cs.day.prev}
          nextLabel={cs.day.next}
          onPrev={prev ? () => navigate(`/dny/${prev}`) : undefined}
          onNext={next ? () => navigate(`/dny/${next}`) : undefined}
        />
        <HeaderDivider />
        <ButtonLink to="/" icon="chevronLeft">
          {cs.day.back}
        </ButtonLink>
      </SectionHeader>

      {data.readiness && data.reason && (
        <div className="nis-panel px-3 py-2">
          <ReadinessBadge state={data.readiness} reason={data.reason} />
        </div>
      )}

      {data.meetings.length === 0 && <p className="nis-panel nis-hatch px-3 py-6 text-center">{cs.day.noMeetings}</p>}

      {data.meetings.map((m) => (
        <Panel
          key={m.id}
          id={m.id}
          title={
            <>
              <span className="text-accent-600">{m.time}</span> {m.label}
            </>
          }
          bodyClassName={m.cases.length ? "" : "p-3"}
          actions={
            <>
              <ReadinessBadge state={m.readiness} reason={m.reason} />
              <ButtonLink
                to={`/pridat?meeting=${encodeURIComponent(m.id)}&group=${encodeURIComponent(m.eligible_groups[0] ?? "")}`}
                icon="userPlus"
              >
                {cs.day.addToMeeting}
              </ButtonLink>
            </>
          }
        >
          {m.cases.length === 0 ? (
            <p className="text-nis-muted">{cs.day.noPatients}</p>
          ) : (
            <DataTable>
              <thead>
                <tr>
                  <th>{cs.day.patient}</th>
                  <th>{cs.day.diagnosis}</th>
                  <th>{cs.day.reason}</th>
                  <th className="w-px text-right">{cs.day.status}</th>
                  <th className="w-px">
                    <span className="sr-only">{cs.day.open}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {m.cases.map((c) => (
                  <tr key={c.id} className={READINESS_ROW[c.readiness]} data-readiness={c.readiness}>
                    <td className="!align-middle">
                      <Link
                        to={`/cases/${c.id}`}
                        title={`${cs.header.pseudonym}: ${c.patient_id}`}
                        className="text-base font-bold text-accent-600 hover:underline"
                      >
                        {c.display_name}
                      </Link>
                    </td>
                    <td className="!align-middle">{c.diagnosis ?? cs.common.unknown}</td>
                    <td className="!align-middle">{c.reason}</td>
                    <td className="whitespace-nowrap text-right !align-middle">
                      <ReadinessTag state={c.readiness} />
                    </td>
                    <td className="!align-middle">
                      <Link
                        to={`/cases/${c.id}`}
                        tabIndex={-1}
                        aria-hidden="true"
                        className="flex text-accent-600 hover:text-accent-700"
                      >
                        <Icon name="chevronRight" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          )}
        </Panel>
      ))}
    </div>
  );
}
