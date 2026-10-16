from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api import cases as cases_api
from app.app_db.models import Case, Meeting
from app.app_db.session import session_scope
from app.config import get_settings
from app.fhir_store.local import LocalBundleStore
from app.llm.client import StructuredLlm
from app.main import create_app
from app.pipeline.run import run_case_check
from tests.fixtures.synthetic import PATIENT, default_backend, write_bundle

MEETING_DATE = date(2026, 10, 20)


@pytest.fixture
def client(tmp_path):
    settings = get_settings()
    fhir_dir = settings.raw_dir / "fhir"
    write_bundle(fhir_dir)
    store = LocalBundleStore(fhir_dir=fhir_dir, out_dir=settings.fhir_out_dir)
    llm = StructuredLlm(default_backend())
    app = create_app()
    app.dependency_overrides[cases_api.get_fhir_store] = lambda: store
    app.dependency_overrides[cases_api.get_llm] = lambda: llm
    with TestClient(app) as c:
        with session_scope() as db:
            db.add(Meeting(id="MDT-TEST", date=MEETING_DATE, time="10:00", label="Testovací MDT",
                           eligible_groups=["uro"], accepts_registrations=True))
            db.add(Case(id="CASE-1", patient_id=PATIENT, meeting_id="MDT-TEST"))
        c.store, c.llm = store, llm  # type: ignore[attr-defined]
        yield c


def test_health_reports_dependencies(client):
    body = client.get("/api/health").json()
    assert client.get("/api/health").status_code == 200
    assert body["database"]["status"] == "ok" and body["fhir_store"]["patients"] == 1
    assert body["llm"]["status"] == "ok"


def test_unknown_case_returns_error_shape(client):
    r = client.get("/api/cases/NOPE")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_case_shows_running_state_before_the_check_finishes(client):
    body = client.get("/api/cases/CASE-1").json()
    assert body["case"]["readiness"] == "not_ready" and body["case"]["reason"] == "Probíhá úvodní kontrola"
    assert body["items"] == [] and body["simulated"] is True


def test_case_detail_view_model_after_check(client):
    run_case_check("CASE-1", client.store, client.llm)
    body = client.get("/api/cases/CASE-1").json()
    assert body["case"]["readiness"] == "not_ready" and body["case"]["reason"].startswith("Chybí:")
    offset = (MEETING_DATE - date(2026, 5, 10)).days
    assert body["case"]["date_offset_days"] == offset
    assert body["planned_exam"]["modality"] == "CT"
    assert body["planned_exam"]["date"] == MEETING_DATE.isoformat()
    assert body["planned_exam"]["quote"].startswith("Kontrolní CT")
    assert body["patient"]["id"] == PATIENT and body["patient"]["display_name"]
    assert body["patient"]["diagnoses"][0]["code"] == "C61"

    items = {i["id"]: i for i in body["items"]}
    states = sorted(i["state"] for i in items.values())
    assert states == ["attention", "missing", "missing", "ok"]
    gap = next(i for i in items.values() if i["availability"] == "not_found")
    assert gap["holding_site"]["name"] == "Nemocnice Na Homolce"
    assert gap["evidence"]["quote"].startswith("Srovnáno s PET/CT") and gap["simulated"] is True

    kinds = {e["kind"] for e in body["timeline"]}
    assert {"study", "referenced", "treatment", "mdt"} <= kinds
    referenced = next(e for e in body["timeline"] if e["kind"] == "referenced")
    assert referenced["date"] == date.fromordinal(date(2025, 5, 12).toordinal() + offset).isoformat()
    assert "text" not in str(body["timeline"][0])


def test_source_document_endpoint_returns_text_and_rejects_foreign_ids(client):
    run_case_check("CASE-1", client.store, client.llm)
    doc = client.get("/api/cases/CASE-1/documents/rep-STU-TEST-0002").json()
    assert doc["kind"] == "radiology_report" and "Srovnáno s PET/CT" in doc["text"]
    note = client.get("/api/cases/CASE-1/documents/DOC-TEST-0001").json()
    assert note["kind"] == "clinical_note" and "Kontrolní CT" in note["text"]
    assert client.get("/api/cases/CASE-1/documents/rep-STU-OTHER").status_code == 404


def test_planned_exam_correction_validates_and_triggers_recheck(client):
    run_case_check("CASE-1", client.store, client.llm)
    bad = client.patch("/api/cases/CASE-1/planned-exam", json={"modality": "xyz", "regions": []})
    assert bad.status_code == 422
    bad_date = client.patch("/api/cases/CASE-1/planned-exam",
                            json={"modality": "MR", "regions": ["pelvis"], "date": "2026-13-01"})
    assert bad_date.status_code == 422

    shown = MEETING_DATE.isoformat()
    ok = client.patch("/api/cases/CASE-1/planned-exam",
                      json={"modality": "mr", "regions": ["pánev"], "date": shown, "coordinator": "Test"})
    assert ok.status_code == 200 and ok.json()["modality"] == "MR"
    body = client.get("/api/cases/CASE-1").json()
    assert body["planned_exam"]["modality"] == "MR" and body["planned_exam"]["regions"] == ["pelvis"]
    assert body["planned_exam"]["date"] == shown
    with session_scope() as db:
        assert db.get(Case, "CASE-1").planned_exam_override["date"] == "2026-05-10"


def test_recheck_is_accepted(client):
    r = client.post("/api/cases/CASE-1/recheck")
    assert r.status_code == 202
    assert client.get("/api/cases/CASE-1").json()["case"]["readiness"] == "not_ready"
    with session_scope() as db:
        assert db.get(Case, "CASE-1").check_status == "done"
