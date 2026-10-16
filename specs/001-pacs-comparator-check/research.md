# Research: FHIR R4 and InterSystems IRIS

## Scope

Resolve the implementation choice for a local FHIR R4 store plus a later InterSystems IRIS for Health backend, including Python integration, resource choices and endpoint compatibility checks. The product stack, privacy constraints, test approach and milestone order are specified in [CLAUDE.md](../../CLAUDE.md); no material product requirement remains unclear for this plan.

## Decision: Keep one FHIR R4 store interface; use standard REST for IRIS

**Decision:** Implement `FhirStore` once as an application port with local-bundle and IRIS REST adapters. The local adapter remains the default and runnable path; IRIS is added in its own milestone. The Python backend will use standard HTTP against the configured FHIR base rather than depend on a proprietary Python SDK. Use only FHIR interactions confirmed by the target server's `CapabilityStatement`.

**Rationale:** IRIS for Health documents a FHIR Resource Repository and REST interactions including create/read/update/search, batch and transaction, with transaction support subject to limitations. The official “FHIR Client” described for InterSystems is an ObjectScript/interoperability construct, not evidence of a Python SDK. A REST adapter keeps Python/FastAPI independent of IRIS-specific runtime classes and preserves local development.

**Compatibility checks before enabling IRIS mode:**

1. Read the endpoint's `GET [base]/metadata` and confirm its FHIR version is R4 and the resource types/interactions needed by this app are enabled. The documentation's package-driven support makes the core resources plausible, but the exact configured endpoint is authoritative.
2. Verify transaction behavior and reference resolution with the actual kit instance. The documented server does not support circular references within a transaction Bundle.
3. Avoid relying on unsupported search behavior: no cross-type search across compartments; chained search and `_include`/`_revinclude` are unsupported; composite search parameters are unsupported; `_total` is unsupported (use supported summary/count mechanisms if needed); `:missing` and several other modifiers are unsupported. Prefer patient-compartment search or direct bundle/resource operations that the endpoint advertises.
4. Do not assume `$validate` accepts arbitrary profile differentials: the documented R4 implementation is partial and requires a profile snapshot.

**Alternatives considered:** An InterSystems ObjectScript FHIR client or interoperability production would couple the Python product to a separate runtime and exceed the hackathon MVP. Making IRIS mandatory would block the core demo on infrastructure. Persisting clinical facts only in SQLite would violate the FHIR system-of-record principle.

**Sources:**

- [InterSystems IRIS for Health 2024.1: FHIR components](https://docs.intersystems.com/irisforhealth20241/csp/docbook/Doc.View.cls?KEY=HXFHIR_fhir_components)
- [InterSystems IRIS for Health 2024.1: supported FHIR interactions and operations](https://docs.intersystems.com/irisforhealth20241/csp/docbook/Doc.View.cls?KEY=HXFHIR_server_arch_supported)
- [InterSystems IRIS for Health 2026.2: FHIR server introduction](https://docs.intersystems.com/irisforhealth20262/csp/docbook/Doc.View.cls?KEY=HXFHIROVW_server_intro)
- [InterSystems IRIS for Health 2026.2: FHIR profiles and packages](https://docs.intersystems.com/irisforhealth20262/csp/docbook/Doc.View.cls?KEY=HXFHIRADM_server_customize)
- [HL7 FHIR R4 RESTful API](https://hl7.org/fhir/R4/http.html)

## Decision: Use FHIR R4 resources according to their semantics

**Decision:** Keep the project's planned mapping: `ServiceRequest` for planned imaging, `Observation` for extracted comparison references, `Task` for coordinator follow-up work, `Communication` for sent/received messages, `Provenance` for AI-derived fact lineage, and `ImagingStudy` for imaging-study metadata. Use `AuditEvent` for applicable audit/security events such as approval and outbound action; keep the full request workflow state/event history in the app's request log and mirror current task status to `Task.businessStatus`.

**Rationale:** HL7 defines `ServiceRequest` as a planned/proposed service request and `Task` as a unit of work with workflow status, which fit the domain. `ImagingStudy` describes imaging metadata and does not contain image payloads, matching the explicit simulated PACS boundary. `Provenance` records entities and processes involved in producing a resource, fitting extraction source/model/quote metadata. `AuditEvent` is intended for security/audit events and is distinct from a general-purpose business event log; it should not replace the request transition history. If every requested approval or patient-view action is represented as `AuditEvent`, verify the chosen IRIS endpoint accepts its creation and preserve local append-only event records regardless.

**Alternatives considered:** Encoding a request lifecycle only in `Communication` loses the explicit work-queue semantics of `Task`. Treating `ImagingStudy` as image storage would misrepresent FHIR and the lack of PACS/image access. Using `AuditEvent` as the sole request state machine would conflate security audit with workflow history.

**Sources:**

- [HL7 FHIR R4 ServiceRequest](https://hl7.org/fhir/R4/servicerequest.html)
- [HL7 FHIR R4 Task](https://hl7.org/fhir/R4/task.html)
- [HL7 FHIR R4 ImagingStudy](https://hl7.org/fhir/R4/imagingstudy.html)
- [HL7 FHIR R4 Provenance](https://hl7.org/fhir/R4/provenance.html)
- [HL7 FHIR R4 AuditEvent](https://hl7.org/fhir/R4/auditevent.html)

## Decisions confirmed from repository context

| Topic | Decision | Rationale / evidence |
|---|---|---|
| API/backend | FastAPI + Python 3.11+, Pydantic v2 | Fixed in project `CLAUDE.md`; the checked repository currently contains only a small gateway-check `main.py`, so app scaffolding belongs in M0. |
| Frontend | React 18 + TypeScript + Vite + Tailwind | Fixed in `CLAUDE.md`; Czech-language coordinator workflow and projection are specified. |
| App-only persistence | SQLite via SQLAlchemy | Fixed in `CLAUDE.md`; keeps local demo simple and avoids a separate DB service. |
| Clinical data | FHIR R4 through local or IRIS implementation of one interface | Constitution principle VII; source bundle inventory and planned mappings in `CLAUDE.md`. |
| AI | Provided OpenAI-compatible Azure APIM gateway, EU data-zone deployments for report text, retry/cache and validated structured output | Fixed by `CLAUDE.md`; patient report data remains within project constraints. |
| PACS/external actions | Explicit simulations behind adapters; approval before any outbound sandbox action | Constitution principles II and IV and challenge data/access constraints. |
| Test strategy | `pytest`, `ruff`, synthetic unit and integration fixtures; no reads of `data/raw/` in tests | Constitution quality gates and `CLAUDE.md` test requirements. |
| Initial delivery order | M0–M9 from `CLAUDE.md`; establish local end-to-end scenario before IRIS integration and polish | Constitution principle VI and the hackathon's short build window. |
| Unspecified quantitative limits | No additional API throughput or population-scale SLO is introduced beyond the measurable demo and extraction targets in the spec | Avoid inventing performance requirements not supported by the use case. |

## Risks and unresolved runtime checks

- The exact hackathon kit's IRIS version, enabled license/features, FHIR base path, credentials, resource interactions and search parameters were not verified against a running instance. Read these from the kit/environment and endpoint metadata; do not hardcode or guess them.
- The official docs reviewed cover IRIS for Health 2024.1/2026.2. Confirm behavior against the actual version packaged for Rakathon before relying on optional interactions.
- No official Python client SDK was identified in the reviewed official documentation; this is a bounded research finding, not an absolute claim that no community client exists. Standard HTTP/FHIR REST is the selected approach.
- Actual training/demo patient selection and extraction quality are data-dependent and must be measured using the labeled sample, without copying records into tracked docs.
