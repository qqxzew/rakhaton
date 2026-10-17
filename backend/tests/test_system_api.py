"""System screens API (worklist, hospitals, integration map) with IRIS faked; synthetic data only."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import requests as req_api
from app.api import search as search_api
from app.api import system
from app.app_db.models import Case, CaseResult, Meeting
from app.app_db.session import session_scope
from app.exchange.dicom import DicomMatch
from app.main import create_app
from app.requests.production_client import ProductionError
from app.search.vector_store import Hit

PATIENT = "PAC-TEST-0001"
CASE = "CASE-TEST-SYS"


class FakeProduction:
    def __init__(self, rows=None, fail=False):
        self.rows = rows or []
        self.fail = fail

    def list(self, case_id=""):
        if self.fail:
            raise ProductionError("down")
        return self.rows


class FakeIris:
    def __init__(self, fail=False, ack="MSH|^~\\&|IRIS\rMSA|AA|1\r"):
        self.fail = fail
        self.ack = ack
        self.sent: list[str] = []
        self.predict_calls = 0

    def _check(self):
        if self.fail:
            raise ConnectionError("iris down")

    def production_status(self):
        self._check()
        return {"name": "PacsComparator.Production", "running": True}

    def production_items(self, name):
        self._check()
        return [("PacsComparator.BS.Ticker", "C1", 1, None), ("PacsComparator.BP.RequestLifecycle", "C2", 1, None),
                ("PacsComparator.BO.Email", "C3", 0, "x")]

    def messages(self, top):
        self._check()
        return [(12, "2026-10-17 10:00:00.123", "A", "B", "Ens.StringRequest", 11, 9)][:top]

    def ml_models(self):
        self._check()
        return [("PacsMLLateArrival", "ArrivedLate", "PacsMLLateArrival_t1"),
                ("PacsMLResponseHours", "ResponseHours", "PacsMLResponseHours_t1")]

    def ml_metrics(self):
        self._check()
        return [("PacsMLLateArrival", "Precision", 0.5), ("PacsMLLateArrival", "Precision", 0.62),
                ("PacsMLLateArrival", "Recall", 0.97), ("PacsMLResponseHours", "R2", 0.56),
                ("PacsMLResponseHours", "RMSE", 25.89)]

    def predict(self, provider, modality, region, sent, deadline):
        self._check()
        self.predict_calls += 1
        return {"late_probability": 0.7 if provider == "nnh" else 0.1, "expected_hours": 20.0, "simulated": True}

    def send_hl7(self, message, port=4561):
        self._check()
        self.sent.append(message)
        return self.ack


class FakeFhir:
    def __init__(self, fail=False):
        self.fail = fail

    def count(self, base, resource_type, params=None):
        if self.fail:
            raise ConnectionError("fhir down")
        return 3

    def exists(self, base, resource_type, resource_id):
        return resource_id.startswith("RIS-SIM-ORD-")


class FakeVector:
    def search(self, query, patient_id=None, source_type=None, top_k=5):
        return [Hit("DiagnosticReport", "rep-TEST-1", 0, date(2025, 1, 2), "CT", "x" * 300, 0.91),
                Hit("DiagnosticReport", "rep-TEST-1", 1, date(2025, 1, 2), "CT", "y", 0.80),
                Hit("DocumentReference", "doc-TEST-2", 0, None, None, "kratky text", 0.70)]


class FakeCFind:
    def find(self, ae, patient_id, window, modality):
        return [DicomMatch(patient_id, date(2025, 3, 4), "CT", "ACC-TEST-1", ae)]


ROWS = [
    {"requestId": "PACS-REQ-000001", "caseId": CASE, "state": "DRAFTED", "modality": "PET", "regions": "chest,abdomen",
     "targetDate": "2025-05-12", "provider": {"id": "nnh", "name": "NNH", "route": "ePACS"}, "deadline": None},
    {"requestId": "PACS-REQ-000002", "caseId": CASE, "state": "VERIFIED", "modality": "CT", "regions": "chest",
     "targetDate": "2025-05", "provider": {"id": "motol", "name": "Motol", "route": "ePACS"}},
    {"requestId": "PACS-REQ-000003", "caseId": "CASE-UNKNOWN", "state": "HUMAN_ESCALATED", "modality": "MR",
     "regions": "", "targetDate": None, "provider": {"id": "fnm", "name": "FNM"}},
]


@pytest.fixture
def ctx():
    state = {"production": FakeProduction(ROWS), "iris": FakeIris(), "fhir": FakeFhir()}
    test_app = create_app()
    test_app.dependency_overrides[req_api.production] = lambda: state["production"]
    test_app.dependency_overrides[system.get_iris] = lambda: state["iris"]
    test_app.dependency_overrides[system.get_fhir] = lambda: state["fhir"]
    test_app.dependency_overrides[system.get_stats_loader] = lambda: (lambda: {"studies": {"total": 3}})
    test_app.dependency_overrides[system.get_cfind] = lambda: FakeCFind()
    test_app.dependency_overrides[search_api.get_vector_backend] = lambda: FakeVector()
    with TestClient(test_app) as client:
        yield client, state


def _seed_case(offset: int = 10) -> None:
    result = {"patient_id": PATIENT, "timeline": {"patient_id": PATIENT, "sex": "female"}, "items": []}
    with session_scope() as db:
        for obj in (db.get(CaseResult, CASE), db.get(Case, CASE), db.get(Meeting, "MDT-TEST-SYS")):
            if obj:
                db.delete(obj)
        db.flush()
        db.add(Meeting(id="MDT-TEST-SYS", date=date.today() + timedelta(days=2), time="14:00", label="T",
                       eligible_groups=[]))
        db.add(Case(id=CASE, patient_id=PATIENT, meeting_id="MDT-TEST-SYS", check_status="done",
                    date_offset_days=offset))
        db.flush()
        db.add(CaseResult(case_id=CASE, result=result))


def test_worklist_joins_cases_shifts_dates_and_predicts_open_only(ctx):
    client, state = ctx
    _seed_case(offset=10)
    data = client.get("/api/worklist").json()
    assert data["available"] and data["counts"] == {"approval": 1, "verified": 1, "escalated": 1}
    by_id = {r["request_id"]: r for r in data["requests"]}
    drafted = by_id["PACS-REQ-000001"]
    assert drafted["patient_id"] == PATIENT and drafted["display_name"]
    assert drafted["target_date"] == "2025-05-22" and drafted["shifted"] is True
    assert drafted["regions"] == ["chest", "abdomen"] and drafted["state_group"] == "approval"
    assert drafted["prediction"]["late_probability"] == 0.7 and drafted["urgency"] == "attention"
    verified = by_id["PACS-REQ-000002"]
    assert verified["prediction"] is None and verified["target_date"] == "2025-05" and not verified["shifted"]
    assert verified["urgency"] == "ready"
    orphan = by_id["PACS-REQ-000003"]
    assert orphan["meeting"] is None and orphan["urgency"] == "danger"
    assert data["requests"][-1]["request_id"] == "PACS-REQ-000003"  # no MDT date sorts last


def test_worklist_degrades_when_production_down(ctx):
    client, state = ctx
    state["production"] = FakeProduction(fail=True)
    data = client.get("/api/worklist").json()
    assert data["available"] is False and data["requests"] == [] and "reason" in data


def test_worklist_without_ml_still_lists(ctx):
    client, state = ctx
    state["iris"] = FakeIris(fail=True)
    data = client.get("/api/worklist").json()
    assert data["available"] and data["ml_available"] is False
    assert all(r["prediction"] is None for r in data["requests"])


def test_hospitals_lists_registry_with_counts(ctx):
    client, _ = ctx
    data = client.get("/api/hospitals").json()
    by_id = {p["id"]: p for p in data["providers"]}
    assert by_id["motol"]["kind"] == "home" and by_id["motol"]["fhir_studies"] == 3
    assert by_id["nnh"]["open_requests"] == 1 and by_id["motol"]["verified"] == 1
    assert by_id["nnh"]["expected_hours"] == {"CT": 20.0, "PET": 20.0}
    assert all(p["simulated"] for p in data["providers"])


def test_hospitals_degrade_without_production_and_fhir(ctx):
    client, state = ctx
    state["production"] = FakeProduction(fail=True)
    state["fhir"] = FakeFhir(fail=True)
    data = client.get("/api/hospitals").json()
    assert data["requests_available"] is False and data["providers"]
    motol = next(p for p in data["providers"] if p["id"] == "motol")
    assert motol["fhir_studies"] is None and motol["fhir_error"]


def test_system_fhir_counts_and_failure(ctx):
    client, state = ctx
    data = client.get("/api/system/fhir").json()
    assert data["available"] and len(data["resources"]) == 10 and data["metadata_url"].endswith("/metadata")
    assert data["hospitals"] and all(h["counts"]["ImagingStudy"] == 3 for h in data["hospitals"])
    state["fhir"] = FakeFhir(fail=True)
    assert client.get("/api/system/fhir").json()["available"] is False


def test_system_production_items_and_trace_links(ctx):
    client, state = ctx
    data = client.get("/api/system/production?top=5").json()
    assert data["running"] and [i["kind"] for i in data["items"]] == ["service", "process", "operation"]
    msg = data["messages"][0]
    assert msg["status"] == "Completed" and msg["visual_trace_url"].endswith("SESSIONID=11")
    state["iris"] = FakeIris(fail=True)
    down = client.get("/api/system/production").json()
    assert down["available"] is False and down["config_url"]


def test_system_ml_reads_metrics_and_falls_back(ctx):
    client, state = ctx
    data = client.get("/api/system/ml").json()
    late = next(m for m in data["models"] if m["model"] == "PacsMLLateArrival")
    assert late["kind"] == "classification" and late["metrics"]["Precision"] == 0.62
    state["iris"] = FakeIris(fail=True)
    fallback = client.get("/api/system/ml").json()
    assert fallback["source"] == "documented" and len(fallback["models"]) == 2


def test_system_sql_and_mcp(ctx):
    client, _ = ctx
    assert client.get("/api/system/sql").json()["stats"]["studies"]["total"] == 3
    names = [t["name"] for t in client.get("/api/system/mcp").json()["tools"]]
    assert "fhir_search" in names and "vector_search" in names


def test_vector_search_hides_text_unless_asked(ctx):
    client, _ = ctx
    data = client.get("/api/system/vector-search", params={"q": "srovnani"}).json()
    assert [h["id"] for h in data["hits"]] == ["rep-TEST-1", "doc-TEST-2"]
    assert all(h["snippet"] is None for h in data["hits"])
    with_text = client.get("/api/system/vector-search", params={"q": "srovnani", "include_text": True}).json()
    assert len(with_text["hits"][0]["snippet"]) == 241
    assert client.get("/api/system/vector-search", params={"q": "ab", "patient_id": "bad id!"}).status_code == 422


def test_patients_lists_case_patients(ctx):
    client, _ = ctx
    _seed_case()
    patients = client.get("/api/system/patients").json()["patients"]
    assert [p["patient_id"] for p in patients] == [PATIENT]


def test_hl7_orm_requires_case_patient(ctx):
    client, state = ctx
    r = client.post("/api/system/hl7-orm", json={"patient_id": "PAC-TEST-9999", "modality": "CT"})
    assert r.status_code == 422 and state["iris"].sent == []


def test_hl7_orm_sends_through_iris(ctx):
    client, state = ctx
    _seed_case()
    data = client.post("/api/system/hl7-orm", json={"patient_id": PATIENT, "modality": "PET", "days": 7}).json()
    assert data["ack"] == "AA" and data["accepted"] and data["service_request"].startswith("ServiceRequest/RIS-SIM-ORD-")
    assert data["message_type"].startswith("ORM") and state["iris"].sent[0].startswith("MSH")


def test_hl7_orm_commit_accept_counts_as_accepted(ctx):
    client, state = ctx
    _seed_case()
    state["iris"] = FakeIris(ack="MSH|^~\\&|IRIS\rMSA|CA|1\r")
    assert client.post("/api/system/hl7-orm", json={"patient_id": PATIENT}).json()["accepted"] is True
    state["iris"] = FakeIris(ack="MSH|^~\\&|IRIS\rMSA|AR|1\r")
    rejected = client.post("/api/system/hl7-orm", json={"patient_id": PATIENT}).json()
    assert rejected["accepted"] is False and rejected["service_request"] is None


def test_hl7_orm_iris_down(ctx):
    client, state = ctx
    _seed_case()
    state["iris"] = FakeIris(fail=True)
    assert client.post("/api/system/hl7-orm", json={"patient_id": PATIENT}).json()["available"] is False


def test_dicom_cfind(ctx):
    client, _ = ctx
    _seed_case()
    data = client.post("/api/system/dicom-cfind", json={"patient_id": PATIENT, "node": "nnh"}).json()
    assert data["available"] and data["matches"][0]["study_date"] == "2025-03-04"
    assert client.post("/api/system/dicom-cfind", json={"patient_id": PATIENT, "node": "x"}).status_code == 422
