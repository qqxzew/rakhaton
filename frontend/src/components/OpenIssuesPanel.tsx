import { cs } from "../i18n/cs";
import type { OpenIssue } from "../services/api-types";

export default function OpenIssuesPanel({ issues }: { issues: OpenIssue[] }) {
  return (
    <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm" aria-labelledby="issues-title">
      <h2 id="issues-title" className="mb-2 text-xl font-bold">
        {cs.issues.title}
      </h2>
      {issues.length === 0 ? (
        <p className="text-slate-600">{cs.issues.empty}</p>
      ) : (
        <ul className="space-y-2">
          {issues.map((issue, i) => (
            <li key={i} className="flex gap-2 rounded border-l-4 border-amber-600 bg-amber-50 p-2">
              <span aria-hidden="true">⚠</span>
              <span>
                <span className="font-semibold">{cs.issueType[issue.type] ?? issue.type}:</span> {issue.text}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
