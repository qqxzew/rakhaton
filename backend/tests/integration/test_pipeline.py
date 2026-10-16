from __future__ import annotations

import json
from datetime import date

import pytest

from app.app_db.models import Case, Meeting
from app.app_db.session import init_db, session_scope
from app.config import get_settings
from app.fhir_store.local import LocalBundleStore
from app.fhir_store.mappers import write_case_outputs
from app.llm.cache import LlmCache
from app.llm.client import StructuredLlm
from app.pipeline.run import run_case_check, run_patient_check
from app.pipeline.timeline import decode_attachment
from tests.fixtures import synthetic
from tests.fixtures.synthetic import (
    PATIENT,
    ScriptedBackend,
    default_backend,
    synthetic_bundle,
    write_bundle,
)


@pytest.fixture
def store(tmp_path):
    fhir_dir = tmp_path / "fhir"
    write_bundle(fhir_dir)
    return LocalBundleStore(fhir_dir=fhir_dir, out_dir=tmp_path / "fhir_out")


def make_llm(backend: ScriptedBackend | None = None) -> tuple[StructuredLlm, ScriptedBackend]:
    backend = backend or default_backend()
    return StructuredLlm(backend), backend


def items_by_study(result):
    return {i.study_id or i.reference_id: i for i in result.items}


def test_pipeline_end_to_end_classifies_every_scenario(store):
    llm, _ = make_llm()
    result = run_patient_check(PATIENT, store, llm)

    assert result.planned_exam is not None
    assert (result.planned_exam.modality, result.planned_exam.date) == ("CT", date(2026, 5, 10))
    assert result.reference_date == date(2026, 5, 10)

    items = items_by_study(result)
    assert items["STU-TEST-0001"].availability == "available" and items["STU-TEST-0001"].state == "ok"
    assert items["STU-TEST-0002"].availability == "not_in_pacs" and items["STU-TEST-0002"].state == "missing"
    assert items["STU-TEST-0003"].availability == "unknown" and items["STU-TEST-0003"].state == "attention"
    pet = next(i for i in result.items if i.reference_id and not i.study_id)
    assert (pet.modality, pet.availability, pet.state) == ("PET", "not_found", "missing")
    assert pet.holding_site_id == "nnh"
    assert pet.target_date.iso == "2025-05-12"

    assert result.readiness == "not_ready"
    assert result.readiness_reason.startswith("Chybí:")
    assert result.timeline.treatment.first_treatment == date(2025, 4, 1)


def test_every_quote_is_an_exact_part_of_its_source(store):
    llm, _ = make_llm()
    result = run_patient_check(PATIENT, store, llm)
    texts = {r["id"]: synthetic.REPORT_2 for r in store.radiology_reports(PATIENT)}
    texts.update({d["id"]: decode_attachment(d) for d in store.clinical_documents(PATIENT)})
    for res in store.radiology_reports(PATIENT):
        texts[res["id"]] = res["conclusion"]
    evidences = [r.evidence for r in result.references] + [result.planned_exam.evidence]
    assert evidences
    for ev in evidences:
        assert texts[ev.doc_id].find(ev.quote) >= 0


def test_invalid_quote_from_the_model_is_dropped_and_reported(store):
    llm, _ = make_llm()
    result = run_patient_check(PATIENT, store, llm)
    quotes = [r.evidence.quote for r in result.references]
    assert not any("vůbec není" in q for q in quotes)
    assert any("not in the source" in n for n in result.notes)
    assert len(result.references) == 2


def test_matched_reference_links_to_internal_study(store):
    llm, _ = make_llm()
    result = run_patient_check(PATIENT, store, llm)
    ct = next(r for r in result.references if r.modality == "CT")
    assert ct.matched_study_id == "STU-TEST-0001"


def test_rerun_is_idempotent_and_uses_the_cache(store):
    llm, backend = make_llm()
    first = run_patient_check(PATIENT, store, llm)
    calls_after_first = len(backend.calls)
    second = run_patient_check(PATIENT, store, llm)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert calls_after_first > 0 and len(backend.calls) == calls_after_first


def test_only_eu_deployments_receive_report_text(store):
    llm, backend = make_llm()
    run_patient_check(PATIENT, store, llm)
    assert backend.calls and all(model.endswith("-dz-eu") for _, model in backend.calls)


def test_patient_without_imaging_requires_attention_not_ready(tmp_path):
    bundle = synthetic_bundle()
    bundle["entry"] = [e for e in bundle["entry"] if e["resource"]["resourceType"] not in
                       ("ImagingStudy", "DiagnosticReport")]
    fhir_dir = tmp_path / "fhir"
    write_bundle(fhir_dir, bundle)
    store = LocalBundleStore(fhir_dir=fhir_dir, out_dir=tmp_path / "out")
    llm, _ = make_llm()
    result = run_patient_check(PATIENT, store, llm)
    assert result.items == []
    assert (result.readiness, result.readiness_reason) == ("attention", "Nenalezena žádná předchozí vyšetření")


def test_missing_planned_exam_is_never_ready(store, tmp_path):
    result = run_patient_check(PATIENT, store, StructuredLlm(ScriptedBackend(), cache=LlmCache(tmp_path / "c")))
    assert result.planned_exam is None
    assert result.open_issues[0].type == "data" and "Plánované vyšetření" in result.open_issues[0].text
    assert result.readiness != "ready"


def test_unmatched_reference_with_implausible_date_is_flagged_not_a_hard_gap(store, tmp_path):
    backend = ScriptedBackend(
        priors={"Srovnáno s PET/CT z NNH": {"references": [
            {"modality": "PET/CT", "regions": [], "date_text": "12. 5. 2025", "date_iso": "2031-05-12",
             "site_text": "NNH", "quote": "Srovnáno s PET/CT z NNH ze dne 12. 5. 2025.", "confidence": 0.9}]}},
    )
    result = run_patient_check(PATIENT, store, StructuredLlm(backend, cache=LlmCache(tmp_path / "c1")))
    ref = result.references[0]
    # the date written in the text wins over the model's ISO guess
    assert ref.ref_date.iso == "2025-05-12" and "date_adjusted" in ref.flags and ref.date_valid
    backend2 = ScriptedBackend(
        priors={"Srovnáno s PET/CT z NNH": {"references": [
            {"modality": "PET/CT", "regions": [], "date_text": "12. 5. 2025", "date_iso": "2025-05-12",
             "site_text": "NNH", "quote": "Srovnáno s PET/CT z NNH ze dne 12. 5. 2025.", "confidence": 0.2}]}},
    )
    low = run_patient_check(PATIENT, store, StructuredLlm(backend2, cache=LlmCache(tmp_path / "c2")))
    pet = next(i for i in low.items if i.reference_id)
    assert pet.state == "attention" and pet.low_confidence
    assert any(i.type == "low_confidence" for i in low.open_issues)


def test_derived_fhir_resources_are_written_with_provenance(store):
    llm, _ = make_llm()
    result = run_patient_check(PATIENT, store, llm)
    written = write_case_outputs(store, result, "test-model-dz-eu")
    again = write_case_outputs(store, result, "test-model-dz-eu")
    assert written == again
    service_requests = store.search("ServiceRequest")
    assert len(service_requests) == 1 and service_requests[0]["intent"] == "plan"
    assert service_requests[0]["subject"] == {"reference": f"Patient/{PATIENT}"}
    observations = store.search("Observation")
    assert len(observations) == 2 and all(o["derivedFrom"] for o in observations)
    provenance = store.search("Provenance")
    assert len(provenance) == 3
    for prov in provenance:
        quote = next(e["valueString"] for e in prov["extension"] if e["url"].endswith("source-quote"))
        assert quote
        assert any(e["url"].endswith("extraction-confidence") for e in prov["extension"])
    json.dumps(service_requests)  # serializable


def test_run_case_check_persists_result_and_keeps_it_when_a_recheck_fails(store):
    init_db("sqlite:///:memory:")
    with session_scope() as db:
        db.add(Meeting(id="MDT-TEST", date=date(2026, 10, 20), time="10:00", label="Testovací MDT",
                       eligible_groups=["uro"], accepts_registrations=True))
        db.add(Case(id="CASE-1", patient_id=PATIENT, meeting_id="MDT-TEST"))
    llm, _ = make_llm()
    result = run_case_check("CASE-1", store, llm)
    assert result is not None
    with session_scope() as db:
        case = db.get(Case, "CASE-1")
        assert case.check_status == "done" and case.readiness == "not_ready"
        assert case.date_offset_days == (date(2026, 10, 20) - date(2026, 5, 10)).days
        assert case.result.result["patient_id"] == PATIENT

    class Broken(ScriptedBackend):
        def complete(self, *a, **k):  # noqa: ANN002, ANN003
            raise RuntimeError("gateway down")

    broken = StructuredLlm(Broken(), cache=type(llm.cache)(get_settings().data_dir / "other_cache"))
    assert run_case_check("CASE-1", store, broken) is None
    with session_scope() as db:
        case = db.get(Case, "CASE-1")
        assert case.check_status == "failed"
        assert case.result.result["patient_id"] == PATIENT and case.result.last_error == "RuntimeError"
        assert case.readiness == "not_ready"
