import { cs } from "../i18n/cs";
import type { CaseDetail } from "../services/api-types";
import { formatDate } from "./format";
import ReadinessBadge from "./ReadinessBadge";
import SimulaceTag from "./SimulaceTag";

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

  return (
    <header className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 text-3xl font-bold">
            {patient.display_name}
            <span className="rounded bg-slate-100 px-2 py-0.5 text-base font-medium text-slate-700">
              {cs.header.pseudonym}: {patient.id}
            </span>
            {data.simulated && <SimulaceTag />}
          </h1>
          <p className="mt-1 text-lg text-slate-700">
            {patient.sex}, {patient.age_band}
            <span className="mx-2" aria-hidden="true">
              ·
            </span>
            {patient.diagnoses.map((d) => `${d.code} ${d.text}`).join("; ") || cs.common.unknown}
          </p>
          <p className="mt-1 text-lg">
            <span className="font-semibold">{cs.header.meeting}:</span>{" "}
            {formatDate(c.meeting.date)} {c.meeting.time} – {c.meeting.label}
          </p>
          {offset !== 0 && <p className="mt-1 text-sm text-slate-600">{cs.header.dateOffset(offset)}</p>}
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onRecheck}
            disabled={rechecking}
            className="rounded-lg bg-accent-600 px-4 py-2 font-semibold text-white hover:bg-accent-700 disabled:opacity-60"
          >
            {rechecking ? cs.header.rechecking : cs.header.recheck}
          </button>
          <button
            type="button"
            onClick={onTogglePresentation}
            aria-pressed={presentation}
            className="rounded-lg border-2 border-accent-600 px-4 py-2 font-semibold text-accent-700 hover:bg-accent-50 aria-pressed:bg-accent-100"
          >
            {presentation ? cs.header.presentationOff : cs.header.presentationOn}
          </button>
        </div>
      </div>

      <div className="mt-3">
        <ReadinessBadge state={c.readiness} reason={c.reason} />
      </div>
    </header>
  );
}
