import { Fragment, useEffect, useMemo, useRef } from "react";
import { cs } from "../i18n/cs";
import { useSourceDocument } from "../services/api";
import { formatDate } from "./format";
import { Icon } from "./ui";

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Finds the quote ignoring differences in whitespace; returns [start, end) or null. */
export function findQuote(text: string, quote: string): [number, number] | null {
  const words = quote.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return null;
  const m = new RegExp(words.map(escapeRe).join("\\s+")).exec(text);
  return m ? [m.index, m.index + m[0].length] : null;
}

export default function SourceDrawer({
  caseId,
  docId,
  quote,
  onClose,
}: {
  caseId: string;
  docId: string;
  quote: string | null;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useSourceDocument(caseId, docId);
  const markRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const span = useMemo(() => (data && quote ? findQuote(data.text, quote) : null), [data, quote]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center" });
  }, [span, data]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <div className="absolute inset-0 bg-nis-text/30" onClick={onClose} aria-hidden="true" />
      <aside className="relative flex h-full w-full max-w-2xl flex-col border-l border-nis-line bg-white shadow-lg">
        <div className="flex items-center justify-between gap-3 border-b border-nis-line px-4 py-2.5">
          <div>
            <h2 id="drawer-title" className="text-base font-bold uppercase tracking-wide">
              {cs.drawer.title}
            </h2>
            {data && (
              <p className="text-sm text-nis-muted">
                {cs.drawer.kind}: {data.kind} · {cs.drawer.date}: {formatDate(data.date)}
              </p>
            )}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="nis-btn-secondary"
          >
            <Icon name="close" size="1.2em" />
            {cs.common.close}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {isLoading && <p>{cs.drawer.loading}</p>}
          {error && (
            <p role="alert" className="text-nis-red">
              {cs.common.error}: {error.message}
            </p>
          )}
          {data && (
            <>
              {quote && !span && (
                <p className="nis-row-attention mb-3 rounded-nis border border-nis-amber p-2 text-sm">
                  {cs.drawer.quoteNotFound}
                </p>
              )}
              <p className="whitespace-pre-wrap text-lg leading-relaxed text-nis-text">
                {span ? (
                  <Fragment>
                    {data.text.slice(0, span[0])}
                    <mark ref={markRef} className="rounded-sm bg-[#ffe27a] px-0.5 font-medium text-nis-text ring-1 ring-nis-amber">
                      {data.text.slice(span[0], span[1])}
                    </mark>
                    {data.text.slice(span[1])}
                  </Fragment>
                ) : (
                  data.text
                )}
              </p>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
