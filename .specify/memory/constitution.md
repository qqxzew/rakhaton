<!--
Sync Impact Report
- Version change: 1.0.0 → 1.1.0 (principle VII: IRIS is the core and primary store)
- Principles added: I. Patient Data Stays Local; II. Human Approves Outbound Actions; III. Traceable AI Output;
  IV. Honest Simulation; V. No Clinical Recommendations; VI. One Working Scenario First; VII. FHIR as System of Record
- Sections added: Technology and Data Constraints; Development Workflow and Quality Gates; Governance
- Templates: plan-template.md (Constitution Check reads these principles) ✅ no edit needed;
  spec-template.md ✅ no edit needed; tasks-template.md ✅ no edit needed
- Runtime guidance file: CLAUDE.md (repository root) is the detailed build specification
- Follow-up TODOs: none
-->

# PACS Comparator Check Constitution

## Core Principles

### I. Patient Data Stays Local (NON-NEGOTIABLE)
Real or pseudonymized patient data, and anything derived from it (report text, pseudonyms, LLM caches,
outbound message files, labels), lives only under the git-ignored `data/` directory. It MUST NOT appear in
code, tests, fixtures, comments, documentation, commit messages, issues or boards. Tests use hand-written
synthetic fixtures. Secrets (the LLM key) live only in `.env` and are read only by the backend. LLM calls that
contain report text use EU data-zone deployments.
Rationale: the dataset is non-public health data under GDPR and the hackathon rules forbid publishing it.

### II. Human Approves Outbound Actions (NON-NEGOTIABLE)
The system may detect gaps and draft requests on its own, but it MUST NOT send any message to an external
party (email, call, API request) without a recorded approval by a coordinator (one click per request or
"approve all"). Outbound messages carry the minimum data: request id, study date, modality, body region.
Voice calls never identify the patient.
Rationale: accountability, data minimization and trust of the clinical customer.

### III. Traceable AI Output
Every fact produced by an AI model (referenced prior study, planned exam, reply classification) MUST keep its
source document id, the exact quoted span and a confidence value. Quotes are verified to be exact substrings of
the source. Low-confidence or implausible results are surfaced as "requires attention", never silently accepted.
Rationale: clinicians must be able to verify every claim in seconds.

### IV. Honest Simulation
Everything that is simulated (PACS inventory, other hospitals, email delivery, voice calls, provider replies,
received studies, the MDT schedule, display names and the demo date shift) MUST be labeled as simulated in the
UI and in stored data, and MUST sit behind an adapter interface that a real integration could replace.
Rationale: the customer and the jury must see working logic, not fake integrations.

### V. No Clinical Recommendations
The product structures information and finds missing material. It MUST NOT suggest diagnoses, therapies or
clinical decisions. MDT eligibility comes from configuration, never from an AI suggestion.
Rationale: this is a prototype, not a medical device; doctors decide.

### VI. One Working Scenario First
Work proceeds in the milestone order defined in CLAUDE.md. One end-to-end demo scenario must keep working at
all times; breadth and polish come only after it works. Prefer simple, boring solutions (YAGNI); every added
component must serve the demo scenario or a judging criterion.
Rationale: a 24-hour hackathon with one developer driving AI agents.

### VII. FHIR as System of Record
Clinical facts are read from HL7 FHIR R4, and our outputs (planned exam, extracted references, tasks, messages,
provenance, audit events) are written back as FHIR R4 resources in InterSystems IRIS for Health, which is the
core of the product: IRIS FHIR is the primary store, app state lives in IRIS SQL, and the request loop runs as an
IRIS Interoperability production. A local file store exists only for unit tests and as a fallback, behind the same
interface.
Rationale: interoperability is the customer's real-world constraint and the InterSystems prize criterion.

## Technology and Data Constraints

- Backend Python 3.11+ (FastAPI, Pydantic v2); frontend React + TypeScript + Vite + Tailwind; UI language Czech.
- LLM access only through the provided OpenAI-compatible gateway, with retry on rate limits and a result cache.
- Dataset handling exactly as described in CLAUDE.md section 4 (shifted dates per patient, no names,
  no planned exams in structured data, PACS flag semantics, references only in free text).
- Out of scope: real PACS/ePACS/DICOM, real telephony, real email to hospitals, authentication, lab and lesion
  dashboards, AI clinical summaries, write-back to a HIS, series-level checks, PostgreSQL, Celery.

## Development Workflow and Quality Gates

- Each milestone has a "Done when" condition (CLAUDE.md section 16) that must be demonstrated before the next one.
- Required tests: date parsing, normalization, matching, rules, readiness precedence, request state machine,
  verification, eligibility, duplicate prevention; one pipeline integration test with a mocked LLM.
- No test reads `data/raw/`.
- Before every commit: no files under `data/`, no `.env`, no zip, no pseudonyms in the diff.
- Extraction quality is measured on a hand-labeled sample (precision and recall, recall first).

## Governance

This constitution supersedes other practices. CLAUDE.md is the detailed runtime build specification and must
stay consistent with these principles; when they conflict, principles I and II win, then this constitution,
then CLAUDE.md. Amendments are made by editing this file with a version bump (MAJOR: principle removed or
redefined; MINOR: principle or section added; PATCH: wording) and a note in the Sync Impact Report. Every plan's
Constitution Check must verify principles I to VII.

**Version**: 1.1.0 | **Ratified**: 2026-10-16 | **Last Amended**: 2026-10-16
