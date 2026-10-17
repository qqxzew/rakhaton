# Feature Specification: PACS Comparator Check

**Feature Branch**: `001-pacs-comparator-check`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "A coordinator-facing tool for oncology tumor board (MDT) preparation. For every patient scheduled for an MDT or a planned CT/MR/PET, it determines from anonymized reports which prior imaging studies are needed for comparison, checks whether they are available (simulated PACS), flags what is missing in time, drafts requests to the hospitals that hold the missing studies, sends them after coordinator approval, follows up automatically (reminder, voice call), verifies received studies and shows a readiness status per patient, per meeting and per day for the next seven days. Full design details are in CLAUDE.md."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See which prior studies a patient needs and which are missing (Priority: P1)

A coordinator (or radiologist) opens one patient. The system has already found the patient's planned examination in the clinical notes and shows a list of the prior imaging studies needed for comparison. For each study it shows why it is needed (for example "baseline before treatment", "latest CT of the same region", "comparison study cited in the report from 2 March"), whether its images are available, and the exact sentence from the source report that proves it. Studies cited in reports but not found anywhere are clearly marked as missing.

**Why this priority**: This is the customer's core problem. Without it nothing else has value; with only this story the coordinator already saves the phone calls needed to find out what is missing.

**Independent Test**: Pick a patient whose reports cite an earlier study that does not exist in the hospital data and who has an internal study without images in PACS. Open the patient and confirm both appear as missing with correct reasons and quotes, and that available studies appear as available.

**Acceptance Scenarios**:

1. **Given** a patient whose report says the current CT was compared with an earlier PET/CT that is not in the hospital data, **When** the coordinator opens the patient, **Then** that PET/CT is listed as "cited in a report but not found", with the cited date, the likely holding hospital if written, and the quoted sentence.
2. **Given** a patient with an internal study whose images are flagged as not in PACS, **When** the coordinator opens the patient, **Then** that study is listed as "exists, images not in PACS".
3. **Given** a patient with a planned examination written in a clinic note (dated or "in 3 months"), **When** the patient is opened, **Then** the planned examination is shown with modality, region, date and the source quote, and the coordinator can correct it.
4. **Given** an extracted reference with an implausible date, **When** the list is shown, **Then** it is marked "requires attention" instead of a hard gap.

---

### User Story 2 - Plan the week: seven-day MDT dashboard and adding patients (Priority: P2)

The coordinator opens the application and sees the MDT meetings of today and the next six days, each with an overall readiness status (Ready, Requires attention, Not ready), patient counts per status, and per-day grouping. A sidebar lists only dates with scheduled meetings, each with its aggregate status. The coordinator adds a patient: picks the patient, selects a diagnosis group, sees only the meetings that accept that diagnosis, selects a meeting and confirms. The patient appears on that meeting immediately as "Not ready, initial check running", and the status updates when the check finishes.

**Why this priority**: It turns the per-patient check into a daily working tool and shows the customer the workflow they actually live in.

**Independent Test**: With a configured schedule, add a patient to an eligible meeting, see it appear as "initial check running", then see the patient, meeting, day and dashboard statuses update consistently after the check.

**Acceptance Scenarios**:

1. **Given** meetings in the next seven days, **When** the dashboard opens, **Then** it shows the explicit window dates, total meetings, counts per readiness state, and each day's meetings with time, label, status and patient counts; days without meetings say "no MDT".
2. **Given** a diagnosis group is selected on the add-patient page, **When** eligible meetings are listed, **Then** only meetings configured for that group appear, including dates beyond seven days; changing the group clears an incompatible selection.
3. **Given** no meeting accepts the selected diagnosis, **When** the page lists meetings, **Then** it explains that none are available and lets the user change the diagnosis.
4. **Given** a meeting with one Not ready patient and one Ready patient, **When** statuses are aggregated, **Then** the meeting and its date are Not ready; an empty meeting shows Requires attention with "no patients".
5. **Given** the user submits the same patient for the same meeting twice, **When** the second submission arrives, **Then** it is rejected without creating a duplicate.

---

### User Story 3 - Request missing studies and track them to verification (Priority: P3)

For every missing study the system drafts a request to the probable holding hospital. The coordinator approves one request or all of a meeting's requests with one click. Approved requests are sent automatically with minimal data. Replies are recognized and classified (will send, sent, not here, need more info, wrong recipient). When a study arrives it is checked against the request; only a matching study counts. When every required study is verified or explicitly waived, the patient becomes Ready.

**Why this priority**: It closes the loop and removes the manual phone work, but it depends on Story 1.

**Independent Test**: For a patient with one missing study, approve the drafted request, simulate a reply "sending via ePACS", simulate delivery of a matching study, and confirm the patient turns Ready; repeat with a non-matching study and confirm it stays Not ready with a reason.

**Acceptance Scenarios**:

1. **Given** a drafted request, **When** the coordinator has not approved it, **Then** nothing is sent.
2. **Given** several drafted requests for one meeting, **When** the coordinator clicks "approve all", **Then** all are sent and each approval is recorded with the coordinator's name and time.
3. **Given** a sent request, **When** a reply saying the hospital does not have the study arrives, **Then** the request is marked rejected with the quoted reason and the item stays missing.
4. **Given** a received study whose modality or date does not match, **When** verification runs, **Then** the item stays missing with the mismatch explained.
5. **Given** a missing study the doctor decides is not needed, **When** the coordinator waives it with a reason, **Then** it no longer blocks readiness and the waiver is visible.

---

### User Story 4 - Proactive preparation before the meeting (Priority: P4)

Two days before each meeting a scheduled run re-checks all its patients and prepares requests; the morning view shows "N requests ready for approval". After approval, the system follows up by itself: if a hospital does not answer within a day, it sends a reminder; if still nothing and the meeting is close, it places an automated voice call (in Czech, without identifying the patient) and finally hands the case to the coordinator. On the meeting day the doctor sees what is ready and what is still missing.

**Why this priority**: This is the strongest differentiator ("the system acts before anyone asks"), but it builds on Stories 1 to 3.

**Independent Test**: Trigger the scheduled run for a meeting two days ahead, approve, advance simulated time without replies, and confirm reminder, voice escalation and human escalation happen in order and are logged.

**Acceptance Scenarios**:

1. **Given** a meeting in two days with unchecked patients, **When** the scheduled run executes, **Then** all its cases are re-checked and drafts are created for every new gap.
2. **Given** an approved request without a reply for one day, **When** time passes, **Then** a reminder is sent; without a reply on the day before the meeting, a voice message is produced and logged.
3. **Given** a voice call, **When** its script is produced, **Then** it mentions only the hospital, the request number and the requested route.

---

### User Story 5 - Show measured quality (Priority: P5)

A teammate labels a sample of reports by hand (which prior studies each report cites). The system computes how many cited studies it finds correctly (recall) and how many of its findings are correct (precision), compared with a naive baseline, and shows whole-dataset statistics (reports with references, cited studies not found, studies not in PACS).

**Why this priority**: Numbers make the result credible for the customer and the jury, but the product works without them.

**Independent Test**: Run the evaluation on the labeled sample and confirm precision, recall and baseline figures are produced.

**Acceptance Scenarios**:

1. **Given** a labeled sample, **When** evaluation runs, **Then** precision and recall of reference extraction and of planned-exam extraction are reported.

---

### Edge Cases

- A patient has no imaging studies at all: show Requires attention, "no prior studies found", not Ready.
- A report cites a study by month only ("from 03/2025"): match any study of that month.
- A cited date is impossible (after the report, or many years back): flag as a likely typo, do not request automatically.
- The holding hospital is not written: mark the site as unknown and let the coordinator choose one before sending.
- The same study is required by several rules: show it once with all reasons.
- The PACS availability flag is unknown: Requires attention, not missing.
- A reply cannot be matched to a request: keep it in an "unmatched replies" list for the coordinator.
- The language model is unavailable or rate-limited: retry, then mark the case check as failed with a clear reason; previously computed results remain visible.
- A received study arrives for a request that was already waived: log it, do not change readiness.
- The patient's records cannot be loaded: Not ready, "records could not be loaded".
- Duplicate clinical documents: count each fact once.

## Requirements *(mandatory)*

### Functional Requirements

**Planned exam and timeline**
- **FR-001**: System MUST build, per patient, a timeline of internal imaging studies, treatment milestones and MDT documents from the hospital records.
- **FR-002**: System MUST extract planned examinations (modality, body region, date or relative timing, target site) from clinical notes, resolving relative timing against the note date.
- **FR-003**: Users MUST be able to correct the planned examination of a case.

**Prior studies and gaps**
- **FR-004**: System MUST extract from each radiology report every cited prior study (modality, region, date as written and normalized, site if written) together with the exact quoted sentence and a confidence value.
- **FR-005**: System MUST reject or flag any extracted quote that is not an exact part of the source text.
- **FR-006**: System MUST match cited studies to the patient's internal studies by modality, date (exact, within 3 days, or same month for month-only dates) and overlapping region.
- **FR-007**: System MUST determine the required prior studies for a planned exam using configurable rules: studies cited in relevant recent reports; the latest and second-latest study of the same modality and region; the baseline before treatment start; the latest study of a complementary modality of the same region; the study before the latest MDT decision.
- **FR-008**: System MUST classify each required study as available, exists without images, availability unknown, or cited but not found.
- **FR-009**: System MUST show for each required study its reasons, availability, likely holding site and source quote.
- **FR-010**: System MUST flag implausible dates, low-confidence extractions and long imaging gaps as items requiring attention.

**Readiness**
- **FR-011**: System MUST compute a readiness state per patient case: Not ready (check pending, records unavailable, or any required study missing and not verified or waived), Requires attention (any uncertain item, pending approval, conflict, or no prior studies found), Ready (all required studies available, verified or waived).
- **FR-012**: System MUST always show a short reason with each readiness state and pair every status color with an icon and text.
- **FR-013**: System MUST give each meeting the most severe state of its cases, each day the most severe state of its meetings, and an empty meeting the state Requires attention with "no patients".
- **FR-014**: System MUST recalculate patient, meeting, day and dashboard states whenever a case changes.

**Scheduling and navigation**
- **FR-015**: System MUST provide a configurable MDT schedule with several meetings per day possible, each with id, date, time, label, eligible diagnosis groups and whether it accepts registrations.
- **FR-016**: System MUST show a landing dashboard for today plus six days with explicit window dates, totals per state and meetings grouped by day.
- **FR-017**: System MUST show a sidebar listing only scheduled dates (including dates beyond the seven-day window) with one aggregate status each.
- **FR-018**: System MUST show, for a selected day, each meeting with its status and its patient rows (display name, diagnosis, status, short reason).
- **FR-019**: Users MUST be able to add a patient by choosing a dataset patient, a diagnosis group and an eligible meeting; eligibility comes only from configuration; linking to records is by patient identifier, never by name.
- **FR-020**: System MUST validate required fields, re-check meeting availability on submission and prevent duplicate cases.
- **FR-021**: System MUST start the preparation check immediately after a case is added and show it as Not ready, "initial check running" until it completes.
- **FR-022**: System MUST present patient dates shifted into the demo calendar consistently per patient and state that dates were shifted.

**Requests**
- **FR-023**: System MUST draft a request for every missing required study, addressed to the probable holding site from a provider registry, or to "unknown site" for the coordinator to choose.
- **FR-024**: System MUST NOT send any request without a recorded approval; users MUST be able to approve one request or all drafted requests of a meeting or of the seven-day window.
- **FR-025**: Outbound messages MUST contain only the request id, study date, modality, body region, requesting site, requested route and deadline.
- **FR-026**: System MUST track each request through: detected, drafted, approved, sent, acknowledged, received, verified, closed, with side outcomes rejected, needs info, wrong recipient, cancelled, reminder sent, voice escalated, human escalated; every transition is logged with time and actor.
- **FR-027**: System MUST classify incoming replies and update the request accordingly, keeping the quoted justification.
- **FR-028**: System MUST verify a received study against the request (modality, date window, region) and only then treat the item as available.
- **FR-029**: Users MUST be able to waive a required study with a reason.

**Proactive follow-up**
- **FR-030**: System MUST run a scheduled preparation for every meeting a configurable number of days ahead (default two) that re-checks cases and drafts requests, and summarize the result for the coordinator.
- **FR-031**: System MUST send a reminder when a sent request has no reply after a configurable period (default one day) and escalate to an automated voice message when the meeting is within 48 hours, then to the coordinator.
- **FR-032**: Voice messages MUST mention only the requesting site, the request number and the requested route.

**Simulation, traceability, interoperability**
- **FR-033**: System MUST label every simulated element (availability, other hospitals, message delivery, calls, replies, received studies, schedule, display names, date shift) in the interface.
- **FR-034**: System MUST store the planned exam, extracted references, required-study tasks, messages, provenance of every AI-derived fact and an audit trail in the standard health-data exchange format used by the hospital records, and read clinical facts from it.
- **FR-035**: Users MUST be able to open the source text of any quote with the quoted part highlighted.
- **FR-036**: System MUST provide demo controls to run the scheduled preparation, advance time, simulate replies, simulate calls and simulate deliveries; a presentation mode hides them.

**Quality measurement**
- **FR-037**: System MUST compute precision and recall of reference and planned-exam extraction against a hand-labeled sample, and whole-dataset statistics, compared with a naive baseline.

### Key Entities

- **Patient**: pseudonymous identifier, fictional display name, sex, age band, diagnoses.
- **Imaging study**: internal, cited or received study with date, modality, region set, site and image availability.
- **Cited reference**: a prior study mentioned in a report, with quote, written and normalized date, site text, confidence, date validity and the matched study if any.
- **Planned examination**: modality, region, date or relative timing, target site, source quote.
- **Meeting**: an MDT session with date, time, label, eligible diagnosis groups and registration flag.
- **Case**: a patient registered to a meeting, with reference date, date shift, check status, readiness and reason.
- **Required study**: one study needed for a case, with rule reasons, availability, holding site, evidence, waiver and its request.
- **Request**: a request to a provider with id, state, approval record, attempts, history and messages.
- **Provider**: a hospital or department with aliases, contacts, working hours, preferred channel and exchange route.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a demo patient, the coordinator sees the complete list of required prior studies with status and evidence within 5 seconds of opening the patient (results prepared in advance).
- **SC-002**: The full demo scenario (dashboard → patient → approve all → no reply → reminder → voice → reply → delivery → Ready) can be shown end to end in under 4 minutes without manual data editing.
- **SC-003**: Reference extraction reaches at least 85% recall and 80% precision on the hand-labeled sample, and recall is higher than the naive "latest same modality" baseline.
- **SC-004**: 100% of shown AI-derived facts have a quote that is an exact part of the source text.
- **SC-005**: 0 outbound messages are sent without a recorded approval, and 0 outbound messages contain a name, birth date or diagnosis text.
- **SC-006**: Preparing one patient for an MDT requires no phone call by the coordinator in the demo scenario (all requests issued and followed up by the system).
- **SC-007**: A coordinator can add a patient to an eligible meeting in under 1 minute.
- **SC-008**: Readiness states of patient, meeting, day and dashboard are consistent in 100% of tested aggregation cases.

## Assumptions

- Users are hospital MDT coordinators and radiologists; a single coordinator name field replaces authentication in the prototype.
- The hospital data is the provided anonymized Motol dataset; dates are shifted per patient, names do not exist, all structured studies are internal, other hospitals appear only in text, and there are no structured planned exams.
- PACS availability, other hospitals, message delivery, calls, replies and received studies are simulated; real PACS/ePACS, telephony and email to real hospitals are out of scope.
- ePACS today offers no query of where a patient's images are, and requests are made by phone or email, so email and voice are the realistic channels.
- The MDT schedule and diagnosis-to-meeting eligibility are configured, not taken from data.
- The interface language is Czech; the prototype targets desktop browsers and projection in a meeting room.
- Lab trends, lesion tracking, therapy tables, AI clinical summaries, decision capture and series-level checks are out of scope for this feature.
- Implementation details (stack, architecture, prompts, data model, API) are defined in CLAUDE.md and are used by the planning phase.
