import { cs } from "../i18n/cs";
import type { TimelineEntry } from "../services/api-types";
import AvailabilityChip from "./AvailabilityChip";
import { formatDate, regionsText } from "./format";

function StudyCard({
  entry,
  onOpenSource,
}: {
  entry: TimelineEntry;
  onOpenSource: (docId: string, quote: string | null) => void;
}) {
  const referenced = entry.kind === "referenced";
  return (
    <div
      className={`w-56 shrink-0 rounded-lg bg-white p-3 ${
        referenced ? "border-2 border-dashed border-slate-500" : "border-2 border-solid border-slate-700"
      }`}
    >
      <div className="text-sm font-semibold text-slate-600">
        {formatDate(entry.date)} · {cs.timelineKind[entry.kind]}
      </div>
      <div className="text-lg font-bold">
        {entry.modality ?? cs.common.none}{" "}
        <span className="font-normal">{regionsText(entry.regions)}</span>
      </div>
      <p className="my-1 line-clamp-2 text-sm text-slate-800">{entry.label}</p>
      <div className="flex flex-wrap items-center gap-2">
        {entry.availability && <AvailabilityChip availability={entry.availability} />}
        {entry.doc_id && (
          <button
            type="button"
            onClick={() => onOpenSource(entry.doc_id as string, null)}
            className="text-sm font-semibold text-accent-700 underline underline-offset-2 hover:text-accent-600"
          >
            {cs.timeline.openReport}
          </button>
        )}
      </div>
    </div>
  );
}

function Marker({ entry }: { entry: TimelineEntry }) {
  const mdt = entry.kind === "mdt";
  return (
    <div
      className={`w-44 shrink-0 rounded-md px-3 py-2 ${
        mdt
          ? "border-2 border-accent-600 bg-accent-600 text-white"
          : "border-l-8 border-accent-500 bg-accent-50 text-slate-900"
      }`}
    >
      <div className="text-sm font-semibold">
        {mdt ? "⚑ " : "▮ "}
        {formatDate(entry.date)} · {cs.timelineKind[entry.kind]}
      </div>
      <div className="text-sm">{entry.label}</div>
    </div>
  );
}

export default function ImagingTimeline({
  entries,
  onOpenSource,
}: {
  entries: TimelineEntry[];
  onOpenSource: (docId: string, quote: string | null) => void;
}) {
  // ISO dates sort lexicographically
  const sorted = [...entries].sort((a, b) => a.date.localeCompare(b.date));

  return (
    <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm" aria-labelledby="timeline-title">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="timeline-title" className="text-xl font-bold">
          {cs.timeline.title}
        </h2>
        <span className="text-sm text-slate-600">
          {cs.timeline.legendSolid} · {cs.timeline.legendDashed}
        </span>
      </div>
      {sorted.length === 0 ? (
        <p className="text-slate-600">{cs.timeline.empty}</p>
      ) : (
        <div className="overflow-x-auto pb-2">
          <ol className="relative flex w-max items-center gap-4 px-1 py-2">
            {/* axis line behind the cards */}
            <div className="absolute inset-x-0 top-1/2 -z-0 h-0.5 bg-slate-300" aria-hidden="true" />
            {sorted.map((entry, i) => (
              <li key={`${entry.kind}-${entry.date}-${i}`} className="relative z-10">
                {entry.kind === "study" || entry.kind === "referenced" ? (
                  <StudyCard entry={entry} onOpenSource={onOpenSource} />
                ) : (
                  <Marker entry={entry} />
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
