import { useState } from "react";
import { cs } from "../i18n/cs";
import type { PlannedExam } from "../services/api-types";
import { useUpdatePlannedExam } from "../services/api";
import { formatDate, parseRegions, percent, regionLabel, regionsText } from "./format";
import { Button, Field, FieldLabel, Panel } from "./ui";

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

  return (
    <Panel
      id="planned-exam"
      icon="calendar"
      title={cs.plannedExam.title}
      actions={
        !editing && (
          <Button icon="edit" onClick={startEdit}>
            {cs.common.edit}
          </Button>
        )
      }
    >
      {editing ? (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
          <div>
            <FieldLabel htmlFor="pe-modality">{cs.plannedExam.modality}</FieldLabel>
            <input id="pe-modality" className="nis-input mt-1" value={modality} onChange={(e) => setModality(e.target.value)} required />
          </div>
          <div>
            <FieldLabel htmlFor="pe-regions">{cs.plannedExam.regions}</FieldLabel>
            <input id="pe-regions" className="nis-input mt-1" value={regions} onChange={(e) => setRegions(e.target.value)} />
            <span className="text-xs text-nis-muted">{cs.plannedExam.regionsHint}</span>
          </div>
          <div>
            <FieldLabel htmlFor="pe-date">{cs.plannedExam.date}</FieldLabel>
            <input id="pe-date" type="date" className="nis-input mt-1" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="flex items-center gap-2 sm:col-span-3">
            <Button type="submit" variant="primary" disabled={update.isPending}>
              {update.isPending ? cs.plannedExam.saving : cs.common.save}
            </Button>
            <Button onClick={() => setEditing(false)}>{cs.common.cancel}</Button>
            {update.isError && (
              <span role="alert" className="text-nis-red">
                {cs.common.error}: {update.error.message}
              </span>
            )}
          </div>
        </form>
      ) : exam ? (
        <div className="flex flex-wrap gap-x-10 gap-y-3">
          <Field label={cs.plannedExam.modality}>
            <span className="text-lg font-bold">{exam.modality}</span>
          </Field>
          <Field label={cs.plannedExam.regions}>{regionsText(exam.regions)}</Field>
          <Field label={cs.plannedExam.date}>
            <span className="font-medium text-accent-600">{formatDate(exam.date)}</span>
          </Field>
          <Field label={cs.plannedExam.site}>{exam.site ?? cs.common.none}</Field>
          {exam.quote && (
            <Field label={cs.plannedExam.quote} className="min-w-[16rem] flex-1">
              {exam.source_doc_id ? (
                <button
                  type="button"
                  onClick={() => onOpenSource(exam.source_doc_id as string, exam.quote)}
                  className="text-left italic text-accent-600 underline decoration-dotted underline-offset-4 hover:text-accent-700"
                  title={cs.plannedExam.openSource}
                >
                  „{exam.quote}“
                </button>
              ) : (
                <span className="italic">„{exam.quote}“</span>
              )}
              <span className="ml-2 text-sm text-nis-muted">
                {cs.common.confidence}: {percent(exam.confidence)}
              </span>
            </Field>
          )}
        </div>
      ) : (
        <p className="text-nis-muted">{cs.plannedExam.empty}</p>
      )}
    </Panel>
  );
}
