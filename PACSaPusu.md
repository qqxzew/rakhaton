# PACS a PUSU: Solution Design Document
**From gap detection to a decision-ready patient dashboard for oncology MDTs**
---
## Table of Contents
1. Executive Summary
2. Problem Statement and Constraints
3. Solution Overview
4. Core Pipeline: Gap Detection
5. HIS Integration
6. Automated Requests to Imaging Providers
7. Frontend and MDT Dashboard
8. MDT Integration
9. End-to-End Demo Flow
10. Architecture and Technology Stack
11. Evaluation and Metrics
12. Safety, Privacy, and Compliance
13. Build Plan and MVP Scope
14. Risks and Mitigations
15. Next Steps
---
## 1. Executive Summary
Oncology teams often discover only at the MDT, or on the day of a CT/MR/PET, that prior imaging from other institutions is missing. Coordinators then spend hours phoning around to have scans resent.
The proposed system is a **closed loop**:
> **HIS integration → expected-priors inference → gap detection → automated requests (email and voice) → tracking and verification → decision-ready patient dashboard**
**Goal:** enter a patient into an MDT without having to call half the country to have previous scans resent.
---
## 2. Problem Statement and Constraints
### 2.1 Task
For a patient with a scheduled CT, MR, PET, or MDT discussion:
1. Determine from the reports which imaging examinations the physician should have.
2. Verify the availability of scans and image series.
3. Flag missing documentation in time, or secure the scans.
### 2.2 Available data
| Included | Not included |
|---|---|
| Anonymized medical reports | Image documentation (scans/images) |
| Text descriptions of CT scans | Secured access to ePACS |
| Laboratory results | |
| Reported procedures and medications | |
| Other HIS data for currently treated oncology patients | |
### 2.3 Key implication
There is no real PACS access, so **the availability check must be simulated**. The design therefore puts all PACS access behind an adapter, so the mock can later be replaced by a real DICOM connection without changing the logic.
### 2.4 Output
An overview of cases to be resolved, per scheduled examination (CT, MR, PET, MDT).
---
## 3. Solution Overview
| Layer | Function |
|---|---|
| **Integration** | Load HIS data (reports, labs, orders, medications) into a canonical model |
| **Extraction** | Build a per-patient imaging and treatment timeline from free text |
| **Expectation** | Rules decide which priors the physician needs |
| **Availability** | Mock PACS inventory (replaceable with a real adapter) |
| **Gap detection** | Classify what is missing and why |
| **Request orchestration** | Draft and send requests (email, then voice), track status |
| **Verification** | Check received studies against what was requested |
| **Dashboard** | One-screen, traceable case overview for MDT decision-making |
| **Write-back** | Record MDT outcome in the HIS |
---
## 4. Core Pipeline: Gap Detection
### Step 1: Extract imaging history from reports (NLP/LLM)
For each patient, extract structured data from free-text reports and CT descriptions:
- Exams performed: modality, body region, date, institution
- Exams *referenced* as comparisons (e.g. "compared with CT from 03/2025, performed at hospital X")
- Treatment milestones (surgery, start of chemo or radiotherapy), which define baseline and follow-up points
**Result:** a per-patient imaging timeline.
### Step 2: Determine the "expected set" of priors
A rule engine, optionally LLM-assisted, defines the relevant priors for each scheduled exam or MDT:
- Same modality and region: the latest and the one before it
- Baseline or staging exam before treatment
- The scan on which the last treatment decision was based
- Any exam an MDT-relevant report compares against
- For PET and MR: the most recent CT of the same region, and vice versa
Rules should be **configurable per diagnosis** (lung, colorectal, etc.).
### Step 3: Simulated PACS availability layer
Build a **mock PACS inventory** (table or JSON: study ID, date, modality, source site, series list) behind an interface that mirrors a real query (DICOM QIDO-RS / C-FIND).
Simulation options:
- **Heuristic:** studies reported in our own HIS are assumed present. External studies are assumed absent unless marked as imported.
- **Configurable noise:** randomly remove studies or series so the checker can be tested properly.
When real PACS access becomes possible, only this adapter is replaced.
### Step 4: Gap detection and classification
Compare the expected set with the inventory:
| Gap type | Meaning |
|---|---|
| External study not imported | Exists elsewhere, not in local PACS |
| Referenced but not found | Mentioned in reports, found nowhere |
| Series missing | e.g. report mentions thin-slice or contrast phase, but only some series present |
| Suspicious time gap | No imaging for longer than the follow-up protocol allows |
### Step 5: Worklist output
Per patient and event (CT, MR, PET, MDT):
- Event date and days remaining (sets priority)
- Missing study, why it's expected, likely holding institution
- Status: OK / missing / requested / received
- Auto-drafted request to the holding site
- Alerts at T-7 and T-3 days, plus a final check at MDT registration
---
## 5. HIS Integration
### 5.1 Data to pull
| Domain | Examples | Used for |
|---|---|---|
| Patient master | Pseudonymized ID, age, sex | Identity matching |
| Oncology diagnosis | ICD-10, TNM stage, histology | Diagnosis-specific rules |
| Orders and appointments | Scheduled CT/MR/PET, MDT date | Trigger for the check |
| Reports | Radiology, pathology, surgery, discharge | Timeline extraction |
| Labs | Tumor markers, blood counts, renal function | Dashboard, contrast safety |
| Medications and procedures | Chemo regimens, radiotherapy, surgery | Treatment milestones |
### 5.2 Architecture
- **Adapter pattern:** one interface, multiple connectors:
  - **HL7 v2** (ADT, ORM, ORU) for events such as a new order or report
  - **FHIR R4** (`Patient`, `Condition`, `ServiceRequest`, `DiagnosticReport`, `Observation`, `MedicationAdministration`, `Appointment`) where supported
  - **Database or CSV export** as the fallback (also what the hackathon dataset is)
- **Canonical data model:** everything maps to one internal schema, so downstream logic is independent of the HIS vendor.
- **Event-driven trigger:** a new CT/MR/PET order or MDT registration starts a "case check" job. A nightly batch sweep catches anything missed.
- **Identity matching:** match external studies by pseudonymized ID plus date of birth and name checks. Uncertain matches go to human review, never auto-accepted.
- **Data quality:** missing fields and conflicting data (e.g. two different staging values) are logged and shown as dashboard warnings rather than silently resolved.
**Demo mode:** the loader reads the anonymized dataset into the canonical model and emits the same events a live HIS would.
---
## 6. Automated Requests to Imaging Providers
### 6.1 Provider registry
A table of imaging providers containing:
- Contact channels and preferred method
- Working hours and language
- Image-exchange route (national image-sharing platform, secure upload link, or CD/DVD courier as a last resort)
The "likely holding institution" from gap detection is looked up here.
### 6.2 Request state machine
```
DETECTED → DRAFTED → (approval) → SENT → ACKNOWLEDGED → RECEIVED → VERIFIED → CLOSED
                                    ↓
                       NO RESPONSE → REMINDER → ESCALATE (voice) → ESCALATE (human)
```
### 6.3 Email channel
- **Content:** minimum necessary data (pseudonym or accession reference, study date, modality, body region, secure upload or exchange link). No full identifiers in the body.
- **Transport:** encrypted email or portal, with a unique request ID in the subject line for reply matching.
- **Reply handling:** an LLM-assisted inbox parser classifies replies as *sent*, *rejected / need more info*, *will send later*, or *wrong recipient*, and updates the status.
- **Reminders:** automatic follow-ups at set intervals, tightened as the exam or MDT date approaches.
### 6.4 Voice channel
Used as escalation when email gets no response, or when the case is urgent (event within 48 hours).
- **Components:** telephony API, speech-to-text, LLM dialog manager, text-to-speech.
- **Script:** introduce the hospital, state the request reference, ask for the study to be sent via the agreed route, ask for a contact name and expected time, confirm.
- **After the call:** transcribe and summarize, write the outcome to the request record (accepted / call back / refused), and schedule a retry if nobody answered.
- **Constraints:** calls only during working hours, and hand-off to a human coordinator whenever the dialog goes off-script.
### 6.5 Demo mode (sandbox)
Real calls and emails are out of scope for a hackathon, so both channels sit behind an interface with a sandbox:
- Emails are written to an outbox file
- Voice calls are simulated with a scripted transcript or a text-to-speech demo clip
### 6.6 Safeguards
- **Approval modes:** start human-in-the-loop (coordinator clicks "send all"), then move to auto-send for low-risk routine requests.
- Full audit trail of every message and call.
- Data minimization; legal basis and agreements with providers confirmed before go-live (GDPR, local health-data regulation).
- Voice is used to trigger the secure route, never to transmit sensitive clinical details.
---
## 7. Frontend and MDT Dashboard
### 7.1 Navigation and scheduled MDT sidebar
The application opens on a simple dashboard for **today and the following six days**, a rolling seven-day window rather than a calendar week.
The persistent sidebar contains **only scheduled dates**, ordered chronologically, with one readiness icon per date. It has no Dashboard or Add patient navigation entries and no individual meeting entries.
There may be MDTs on every day of the week and multiple MDTs on the same day. Each meeting has its own identifier, date, time, diagnosis scope or specialty, and patient list. Selecting a sidebar date opens that day's patient lists in the main area, grouped by MDT with a time and meeting label to distinguish meetings. The sidebar can expose later scheduled dates beyond the dashboard's seven-day window.
An optional compact monthly calendar sits in the sidebar footer. Color days with scheduled MDTs **green (Ready), yellow (Requires attention), or red (Not ready)** using the day's aggregate status. Days without MDTs remain neutral; this is an absence of scheduled meetings, not a fourth readiness state. Selecting a scheduled day opens the same day view as its sidebar entry. Include month navigation, a distinct selected-day indicator, and accessible date/status labels so color is not the only cue.
Keep **Add patient** in the main page header. The application title or logo in the top header returns to the initial seven-day dashboard.

### 7.2 Readiness states
Use exactly three readiness states for patient cases and scheduled MDTs. Pair each icon with a text label; do not rely on color alone.
| State | Suggested icon | Patient case meaning |
|---|---|---|
| **Ready** | Green check circle | All required items are verified, or missing items have been explicitly waived and no unresolved review issue remains |
| **Requires attention** | Amber warning triangle | Review is needed, such as uncertain extraction, conflicting data, or a pending approval, with no confirmed blocking missing item |
| **Not ready** | Red cross circle | A required item is missing or unverified, or the initial preparation check has not completed |
Always show the reason alongside a patient's status, including "Initial check pending" for newly added cases. Request progress such as requested or received is separate from readiness; receipt alone does not mean verification.
An MDT inherits the most severe patient status: **Not ready** takes precedence over **Requires attention**, which takes precedence over **Ready**. An empty MDT uses **Requires attention** with "No patients scheduled" so it is not presented as a verified meeting. A date inherits the most severe status among its MDTs, using the same precedence. Use this aggregate consistently for its sidebar icon and calendar color. Recalculate meeting and date statuses when a patient is added or their readiness changes.

### 7.3 Initial dashboard: next seven days
Keep the landing page focused on preparation status:
- Show the explicit start and end dates of the rolling window.
- Show total scheduled MDTs and counts in each of the three readiness states.
- List meetings grouped by day, with time, specialty or diagnosis scope, overall status, patient count, and patient counts by readiness state.
- Show "No MDT scheduled" for days without meetings, and a clear empty state if the entire window has no scheduled MDTs.
- Clicking a day or meeting opens the corresponding patient list. Keep **Add patient** accessible from this page.

### 7.4 Selected day and MDT patient lists
Display the selected date and, for each MDT that day, its time, label, and overall readiness. Each patient row shows:
- Patient name (a fictional name or pseudonym in the anonymized demo).
- Diagnosis.
- Individual readiness icon and text label.
- A short reason or outstanding item, such as "Waiting for external CT".
Selecting a patient opens the detailed patient view in section 7.6. An **Add patient** action opens the dedicated registration page; a date or meeting selected from this context is only retained if it supports the entered diagnosis.

### 7.5 Add patient page
The user can add a patient to the system and schedule their MDT through a dedicated page:
1. Enter the **patient name**.
2. Select the **diagnosis** from the supported diagnosis list.
3. Show **available MDT dates for that diagnosis**, using configured diagnosis-to-MDT eligibility and the actual meeting schedule. Do not infer eligibility from an AI recommendation.
4. Select a date and, if multiple eligible MDTs occur that day, select the specific meeting by time and label.
5. Review the name, diagnosis, and chosen meeting, then select **Add patient**.
The page must require a name, diagnosis, and eligible MDT selection. Changing the diagnosis refreshes the available dates and clears an incompatible selection. If no eligible dates are available, explain this and allow the user to change the diagnosis; do not silently assign an unrelated meeting. Check that the selected meeting is still available on submission and prevent duplicate submissions.
Successful submission creates the patient record and MDT case, starts the preparation check, and opens the selected MDT's patient list with the new patient visible. The case initially shows **Not ready — Initial check pending**. Name and diagnosis support registration; linking clinical records requires a stable patient identifier or an explicit matching workflow, not a name-only match. If source records cannot be linked, display that reason rather than implying the check passed.
The scheduling model must include meeting ID, date/time, label, eligible diagnoses, and whether the meeting accepts registrations. The selectable dates are not limited to the dashboard's next seven days.

### 7.6 Patient detail layout
One screen, designed for projection in an MDT meeting:
| # | Section | Content |
|---|---|---|
| 1 | **Header strip** | Pseudonym, age/sex, diagnosis, stage, ECOG if available, MDT date, readiness badge (green / amber / red) |
| 2 | **Key question box** | The question for the MDT, taken from the referral |
| 3 | **Imaging timeline** (center) | Horizontal timeline of CT/MR/PET overlaid with treatment events. Each exam card shows date, one-line impression, comparison relationship, availability status, and a link to the report or image viewer |
| 4 | **Lesion and response tracker** | Target lesion sizes over time, extracted from reports, with RECIST-style categories where supported. Clearly marked as *extracted values, to be verified against images* |
| 5 | **Lab trends** | Tumor markers and key labs as sparklines, with treatment overlay |
| 6 | **Treatment history** | Lines of therapy, dates, doses, toxicities, reasons for stopping |
| 7 | **Open issues panel** | Waived or missing items, data conflicts, low-confidence extractions |
| 8 | **AI summary** (optional) | Short narrative with each statement linked to its source document; labeled as an aid, not a recommendation |
| 9 | **Decision capture** | Form for MDT outcome (recommended action, responsible doctor, follow-up date), written back to the HIS |
### 7.7 Design principles
- **Traceability:** every number and claim links to its source report.
- **Presentation mode:** large font, high contrast, single page, plus print/PDF export for MDT minutes.
- **Multi-patient MDT agenda:** a list of the day's cases with readiness badges.
- **Role-aware views:** radiologists see imaging detail first; oncologists see treatment and labs first.
- **No AI treatment recommendations.** The system structures information; doctors decide.
---
## 8. MDT Integration
Allow registration before preparation is complete. Adding a patient to an eligible MDT starts the check and immediately shows the case on its agenda with one of the three readiness states and a clear reason, such as "missing: PET 05/2025 from Hospital X, request sent." Readiness must remain visible in the patient list, scheduled MDT sidebar, and seven-day dashboard; it must not prevent the user from adding a patient.
This directly addresses the core goal of entering a patient into an MDT without calling around.
---
## 9. End-to-End Demo Flow
1. From the seven-day dashboard, the user opens **Add patient**, enters a name and diagnosis, chooses an eligible MDT date and meeting, and submits. The patient appears on the agenda as **Not ready — Initial check pending**.
2. The HIS integration loads reports, labs, and medications into the canonical model.
3. The pipeline builds the imaging timeline and finds that a PET from an external hospital is referenced but absent from the mock PACS.
4. A request is drafted and sent by email. After no reply, the system escalates with a simulated voice call.
5. The provider "sends" the study, status turns to `RECEIVED`, and a verification step checks modality, date, and series.
6. All items are verified, so the patient changes to **Ready** on the existing MDT agenda. The meeting status and seven-day dashboard counts update accordingly.
7. In the meeting, doctors review the dashboard, record a decision, and it is written back to the HIS.
---
## 10. Architecture and Technology Stack
### 10.1 Logical components
```
[HIS / dataset] → [Integration adapters] → [Canonical model (DB)]
                                                  ↓
                         [Extraction (LLM + rules)] → [Timeline]
                                                  ↓
              [Rule engine: expected priors] + [PACS adapter (mock)]
                                                  ↓
                                      [Gap detection]
                                                  ↓
                         [Request orchestrator] ↔ [Email / Voice sandbox]
                                                  ↓
                                   [Verification → Readiness]
                                                  ↓
                          [Dashboard + MDT agenda + HIS write-back]
```
### 10.2 Suggested stack
| Area | Choice |
|---|---|
| Backend | Python (FastAPI), PostgreSQL |
| Workflow | Task queue (Celery or similar) for the request state machine |
| Extraction | LLM with strict JSON schema, plus rule-based validation |
| Frontend | React or Streamlit for a quick demo |
| Visualization | Plotly or vis-timeline for timelines, standard charting for labs and lesions |
| Standards | FHIR for HIS exchange; DICOM (QIDO-RS/WADO-RS) for the future PACS adapter |
---
## 11. Evaluation and Metrics
### 11.1 Gap detection
- Manually annotate a sample of patients with their truly required priors.
- Measure **recall** (the critical metric, since a missed scan is the costly error) and **precision** (to avoid alert fatigue).
- Compare against a naive baseline such as "last exam of the same modality."
### 11.2 Request loop
- Median time from detection to receipt
- Number of manual phone calls avoided
- Share of requests resolved without escalation
### 11.3 Dashboard
- Case preparation time before and after
- Clinician feedback (short usability questionnaire) on whether it contains what is needed for the decision
### 11.4 Extraction accuracy
- Field-level accuracy of lesion sizes, dates, and treatment lines against a hand-labeled sample
---
## 12. Safety, Privacy, and Compliance
- **Human in the loop:** the system flags and drafts; a coordinator confirms.
- **Privacy:** run any LLM locally or in a compliant environment; never attempt to re-identify patients; minimize data in outbound messages.
- **Legal:** confirm legal basis and inter-institution agreements before real deployment (GDPR, national health-data law).
- **Transparency:** state clearly that availability is simulated, so results demonstrate the logic, not real PACS coverage.
- **Clinical safety:** extracted values (e.g. lesion sizes) are aids and must be verified against source reports and images. The AI makes no treatment recommendations.
- **Auditability:** every request, call, status change, and waiver is logged.
---
## 13. Build Plan and MVP Scope
### 13.1 MVP (enough to demo the full flow)
1. Extract the timeline and external comparisons from reports.
2. Apply simple rules (last same-region exam plus baseline).
3. Run against a mock inventory.
4. Output a sortable worklist with draft request messages.
### 13.2 Suggested build order
| Phase | Deliverable |
|---|---|
| 1 | Canonical data model and dataset-based HIS loader |
| 2 | Timeline extraction and gap detection with mock PACS |
| 3 | Request state machine with sandbox email and voice |
| 4 | Scheduled MDT sidebar, seven-day dashboard, per-MDT patient lists, diagnosis-filtered patient registration, and patient detail view |
| 5 | Polish: AI summary with source links, presentation mode, MDT agenda view |
### 13.3 Later extensions
- Diagnosis-specific rule sets
- Real PACS adapter (DICOM QIDO-RS/WADO-RS)
- Live HL7/FHIR connectors
- Auto-send for low-risk routine requests
- Direct integration with national image-sharing platforms
---
## 14. Risks and Mitigations
| Risk | Mitigation |
|---|---|
| Wrong inference of required priors | Configurable per-diagnosis rules, recall-focused evaluation, human confirmation |
| Extraction errors (dates, sizes) | Strict schema, validation rules, source links, confidence flags |
| Alert fatigue | Precision tracking, priority by days remaining, tuned thresholds |
| Wrong patient match on external studies | Multi-field matching, human review for uncertain cases |
| Privacy breach in outbound requests | Data minimization, secure channels, no sensitive details by voice |
| Provider non-response | Reminder cascade, voice escalation, human fallback |
| Overreliance on AI summary | Source-linked statements, "aid only" labeling, no recommendations |
| Simulated PACS misrepresents reality | Explicit disclosure; adapter isolates the simulation |
---
## 15. Next Steps
Depending on priorities, the following could be drafted next:
- The **canonical data schema** (patient, report, imaging study, treatment event, request)
- The **request state machine in code**
- A **wireframe of the dashboard**
- The **LLM extraction prompt and JSON schema** for reports
If you share the dataset format (structured or free text, language, size), the extraction schema and rule set can be made much more specific.
