import { useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { cs } from "../i18n/cs";
import SimulaceTag from "../components/SimulaceTag";
import { formatDate } from "../components/format";
import { Button, DataTable, Field, Icon, Muted, Panel, SectionHeader, Tag, type IconName } from "../components/ui";
import {
  systemApi,
  useCasePatients,
  useSystemSection,
  type Availability,
  type FhirOverview,
  type ProductionOverview,
  type SqlStats,
} from "../services/systemApi";

const t = cs.system.integration;
const MODALITIES = ["CT", "MR", "PET", "RTG", "SONO", "MAMO"];
const NODES = [
  { id: "motol", label: "MOTOL (FN Motol)" },
  { id: "nnh", label: "NNH" },
  { id: "homolka", label: "HOMOLKA" },
  { id: "fnm", label: "FNM" },
];

function ExtLink({ href, children }: { href?: string | null; children: ReactNode }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-sm font-medium text-accent-600 hover:underline"
    >
      {children}
      <Icon name="external" />
    </a>
  );
}

/** Loading / error / unavailable states shared by all panels. */
function Section<T extends Availability>({
  title,
  icon,
  query,
  actions,
  className = "",
  bodyClassName,
  children,
}: {
  title: string;
  icon: IconName;
  query: { data?: T; isLoading: boolean; error: Error | null };
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: (data: T) => ReactNode;
}) {
  const { data, isLoading, error } = query;
  let body: ReactNode;
  if (isLoading) body = <Muted>{cs.app.loading}</Muted>;
  else if (error || !data) body = <p className="text-nis-red">{`${cs.common.error}: ${error?.message ?? ""}`}</p>;
  else if (!data.available)
    body = (
      <p className="flex items-start gap-2 text-nis-ink">
        <Icon name="crossCircle" className="mt-0.5 shrink-0 text-nis-red" />
        {cs.system.unavailable}: {data.reason}
      </p>
    );
  else body = children(data);
  const raw = !isLoading && data?.available;
  return (
    <Panel title={title} icon={icon} actions={actions} className={className} bodyClassName={raw ? bodyClassName : "p-3"}>
      {body}
    </Panel>
  );
}

export default function Integration() {
  return (
    <div className="space-y-3">
      <SectionHeader icon="network" title={t.title} subtitle={t.subtitle} />
      <div className="grid gap-3 xl:grid-cols-2">
        <FhirPanel />
        <ProductionPanel />
      </div>
      <ActionsPanel />
      <VectorPanel />
      <div className="grid gap-3 xl:grid-cols-3">
        <SqlPanel />
        <MlPanel />
        <McpPanel />
      </div>
    </div>
  );
}

function FhirPanel() {
  const q = useSystemSection<FhirOverview>("fhir", systemApi.fhir, 30_000);
  return (
    <Section
      title={t.fhir}
      icon="database"
      query={q}
      bodyClassName=""
      actions={
        <>
          <ExtLink href={q.data?.portal_url}>{t.portal}</ExtLink>
          <ExtLink href={q.data?.metadata_url}>{t.metadata}</ExtLink>
        </>
      }
    >
      {(d) => (
        <>
          <div className="border-b border-nis-line px-3 py-1.5 font-mono text-sm text-nis-ink">{d.base}</div>
          <DataTable>
            <thead>
              <tr>
                <th>{t.resource}</th>
                <th className="text-right">{t.count}</th>
              </tr>
            </thead>
            <tbody>
              {d.resources?.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td className="text-right font-medium tabular-nums">{r.count.toLocaleString("cs-CZ")}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          <div className="flex items-center gap-2 border-t border-nis-line px-3 py-1.5">
            <span className="nis-label">{t.hospitalEndpoints}</span>
            <SimulaceTag />
          </div>
          <DataTable>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th className="text-right">Patient</th>
                <th className="text-right">ImagingStudy</th>
                <th className="text-right">DiagnosticReport</th>
              </tr>
            </thead>
            <tbody>
              {d.hospitals?.map((h) => (
                <tr key={h.id} className={h.available ? "" : "nis-row-danger"}>
                  <td>
                    <div className="font-medium">{h.name}</div>
                    <div className="font-mono text-xs text-nis-muted">{h.base}</div>
                  </td>
                  {["Patient", "ImagingStudy", "DiagnosticReport"].map((rt) => (
                    <td key={rt} className="text-right tabular-nums">
                      {h.available ? h.counts[rt] : cs.system.unavailable}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </DataTable>
        </>
      )}
    </Section>
  );
}

const KIND_TONE: Record<string, "blue" | "teal" | "slate" | "gray"> = {
  service: "blue",
  process: "teal",
  operation: "slate",
  other: "gray",
};

function ProductionPanel() {
  const q = useSystemSection<ProductionOverview>("production", systemApi.production, 10_000);
  return (
    <Section
      title={t.production}
      icon="pulse"
      query={q}
      bodyClassName=""
      actions={
        <>
          <ExtLink href={q.data?.config_url}>{t.config}</ExtLink>
          <ExtLink href={q.data?.messages_url}>{t.messageViewer}</ExtLink>
        </>
      }
    >
      {(d) => (
        <>
          <div className="flex flex-wrap items-center gap-2 border-b border-nis-line px-3 py-1.5">
            <span className="font-mono text-sm font-medium text-nis-text">{d.name}</span>
            <span className="text-sm text-nis-muted">· {d.namespace}</span>
            <Tag tone={d.running ? "green" : "red"} icon={d.running ? "checkCircle" : "crossCircle"}>
              {d.running ? t.running : t.stopped}
            </Tag>
          </div>
          <div className="nis-label px-3 pt-2">
            {t.items} ({d.items?.length ?? 0})
          </div>
          <ul className="flex flex-wrap gap-1.5 px-3 pb-2 pt-1">
            {d.items?.map((i) => (
              <li
                key={i.name}
                title={`${i.class_name} · ${i.enabled ? t.enabled : t.disabled}`}
                className={`inline-flex items-center gap-1.5 rounded-nis border px-2 py-0.5 text-sm ${
                  i.enabled ? "border-nis-line bg-white" : "border-dashed border-nis-line bg-[#f3f4f6] text-nis-muted"
                }`}
              >
                <Tag tone={KIND_TONE[i.kind] ?? "gray"} className="text-2xs">
                  {t.kinds[i.kind] ?? i.kind}
                </Tag>
                {(i.name ?? "").replace(/^PacsComparator\./, "")}
                {!i.enabled && <span className="text-xs">({t.disabled})</span>}
              </li>
            ))}
          </ul>
          <div className="nis-label border-t border-nis-line px-3 pt-2">{t.messages}</div>
          <DataTable>
            <thead>
              <tr>
                <th>{t.time}</th>
                <th>{t.source}</th>
                <th>{t.target}</th>
                <th>{t.bodyClass}</th>
                <th>{t.session}</th>
              </tr>
            </thead>
            <tbody>
              {d.messages?.map((m) => (
                <tr key={m.id} className={m.status === "Error" ? "nis-row-danger" : ""}>
                  <td className="whitespace-nowrap text-sm">{m.time?.slice(11, 19) ?? cs.common.none}</td>
                  <td className="text-sm">{(m.source ?? "").replace(/^PacsComparator\./, "")}</td>
                  <td className="text-sm">{(m.target ?? "").replace(/^PacsComparator\./, "")}</td>
                  <td className="text-xs text-nis-ink">{(m.body_class ?? "").replace(/^PacsComparator\./, "")}</td>
                  <td className="whitespace-nowrap">
                    {m.visual_trace_url ? (
                      <a
                        href={m.visual_trace_url}
                        target="_blank"
                        rel="noreferrer"
                        title={t.visualTrace}
                        className="inline-flex items-center gap-1 text-sm text-accent-600 hover:underline"
                      >
                        {m.session_id}
                        <Icon name="external" />
                      </a>
                    ) : (
                      cs.common.none
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </>
      )}
    </Section>
  );
}

function PatientSelect({ id, value, onChange, optional }: { id: string; value: string; onChange: (v: string) => void; optional?: boolean }) {
  const { data } = useCasePatients();
  return (
    <select id={id} className="nis-input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{optional ? t.anyPatient : t.choosePatient}</option>
      {data?.patients.map((p) => (
        <option key={p.patient_id} value={p.patient_id}>
          {p.display_name} · {p.patient_id}
        </option>
      ))}
    </select>
  );
}

function ResultBox({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <div role="status" className={`mt-2 rounded-nis border px-3 py-2 text-sm ${ok ? "nis-row-ready border-[#b9d9a6]" : "nis-row-danger border-[#efb3b3]"}`}>
      {children}
    </div>
  );
}

function ActionsPanel() {
  return (
    <Panel title={t.actions} icon="send" actions={<SimulaceTag />}>
      <p className="mb-3 text-sm text-nis-muted">{t.actionsHint}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Hl7Action />
        <CFindAction />
      </div>
    </Panel>
  );
}

function Hl7Action() {
  const [patient, setPatient] = useState("");
  const [modality, setModality] = useState("CT");
  const [days, setDays] = useState(14);
  const m = useMutation({ mutationFn: () => systemApi.hl7Orm({ patient_id: patient, modality, days }) });
  const d = m.data;
  return (
    <form
      className="rounded-nis border border-nis-line p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (patient) m.mutate();
      }}
    >
      <h3 className="mb-2 flex items-center gap-2 font-bold text-nis-text">
        <Icon name="mail" className="text-accent-600" />
        {t.sendHl7}
        <span className="text-sm font-normal text-nis-muted">ORM^O01 → MLLP → FHIR ServiceRequest</span>
      </h3>
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[14rem] flex-1">
          <label htmlFor="hl7-patient" className="nis-label block">{t.patient}</label>
          <PatientSelect id="hl7-patient" value={patient} onChange={setPatient} />
        </div>
        <div>
          <label htmlFor="hl7-modality" className="nis-label block">{t.modality}</label>
          <select id="hl7-modality" className="nis-input" value={modality} onChange={(e) => setModality(e.target.value)}>
            {MODALITIES.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </div>
        <div className="w-24">
          <label htmlFor="hl7-days" className="nis-label block">{t.days}</label>
          <input
            id="hl7-days"
            type="number"
            min={0}
            max={365}
            className="nis-input"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          />
        </div>
        <Button type="submit" variant="primary" icon="send" disabled={!patient || m.isPending}>
          {m.isPending ? t.sending : t.sendHl7}
        </Button>
      </div>
      {m.isError && <ResultBox ok={false}>{m.error.message}</ResultBox>}
      {d && !d.available && <ResultBox ok={false}>{d.reason}</ResultBox>}
      {d && d.available && (
        <ResultBox ok={!!d.accepted}>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <Field label={t.ack}>
              <Tag tone={d.accepted ? "green" : "red"}>{d.ack}</Tag> {d.message_type}
              <span className="ml-1 text-sm text-nis-muted">{d.accepted ? t.ackOk : t.ackFail}</span>
            </Field>
            <Field label={t.serviceRequest}>
              <span className="font-mono text-sm">{d.service_request ?? t.notYet}</span>
            </Field>
            <Field label={t.segments} className="col-span-2">
              <span className="font-mono text-sm">{d.segments?.join(" · ")}</span>
            </Field>
          </div>
          <div className="mt-1">
            <ExtLink href={d.messages_url}>{t.messageViewer}</ExtLink>
          </div>
        </ResultBox>
      )}
    </form>
  );
}

function CFindAction() {
  const [patient, setPatient] = useState("");
  const [node, setNode] = useState("motol");
  const [modality, setModality] = useState("");
  const m = useMutation({
    mutationFn: () => systemApi.cfind({ patient_id: patient, node, ...(modality ? { modality } : {}) }),
  });
  const d = m.data;
  return (
    <form
      className="rounded-nis border border-nis-line p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (patient) m.mutate();
      }}
    >
      <h3 className="mb-2 flex items-center gap-2 font-bold text-nis-text">
        <Icon name="scan" className="text-accent-600" />
        {t.cfind}
        <span className="text-sm font-normal text-nis-muted">IRIS PACSDICOM → Orthanc (study level)</span>
      </h3>
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[14rem] flex-1">
          <label htmlFor="cf-patient" className="nis-label block">{t.patient}</label>
          <PatientSelect id="cf-patient" value={patient} onChange={setPatient} />
        </div>
        <div>
          <label htmlFor="cf-node" className="nis-label block">{t.node}</label>
          <select id="cf-node" className="nis-input" value={node} onChange={(e) => setNode(e.target.value)}>
            {NODES.map((n) => (
              <option key={n.id} value={n.id}>
                {n.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="cf-modality" className="nis-label block">{t.modality}</label>
          <select id="cf-modality" className="nis-input" value={modality} onChange={(e) => setModality(e.target.value)}>
            <option value="">{t.anyModality}</option>
            {MODALITIES.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </div>
        <Button type="submit" variant="primary" icon="search" disabled={!patient || m.isPending}>
          {m.isPending ? t.running2 : t.runCfind}
        </Button>
      </div>
      {m.isError && <ResultBox ok={false}>{m.error.message}</ResultBox>}
      {d && !d.available && <ResultBox ok={false}>{d.reason}</ResultBox>}
      {d && d.available && (
        <ResultBox ok>
          <div className="mb-1 flex flex-wrap gap-x-3 text-sm">
            <b>AE {d.ae}</b>
            <span>{t.matches(d.matches?.length ?? 0)}</span>
            <span className="text-nis-muted">
              {t.client}: {d.client} · {t.elapsed(d.elapsed_ms ?? 0)}
            </span>
          </div>
          {(d.matches?.length ?? 0) > 0 && (
            <ul className="flex flex-wrap gap-1.5">
              {d.matches?.map((x, i) => (
                <li key={i}>
                  <Tag tone="outline">
                    {formatDate(x.study_date)} · {x.modality ?? "?"}
                  </Tag>
                </li>
              ))}
            </ul>
          )}
        </ResultBox>
      )}
    </form>
  );
}

function VectorPanel() {
  const [q, setQ] = useState("");
  const [patient, setPatient] = useState("");
  const [withText, setWithText] = useState(false);
  const m = useMutation({ mutationFn: () => systemApi.vectorSearch(q.trim(), patient, withText) });
  const d = m.data;
  return (
    <Panel title={t.vector} icon="search" actions={<span className="text-sm text-nis-muted">{t.vectorHint}</span>}>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim().length >= 2) m.mutate();
        }}
      >
        <div className="min-w-[18rem] flex-[2]">
          <label htmlFor="vs-q" className="nis-label block">{t.query}</label>
          <input id="vs-q" className="nis-input" placeholder={t.queryPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="min-w-[14rem] flex-1">
          <label htmlFor="vs-patient" className="nis-label block">{t.patient}</label>
          <PatientSelect id="vs-patient" value={patient} onChange={setPatient} optional />
        </div>
        <label className="flex h-9 items-center gap-2 text-base text-nis-text">
          <input type="checkbox" checked={withText} onChange={(e) => setWithText(e.target.checked)} />
          {t.includeText}
        </label>
        <Button type="submit" variant="primary" icon="search" disabled={q.trim().length < 2 || m.isPending}>
          {m.isPending ? cs.app.loading : t.search}
        </Button>
      </form>
      {m.isError && <ResultBox ok={false}>{m.error.message}</ResultBox>}
      {d && !d.available && <ResultBox ok={false}>{d.reason}</ResultBox>}
      {d && d.available && (
        <div className="mt-3">
          <div className="mb-1 text-sm text-nis-muted">
            {d.table} · {t.elapsed(d.elapsed_ms ?? 0)}
          </div>
          {d.hits.length === 0 ? (
            <Muted>{t.noHits}</Muted>
          ) : (
            <DataTable>
              <thead>
                <tr>
                  <th className="text-right">{t.score}</th>
                  <th>{t.sourceType}</th>
                  <th>{t.date}</th>
                  <th>{t.modality}</th>
                  <th>{t.snippet}</th>
                </tr>
              </thead>
              <tbody>
                {d.hits.map((h) => (
                  <tr key={h.id}>
                    <td className="text-right font-bold tabular-nums">{h.score.toFixed(3)}</td>
                    <td className="whitespace-nowrap text-sm">{h.source_type}</td>
                    <td className="whitespace-nowrap">{formatDate(h.date)}</td>
                    <td>{h.modality ?? cs.common.none}</td>
                    <td className="text-sm text-nis-ink">{h.snippet ?? <span className="text-nis-muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          )}
        </div>
      )}
    </Panel>
  );
}

function sqlRows(s: SqlStats): [string, number][] {
  const r = t.sqlRows;
  return [
    [r.studies, s.studies.total],
    [r.inPacs, s.studies.in_pacs],
    [r.notInPacs, s.studies.not_in_pacs],
    [r.pacsUnknown, s.studies.pacs_unknown],
    [r.openTasks, s.open_tasks.total],
    [r.citedPriors, s.cited_priors.total],
    [r.citedNotFound, s.cited_priors.not_found],
    [r.plannedExams, Object.values(s.planned_exams_per_modality).reduce((a, b) => a + b, 0)],
  ];
}

function SqlPanel() {
  const q = useSystemSection("sql", systemApi.sql, 60_000);
  return (
    <Section title={t.sql} icon="chart" query={q} bodyClassName="">
      {(d) =>
        d.stats && (
          <>
            <div className="border-b border-nis-line px-3 py-1.5 text-sm text-nis-muted">{t.sqlSource}</div>
            <DataTable>
              <thead>
                <tr>
                  <th>{t.metric}</th>
                  <th className="text-right">{t.value}</th>
                </tr>
              </thead>
              <tbody>
                {sqlRows(d.stats).map(([label, value]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td className="text-right font-medium tabular-nums">{value.toLocaleString("cs-CZ")}</td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
            <div className="border-t border-nis-line px-3 py-2">
              <div className="nis-label mb-1">{t.perModality}</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(d.stats.studies.per_modality).map(([mod, n]) => (
                  <Tag key={mod} tone="outline">
                    {mod} {n}
                  </Tag>
                ))}
              </div>
            </div>
          </>
        )
      }
    </Section>
  );
}

function MlPanel() {
  const q = useSystemSection("ml", systemApi.ml);
  return (
    <Section title={t.ml} icon="chart" query={q} actions={<SimulaceTag />}>
      {(d) => (
        <div className="space-y-3">
          <div className="text-sm text-nis-muted">
            {d.source === "documented" ? t.mlDocumented : `${t.mlSource}: ${d.source}`}
          </div>
          {d.models.map((m) => (
            <div key={m.model} className="rounded-nis border border-nis-line p-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-bold text-nis-text">{m.model}</span>
                <Tag tone="gray">{m.kind}</Tag>
              </div>
              <div className="text-sm text-nis-muted">
                {t.predicts}: {m.predicts}
              </div>
              <dl className="mt-1.5 flex flex-wrap gap-1.5">
                {Object.entries(m.metrics).map(([k, v]) => (
                  <div key={k} className="rounded-nis bg-accent-50 px-2 py-0.5 text-sm">
                    <dt className="inline text-nis-ink">{k} </dt>
                    <dd className="inline font-bold text-accent-700">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function McpPanel() {
  const q = useSystemSection("mcp", systemApi.mcp, false);
  return (
    <Section title={t.mcp} icon="chat" query={q} bodyClassName="">
      {(d) => (
        <>
          <div className="border-b border-nis-line px-3 py-1.5 text-sm text-nis-muted">
            <span className="font-mono">{d.server}</span> · {d.transports.join(" · ")}
          </div>
          <ul className="divide-y divide-nis-line">
            {d.tools.map((tool) => (
              <li key={tool.name} className="px-3 py-1.5">
                <div className="font-mono text-sm font-bold text-accent-700">{tool.name}</div>
                <div className="text-sm text-nis-ink">{tool.description.split(". ")[0]}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Section>
  );
}
