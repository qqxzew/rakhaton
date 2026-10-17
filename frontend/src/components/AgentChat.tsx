import { useState, type FormEvent } from "react";
import { cs } from "../i18n/cs";
import { requestsApi, type ChatResult } from "../services/requestsApi";
import { useMutation } from "@tanstack/react-query";
import { Button, Icon, Panel, Tag } from "./ui";

const DOC_PREFIX = /^(DiagnosticReport|DocumentReference)\//;

/** Agent question panel (MCP tools over IRIS). It structures information only, never advises treatment. */
export default function AgentChat({
  caseId,
  onOpenSource,
  onShowRequest,
}: {
  caseId: string;
  onOpenSource: (docId: string, quote: string | null) => void;
  onShowRequest: (requestId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<{ q: string; a: ChatResult }[]>([]);
  const ask = useMutation({
    mutationFn: (q: string) => requestsApi.chat(caseId, q),
    onSuccess: (a, q) => {
      setHistory((h) => [...h, { q, a }]);
      setQuestion("");
    },
  });
  const t = cs.agent;

  const submit = (q: string) => {
    if (q.trim() && !ask.isPending) ask.mutate(q.trim());
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(question);
  };

  const sourceButton = (s: string) => {
    const doc = DOC_PREFIX.test(s) ? s.replace(DOC_PREFIX, "") : s.startsWith("rep-") ? s : null;
    if (doc) {
      return (
        <button key={s} type="button" className="text-accent-700 underline" onClick={() => onOpenSource(doc, null)}>
          {s}
        </button>
      );
    }
    if (s.startsWith("PACS-REQ-")) {
      return (
        <button key={s} type="button" className="text-accent-700 underline" onClick={() => onShowRequest(s)}>
          {s}
        </button>
      );
    }
    return (
      <code key={s} className="text-xs">
        {s}
      </code>
    );
  };

  return (
    <Panel
      id="agent"
      icon="chat"
      title={
        <>
          {t.title} <Tag tone="blue">AI</Tag>
        </>
      }
      actions={
        <Button variant="ghost" icon={open ? "chevronDown" : "chevronRight"} onClick={() => setOpen((o) => !o)}>
          {open ? t.collapse : t.open}
        </Button>
      }
    >
      <p className="text-sm text-nis-muted">{t.hint}</p>
      {open && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            {t.suggestions.map((s) => (
              <Button key={s} className="!px-2 !py-0.5 text-sm" disabled={ask.isPending} onClick={() => submit(s)}>
                {s}
              </Button>
            ))}
          </div>
          {history.map(({ q, a }, i) => (
            <div key={i} className="space-y-1 rounded-nis border border-nis-line p-3" data-agent-answer>
              <div className="font-bold">
                <Icon name="user" className="mr-1 text-accent-600" />
                {q}
              </div>
              {a.refused && <Tag tone="amber">{t.refused}</Tag>}
              <p className="whitespace-pre-wrap">{a.answer}</p>
              {a.tools_called.length > 0 && (
                <div className="text-xs text-nis-muted">
                  {t.tools}: {a.tools_called.map((c) => c.name ?? c.tool).join(", ")}
                </div>
              )}
              {a.sources.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-nis-muted">{t.sources}:</span>
                  {a.sources.map(sourceButton)}
                </div>
              )}
            </div>
          ))}
          {ask.isPending && <p className="text-nis-muted" role="status">{t.asking}</p>}
          {ask.isError && (
            <p role="alert" className="text-nis-red">
              {cs.common.error}: {ask.error.message}
            </p>
          )}
          <form onSubmit={onSubmit} className="flex gap-2">
            <input
              className="nis-input flex-1"
              value={question}
              maxLength={1000}
              placeholder={t.placeholder}
              aria-label={t.placeholder}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <Button type="submit" variant="primary" icon="send" disabled={!question.trim() || ask.isPending}>
              {t.ask}
            </Button>
          </form>
        </div>
      )}
    </Panel>
  );
}
