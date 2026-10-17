import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { cs } from "../i18n/cs";
import {
  useCreateCase,
  useDiagnosisGroups,
  useEligibleMeetings,
  usePatientSearch,
} from "../services/api";
import type { PatientSearchResult } from "../services/api-types";
import { formatDate } from "../components/format";
import { Button, FieldLabel, Icon, SectionHeader, Tag } from "../components/ui";

type Errors = Partial<Record<"patient" | "group" | "meeting", string>>;

export default function AddPatient() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const prefilledMeeting = params.get("meeting") ?? "";

  const [query, setQuery] = useState(params.get("q") ?? "");
  const [debounced, setDebounced] = useState("");
  const [patient, setPatient] = useState<PatientSearchResult | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [group, setGroup] = useState(params.get("group") ?? "");
  const [meetingId, setMeetingId] = useState(prefilledMeeting);
  const [errors, setErrors] = useState<Errors>({});

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  const search = usePatientSearch(debounced);
  const groups = useDiagnosisGroups();
  const eligible = useEligibleMeetings(group);
  const create = useCreateCase();

  // Changing the group clears a meeting that does not accept it.
  useEffect(() => {
    if (eligible.data && meetingId && !eligible.data.some((m) => m.id === meetingId)) setMeetingId("");
  }, [eligible.data, meetingId]);

  const pickPatient = (p: PatientSearchResult) => {
    setPatient(p);
    if (!prefilledMeeting) setGroup(p.suggested_group);
    setErrors((e) => ({ ...e, patient: undefined }));
  };

  const onSubmit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (create.isPending) return;
    const next: Errors = {};
    if (!patient) next.patient = cs.addPatient.errPatient;
    if (!group) next.group = cs.addPatient.errGroup;
    if (!meetingId) next.meeting = cs.addPatient.errMeeting;
    setErrors(next);
    if (!patient || Object.keys(next).length > 0) return;
    create.mutate(
      {
        patient_id: patient.id,
        display_name: displayName.trim() || null,
        group_id: group,
        meeting_id: meetingId,
      },
      { onSuccess: (data) => navigate(`/dny/${data.case.meeting.date}`) },
    );
  };

  return (
    <form onSubmit={onSubmit} className="max-w-4xl space-y-3" noValidate>
      <SectionHeader icon="userPlus" title={cs.addPatient.title} />

      <Step legend={cs.addPatient.patientStep}>
        <FieldLabel htmlFor="patient-search">{cs.addPatient.searchLabel}</FieldLabel>
        <div className="relative">
          <Icon name="search" className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-nis-icon" />
          <input
            id="patient-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={cs.addPatient.searchPlaceholder}
            className="nis-input pl-8"
          />
        </div>
        {search.isLoading && <p className="text-nis-muted">{cs.app.loading}</p>}
        {search.error && (
          <p role="alert" className="text-nis-red">
            {cs.common.error}: {search.error.message}
          </p>
        )}
        {search.data && search.data.length === 0 && <p className="text-nis-muted">{cs.addPatient.noResults}</p>}
        {search.data && search.data.length > 0 && (
          <ul className="max-h-64 overflow-auto rounded-nis border border-nis-line">
            {search.data.map((p) => (
              <li key={p.id} className="border-b border-nis-line last:border-b-0">
                <button
                  type="button"
                  onClick={() => pickPatient(p)}
                  aria-pressed={patient?.id === p.id}
                  className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 border-l-[3px] border-transparent px-2.5 py-2 text-left hover:bg-accent-50 aria-pressed:border-accent-600 aria-pressed:bg-accent-50"
                >
                  <span className="font-bold text-accent-600">{p.id}</span>
                  <span className="text-nis-ink">
                    {p.sex}, {p.age_band}
                  </span>
                  <span className="text-nis-text">{p.diagnoses.map((d) => d.code).join(", ") || cs.common.unknown}</span>
                  <span className="ml-auto flex gap-1">
                    {p.has_imaging && <Tag tone="teal">{cs.addPatient.hasImaging}</Tag>}
                    {p.has_documents && <Tag tone="gray">{cs.addPatient.hasDocuments}</Tag>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {patient && (
          <p className="flex items-center gap-2 font-medium">
            <Icon name="check" className="text-nis-green" />
            {cs.addPatient.selected}: <span className="font-bold text-accent-600">{patient.id}</span>
          </p>
        )}
        {errors.patient && <FieldError text={errors.patient} />}

        <div className="pt-2">
          <FieldLabel htmlFor="display-name">{cs.addPatient.displayName}</FieldLabel>
          <input
            id="display-name"
            type="text"
            maxLength={200}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="nis-input mt-1"
          />
          <p className="mt-1 text-sm text-nis-muted">{cs.addPatient.displayNameHint}</p>
        </div>
      </Step>

      <Step legend={cs.addPatient.groupStep}>
        <select
          aria-label={cs.addPatient.groupStep}
          value={group}
          onChange={(e) => {
            setGroup(e.target.value);
            setMeetingId("");
          }}
          className="nis-input"
        >
          <option value="">—</option>
          {groups.data?.map((g) => (
            <option key={g.id} value={g.id}>
              {g.label}
            </option>
          ))}
        </select>
        {errors.group && <FieldError text={errors.group} />}
      </Step>

      <Step legend={cs.addPatient.meetingStep}>
        {eligible.isLoading && <p className="text-nis-muted">{cs.app.loading}</p>}
        {eligible.error && (
          <p role="alert" className="text-nis-red">
            {cs.common.error}: {eligible.error.message}
          </p>
        )}
        {eligible.data && eligible.data.length === 0 && (
          <p className="nis-row-attention rounded-nis px-2.5 py-2">{cs.addPatient.noMeetings}</p>
        )}
        {eligible.data && eligible.data.length > 0 && (
          <div className="max-h-64 overflow-auto rounded-nis border border-nis-line">
            {eligible.data.map((m) => (
              <label
                key={m.id}
                className={`flex cursor-pointer items-center gap-2.5 border-b border-nis-line px-2.5 py-2 last:border-b-0 hover:bg-accent-50 ${
                  meetingId === m.id ? "bg-accent-50" : ""
                }`}
              >
                <input
                  type="radio"
                  name="meeting"
                  value={m.id}
                  checked={meetingId === m.id}
                  className="accent-accent-600"
                  onChange={() => {
                    setMeetingId(m.id);
                    setErrors((e) => ({ ...e, meeting: undefined }));
                  }}
                />
                <span className="font-bold text-accent-600">
                  {formatDate(m.date)} {m.time}
                </span>
                <span>– {m.label}</span>
              </label>
            ))}
          </div>
        )}
        {errors.meeting && <FieldError text={errors.meeting} />}
      </Step>

      {create.isError && (
        <p role="alert" className="nis-panel nis-row-danger px-3 py-2 font-medium">
          {cs.common.error}: {create.error.message}
        </p>
      )}
      <div className="flex justify-end">
        <Button type="submit" variant="primary" icon="userPlus" disabled={create.isPending} className="h-9 px-5">
          {create.isPending ? cs.addPatient.submitting : cs.addPatient.submit}
        </Button>
      </div>
    </form>
  );
}

/** Form step as an NIS panel; the float keeps the legend inside the panel instead of on its border. */
function Step({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset className="nis-panel">
      <legend className="float-left w-full border-b border-nis-line px-3 py-2.5 text-lg font-bold text-nis-text">
        {legend}
      </legend>
      <div className="clear-both space-y-2 p-3">{children}</div>
    </fieldset>
  );
}

function FieldError({ text }: { text: string }) {
  return (
    <p role="alert" className="flex items-center gap-1.5 font-medium text-nis-red">
      <Icon name="crossCircle" />
      {text}
    </p>
  );
}
