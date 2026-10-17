import { useEffect, useRef, useState } from "react";
import { cs } from "../i18n/cs";
import { requestsApi, useRequestDetail, type RequestMessage } from "../services/requestsApi";
import { formatDate, formatDateTime, regionsText } from "./format";
import SimulaceTag from "./SimulaceTag";
import { DataTable, Field, Icon, REQUEST_TONE, StatusTag } from "./ui";

function VoicePlayer({ requestId, message }: { requestId: string; message: RequestMessage }) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(
    () => () => {
      audioRef.current?.pause();
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    },
    [],
  );

  const play = () => {
    if (message.hasAudio) {
      const audio = new Audio(requestsApi.audioUrl(requestId, message.id));
      audioRef.current = audio;
      audio.onended = () => setPlaying(false);
      setPlaying(true);
      void audio.play().catch(() => setPlaying(false));
      return;
    }
    if (!("speechSynthesis" in window)) return;
    const u = new SpeechSynthesisUtterance(message.body);
    u.lang = "cs-CZ";
    const voice = window.speechSynthesis.getVoices().find((v) => v.lang.startsWith("cs"));
    if (voice) u.voice = voice;
    u.onend = () => setPlaying(false);
    window.speechSynthesis.cancel();
    setPlaying(true);
    window.speechSynthesis.speak(u);
  };

  return (
    <div className="flex items-center gap-2">
      <button type="button" className="nis-btn-secondary" onClick={play} disabled={playing}>
        <Icon name="phone" size="1.2em" />
        {playing ? cs.requestDrawer.playing : cs.requestDrawer.play}
      </button>
      {!message.hasAudio && <span className="text-xs text-nis-muted">{cs.requestDrawer.tts}</span>}
    </div>
  );
}

const TRACE_BASE = "http://localhost:52773/csp/healthshare/fhirserver/EnsPortal.VisualTrace.zen";

function traceUrl(known: string[] | undefined, sessionId: string): string {
  const hit = (known ?? []).find((u) => u.endsWith(`=${sessionId}`));
  return hit ?? `${known?.[0]?.split("?")[0] ?? TRACE_BASE}?SESSIONID=${encodeURIComponent(sessionId)}`;
}

const KIND_LABEL: Record<string, string> = {
  email: cs.requestDrawer.email,
  reminder: cs.requestDrawer.reminder,
  voice_call: cs.requestDrawer.voice,
  call_outcome: cs.requestDrawer.callOutcome,
  reply: cs.requestDrawer.reply,
  delivery: cs.requestDrawer.delivery,
};

function MessageCard({ requestId, m }: { requestId: string; m: RequestMessage }) {
  return (
    <article className="rounded-nis border border-nis-line p-3" data-message-kind={m.kind}>
      <header className="mb-1 flex flex-wrap items-center gap-2">
        <Icon name={m.channel === "phone" ? "phone" : m.direction === "in" ? "inbox" : "mail"} className="text-accent-600" />
        <span className="font-bold">{KIND_LABEL[m.kind] ?? m.kind}</span>
        <span className="text-xs text-nis-muted">{formatDateTime(m.ts)}</span>
        <SimulaceTag />
      </header>
      {m.subject && <div className="text-sm font-medium">{m.subject}</div>}
      {m.kind === "call_outcome" ? (
        <p className="text-sm">{cs.actions.callOutcomes[m.body] ?? m.body}</p>
      ) : (
        m.body && <pre className="mt-1 whitespace-pre-wrap font-sans text-sm text-nis-text">{m.body}</pre>
      )}
      {m.kind === "reply" && m.class && (
        <div className="mt-2 space-y-1 text-sm">
          <div>
            <span className="nis-label">{cs.requestDrawer.replyClass}: </span>
            <strong>{cs.requestDrawer.classes[m.class] ?? m.class}</strong>
            {m.method && <span className="text-xs text-nis-muted"> ({m.method})</span>}
          </div>
          {m.quote && (
            <div>
              <span className="nis-label">{cs.requestDrawer.replyQuote}: </span>
              <mark className="rounded-sm bg-[#ffe27a] px-0.5">„{m.quote}“</mark>
            </div>
          )}
        </div>
      )}
      {m.kind === "voice_call" && (
        <div className="mt-2">
          <VoicePlayer requestId={requestId} message={m} />
        </div>
      )}
    </article>
  );
}

export default function RequestDrawer({ requestId, onClose }: { requestId: string; onClose: () => void }) {
  const { data, isLoading, error } = useRequestDetail(requestId);
  const closeRef = useRef<HTMLButtonElement>(null);
  const t = cs.requestDrawer;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pred = data?.prediction;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="request-title">
      <div className="absolute inset-0 bg-nis-text/30" onClick={onClose} aria-hidden="true" />
      <aside className="relative flex h-full w-full max-w-3xl flex-col border-l border-nis-line bg-white shadow-lg">
        <div className="flex items-center justify-between gap-3 border-b border-nis-line px-4 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="request-title" className="text-base font-bold uppercase tracking-wide">
              {t.title} {requestId}
            </h2>
            {data && <StatusTag tone={REQUEST_TONE[data.state]}>{cs.requestState[data.state] ?? data.state}</StatusTag>}
            <SimulaceTag />
          </div>
          <button ref={closeRef} type="button" onClick={onClose} className="nis-btn-secondary">
            <Icon name="close" size="1.2em" />
            {cs.common.close}
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {isLoading && <p>{t.loading}</p>}
          {error && (
            <p role="alert" className="text-nis-red">
              {cs.common.error}: {error.message}
            </p>
          )}
          {data && (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                <Field label={cs.items.modality}>
                  {data.modality} · {regionsText((data.regions ?? "").split(",").filter(Boolean))}
                </Field>
                <Field label={cs.items.targetDate}>{formatDate(data.targetDate)}</Field>
                <Field label={t.provider}>{data.provider?.name ?? cs.common.none}</Field>
                <Field label={t.route}>{data.provider?.route ?? cs.common.none}</Field>
                <Field label={t.deadline}>{formatDate(data.deadline)}</Field>
                <Field label={t.approvedBy}>
                  {data.approvedBy ? `${data.approvedBy}, ${formatDateTime(data.approvedAt ?? "")}` : cs.common.none}
                </Field>
                <Field label={t.attempts}>{data.attempts ?? 0}</Field>
                <Field label={t.task}>
                  <code className="text-sm">{data.fhirTaskId ? `Task/${data.fhirTaskId}` : cs.common.none}</code>
                </Field>
                <Field label={t.prediction}>
                  {pred && (pred.late_probability != null || pred.expected_hours != null) ? (
                    <span>
                      {pred.late_probability != null && `${t.late} ${Math.round(pred.late_probability * 100)} %`}
                      {pred.expected_hours != null && ` · ${t.expected} ${Math.round(pred.expected_hours)} h`}
                      {pred.simulated && <span className="ml-1"><SimulaceTag /></span>}
                    </span>
                  ) : (
                    <span className="text-nis-muted">{t.noPrediction}</span>
                  )}
                </Field>
              </div>
              {data.verifyReason && (
                <p className="rounded-nis border border-nis-line px-2 py-1 text-sm">
                  <span className="nis-label">{t.verifyReason}: </span>
                  {data.verifyReason}
                </p>
              )}

              <section>
                <h3 className="mb-2 text-base font-bold">{t.messages}</h3>
                {data.messages.length === 0 ? (
                  <p className="text-nis-muted">{t.noMessages}</p>
                ) : (
                  <div className="space-y-2">
                    {data.messages.map((m) => (
                      <MessageCard key={m.id} requestId={requestId} m={m} />
                    ))}
                  </div>
                )}
              </section>

              <section>
                <h3 className="mb-2 text-base font-bold">{t.history}</h3>
                <DataTable>
                  <thead>
                    <tr>
                      <th>{t.time}</th>
                      <th>{t.actor}</th>
                      <th>{t.transition}</th>
                      <th>{t.note}</th>
                      <th>{t.visualTrace}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.map((h, i) => (
                      <tr key={`${h.ts}-${i}`}>
                        <td className="whitespace-nowrap">{formatDateTime(h.ts)}</td>
                        <td>{t.actors[h.actor] ?? h.actor}</td>
                        <td className="whitespace-nowrap">
                          {h.from ? `${cs.requestState[h.from as keyof typeof cs.requestState] ?? h.from} → ` : ""}
                          <strong>{cs.requestState[h.to as keyof typeof cs.requestState] ?? h.to}</strong>
                        </td>
                        <td className="text-sm">{h.note}</td>
                        <td>
                          {h.sessionId && (
                            <a
                              className="inline-flex items-center gap-1 text-accent-700 underline"
                              target="_blank"
                              rel="noreferrer"
                              href={traceUrl(data.visualTrace, h.sessionId)}
                            >
                              <Icon name="external" size="1em" />
                              {t.session(h.sessionId)}
                            </a>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
