import { useEffect, useState } from "react";
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

type Errors = Partial<Record<"patient" | "group" | "meeting", string>>;

export default function AddPatient() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const prefilledMeeting = params.get("meeting") ?? "";

  const [query, setQuery] = useState("");
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
    <form onSubmit={onSubmit} className="mx-auto max-w-4xl space-y-6 p-4" noValidate>
      <h1 className="text-3xl font-bold">{cs.addPatient.title}</h1>

      <fieldset className="space-y-2 rounded-xl border border-slate-300 bg-white p-4">
        <legend className="px-1 text-xl font-bold">{cs.addPatient.patientStep}</legend>
        <label className="block font-semibold" htmlFor="patient-search">
          {cs.addPatient.searchLabel}
        </label>
        <input
          id="patient-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={cs.addPatient.searchPlaceholder}
          className="w-full rounded-lg border-2 border-slate-400 px-3 py-2"
        />
        {search.isLoading && <p>{cs.app.loading}</p>}
        {search.error && (
          <p role="alert" className="text-red-800">
            {cs.common.error}: {search.error.message}
          </p>
        )}
        {search.data && search.data.length === 0 && <p>{cs.addPatient.noResults}</p>}
        <ul className="max-h-64 space-y-1 overflow-auto">
          {search.data?.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => pickPatient(p)}
                aria-pressed={patient?.id === p.id}
                className="w-full rounded-lg border-2 border-transparent px-2 py-1.5 text-left hover:bg-accent-50 aria-pressed:border-accent-600 aria-pressed:bg-accent-100"
              >
                <span className="font-semibold">{p.id}</span>
                <span className="ml-2">
                  {p.sex}, {p.age_band}
                </span>
                <span className="ml-2 text-slate-700">
                  {p.diagnoses.map((d) => d.code).join(", ") || cs.common.unknown}
                </span>
                {p.has_imaging && <Badge text={cs.addPatient.hasImaging} />}
                {p.has_documents && <Badge text={cs.addPatient.hasDocuments} />}
              </button>
            </li>
          ))}
        </ul>
        {patient && (
          <p className="font-semibold">
            {cs.addPatient.selected}: {patient.id}
          </p>
        )}
        {errors.patient && <FieldError text={errors.patient} />}

        <label className="mt-2 block font-semibold" htmlFor="display-name">
          {cs.addPatient.displayName}
        </label>
        <input
          id="display-name"
          type="text"
          maxLength={200}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full rounded-lg border-2 border-slate-400 px-3 py-2"
        />
        <p className="text-sm text-slate-600">{cs.addPatient.displayNameHint}</p>
      </fieldset>

      <fieldset className="space-y-2 rounded-xl border border-slate-300 bg-white p-4">
        <legend className="px-1 text-xl font-bold">{cs.addPatient.groupStep}</legend>
        <select
          aria-label={cs.addPatient.groupStep}
          value={group}
          onChange={(e) => {
            setGroup(e.target.value);
            setMeetingId("");
          }}
          className="w-full rounded-lg border-2 border-slate-400 px-3 py-2"
        >
          <option value="">—</option>
          {groups.data?.map((g) => (
            <option key={g.id} value={g.id}>
              {g.label}
            </option>
          ))}
        </select>
        {errors.group && <FieldError text={errors.group} />}
      </fieldset>

      <fieldset className="space-y-2 rounded-xl border border-slate-300 bg-white p-4">
        <legend className="px-1 text-xl font-bold">{cs.addPatient.meetingStep}</legend>
        {eligible.isLoading && <p>{cs.app.loading}</p>}
        {eligible.error && (
          <p role="alert" className="text-red-800">
            {cs.common.error}: {eligible.error.message}
          </p>
        )}
        {eligible.data && eligible.data.length === 0 && <p>{cs.addPatient.noMeetings}</p>}
        <div className="max-h-64 space-y-1 overflow-auto">
          {eligible.data?.map((m) => (
            <label key={m.id} className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-accent-50">
              <input
                type="radio"
                name="meeting"
                value={m.id}
                checked={meetingId === m.id}
                onChange={() => {
                  setMeetingId(m.id);
                  setErrors((e) => ({ ...e, meeting: undefined }));
                }}
              />
              <span>
                {formatDate(m.date)} {m.time} – {m.label}
              </span>
            </label>
          ))}
        </div>
        {errors.meeting && <FieldError text={errors.meeting} />}
      </fieldset>

      {create.isError && (
        <p role="alert" className="font-semibold text-red-800">
          {cs.common.error}: {create.error.message}
        </p>
      )}
      <button
        type="submit"
        disabled={create.isPending}
        className="rounded-lg bg-accent-600 px-5 py-2 text-lg font-semibold text-white hover:bg-accent-700 disabled:opacity-60"
      >
        {create.isPending ? cs.addPatient.submitting : cs.addPatient.submit}
      </button>
    </form>
  );
}

function Badge({ text }: { text: string }) {
  return <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-sm text-slate-700">{text}</span>;
}

function FieldError({ text }: { text: string }) {
  return (
    <p role="alert" className="font-semibold text-red-800">
      {text}
    </p>
  );
}
