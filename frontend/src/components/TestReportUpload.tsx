import { useEffect, useState, type ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cs } from "../i18n/cs";
import { testReportApi } from "../services/api";
import ActionDialog from "./ActionDialog";
import { Button } from "./ui";

const t = cs.testReport;

/** Button + dialog: upload a test radiology report so the live pipeline reads it (simulation). */
export default function TestReportUpload({ caseId, onUploaded }: { caseId: string; onUploaded: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button icon="document" onClick={() => setOpen(true)}>
        {t.open}
      </Button>
      {open && (
        <UploadDialog
          caseId={caseId}
          onClose={() => setOpen(false)}
          onDone={() => {
            setOpen(false);
            onUploaded();
          }}
        />
      )}
    </>
  );
}

function UploadDialog({ caseId, onClose, onDone }: { caseId: string; onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient();
  const template = useQuery({
    queryKey: ["test-report-template", caseId],
    queryFn: () => testReportApi.template(caseId),
    staleTime: 0,
  });
  const [text, setText] = useState("");
  const [date, setDate] = useState("");
  const [modality, setModality] = useState("CT");

  useEffect(() => {
    if (!template.data) return;
    setText((v) => v || template.data.text);
    setDate((v) => v || template.data.date);
    setModality(template.data.modality);
  }, [template.data]);

  const done = () => {
    qc.invalidateQueries({ queryKey: ["case", caseId] });
    qc.invalidateQueries({ queryKey: ["test-report-template", caseId] });
    onDone();
  };
  const upload = useMutation({
    mutationFn: () => testReportApi.upload(caseId, { text, date, modality }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: () => testReportApi.removeAll(caseId),
    onSuccess: done, // closes the dialog; the page polls while the check runs again
  });

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setText(await file.text());
  };

  const error = upload.error?.message ?? remove.error?.message ?? template.error?.message ?? null;
  const uploaded = template.data?.uploaded ?? 0;

  return (
    <ActionDialog
      title={t.title}
      hint={t.hint}
      simulated
      submitLabel={upload.isPending ? t.sending : t.submit}
      canSubmit={text.trim().length >= 20 && date !== "" && !template.isLoading}
      busy={upload.isPending}
      error={error}
      onSubmit={() => upload.mutate()}
      onClose={onClose}
    >
      <label className="block">
        <span className="nis-label block">{t.file}</span>
        <input type="file" accept=".txt,text/plain" className="mt-1 block w-full text-sm" onChange={onFile} />
      </label>
      <label className="block">
        <span className="nis-label block">{t.text}</span>
        <textarea
          className="nis-input mt-1 h-44 w-full font-mono text-sm"
          value={template.isLoading && !text ? t.loading : text}
          onChange={(e) => setText(e.target.value)}
          required
        />
      </label>
      <div className="flex flex-wrap gap-3">
        <label className="block">
          <span className="nis-label block">{t.date}</span>
          <input type="date" className="nis-input mt-1" value={date} onChange={(e) => setDate(e.target.value)} required />
        </label>
        <label className="block">
          <span className="nis-label block">{t.modality}</span>
          <select className="nis-input mt-1" value={modality} onChange={(e) => setModality(e.target.value)}>
            {(template.data?.modalities ?? ["CT", "MR", "PET", "RTG", "SONO", "MAMO"]).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="ghost" disabled={!template.data} onClick={() => template.data && setText(template.data.text)}>
          {t.template}
        </Button>
        {uploaded > 0 && (
          <Button variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
            {t.remove(uploaded)}
          </Button>
        )}
      </div>
    </ActionDialog>
  );
}
