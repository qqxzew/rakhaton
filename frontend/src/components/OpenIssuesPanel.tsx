import { cs } from "../i18n/cs";
import type { OpenIssue } from "../services/api-types";
import { Icon, Panel } from "./ui";

export default function OpenIssuesPanel({ issues }: { issues: OpenIssue[] }) {
  return (
    <Panel id="issues" icon="warning" title={cs.issues.title} bodyClassName={issues.length ? "" : "p-3"}>
      {issues.length === 0 ? (
        <p className="text-nis-muted">{cs.issues.empty}</p>
      ) : (
        <ul>
          {issues.map((issue, i) => (
            <li key={i} className="nis-row-attention flex items-start gap-2 border-b border-nis-line px-3 py-2 last:border-b-0">
              <Icon name="warning" className="mt-0.5 text-[#9a6b00]" />
              <span>
                <span className="font-bold">{cs.issueType[issue.type] ?? issue.type}:</span> {issue.text}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
