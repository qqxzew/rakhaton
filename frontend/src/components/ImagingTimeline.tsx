import { cs } from "../i18n/cs";
import type { TimelineEntry } from "../services/api-types";
import AvailabilityChip from "./AvailabilityChip";
import { formatDate, regionsText } from "./format";
import { Icon, Panel } from "./ui";

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
      className={`w-56 shrink-0 rounded-nis p-2.5 ${
        referenced ? "border border-dashed border-nis-ink bg-[#f7f9fb]" : "border border-nis-line bg-white"
      }`}
    >
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-bold text-accent-600">{formatDate(entry.date)}</span>
        <span className="text-xs text-nis-muted">{cs.timelineKind[entry.kind]}</span>
      </div>
      <div className="mt-0.5 font-bold text-nis-text">
        {entry.modality ?? cs.common.none} <span className="font-normal">{regionsText(entry.regions)}</span>
      </div>
      <p className="my-1 line-clamp-2 text-sm text-nis-ink">{entry.label}</p>
      <div className="flex flex-wrap items-center gap-2">
        {entry.availability && <AvailabilityChip availability={entry.availability} />}
        {entry.doc_id && (
          <button
            type="button"
            onClick={() => onOpenSource(entry.doc_id as string, null)}
            className="inline-flex items-center gap-1 text-sm font-medium text-accent-600 hover:underline"
          >
            <Icon name="document" size="1.1em" />
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
      className={`w-44 shrink-0 rounded-nis px-2.5 py-2 text-sm ${
        mdt ? "bg-nis-slate text-white" : "border-l-4 border-accent-600 bg-nis-info text-nis-text"
      }`}
    >
      <div className="flex items-center gap-1.5 font-bold">
        <Icon name={mdt ? "flag" : "pulse"} size="1.1em" />
        {formatDate(entry.date)} · {cs.timelineKind[entry.kind]}
      </div>
      <div className="mt-0.5">{entry.label}</div>
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
    <Panel
      id="timeline"
      icon="scan"
      title={cs.timeline.title}
      actions={
        <span className="text-xs text-nis-muted">
          {cs.timeline.legendSolid} · {cs.timeline.legendDashed}
        </span>
      }
    >
      {sorted.length === 0 ? (
        <p className="text-nis-muted">{cs.timeline.empty}</p>
      ) : (
        <div className="overflow-x-auto pb-1">
          <ol className="relative flex w-max items-center gap-3 px-1 py-1">
            {/* axis line behind the cards */}
            <div className="absolute inset-x-0 top-1/2 h-px bg-nis-line" aria-hidden="true" />
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
    </Panel>
  );
}
