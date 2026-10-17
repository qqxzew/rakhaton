import { cs } from "../i18n/cs";
import type { CaseDetail } from "../services/api-types";
import { formatDate } from "./format";
import ReadinessBadge from "./ReadinessBadge";
import SimulaceTag from "./SimulaceTag";
import { Button, TagField } from "./ui";

/** NIS record header: blue name, dark label tags with values, readiness and actions. */
export default function HeaderStrip({
  data,
  presentation,
  rechecking,
  onRecheck,
  onTogglePresentation,
}: {
  data: CaseDetail;
  presentation: boolean;
  rechecking: boolean;
  onRecheck: () => void;
  onTogglePresentation: () => void;
}) {
  const { case: c, patient } = data;
  const offset = c.date_offset_days;
  const diagnoses = patient.diagnoses.map((d) => `${d.code} ${d.text}`).join("; ") || cs.common.unknown;

  return (
    <header className="nis-panel px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <h1 className="text-2xl font-bold text-accent-600">{patient.display_name}</h1>
            <TagField label={cs.header.pseudonym}>{patient.id}</TagField>
            <TagField label={cs.header.sexAge}>
              {patient.sex}, {patient.age_band}
            </TagField>
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <TagField label={cs.header.dg}>
                <span className="whitespace-normal">{diagnoses}</span>
              </TagField>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <TagField label={cs.header.meeting} tone="blue">
              {formatDate(c.meeting.date)} {c.meeting.time} – {c.meeting.label}
            </TagField>
            <ReadinessBadge state={c.readiness} reason={c.reason} />
          </div>
          {(offset !== 0 || data.simulated) && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-nis-muted">
              {data.simulated && <SimulaceTag />}
              {offset !== 0 && <span>{cs.header.dateOffset(offset)}</span>}
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <Button variant="secondary" icon="screen" onClick={onTogglePresentation} aria-pressed={presentation}>
            {presentation ? cs.header.presentationOff : cs.header.presentationOn}
          </Button>
          <Button variant="primary" icon="refresh" onClick={onRecheck} disabled={rechecking}>
            {rechecking ? cs.header.rechecking : cs.header.recheck}
          </Button>
        </div>
      </div>
    </header>
  );
}
