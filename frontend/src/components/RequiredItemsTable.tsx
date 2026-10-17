import { cs } from "../i18n/cs";
import type { RequiredItem } from "../services/api-types";
import AvailabilityChip from "./AvailabilityChip";
import { formatItemDate, percent, regionsText } from "./format";
import RequestProgress from "./RequestProgress";
import SimulaceTag from "./SimulaceTag";
import { DataTable, ITEM_ROW, Panel } from "./ui";

export default function RequiredItemsTable({
  items,
  onOpenSource,
}: {
  items: RequiredItem[];
  onOpenSource: (docId: string, quote: string | null) => void;
}) {
  return (
    <Panel id="items" icon="list" title={cs.items.title} bodyClassName={items.length ? "" : "p-3"}>
      {items.length === 0 ? (
        <p className="text-nis-muted">{cs.items.empty}</p>
      ) : (
        <DataTable>
          <thead>
            <tr>
              <th>{cs.items.reasons}</th>
              <th>{cs.items.modality}</th>
              <th>{cs.items.region}</th>
              <th>{cs.items.targetDate}</th>
              <th>{cs.items.availability}</th>
              <th>{cs.items.holdingSite}</th>
              <th>{cs.items.evidence}</th>
              <th>{cs.items.request}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className={ITEM_ROW[item.state]} data-item-state={item.state}>
                <td>
                  <ul className="space-y-0.5">
                    {item.reasons.map((r) => (
                      <li key={r} className="font-medium">
                        {r}
                      </li>
                    ))}
                  </ul>
                  {item.simulated && (
                    <div className="mt-1">
                      <SimulaceTag />
                    </div>
                  )}
                </td>
                <td className="font-bold">{item.modality}</td>
                <td>{regionsText(item.regions)}</td>
                <td className="whitespace-nowrap font-medium text-accent-700">
                  {formatItemDate(item.target_date, item.target_date_precision)}
                </td>
                <td>
                  <AvailabilityChip availability={item.availability} />
                </td>
                <td>
                  {item.holding_site?.name ?? cs.items.unknownSite}
                  {item.holding_site_basis === "text_near_date" && (
                    <span className="ml-1 text-xs text-nis-muted">({cs.items.siteFromText})</span>
                  )}
                </td>
                <td className="max-w-xs">
                  {item.evidence ? (
                    <>
                      <button
                        type="button"
                        onClick={() => onOpenSource(item.evidence!.doc_id, item.evidence!.quote)}
                        className="text-left italic text-accent-700 underline decoration-dotted underline-offset-4 hover:text-accent-600"
                      >
                        „{item.evidence.quote}“
                      </button>
                      <div className="text-xs text-nis-muted">
                        {cs.common.confidence}: {percent(item.evidence.confidence)}
                      </div>
                    </>
                  ) : (
                    <span className="text-nis-muted">{cs.items.noEvidence}</span>
                  )}
                </td>
                <td>
                  <RequestProgress request={item.request} />
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Panel>
  );
}
