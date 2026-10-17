import { useState } from "react";
import { cs } from "../i18n/cs";
import type { OpenIssue } from "../services/api-types";
import { getCoordinator, requestsApi, setCoordinator, useAction } from "../services/requestsApi";
import { Icon, Panel } from "./ui";

/** Open issues; the coordinator can acknowledge one (who, when), after which it no longer blocks readiness. */
export default function OpenIssuesPanel({ issues, caseId }: { issues: OpenIssue[]; caseId?: string }) {
  const [name, setName] = useState(getCoordinator());
  const ack = useAction((args: { key: string; coordinator: string }) =>
    requestsApi.acknowledge(caseId as string, args.key, args.coordinator),
  );
  const open = issues.filter((i) => !i.acknowledged);

  return (
    <Panel id="issues" icon="warning" title={cs.issues.title} bodyClassName={issues.length ? "" : "p-3"}>
      {issues.length === 0 ? (
        <p className="text-nis-muted">{cs.issues.empty}</p>
      ) : (
        <ul>
          {issues.map((issue, i) => (
            <li
              key={issue.key ?? i}
              className={`flex items-start gap-2 border-b border-nis-line px-3 py-2 last:border-b-0 ${
                issue.acknowledged ? "bg-white text-nis-muted" : "nis-row-attention"
              }`}
            >
              <Icon name="warning" className={`mt-0.5 ${issue.acknowledged ? "text-nis-muted" : "text-[#9a6b00]"}`} />
              <span className="flex-1">
                <span className="font-bold">{cs.issueType[issue.type] ?? issue.type}:</span> {issue.text}
                {issue.acknowledged && (
                  <span className="ml-2 text-sm">
                    ({cs.issues.acknowledged}
                    {issue.ack_note ? ` – ${issue.ack_note}` : ""})
                  </span>
                )}
              </span>
              {!issue.acknowledged && caseId && issue.key && (
                <button
                  type="button"
                  className="nis-btn-secondary shrink-0"
                  disabled={ack.isPending || !name.trim()}
                  onClick={() => {
                    setCoordinator(name);
                    ack.mutate({ key: issue.key as string, coordinator: name.trim() });
                  }}
                >
                  {cs.issues.acknowledge}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {open.length > 0 && caseId && (
        <div className="flex items-center gap-2 border-t border-nis-line px-3 py-2 text-sm">
          <label htmlFor="ack-coordinator" className="text-nis-muted">
            {cs.issues.coordinatorPrompt}
          </label>
          <input
            id="ack-coordinator"
            className="nis-input max-w-xs"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
      )}
    </Panel>
  );
}
