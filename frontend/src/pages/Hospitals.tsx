import { cs } from "../i18n/cs";
import SimulaceTag from "../components/SimulaceTag";
import { ErrorState, Field, Icon, Muted, Panel, SectionHeader, Tag, type TagTone } from "../components/ui";
import { useHospitals, type Provider } from "../services/systemApi";

const t = cs.system.hospitals;

const KIND_TONE: Record<Provider["kind"], TagTone> = {
  home: "blue",
  simulated_endpoint: "teal",
  registry: "gray",
  unknown: "outline",
};

export default function Hospitals() {
  const { data, isLoading, error, refetch } = useHospitals();

  if (isLoading) return <p className="nis-panel p-4 text-nis-muted">{cs.app.loading}</p>;
  if (error || !data) {
    return (
      <ErrorState
        message={`${cs.common.error}: ${error?.message ?? ""}`}
        retryLabel={cs.common.retry}
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="space-y-3">
      <SectionHeader icon="building" title={t.title} subtitle={t.subtitle}>
        <SimulaceTag />
      </SectionHeader>
      {!data.requests_available && (
        <p role="alert" className="nis-panel nis-row-attention px-3 py-2.5">
          {t.requestsDown}: {data.requests_reason}
        </p>
      )}
      <div className="grid gap-3 xl:grid-cols-2">
        {data.providers.map((p) => (
          <ProviderPanel key={p.id} p={p} />
        ))}
      </div>
    </div>
  );
}

function Counter({ label, value, tone = "text-nis-text" }: { label: string; value: number | null; tone?: string }) {
  return (
    <div className="min-w-[7rem] flex-1 rounded-nis border border-nis-line bg-white px-3 py-2">
      <div className="nis-label">{label}</div>
      <div className={`text-2xl font-bold leading-tight ${tone}`}>{value ?? cs.common.none}</div>
    </div>
  );
}

function ProviderPanel({ p }: { p: Provider }) {
  const simulated = p.kind !== "home";
  const hours = Object.entries(p.expected_hours);
  return (
    <Panel
      icon="building"
      title={p.name}
      className={p.kind === "unknown" ? "border-dashed" : ""}
      actions={
        <>
          <Tag tone={KIND_TONE[p.kind]}>{t.kind[p.kind]}</Tag>
          {simulated && <SimulaceTag />}
        </>
      }
    >
      <div className="flex flex-wrap gap-2">
        <Counter label={t.studies} value={p.fhir_studies} />
        <Counter label={t.open} value={p.open_requests} tone={p.open_requests ? "text-[#9a6b00]" : undefined} />
        <Counter label={t.verified} value={p.verified} tone={p.verified ? "text-nis-green" : undefined} />
        <Counter label={t.total} value={p.total_requests} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <Field label={t.email}>
          <span className="flex min-w-0 items-center gap-1">
            <Icon name="mail" className="shrink-0 text-nis-icon" />
            <span className="truncate" title={p.email ?? undefined}>{p.email ?? cs.common.none}</span>
          </span>
        </Field>
        <Field label={t.phone}>
          <span className="flex items-center gap-1 whitespace-nowrap">
            <Icon name="phone" className="shrink-0 text-nis-icon" />
            {p.phone ?? cs.common.none}
          </span>
        </Field>
        <Field label={t.hours}>{p.hours ?? cs.common.none}</Field>
        <Field label={t.channel}>{t.channels[p.preferred_channel ?? ""] ?? p.preferred_channel ?? cs.common.none}</Field>
        <Field label={t.route}>{p.exchange_route ?? cs.common.none}</Field>
        <Field label={t.expected}>
          {hours.length === 0 || hours.every(([, h]) => h == null) ? (
            cs.common.none
          ) : (
            <span className="flex flex-wrap gap-2">
              {hours.map(([m, h]) => (
                <span key={m} className="whitespace-nowrap">
                  <b>{m}</b> {h == null ? cs.common.none : `${Math.round(h)} h`}
                </span>
              ))}
            </span>
          )}
        </Field>
        <Field label={t.endpoint} className="col-span-2 md:col-span-3">
          {p.fhir_base ? (
            <a
              href={`${p.fhir_base}/metadata`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 break-all font-mono text-sm text-accent-600 hover:underline"
            >
              {p.fhir_base}
              <Icon name="external" />
            </a>
          ) : (
            <Muted>{t.noEndpoint}</Muted>
          )}
          {p.fhir_error && <div className="text-sm text-nis-red">{p.fhir_error}</div>}
        </Field>
        {p.aliases.length > 0 && (
          <Field label={t.aliases} className="col-span-2 md:col-span-3">
            <span className="flex flex-wrap gap-1">
              {p.aliases.map((a) => (
                <Tag key={a} tone="outline">
                  {a}
                </Tag>
              ))}
            </span>
          </Field>
        )}
      </div>
    </Panel>
  );
}
