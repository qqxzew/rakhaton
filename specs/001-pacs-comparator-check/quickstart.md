# Quickstart: Local Validation

This is the target validation path for the implementation in [CLAUDE.md](../../CLAUDE.md). It begins with the local FHIR store so that development and the demo do not depend on an IRIS instance. Runtime data remains in git-ignored `data/`.

## Prerequisites

- Python 3.11 or later and `uv`.
- Node.js and npm compatible with the Vite frontend.
- The provided dataset archive at the repository root for dataset-backed demo preparation.
- A valid hackathon LLM gateway key in the ignored root `.env` only if running live extraction. Never put the key in frontend settings, source files, output, or version control.
- Docker Compose and the InterSystems FHIR-AI Hackathon Kit setup only for the optional IRIS-mode check.

## Local-mode setup

From the repository root in PowerShell:

```powershell
Set-Location C:\Users\fandr\Desktop\walking-legs
uv sync --project backend
npm --prefix frontend ci
```

Configure the backend to use `FHIR_BACKEND=local`, `APP_DB_URL=sqlite:///data/app.db`, and the required LLM settings in the ignored `.env`. Do not copy patient records or credentials into documentation or commands. Extract the archive only with the project extraction script into `data/raw/`; do not commit or inspect raw data outside the approved application workflow.

## Validate the core behavior

Run automated tests before launching the UI:

```powershell
uv run --project backend pytest
uv run --project backend ruff check backend
npm --prefix frontend run build
```

Expected: unit tests cover date parsing, modality/region normalization, matching, rules, readiness precedence, request transitions, eligibility, duplicate prevention and verification using synthetic fixtures; the pipeline integration test uses a synthetic FHIR bundle and mocked LLM. No test reads `data/raw/`.

Start the local application in two terminals:

```powershell
uv run --project backend uvicorn app.main:app --reload
```

```powershell
npm --prefix frontend run dev
```

Open the local Vite URL. Check `/api/health`, the next-seven-day dashboard, one patient detail and the source evidence for an extracted fact. The detail should display simulated availability explicitly, and any AI-derived quote must be an exact part of its source text.

## End-to-end demo check

Use a configured demo patient with synthetic data for automated validation, or the approved dataset-backed demo patient selection for the live hackathon demonstration. Do not write dataset pseudonyms or report text into tracked files.

1. Add a patient to a configured eligible MDT; confirm it appears as `Nepřipraveno – Probíhá úvodní kontrola`.
2. Open the patient and confirm the planned exam, required prior studies, exact quote, and availability classification.
3. Confirm one unavailable or unlocated study produces a draft request and the interface labels simulated elements.
4. Approve the request; verify approval actor/time exists before a message appears in the sandbox outbox/Mailpit.
5. Simulate a reply and advance demo time to trigger reminder and voice escalation.
6. Simulate a matching study receipt and verify that only a modality/date/region match resolves the item; a mismatch must remain blocking with an explanation.
7. Confirm case, meeting, day and dashboard readiness/counts update consistently. Target complete customer-table flow: under 4 minutes.

## Optional IRIS-mode check

After the IRIS milestone (M7), start the kit's configured FHIR R4 service with the project Compose setup, load only the selected demo/subset bundles, set `FHIR_BACKEND=iris` and the endpoint/credentials through ignored environment configuration, then repeat the health and end-to-end checks. Confirm the same FHIR `ServiceRequest`, `Observation`, `Provenance`, `Task`, `Communication` and `AuditEvent` resources can be read through IRIS. Keep the local store usable as a fallback.

IRIS endpoint path, authentication, and exact Compose service names come from the checked-out Hackathon Kit version and `.env`; do not infer them or commit credentials. This project does not connect to a real PACS, ePACS, hospital, email recipient, or telephone endpoint.
