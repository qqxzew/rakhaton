"""Case pipeline: timeline -> priors -> planned exam -> rules -> availability -> gaps -> readiness.

Run from the backend directory:
    python -m app.pipeline.run --patient <id> [--out data/review/<id>.json]
Output is JSON on stdout (or a file inside the git-ignored data directory).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from app.app_db.models import Case, CaseResult, utcnow
from app.app_db.session import session_scope
from app.config import get_settings
from app.fhir_store.base import FhirStore
from app.fhir_store.mappers import write_case_outputs
from app.llm.client import ExtractionFailed, GatewayBackend, LlmBackend, StructuredLlm
from app.logging import configure_logging, get_logger
from app.pipeline.availability import AvailabilityAdapter, DatasetFlagAdapter
from app.pipeline.extract_planned import choose_planned_exam, extract_planned_exams
from app.pipeline.extract_priors import extract_references
from app.pipeline.gaps import build_items, open_issues
from app.pipeline.match import match_references
from app.pipeline.normalize import clean_regions, normalize_modality
from app.pipeline.readiness import compute_readiness
from app.pipeline.rules import compute_required, load_rules_config
from app.pipeline.schemas import (
    CaseCheckResult,
    Evidence,
    OpenIssue,
    PlannedExam,
    PriorReference,
    Timeline,
)
from app.pipeline.timeline import build_timeline

log = get_logger(__name__)


def planned_from_override(override: dict, patient_id: str, fallback: PlannedExam | None) -> PlannedExam:
    """A coordinator correction of the planned exam (modality, regions, date)."""
    exam_date = date.fromisoformat(override["date"]) if override.get("date") else None
    evidence = fallback.evidence if fallback else Evidence(
        doc_id="coordinator", quote="Zadáno koordinátorem", confidence=1.0
    )
    return PlannedExam(
        id=fallback.id if fallback else f"PLAN-manual-{patient_id}",
        patient_id=patient_id,
        modality=normalize_modality(override.get("modality")),
        regions=clean_regions(override.get("regions")),
        date=exam_date,
        site_text=fallback.site_text if fallback else None,
        kind="imaging",
        source_doc_id=fallback.source_doc_id if fallback else "coordinator",
        source_doc_date=fallback.source_doc_date if fallback else None,
        evidence=evidence,
        corrected_by_coordinator=True,
    )


def _strip_text(timeline: Timeline) -> Timeline:
    """Persisted results keep quotes and metadata only; full document text stays in the store."""
    return timeline.model_copy(
        update={"documents": [d.model_copy(update={"text": ""}) for d in timeline.documents]}
    )


def run_patient_check(
    patient_id: str,
    store: FhirStore,
    llm: StructuredLlm,
    *,
    planned_override: dict | None = None,
    group_id: str | None = None,
    adapter: AvailabilityAdapter | None = None,
) -> CaseCheckResult:
    """Pure pipeline run for one patient. Dates stay in the patient's own frame."""
    adapter = adapter or DatasetFlagAdapter()
    timeline = build_timeline(store, patient_id)
    notes: list[str] = []
    extra_issues: list[OpenIssue] = []

    studies_by_report = {s.report_id: s for s in timeline.studies if s.report_id}
    references: list[PriorReference] = []
    for doc in timeline.documents:
        if doc.kind != "radiology_report":
            continue
        study = studies_by_report.get(doc.id)
        try:
            found, dropped = extract_references(llm, doc, patient_id, study.modality if study else None)
        except ExtractionFailed:
            extra_issues.append(OpenIssue(type="data", text="Extrakci odkazů z jednoho nálezu se nezdařila"))
            continue
        references.extend(found)
        notes.extend(dropped)
    references = match_references(references, timeline.studies)

    planned: PlannedExam | None = None
    latest_doc = max((d.date for d in timeline.documents if d.date), default=None)
    try:
        exams, dropped = extract_planned_exams(llm, timeline.documents, patient_id)
        notes.extend(dropped)
        planned = choose_planned_exam(exams, latest_doc)
    except ExtractionFailed:
        extra_issues.append(OpenIssue(type="data", text="Extrakce plánovaného vyšetření se nezdařila"))
    if planned_override:
        planned = planned_from_override(planned_override, patient_id, planned)

    if planned and planned.date and (latest_doc is None or planned.date >= latest_doc):
        reference_date = planned.date
    else:
        reference_date = (latest_doc or max((s.date for s in timeline.studies), default=date.today())) \
            + timedelta(days=1)

    candidates = compute_required(timeline, references, planned, reference_date, load_rules_config(group_id))
    items = build_items(patient_id, candidates, timeline.studies, references, adapter)
    issues = open_issues(timeline, references, items, planned, reference_date) + extra_issues
    readiness, reason = compute_readiness("done", items, issues)
    return CaseCheckResult(
        patient_id=patient_id, reference_date=reference_date, planned_exam=planned,
        timeline=_strip_text(timeline), references=references, items=items, open_issues=issues,
        readiness=readiness, readiness_reason=reason, notes=sorted(set(notes)),
    )


def run_case_check(case_id: str, store: FhirStore, llm: StructuredLlm) -> CaseCheckResult | None:
    """Run the check for a stored case and persist the outcome. A failed run keeps the last result."""
    with session_scope() as db:
        case = db.get(Case, case_id)
        if case is None:
            return None
        case.check_status = "running"
        if case.result is None:
            case.readiness, case.readiness_reason = "not_ready", "Probíhá úvodní kontrola"
        patient_id, override, group = case.patient_id, case.planned_exam_override, case.group_id

    try:
        result = run_patient_check(patient_id, store, llm, planned_override=override, group_id=group)
        write_case_outputs(store, result, llm.settings.llm_model_extract)
    except Exception as exc:  # noqa: BLE001 - recorded on the case, previous result stays visible
        log.error("case check failed", extra={"fields": {"case": case_id, "error": type(exc).__name__}})
        with session_scope() as db:
            case = db.get(Case, case_id)
            case.check_status = "failed"
            if case.result is None:
                case.readiness, case.readiness_reason = compute_readiness("failed", [], [])
            else:
                case.result.last_error = type(exc).__name__
        return None

    with session_scope() as db:
        case = db.get(Case, case_id)
        case.check_status = "done"
        case.readiness, case.readiness_reason = result.readiness, result.readiness_reason
        case.reference_date = result.reference_date
        if result.reference_date is not None:
            case.date_offset_days = (case.meeting.date - result.reference_date).days
        payload = json.loads(result.model_dump_json())
        if case.result is None:
            db.add(CaseResult(case_id=case_id, result=payload, computed_at=utcnow()))
        else:
            case.result.result, case.result.computed_at, case.result.last_error = (
                payload, utcnow(), None)
    return result


def _safe_out_path(out: str) -> Path:
    path = Path(out).resolve()
    data_dir = get_settings().data_dir.resolve()
    if data_dir not in path.parents:
        raise SystemExit(f"--out must be inside the ignored data directory ({data_dir})")
    return path


def main(argv: list[str] | None = None, backend: LlmBackend | None = None,
         store: FhirStore | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient", required=True, help="dataset patient id (PAC-...)")
    parser.add_argument("--group", default=None, help="diagnosis group id for rule overrides")
    parser.add_argument("--out", default=None, help="write JSON to this file under data/")
    parser.add_argument("--no-write-fhir", action="store_true", help="do not write derived FHIR resources")
    args = parser.parse_args(argv)
    configure_logging()

    from app.fhir_store.factory import get_store

    store = store or get_store()
    llm = StructuredLlm(backend or GatewayBackend())
    result = run_patient_check(args.patient, store, llm, group_id=args.group)
    if not args.no_write_fhir:
        write_case_outputs(store, result, llm.settings.llm_model_extract)
    text = result.model_dump_json(indent=2)
    if args.out:
        path = _safe_out_path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
