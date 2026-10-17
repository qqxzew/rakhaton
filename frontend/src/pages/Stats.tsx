import { cs } from "../i18n/cs";
import { useEvaluation } from "../services/requestsApi";
import { systemApi, useSystemSection, type SqlStats } from "../services/systemApi";
import SimulaceTag from "../components/SimulaceTag";
import { DataTable, ErrorState, Panel, SectionHeader, StatChip, Tag } from "../components/ui";

function CountTable({ title, data, simulated = false }: { title: string; data: Record<string, number>; simulated?: boolean }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <Panel title={<>{title} {simulated && <SimulaceTag />}</>} bodyClassName="">
      {rows.length === 0 ? (
        <p className="p-3 text-nis-muted">{cs.common.none}</p>
      ) : (
        <DataTable>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td>{k || cs.common.unknown}</td>
                <td className="text-right font-bold">{v}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Panel>
  );
}

const pct = (v: number | null | undefined) => (v == null ? cs.common.none : `${v.toLocaleString("cs-CZ")} %`);

export default function Stats() {
  const t = cs.stats;
  const sql = useSystemSection<SqlStats>("stats", () => systemApi.stats());
  const ev = useEvaluation();
  const s = sql.data;
  const e = ev.data;

  return (
    <div className="space-y-3">
      <SectionHeader icon="chart" title={t.title} />
      <p className="text-nis-muted">{t.subtitle}</p>

      <Panel id="ai-quality" icon="pulse" title={t.aiTitle}>
        {ev.isLoading ? (
          <p className="text-nis-muted">{cs.app.loading}</p>
        ) : !e || !e.available ? (
          <p className="text-nis-muted">
            {t.aiDown}
            {e?.reason ? ` (${e.reason})` : ""}
          </p>
        ) : (
          <div className="space-y-3">
            <Tag tone="amber">{e.label ?? t.aiLabel}</Tag>
            <div className="flex flex-wrap gap-2">
              <StatChip icon="document" label={t.reports} value={e.reports ?? 0} />
              <StatChip icon="list" label={t.citations} value={e.silver_citations ?? 0} />
              <StatChip icon="checkCircle" label={t.recall} value={pct(e.recall_pct)} />
              <StatChip icon="calendar" label={t.dateAccuracy} value={pct(e.date_accuracy_given_modality_pct)} />
              <StatChip icon="database" label={t.inDataset} value={pct(e.in_dataset_pct)} />
              <StatChip icon="warning" label={t.naive} value={pct(e.naive_latest_same_modality_pct)} />
            </div>
          </div>
        )}
      </Panel>

      {sql.error ? (
        <ErrorState message={`${t.sqlDown}: ${sql.error.message}`} retryLabel={cs.common.retry} onRetry={() => void sql.refetch()} />
      ) : !s ? (
        <p className="nis-panel p-4 text-nis-muted">{cs.app.loading}</p>
      ) : (
        <>
          <Panel id="sql-stats" icon="database" title={t.sqlTitle}>
            <p className="mb-2 text-sm text-nis-muted">{t.sqlSource}</p>
            <div className="flex flex-wrap gap-2">
              <StatChip icon="scan" label={cs.system.integration.sqlRows.studies} value={s.studies.total} />
              <StatChip icon="checkCircle" label={cs.system.integration.sqlRows.inPacs} value={s.studies.in_pacs} />
              <StatChip icon="crossCircle" label={cs.system.integration.sqlRows.notInPacs} value={s.studies.not_in_pacs} />
              <StatChip icon="question" label={cs.system.integration.sqlRows.pacsUnknown} value={s.studies.pacs_unknown} />
              <StatChip icon="list" label={cs.system.integration.sqlRows.openTasks} value={s.open_tasks.total} />
              <StatChip icon="document" label={cs.system.integration.sqlRows.citedPriors} value={s.cited_priors.total} />
              <StatChip icon="warning" label={cs.system.integration.sqlRows.citedNotFound} value={s.cited_priors.not_found} />
            </div>
          </Panel>
          <div className="grid gap-3 md:grid-cols-2">
            <CountTable title={t.perModality} data={s.studies.per_modality} />
            <CountTable title={t.planned} data={s.planned_exams_per_modality} />
            <CountTable title={t.openTasks} data={s.open_tasks.per_state} />
            <CountTable title={t.perHospital} data={s.requests_per_hospital} simulated />
          </div>
        </>
      )}
    </div>
  );
}
