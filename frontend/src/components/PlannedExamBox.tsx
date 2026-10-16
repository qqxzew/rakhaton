import { useState } from "react";
import { cs } from "../i18n/cs";
import type { PlannedExam } from "../services/api-types";
import { useUpdatePlannedExam } from "../services/api";
import { formatDate, parseRegions, percent, regionLabel, regionsText } from "./format";

interface Props {
  caseId: string;
  exam: PlannedExam | null;
  onOpenSource: (docId: string, quote: string | null) => void;
}

export default function PlannedExamBox({ caseId, exam, onOpenSource }: Props) {
  const [editing, setEditing] = useState(false);
  const [modality, setModality] = useState("");
  const [regions, setRegions] = useState("");
  const [date, setDate] = useState("");
  const update = useUpdatePlannedExam(caseId);

  const startEdit = () => {
    setModality(exam?.modality ?? "");
    setRegions(exam ? exam.regions.map(regionLabel).join(", ") : "");
    setDate(exam?.date ?? "");
    update.reset();
    setEditing(true);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    update.mutate(
      { modality: modality.trim(), regions: parseRegions(regions), date: date || null },
      { onSuccess: () => setEditing(false) },
    );
  };

  const field = "rounded border border-slate-400 px-2 py-1 w-full";

  return (
    <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm" aria-labelledby="planned-exam-title">
      <div className="mb-2 flex items-center justify-between">
        <h2 id="planned-exam-title" className="text-xl font-bold">
          {cs.plannedExam.title}
        </h2>
        {!editing && (
          <button
            type="button"
            onClick={startEdit}
            className="rounded border-2 border-accent-600 px-3 py-1 font-semibold text-accent-700 hover:bg-accent-50"
          >
            {cs.common.edit}
          </button>
        )}
      </div>

      {editing ? (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="text-sm font-semibold">{cs.plannedExam.modality}</span>
            <input className={field} value={modality} onChange={(e) => setModality(e.target.value)} required />
          </label>
          <label className="block">
            <span className="text-sm font-semibold">{cs.plannedExam.regions}</span>
            <input className={field} value={regions} onChange={(e) => setRegions(e.target.value)} />
            <span className="text-xs text-slate-600">{cs.plannedExam.regionsHint}</span>
          </label>
          <label className="block">
            <span className="text-sm font-semibold">{cs.plannedExam.date}</span>
            <input type="date" className={field} value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <div className="flex items-center gap-2 sm:col-span-3">
            <button
              type="submit"
              disabled={update.isPending}
              className="rounded bg-accent-600 px-4 py-1.5 font-semibold text-white hover:bg-accent-700 disabled:opacity-60"
            >
              {update.isPending ? cs.plannedExam.saving : cs.common.save}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded border border-slate-400 px-4 py-1.5 font-semibold"
            >
              {cs.common.cancel}
            </button>
            {update.isError && (
              <span role="alert" className="text-red-800">
                {cs.common.error}: {update.error.message}
              </span>
            )}
          </div>
        </form>
      ) : exam ? (
        <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
          <Fact label={cs.plannedExam.modality} value={exam.modality} />
          <Fact label={cs.plannedExam.regions} value={regionsText(exam.regions)} />
          <Fact label={cs.plannedExam.date} value={formatDate(exam.date)} />
          <Fact label={cs.plannedExam.site} value={exam.site ?? cs.common.none} />
          {exam.quote && (
            <div className="sm:col-span-2 lg:col-span-4">
              <div className="text-sm font-semibold text-slate-600">{cs.plannedExam.quote}</div>
              {exam.source_doc_id ? (
                <button
                  type="button"
                  onClick={() => onOpenSource(exam.source_doc_id as string, exam.quote)}
                  className="mt-0.5 text-left italic text-accent-700 underline decoration-dotted underline-offset-4 hover:text-accent-600"
                  title={cs.plannedExam.openSource}
                >
                  „{exam.quote}“
                </button>
              ) : (
                <span className="italic">„{exam.quote}“</span>
              )}
              <span className="ml-2 text-sm text-slate-600">
                {cs.common.confidence}: {percent(exam.confidence)}
              </span>
            </div>
          )}
        </div>
      ) : (
        <p className="text-slate-600">{cs.plannedExam.empty}</p>
      )}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-sm font-semibold text-slate-600">{label}</div>
      <div className="text-lg">{value}</div>
    </div>
  );
}
