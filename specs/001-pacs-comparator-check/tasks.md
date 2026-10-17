# Tasks: PACS Comparator Check

**Input**: Design documents from `specs/001-pacs-comparator-check/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/http-api.md`

**Tests**: Test work is included because the project constitution and specification explicitly require date parsing, normalization, matching, rules, readiness, request-state, verification, eligibility, duplicate-prevention and mocked pipeline integration tests. Tests use hand-written synthetic data only and never read `data/raw/`.

**Organization**: Tasks are grouped by user story; setup and foundational tasks establish the shared runtime before story work starts.

## Phase 1: Setup

**Purpose**: Create the backend/frontend application skeleton and development tooling.

- [X] T001 Create the Python backend package, module entry point, and package metadata in `backend/pyproject.toml` and `backend/app/__init__.py`
- [X] T002 [P] Create the React 18, TypeScript, Vite and Tailwind application scaffold in `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.js`, and `frontend/src/main.tsx`
- [X] T003 [P] Add the environment-variable names and safe local defaults to `.env.example` without copying any secret values
- [X] T004 Configure Python Ruff and pytest discovery in `backend/pyproject.toml`
- [X] T005 [P] Create shared frontend source directories and Czech UI entry point in `frontend/src/components/`, `frontend/src/pages/`, `frontend/src/services/`, and `frontend/src/i18n/cs.ts`
- [X] T006 Create the backend configuration, structured logging, and common API error response modules in `backend/app/config.py`, `backend/app/logging.py`, and `backend/app/api/errors.py`
- [X] T061 [P] Document the label-file schema for references and planned exams without including any patient-derived content in `backend/scripts/labels-schema.md`; keep actual labels under ignored `data/labels/` (moved here from US5 so a teammate can start hand-labeling while the pipeline is built)

---

## Phase 2: Foundational

**Purpose**: Establish the data access, LLM, FHIR persistence and app service foundations required by all stories.

**⚠️ CRITICAL**: Complete this phase before starting user-story implementation.

- [X] T007 [P] Implement the `FhirStore` interface for patient bundles, resource search, create and update operations in `backend/app/fhir_store/base.py`
- [X] T008 Implement the local per-patient FHIR R4 bundle reader and generated-resource writer under `data/fhir_out/` in `backend/app/fhir_store/local.py` using the interface from `backend/app/fhir_store/base.py`
- [X] T009 Implement dataset extraction into the git-ignored `data/raw/` directory, reading CSV as UTF-8 with BOM and never executing archive contents, in `backend/scripts/extract_dataset.py`
- [X] T010 Implement environment-driven LLM gateway client, EU deployment guard for report-text calls, retry/backoff, structured response validation and ignored-data cache in `backend/app/llm/client.py`, `backend/app/llm/schemas.py`, and `backend/app/llm/cache.py`
- [X] T011 [P] Add synthetic FHIR bundle and Czech-like report/note fixtures under `backend/tests/fixtures/`; do not copy dataset records or pseudonyms
- [X] T012 Implement FastAPI application startup, `/api/health`, explicit dependency health errors and API router registration in `backend/app/main.py` and `backend/app/api/health.py`
- [X] T013 Add the project HTTP API Pydantic response/error base schemas in `backend/app/api/schemas.py` and document their mapping to `frontend/src/services/api-types.ts`
- [X] T014 Implement SQLite/SQLAlchemy session lifecycle and the initial app-state models in `backend/app/app_db/session.py` and `backend/app/app_db/models.py`, including `Meeting` and `Case` (moved here from US2 because US1's `/api/cases/{id}` needs them): required ids, date/time and label, configured eligible groups, registration flag, patient/meeting linkage, `check_status` values `pending`, `running`, `done`, `failed`, `readiness` values `not_ready`, `attention`, `ready`, reason text, `date_offset_days`, and a unique `(patient_id, meeting_id)` constraint. US1 creates cases through a dev helper (`backend/scripts/create_case.py --patient <id>`) attached to a placeholder meeting until US2 adds scheduling
- [X] T015 [P] Add synthetic-only test configuration and fixtures enforcing that automated tests do not access `data/raw/` in `backend/tests/conftest.py`

**Checkpoint**: API starts in local mode; health reports configured dependencies accurately; LLM and data access can be mocked; no user story requires IRIS to run.

---

## IRIS Core Track: InterSystems IRIS for Health is the product's core (decided by the team, 2026-10-16)

**Purpose**: IRIS is the primary store and runtime of the product, not an optional adapter: the dataset and all our resources live in the IRIS FHIR server, app state lives in IRIS SQL, the request loop runs as an IRIS Interoperability production, and search/AI features use IRIS Vector Search, FHIR SQL Builder, IntegratedML and an MCP server. The local file store stays only for unit tests and as a fallback. Built in the `iris-track` branch/worktree (by Sonnet subagents) and merged after the main track commits; stages run in order A → B → C → D → E.

### Stage A: IRIS as the base

- [X] T067 [IRIS-A1] Add `docker-compose.yml` to this repo with IRIS for Health (InterSystems FHIR-AI-Hackathon-Kit image/config, ports 1972 and 52773) and Mailpit (`axllent/mailpit`, SMTP 1025, UI 8025), plus `backend/scripts/iris_setup.py` that creates namespace `FHIRSERVER` with FHIR R4 endpoint `/fhir/r4` without loading the kit's Synthea data; `.env.example` gets `IRIS_FHIR_BASE=http://localhost:52773/fhir/r4`
- [X] T074 [IRIS-A2] `backend/scripts/load_iris.py`: load all 1,830 per-patient transaction bundles (PUT with dataset ids, lab Observations skipped) into IRIS FHIR, demo patients first; verify counts of Patient, ImagingStudy, DiagnosticReport, DocumentReference against the files
- [X] T066 [IRIS-A3] `backend/app/fhir_store/iris.py` (`IrisFhirStore`) and `FHIR_BACKEND=iris` as the **default**; the pipeline result on the 10 review patients is identical for `iris` and `local` (LLM from cache)
- [X] T076 [IRIS-A4] App state (meetings, cases, case results, requests, events) in **IRIS SQL** via SQLAlchemy and the `sqlalchemy-iris` dialect instead of SQLite; `APP_DB_URL=iris://SuperUser:SYS@localhost:1972/FHIRSERVER`; SQLite remains only for unit tests
- [x] T077 [IRIS-A5] Update CLAUDE.md (sections 0, 5, 6, 16, 17, 20), the constitution (principle VII) and `plan.md` so that IRIS is the primary store everywhere; remove all "IRIS optional/later" wording (done)

**Checkpoint A**: `docker compose up` + `iris_setup.py` + `load_iris.py` give a loaded IRIS; the app and pipeline run with IRIS FHIR and IRIS SQL by default.

### Stage B: hospitals and exchange on IRIS

- [X] T078 [IRIS-B1] Separate FHIR R4 endpoints in IRIS as hospitals: Motol (`/fhir/r4`), NNH, Homolka, FNM (own endpoints/namespaces); seed the external ones with **synthetic** ImagingStudy + DiagnosticReport metadata for studies that our pipeline found "referenced but not found" (no real text, labeled simulated)
- [X] T079 [IRIS-B2] Availability adapter `FhirHospitalAdapter`: availability = FHIR search of `ImagingStudy` in the holding hospital's endpoint (replaces the dataset-flag adapter as default; the flag adapter stays as fallback)
- [X] T080 [IRIS-B3] IHE MHD exchange between hospital endpoints: a provider "sends" a study as an MHD Provide Document Bundle (ITI-65: DocumentReference + List/SubmissionSet with the study reference) into Motol; receipt detection reads it

**Checkpoint B**: requesting a study and receiving it are real FHIR/MHD calls between IRIS endpoints.

### Stage C: Interoperability production runs the request loop

- [X] T081 [IRIS-C1] IRIS Interoperability production `PacsComparator.Production`: Business Service (new gap / approved request from the app via REST or FHIR Task), Business Process (request state machine of CLAUDE.md 10.2: approval wait, sending, reminder timer, voice escalation, human escalation), Business Operations (email via SMTP to Mailpit, FHIR/MHD request to the hospital endpoint, voice message via ElevenLabs, FHIR `Task`/`Communication`/`AuditEvent` updates)
- [X] T082 [IRIS-C2] Embedded Python inside the production for reply parsing (LLM gateway) and received-study verification (CLAUDE.md 10.4, 10.7)
- [X] T083 [IRIS-C3] The backend request API delegates to the production (no separate Python state machine); request history shows the production's message trace; the demo opens **Visual Trace** for one request

**Checkpoint C**: approve → email in Mailpit → reminder → voice → reply → delivery → verified, all visible in Visual Trace.

### Stage D: data and AI on IRIS

- [X] T084 [IRIS-D1] IRIS **Vector Search**: chunks of all radiology reports and clinical notes embedded locally (multilingual sentence-transformers model; the gateway has no embedding model, and text never leaves the machine), vectors in an IRIS SQL table; used in matching to find priors cited without an explicit date
- [X] T085 [IRIS-D2] **FHIR SQL Builder** projection of ImagingStudy, ServiceRequest, Task, Observation (imaging-reference) to SQL; dashboard counts and `/stats` read from it
- [X] T086 [IRIS-D3] **HL7 v2**: simulated RIS sends ORM^O01 (planned exam) and ORU^R01 (report) into the production; transformed to FHIR `ServiceRequest`/`DiagnosticReport`; a new ORM triggers the case check
- [X] T087 [IRIS-D4] **DICOM**: mock PACS (Orthanc container) with synthetic DICOM study metadata per hospital; IRIS DICOM adapter performs C-FIND as the availability check (`DicomAdapter`), labeled simulated
- [X] T088 [IRIS-D5] **IntegratedML**: models predicting late arrival of a requested study and provider response time, trained on a synthetic request history (labeled simulated); prediction shown next to each request
- [X] T089 [IRIS-D6] **MCP server / agent** over IRIS tools (`fhir_search`, `sql_query`, `vector_search`, `create_task`, `request_status`), as in the kit's 5.2 tutorial; a chat panel in the patient view

**Checkpoint D**: each feature has a working demo path on the demo patients.

### Stage E: demo on IRIS

- [ ] T090 [IRIS-E1] Demo script and check: Management Portal, FHIR Explorer (our ServiceRequest/Task/Provenance), Visual Trace of one request, SQL query on the projection, Vector Search query, MCP agent question; recorded in `quickstart.md`

---

## Phase 3: User Story 1 - See required prior studies and missing material (Priority: P1) 🎯 MVP

**Goal**: Show a patient's planned exam, imaging timeline and required prior studies with availability, exact quoted evidence and an explainable readiness state.

**Independent Test**: Using a synthetic patient with a planned exam, one available internal study, one internal study without images and one cited unmatched prior, open the patient and verify the required-study list, reasons, exact source quotes, availability and readiness; invalid dates/quotes must be flagged rather than treated as confirmed gaps.

### Implementation for User Story 1

- [X] T016 [P] [US1] Define typed timeline, imaging study, prior-reference, planned-exam and extraction evidence schemas; require entity ids, require each quote to be an exact source substring, and constrain confidence to `[0,1]` in `backend/app/pipeline/schemas.py`
- [X] T017 [P] [US1] Implement Czech modality/region normalization, including `HBMP` and month-only date precision, in `backend/app/pipeline/normalize.py`
- [X] T018 [US1] Implement per-patient imaging/report/document/treatment timeline assembly with duplicate-document elimination in `backend/app/pipeline/timeline.py`
- [X] T019 [US1] Implement reference extraction prompts, regex prefilter, exact-substring quote verification, confidence validation and implausible-date flags in `backend/app/llm/prompts/extract_priors.md` and `backend/app/pipeline/extract_priors.py`
- [X] T020 [US1] Implement planned-exam extraction with modality, region set, absolute date or note-relative interval, target site, source document id, exact quote and confidence; resolve relative dates against note date, allow coordinator corrections, and exclude radiotherapy-planning CT as a comparator trigger unless no other exam exists in `backend/app/llm/prompts/extract_planned.md` and `backend/app/pipeline/extract_planned.py`
- [X] T021 [US1] Implement patient-local study matching by modality, exact/±3-day/same-month date and region overlap in `backend/app/pipeline/match.py`
- [X] T022 [US1] Implement configurable R1-R5 required-prior rules, rule-reason preservation and duplicate consolidation in `config/rules.yaml` and `backend/app/pipeline/rules.py`
- [X] T023 [US1] Implement `AvailabilityAdapter` and simulated dataset PACS-flag mapping (`available`, `not_in_pacs`, `unknown`, `not_found`) in `backend/app/pipeline/availability.py`
- [X] T024 [US1] Implement gap classification, provider-site hint resolution and uncertainty/open-issue creation in `backend/app/pipeline/gaps.py`
- [X] T025 [US1] Implement case readiness precedence and concise reasons without using LLM-generated clinical recommendations in `backend/app/pipeline/readiness.py`
- [X] T026 [US1] Implement idempotent case pipeline orchestration that preserves request history and keeps patient dates unshifted internally in `backend/app/pipeline/run.py`
- [X] T027 [US1] Map planned exams to FHIR `ServiceRequest`, extracted priors to FHIR `Observation`, and each derived fact to FHIR `Provenance` in `backend/app/fhir_store/mappers.py`
- [X] T028 [US1] Implement patient timeline, required-item and source-document view-model assembly with presentation-only date shifting in `backend/app/api/case_views.py`
- [X] T029 [US1] Implement `GET /api/cases/{id}`, `POST /api/cases/{id}/recheck`, and `PATCH /api/cases/{id}/planned-exam` according to `contracts/http-api.md` in `backend/app/api/cases.py`
- [X] T030 [US1] Build the Czech patient-detail view with planned-exam correction, timeline, required-study evidence, source quote highlighting, explicit simulated tags and all three accessible readiness states in `frontend/src/pages/PatientDetail.tsx` and `frontend/src/components/`
- [X] T031 [US1] Add unit tests for date parsing, normalization, matching tolerances, R1-R5, quote validation and readiness precedence using synthetic fixtures in `backend/tests/unit/test_pipeline.py`
- [X] T032 [US1] Add mocked-LLM pipeline integration coverage for available, missing, unknown, unmatched and invalid-quote inputs in `backend/tests/integration/test_pipeline.py`
- [X] T068 [US1] Implement subset/demo-patient selection (criteria in CLAUDE.md section 13) and pipeline precomputation with all output restricted to ignored `data/` (`data/demo_patients.json`, `data/cache/`) in `backend/scripts/pick_demo_patients.py` and `backend/scripts/precompute.py` (moved here from Polish because the real-data check below and the demo depend on it)
- [X] T073 [US1] Add the CLI `python -m app.pipeline.run --patient <id>` that prints the case result as JSON to stdout, and run it on the selected demo patients plus 5 random patients with imaging against the real local dataset (real LLM, cached). A human checks that planned exams, cited priors, matches and gaps are plausible and that every quote appears in the source. Record findings, prompt fixes and the DocumentReference full-text location (CLAUDE.md section 4.3) in CLAUDE.md section 20. Nothing from this run is written outside ignored `data/` and no output is pasted into tracked files

**Checkpoint**: The patient detail path works from local FHIR input through extraction/rules to evidence-backed, visibly simulated availability and a correct readiness state, **on synthetic fixtures and on the real demo patients** (T073 reviewed by a human).

---

## Phase 4: User Story 2 - Plan the week and register patients (Priority: P2)

**Goal**: Show configured MDT meetings for the next seven days and scheduled sidebar dates; let the coordinator register an eligible patient without duplicates and see the check run.

**Independent Test**: With a synthetic schedule, register a patient to an eligible meeting and verify immediate “initial check running,” completed patient/meeting/day/dashboard status aggregation, dates shifted only for display, duplicate rejection and empty-meeting attention state.

**Dependency**: Requires the patient read/check pipeline and case detail data from US1.

### Implementation for User Story 2

- [X] T033 [P] [US2] Add meeting/case repository functions (list by date range, list cases per meeting, create with duplicate check) on top of the `Meeting` and `Case` models from T014, and replace the US1 placeholder meeting with materialized meetings, in `backend/app/app_db/repositories.py`
- [X] T034 [P] [US2] Add configurable diagnosis-group mappings and recurring MDT templates materialized for the next eight weeks in `config/diagnosis_groups.json`, `config/mdt_schedule.json`, and `backend/app/scheduling/meetings.py`
- [X] T035 [US2] Implement diagnosis-group eligibility filtering and server-side duplicate/meeting-availability validation in `backend/app/scheduling/eligibility.py`
- [X] T036 [US2] Implement per-case date anchoring so pipeline dates remain in patient time and UI dates apply one consistent case offset in `backend/app/scheduling/anchoring.py`
- [X] T037 [US2] Implement readiness aggregation for case, meeting, day and dashboard, including empty-meeting `attention` with reason “no patients,” in `backend/app/scheduling/aggregation.py`
- [X] T038 [US2] Implement `GET /api/dashboard`, `/api/schedule/dates`, `/api/days/{date}`, `/api/meetings/{id}`, `/api/diagnosis-groups`, and `/api/meetings/eligible` in `backend/app/api/meetings.py`
- [X] T039 [US2] Implement patient-picker search and `POST /api/cases` with atomic eligibility/duplicate checks and immediate background pipeline start in `backend/app/api/patients.py` and `backend/app/api/cases.py`
- [X] T040 [US2] Build the Czech seven-day dashboard, scheduled-date sidebar and day/meeting patient list with explicit window dates and icon-plus-text readiness in `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/DayView.tsx`, and `frontend/src/components/DateSidebar.tsx`
- [X] T041 [US2] Build the patient registration flow with dataset patient picker, configured diagnosis group, only eligible meetings, required-field validation and post-submit running status in `frontend/src/pages/AddPatient.tsx`
- [X] T042 [US2] Add synthetic tests for eligibility, atomic duplicate prevention, date anchoring and patient/meeting/day/dashboard readiness aggregation in `backend/tests/unit/test_scheduling.py` and `backend/tests/api/test_cases.py`

**Checkpoint**: A coordinator can add a patient in under one minute; all aggregate counts/statuses remain consistent and dates are labeled as shifted.

---

## Phase 5: User Story 3 - Request missing studies and verify receipt (Priority: P3)

**Goal**: Draft minimal-data requests for every actionable missing study, require coordinator approval before sandbox delivery, track replies, verify receipts and support explicit waiver.

**Independent Test**: For one synthetic missing item, verify a draft is not delivered before approval; after approval verify actor/time and minimal message fields; reject a mismatching receipt, accept a matching receipt, and confirm an explained waiver resolves readiness without erasing history.

**Dependency**: Requires US1 required-item and readiness pipeline; US2 meeting links are needed for approve-all by meeting.

### Implementation for User Story 3

- [x] T043 [P] [US3] Define provider, request and append-only request-event models; require request id, required-item/provider links and approval actor/time before send, with attempts, next-action time and transition history, in `backend/app/requests/models.py` and `backend/app/app_db/models.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T044 [P] [US3] Add provider aliases with fake/non-routable contact details and simulated exchange routes in `config/providers.json` and `backend/app/requests/providers.py` (done; `config/providers.json`)
- [x] T045 [US3] Implement request states `DETECTED`, `DRAFTED`, `APPROVED`, `SENT`, `ACKNOWLEDGED`, `RECEIVED`, `VERIFIED`, `CLOSED`, `REJECTED`, `NEEDS_INFO`, `WRONG_RECIPIENT`, `CANCELLED`, `REMINDER_SENT`, `VOICE_ESCALATED`, and `HUMAN_ESCALATED`; reject `SENT` unless a durable approval actor and timestamp exist in `backend/app/requests/state_machine.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T046 [US3] Implement draft creation per actionable missing item with availability `available`, `not_in_pacs`, `unknown`, or `not_found`; serialize FHIR `Task` with patient focus, coordinator owner, due date and exact request business status in `backend/app/requests/drafts.py` and `backend/app/fhir_store/mappers.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T047 [US3] Implement one-request approval and meeting/seven-day approve-all with per-request approval records and `AuditEvent` creation in `backend/app/requests/approval.py` and `backend/app/api/requests.py` (done: `POST /api/requests/{id}/approve`, `/api/requests/approve-all` with `case_ids`; approval and AuditEvent in the production)
- [x] T048 [US3] Implement Czech email rendering containing only request id, study date, modality, body region, requesting site, requested route and deadline; write to ignored `data/outbox/` and optionally deliver via Mailpit SMTP sandbox in `backend/app/requests/email_channel.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T049 [US3] Implement reply-to-request matching, reply classification and exact quoted justification persistence in `backend/app/requests/reply_parser.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T050 [US3] Implement received-study verification by modality, exact/±3-day or same-month date and region overlap; preserve mismatches and waived state in `backend/app/requests/verification.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T051 [US3] Implement item waiver with required non-empty reason, actor/time, append-only transition history and readiness recalculation in `backend/app/api/items.py` (done: `POST /api/items/{id}/waive`, table `ItemWaiver`, cancels the open request, readiness overlay in `app/requests/overlay.py`)
- [x] T052 [US3] Implement FHIR `Communication` and audit mappings for outgoing/received messages and coordinator actions in `backend/app/fhir_store/mappers.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T053 [US3] Build required-item request actions, approval confirmation, waiver reason input, reply/delivery simulation and request-history drawer in `frontend/src/components/RequiredItems.tsx` and `frontend/src/components/RequestDrawer.tsx` (done: `ItemActions.tsx`, `ActionDialog.tsx`, `RequestDrawer.tsx` in the required studies table)
- [x] T054 [US3] Add synthetic tests for request state transitions, approval-before-send, minimal outbound fields, reply classifications, receipt verification and waiver readiness in `backend/tests/unit/test_requests.py` and `backend/tests/api/test_requests.py` (done: `tests/test_requests_api.py` with a fake production; transitions are tested in the production)

**Checkpoint**: The end-to-end request loop is safe by default; no message is delivered before recorded approval, and only a matching receipt can resolve a missing item.

---

## Phase 6: User Story 4 - Proactive preparation and escalation (Priority: P4)

**Goal**: Recheck upcoming meetings, prepare approval-ready drafts and advance simulated reminders, Czech voice escalation and coordinator handoff using the demo clock.

**Independent Test**: Trigger preparation for a meeting two days ahead, approve the draft, advance demo time without reply, and verify reminder → voice → human escalation in order with immutable timestamps/actors and a patient-free voice script.

**Dependency**: Requires US3 request lifecycle and sandbox channel.

### Implementation for User Story 4

- [x] T055 [US4] Implement configurable preparation lead time and nightly meeting/case recheck that summarizes newly drafted requests in `backend/app/requests/scheduler.py` (done: `POST /api/demo/nightly-run`, synchronous, drafts only; `GET /api/demo/summary`)
- [x] T056 [US4] Implement demo-clock advancement, one-day reminder, within-48-hour voice escalation and human escalation transitions in `backend/app/requests/follow_up.py` and `backend/app/api/demo.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T057 [US4] Implement Czech voice script containing only requesting site, request id and requested route; use optional TTS or browser playback without real telephony in `backend/app/requests/voice_channel.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T058 [US4] Implement FHIR `Communication` records for simulated reminders, voice messages and outcomes in `backend/app/fhir_store/mappers.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)
- [x] T059 [US4] Add dashboard morning summary, nightly-run/advance-time controls and simulated call outcome controls; hide controls in presentation mode in `frontend/src/components/DemoControls.tsx` and `frontend/src/pages/Dashboard.tsx` (done: `NightlyBanner.tsx` on the dashboard; call outcome in `ItemActions.tsx`; `.demo-only` hidden in presentation mode; `DemoControls.tsx` removed)
- [x] T060 [US4] Add synthetic scheduler tests proving reminder/voice/human escalation ordering, working time conditions, logged events and absence of patient-identifying voice content in `backend/tests/unit/test_follow_up.py` (covered by the IRIS production `PacsComparator.Production`, T081 to T083; branch `ui-func2` adds the backend calls and the overlay)

**Checkpoint**: Demo controls can run the proactive flow without editing data manually; every simulated action is visibly labeled.

---

## Phase 7: User Story 5 - Show measured extraction quality (Priority: P5)

**Goal**: Measure prior-reference and planned-exam extraction precision/recall against a human-labeled sample, compare a naive baseline and report corpus-level counts.

**Independent Test**: Run evaluation against a small synthetic hand-labeled sample and verify reference/planned-exam precision and recall, naive baseline comparison, dataset totals and no raw record content in output.

**Dependency**: Requires US1 extraction/normalization outputs.

### Implementation for User Story 5

- [x] T062 [US5] Implement extraction precision/recall, date accuracy, naive latest-same-modality baseline and aggregate counts without logging report text in `backend/scripts/eval_extraction.py` (done: `GET /api/stats/eval` reads the silver-set results, counts only)
- [x] T063 [US5] Implement summary-only `/api/stats` response for extraction and dataset counts in `backend/app/api/stats.py` (done: `GET /api/stats`, FHIR SQL projection, and `/api/system/eval`)
- [x] T064 [US5] Build an internal Czech evaluation metrics page showing measured counts and precision/recall without patient identifiers in `frontend/src/pages/Stats.tsx` (done: `frontend/src/pages/Stats.tsx`, route `/statistiky`)
- [x] T065 [US5] Add synthetic labeled evaluation fixtures and metric/baseline correctness tests in `backend/tests/unit/test_evaluation.py` (done: `tests/test_eval_and_cache.py`)

**Checkpoint**: Reported extraction metrics can be reproduced from the label file and do not expose report contents or pseudonyms.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Complete operational verification, optional IRIS deployment and safe demo preparation after the core stories work.

- [ ] T075 Run the full demo with `FHIR_BACKEND=iris` and confirm our ServiceRequest, Observation, Provenance, Task and Communication resources are visible through the IRIS FHIR API
- [ ] T069 [P] Add complete local and optional IRIS-mode run/validation instructions in `README.md`, consistent with `specs/001-pacs-comparator-check/quickstart.md`
- [ ] T070 Validate route schemas against `specs/001-pacs-comparator-check/contracts/http-api.md` and keep generated/manual frontend API types synchronized in `backend/app/api/` and `frontend/src/services/api-types.ts`
- [ ] T071 Run the complete synthetic backend suite, Ruff checks, frontend production build and local quickstart; record any implementation deviations in `CLAUDE.md`
- [ ] T072 Verify the final diff contains no `.env`, archive, `data/` content, patient pseudonyms or report excerpts and that all simulated elements remain labeled in `frontend/src/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; establishes the application scaffold.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories. Includes the `Meeting`/`Case` models (T014) that US1 already needs.
- **IRIS Core Track (T067, T074, T066, T076 to T090)**: IRIS is the product's core. Stage A depends only on dataset extraction (T009) and the `FhirStore` interface (T007) and makes IRIS FHIR + IRIS SQL the default; stages B to E run in order after it. The main track (US2 to US5) builds on IRIS once Stage A is merged; US3's request engine is the IRIS production (Stage C), US3 keeps only the API and UI around it. T075 runs after Stage C.
- **US1 (Phase 3)**: Depends on Foundational; delivers the P1 patient evidence/required-study MVP. Its checkpoint requires the human-reviewed real-data run (T073).
- **US2 (Phase 4)**: Depends on US1 pipeline/check status for its registered patient workflow.
- **US3 (Phase 5)**: Depends on US1 required items/readiness and US2 meeting relationships for meeting-wide approval.
- **US4 (Phase 6)**: Depends on US3 request approval, delivery and state transitions.
- **US5 (Phase 7)**: Depends on US1 extraction outputs; can run independently of US2–US4 after US1.
- **Polish (Phase 8)**: Core validation depends on desired stories. The local store stays the default; IRIS must never block local demo operation, but it is built early in its own track, not left for the end.

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational; recommended MVP scope.
- **US2 (P2)**: Depends on US1 for pipeline status and patient-detail integration.
- **US3 (P3)**: Depends on US1 required-item generation and US2 meeting/case grouping.
- **US4 (P4)**: Depends on US3 request lifecycle and sandbox delivery.
- **US5 (P5)**: Depends on US1 extraction and normalization; independent of US2–US4.

### Parallel Opportunities

- Setup tasks T002, T003 and T005 touch separate frontend/config files and can be parallelized once T001's project root is known; T004 follows T001 because both update `backend/pyproject.toml`.
- Foundational tasks T007, T009, T011, T015 can be developed concurrently; T008 depends on T007, and T010/API startup depend on configuration and package setup.
- Within US1, T016 and T017 are parallelizable; T019 and T020 can be authored separately after shared schemas/prompts are agreed; timeline, matching and UI work can proceed in separate files after their interfaces are fixed.
- Within US2, T033 and T034 are separate; schedule services, endpoint/UI work can proceed in parallel after the model and route schemas are agreed.
- Within US3, provider configuration, request models and state machine work in separate files; the frontend request drawer can start against the contract while backend implementation proceeds.
- **US5 can run in parallel with US2–US4 after US1** if a teammate owns evaluation. US2, US3 and US5 otherwise have distinct code areas, but their shared API/FHIR mapper files require coordination.

### Parallel Example: User Story 1

```text
After T016/T017 interfaces are agreed:
Task: T018 timeline assembly in backend/app/pipeline/timeline.py
Task: T019 prior-reference extraction in backend/app/pipeline/extract_priors.py
Task: T020 planned-exam extraction in backend/app/pipeline/extract_planned.py

After the corresponding implementation interfaces are stable:
Task: T030 patient-detail UI in frontend/src/pages/PatientDetail.tsx
Task: T031 pipeline unit tests in backend/tests/unit/test_pipeline.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 Setup and Phase 2 Foundational.
2. Complete Phase 3 US1: local FHIR input, traceable extraction, required studies, simulated availability and patient detail.
3. **STOP and validate US1 independently** using the synthetic fixtures **and the real-data run T073 reviewed by a human**; ensure exact-quote, readiness and missing-study behavior.
4. Demonstrate the P1 customer workflow before starting breadth. IRIS is the core: once IRIS Core Stage A is merged, all further work runs on IRIS FHIR and IRIS SQL by default.

### Incremental Delivery

1. Setup + Foundational → local service and data/LLM adapters.
2. US1 → patient-level evidence-backed comparator (MVP).
3. US2 → schedule, dashboard and patient registration.
4. US3 → coordinator-approved request/receipt loop.
5. US4 → proactive preparation and escalation.
6. US5 → quality metrics and naive baseline.
7. Polish → optional IRIS mode, demo precomputation, full quickstart and release checks.

### Parallel Team Strategy

After Foundational is complete and interfaces are stable:

- Developer A (main agent): Setup, Foundational, US1 pipeline and evidence-backed detail, then US2 to US4.
- IRIS Core Track (T067, T074, T066, T076 to T090): Sonnet subagents in the `iris-track` worktree, stage by stage.
- Teammate C: hand-labels reports per T061 right away, then helps review T073 output and runs US5 evaluation.
- US3 then builds on stable required-item and meeting models; US4 follows the request lifecycle.
- Keep shared `backend/app/fhir_store/mappers.py`, `backend/app/api/cases.py`, and `CLAUDE.md` edits coordinated to avoid conflicts.

## Notes

- Every task uses the required checkbox/ID format; `[P]` is present only for tasks on independent files or workstreams.
- Story tasks carry their `[US1]`–`[US5]` label; setup, foundational and polish tasks do not.
- Tests use hand-written synthetic fixtures only. Never run tests against `data/raw/`.
- The local store is the default. Verify the IRIS version, FHIR R4 endpoint and supported interactions through the running kit and endpoint `CapabilityStatement` before enabling IRIS mode.
- Keep one end-to-end demo scenario working throughout; do not begin optional polish before the previous milestone passes its acceptance check.
