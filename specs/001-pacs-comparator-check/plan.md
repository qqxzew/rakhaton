# Implementation Plan: PACS Comparator Check

**Branch**: `001-pacs-comparator-check` | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

## Summary

Build a Czech-language coordinator web app that finds the previous imaging studies needed for a planned CT/MR/PET or MDT, explains each finding with a source quote, checks image availability through an explicitly simulated PACS adapter, and tracks missing studies through human-approved requests, follow-up, receipt verification, and readiness. Read clinical facts from FHIR R4 and write derived facts and workflow records as FHIR resources. Keep app-only meeting/case state in a relational store. Start with a local FHIR bundle store so the end-to-end scenario works without IRIS; add the InterSystems IRIS for Health FHIR R4 store as a replaceable backend.

Implementation is sequenced by the milestones in [CLAUDE.md](../../CLAUDE.md#16-build-order-milestones): local data/store and LLM foundation; extraction and rules; FHIR outputs; scheduling/API; UI; approved request loop; simulated escalation; optional IRIS deployment; evaluation and polish.

## Technical Context

**Language/Version**: Python 3.11+ backend; TypeScript with React 18 frontend.

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy, OpenAI-compatible client for the provided Azure APIM LLM gateway; Vite, React Router, TanStack Query, Tailwind; Docker Compose for the optional IRIS/Mailpit services. The LLM model and gateway settings come from environment configuration; report-text calls use EU data-zone deployments.

**Storage**: FHIR R4 per-patient bundles in the local mode and InterSystems IRIS for Health FHIR R4 in the IRIS mode. Derived FHIR resources are written to `data/fhir_out/` by the local store. App-only state uses SQLite in `data/app.db`. Dataset, report text, caches, labels, outbox and generated voice files stay under git-ignored `data/`.

**Testing**: `pytest` and `ruff` for Python; frontend validation/build using the Vite project scripts. Unit tests use hand-written synthetic fixtures only. A pipeline integration test uses a synthetic FHIR bundle and a mocked LLM; tests must not read `data/raw/`.

**Target Platform**: Desktop browser for a coordinator and projection; local development on Python 3.11+ and Node.js, with Docker for the optional IRIS environment.

**Project Type**: Full-stack web application with Python API/backend and React frontend.

**Performance Goals**: A prepared patient detail view is available within 5 seconds; a coordinator can add a patient in under 1 minute; the full demo workflow is shown in under 4 minutes. Report extraction targets at least 85% recall and 80% precision on the hand-labeled sample; every surfaced AI fact has an exact source quote.

**Constraints**: Patient data and derived text stay in ignored local storage; no patient data in source, tests, logs, commits, or external messages. No message is sent without recorded coordinator approval. All AI facts retain document id, exact quote, and confidence. Simulated PACS, providers, messages, calls, replies, and receipts are visibly labeled and isolated behind adapters. No clinical recommendations, live PACS/ePACS/DICOM, real external email/telephony, authentication, or write-back to a HIS. The application reads and writes FHIR R4; only app-only scheduling and UI state may use SQLite.

**Scale/Scope**: The supplied dataset covers 1,830 patients, 29,324 clinical documents, 3,254 imaging studies and full FHIR R4 bundles per patient. IRIS loading is initially capped to a configured subset (default 300); local mode remains usable across milestones. The feature includes the five user stories and acceptance requirements in `spec.md`, delivered in milestone order.

## Constitution Check

*Gate: evaluated before research and re-evaluated after design.*

| Principle | Gate | Plan evidence |
|---|---|---|
| I. Patient Data Stays Local | PASS | Raw data, derived text, caches, labels, outbox and app data remain under ignored `data/`; tests and docs use synthetic examples only. LLM report-text calls use EU deployments. |
| II. Human Approves Outbound Actions | PASS | Request state machine records coordinator and time before any simulated delivery; approve-one and approve-all share the same guarded transition. |
| III. Traceable AI Output | PASS | Extracted facts retain source resource/document id, exact-substring quote and confidence; invalid quotes are rejected or surfaced for attention. |
| IV. Honest Simulation | PASS | PACS and external workflow behavior use narrow adapter interfaces and are marked simulated in the UI and stored records. |
| V. No Clinical Recommendations | PASS | The system structures records and identifies missing material only; meeting eligibility is configuration-based. |
| VI. One Working Scenario First | PASS | Work follows M0–M9 in `CLAUDE.md`, keeping a local end-to-end scenario working before breadth and polish. |
| VII. FHIR as System of Record | PASS | Clinical inputs and clinical/workflow outputs use FHIR R4 through one store interface; SQLite is restricted to app-only state. |

No constitution violations or unresolved product clarifications were identified. IRIS is an optional later milestone, not a prerequisite for delivering the local working scenario.

## Project Structure

### Documentation (this feature)

```text
specs/001-pacs-comparator-check/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── http-api.md
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── api/
│   ├── app_db/
│   ├── fhir_store/
│   ├── llm/
│   ├── pipeline/
│   ├── requests/
│   └── scheduling/
├── scripts/
└── tests/
frontend/
└── src/
    ├── components/
    ├── i18n/
    ├── pages/
    └── services/
config/
data/                         # git-ignored runtime data only
docker-compose.yml            # IRIS and Mailpit development services
```

**Structure Decision**: Full-stack web application, matching the existing architecture in `CLAUDE.md`. The API, processing pipeline, FHIR adapters and app-state persistence remain in `backend/`; the Czech UI and typed API client remain in `frontend/`. Runtime/patient data is isolated under ignored `data/`. No additional service or database is introduced.

## Design Outputs

- [research.md](./research.md) records integration choices, evidence, alternatives and compatibility boundaries for FHIR R4 and IRIS.
- [data-model.md](./data-model.md) specifies application entities, relationships, validations, state transitions and their FHIR persistence mapping.
- [contracts/http-api.md](./contracts/http-api.md) defines the JSON API surface, workflow guarantees and error behavior.
- [quickstart.md](./quickstart.md) gives the local-mode validation path and optional IRIS verification path.

## Complexity Tracking

No constitution exceptions. The two-store abstraction is required to keep the demo runnable without IRIS while preserving FHIR R4 as the clinical source of truth; it is not a second application or a second clinical data model.
