# HTTP API Contract

The backend exposes JSON over HTTP to the React client. Paths and purposes below follow the API in [CLAUDE.md](../../../CLAUDE.md#11-backend-api-fastapi-json). Clinical resource JSON is not returned directly to the browser; routes return application view models. Dates are presentation-shifted where applicable and identify that shift. The interface language is Czech.

## Shared behavior

- All paths use the `/api` prefix and JSON request/response bodies.
- IDs are opaque strings. Patient records are addressed only by dataset pseudonym; never use names or birth dates as identifiers.
- Readiness is one of `ready`, `attention`, or `not_ready`, always accompanied by a short reason.
- Simulated content and all simulated actions are explicitly tagged. The simulate-* routes are demo-only and do not connect to real hospitals, PACS, email, or telephony.
- A request cannot be sent unless an approval actor and timestamp have been durably recorded.
- Errors use a JSON object with a stable `code` and human-readable `message`; validation failures return 422, missing IDs 404, duplicate case/invalid state transitions 409, and unavailable dependencies 503. Do not return a successful-shaped empty result when a required store/LLM operation fails.

## Routes

| Method and path | Request | Success response / effect |
|---|---|---|
| `GET /api/dashboard?start={date}&days=7` | Query: start date, window length. | Window dates, readiness totals, and meetings grouped by day. |
| `GET /api/schedule/dates?from={date}&to={date}` | Date range. | Scheduled dates and each date's aggregate readiness, including dates outside the dashboard window. |
| `GET /api/days/{date}` | Date path parameter. | Meetings for that day, status and patient rows. |
| `GET /api/meetings/{id}` | Meeting id. | Meeting detail and registered cases. |
| `GET /api/diagnosis-groups` | — | Configured diagnosis groups. |
| `GET /api/meetings/eligible?group={id}&from={date}` | Diagnosis group and start date. | Only meetings accepting registrations for that configured group. |
| `GET /api/patients/search?q={query}&group={id}` | Search text and optional group. | Patient picker results with pseudonym, diagnosis and data-availability badges; no source report text. |
| `POST /api/cases` | `{patient_id, display_name?, group_id, meeting_id}` | `201`: case created with `not_ready` / `initial check running`; background check begins. Reject invalid eligibility or duplicate `(patient, meeting)`. |
| `GET /api/cases/{id}` | Case id. | Case detail view model: case, patient summary, planned exam/evidence, timeline, required items, requests, open issues and simulation marker. |
| `POST /api/cases/{id}/recheck` | Case id. | Starts an idempotent check; previous computed results remain available until replacement succeeds. |
| `PATCH /api/cases/{id}/planned-exam` | Coordinator correction to modality/region/date fields. | Updated planned exam and recomputed derived state, with actor/time recorded. |
| `POST /api/items/{id}/waive` | `{reason}` | Waives one required item, records reason/actor/time and recalculates readiness. |
| `POST /api/requests/{id}/approve` | Coordinator identity/name. | Records approval and timestamp, then sends through the sandbox channel; returns updated request/history. |
| `POST /api/requests/approve-all` | `{meeting_id? , window? , coordinator}` | Approves eligible drafted requests in the selected meeting or seven-day window; records approval per request. |
| `POST /api/requests/{id}/simulate-reply` | `{text}` | Classifies a demo reply, stores its evidence quote and updates the simulated request state. |
| `POST /api/requests/{id}/simulate-call` | `{outcome}` | Records the selected simulated call outcome and communication. |
| `POST /api/requests/{id}/simulate-delivery` | `{modality, date, region}` | Creates a simulated received study; verifies it against the request and updates readiness only on a match. |
| `POST /api/demo/nightly-run` | — | Rechecks cases for meetings in the window, drafts requests and runs due simulated follow-up; returns a summary. |
| `POST /api/demo/advance-time` | `{hours}` | Advances the demo clock and executes due reminder/escalation rules; returns resulting events. |
| `GET /api/requests/{id}` | Request id. | Request state, transitions, rendered sandbox message, parsed replies, voice transcript and FHIR Task id. |
| `GET /api/health` | — | Health of API, configured FHIR store, app database and LLM gateway; unavailable required dependencies are reported explicitly. |

## Core response shape

`GET /api/cases/{id}` returns a case-detail view model, not a raw FHIR Bundle. It contains:

- `case`: id, meeting, readiness and reason, date offset.
- `patient`: pseudonym, fictional display name, sex/age band and diagnosis summary.
- `planned_exam`: modality, regions, shifted display date, site, source quote/id and confidence.
- `timeline`: study/reference/treatment/MDT rows with display dates and availability.
- `items`: reasons, modality/regions, target date, availability, holding site, evidence quote/source/confidence and linked request state.
- `open_issues`: low confidence, date error, conflict, time gap or failed verification.
- `simulated`: boolean indicator.

The detailed schema is maintained with backend Pydantic models and kept in sync with the frontend's TypeScript API types.

## Workflow guarantees

1. Creating a case revalidates meeting eligibility and uniqueness atomically before starting the background check.
2. Any send operation verifies the recorded approval for that exact request; approval-all records a distinct approval per request.
3. `simulate-delivery` only changes an item to ready after modality, date tolerance and region match; mismatches are retained with a clear reason.
4. Waivers require a non-empty reason; they do not delete evidence or request history.
5. State transitions and readiness recalculations are idempotent where retried, and failures are explicit.
6. Real email, real calls, real PACS, real ePACS and live HIS write-back are not exposed by this contract.
