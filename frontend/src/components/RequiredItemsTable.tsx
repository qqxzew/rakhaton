import { cs } from "../i18n/cs";
import type { RequiredItem } from "../services/api-types";
import AvailabilityChip from "./AvailabilityChip";
import { formatItemDate, percent, regionsText } from "./format";
import RequestProgress from "./RequestProgress";
import SimulaceTag from "./SimulaceTag";

export default function RequiredItemsTable({
  items,
  onOpenSource,
}: {
  items: RequiredItem[];
  onOpenSource: (docId: string, quote: string | null) => void;
}) {
  return (
    <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm" aria-labelledby="items-title">
      <h2 id="items-title" className="mb-2 text-xl font-bold">
        {cs.items.title}
      </h2>
      {items.length === 0 ? (
        <p className="text-slate-600">{cs.items.empty}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left align-top">
            <thead>
              <tr className="border-b-2 border-slate-300 text-sm text-slate-700">
                <th className="py-2 pr-3">{cs.items.reasons}</th>
                <th className="py-2 pr-3">{cs.items.modality}</th>
                <th className="py-2 pr-3">{cs.items.region}</th>
                <th className="py-2 pr-3">{cs.items.targetDate}</th>
                <th className="py-2 pr-3">{cs.items.availability}</th>
                <th className="py-2 pr-3">{cs.items.holdingSite}</th>
                <th className="py-2 pr-3">{cs.items.evidence}</th>
                <th className="py-2">{cs.items.request}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-slate-200 align-top">
                  <td className="py-2 pr-3">
                    <ul className="list-disc pl-4">
                      {item.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                    {item.simulated && (
                      <div className="mt-1">
                        <SimulaceTag />
                      </div>
                    )}
                  </td>
                  <td className="py-2 pr-3 font-semibold">{item.modality}</td>
                  <td className="py-2 pr-3">{regionsText(item.regions)}</td>
                  <td className="py-2 pr-3 whitespace-nowrap">{formatItemDate(item.target_date, item.target_date_precision)}</td>
                  <td className="py-2 pr-3">
                    <AvailabilityChip availability={item.availability} />
                  </td>
                  <td className="py-2 pr-3">
                    {item.holding_site?.name ?? cs.items.unknownSite}
                    {item.holding_site_basis === "text_near_date" && (
                      <span className="ml-1 text-xs text-slate-500">({cs.items.siteFromText})</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 max-w-xs">
                    {item.evidence ? (
                      <>
                        <button
                          type="button"
                          onClick={() => onOpenSource(item.evidence!.doc_id, item.evidence!.quote)}
                          className="text-left italic text-accent-700 underline decoration-dotted underline-offset-4 hover:text-accent-600"
                        >
                          „{item.evidence.quote}“
                        </button>
                        <div className="text-sm text-slate-600">
                          {cs.common.confidence}: {percent(item.evidence.confidence)}
                        </div>
                      </>
                    ) : (
                      <span className="text-slate-600">{cs.items.noEvidence}</span>
                    )}
                  </td>
                  <td className="py-2">
                    <RequestProgress request={item.request} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
