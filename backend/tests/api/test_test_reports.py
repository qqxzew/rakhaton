"""Test radiology report upload from the patient view (synthetic data, LLM mocked)."""

from __future__ import annotations

from datetime import date, timedelta

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
from app.pipeline.schemas import Study
from app.pipeline.test_upload import default_report_date, shift_text_dates, template_text
from tests.fixtures.synthetic import PATIENT, default_backend, write_bundle

MEETING_DATE = date(2026, 10, 20)


@pytest.fixture
def client():
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
        run_case_check("CASE-1", store, llm)
        c.store, c.llm = store, llm  # type: ignore[attr-defined]
        yield c


def test_shift_text_dates_moves_full_dates_only():
    text = "Ve srovnání s CT z 3. 4. 26 a s MR z 10.12.2025, kontrola 11/2025."
    assert shift_text_dates(text, -3) == "Ve srovnání s CT z 31. 3. 2026 a s MR z 7. 12. 2025, kontrola 11/2025."
    assert shift_text_dates("datum 31. 2. 2026", 5) == "datum 31. 2. 2026"
    assert shift_text_dates(text, 0) == text


def test_template_cites_an_internal_prior_and_an_external_pet():
    ct = Study(id="STU-TEST-1", patient_id=PATIENT, date=date(2026, 1, 5), modality="CT",
               regions=["chest", "abdomen"])
    day = default_report_date([ct], date(2026, 6, 1), date(2025, 12, 1))
    assert day == date(2026, 1, 6)  # newer than every study, before the planned exam
    text, modality = template_text([ct], None, day, offset=10)
    assert modality == "CT" and text.startswith("CT hrudníku, břicha a pánve")
    assert "CT z 15. 1. 2026" in text  # shown in the UI frame (+10 days)
    assert "PET/CT z" in text and "Na Homolce" in text


def test_upload_is_read_by_the_pipeline_and_can_be_removed(client):
    offset = client.get("/api/cases/CASE-1").json()["case"]["date_offset_days"]
    tpl = client.get("/api/cases/CASE-1/test-reports/template").json()
    assert tpl["uploaded"] == 0 and tpl["simulated"] is True and "PET/CT" in tpl["text"]

    shown = date.fromisoformat(tpl["date"])
    r = client.post("/api/cases/CASE-1/test-reports",
                    json={"text": "CT hrudníku. Ve srovnání s CT z 1. 2. 2026 bez změn.",
                          "date": tpl["date"], "modality": "CT"})
    assert r.status_code == 201
    report_id = r.json()["report_id"]

    body = client.get("/api/cases/CASE-1").json()  # the background check has run inside TestClient
    study = next(e for e in body["timeline"] if e["kind"] == "study" and e["study_id"].startswith("TEST-"))
    assert study["date"] == shown.isoformat() and study["modality"] == "CT"

    doc = client.get(f"/api/cases/CASE-1/documents/{report_id}").json()
    stored_date = date(2026, 2, 1) - timedelta(days=offset)
    assert f"CT z {stored_date.day}. {stored_date.month}. {stored_date.year}" in doc["text"]
    assert client.get("/api/cases/CASE-1/test-reports/template").json()["uploaded"] == 1

    removed = client.delete("/api/cases/CASE-1/test-reports").json()
    assert removed["deleted"] == 2
    body = client.get("/api/cases/CASE-1").json()
    assert not any((e.get("study_id") or "").startswith("TEST-") for e in body["timeline"])


def test_upload_rejects_unknown_modality(client):
    r = client.post("/api/cases/CASE-1/test-reports",
                    json={"text": "x" * 30, "date": "2026-10-17", "modality": "XYZ"})
    assert r.status_code == 422
