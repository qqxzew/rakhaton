"""Schedule and registration API tests on synthetic data with a fixed demo date."""

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
from tests.fixtures.synthetic import PATIENT, default_backend, write_bundle

TODAY = date(2026, 10, 19)  # Monday
URO_MEETING = "MDT-uro-20261019-1400"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_TODAY", TODAY.isoformat())
    get_settings.cache_clear()
    settings = get_settings()
    fhir_dir = settings.raw_dir / "fhir"
    write_bundle(fhir_dir)
    store = LocalBundleStore(fhir_dir=fhir_dir, out_dir=settings.fhir_out_dir)
    llm = StructuredLlm(default_backend())
    app = create_app()
    app.dependency_overrides[cases_api.get_fhir_store] = lambda: store
    app.dependency_overrides[cases_api.get_llm] = lambda: llm
    with TestClient(app) as c:
        yield c


def register(client, meeting_id=URO_MEETING, group="uro", patient=PATIENT, **extra):
    return client.post("/api/cases", json={"patient_id": patient, "group_id": group,
                                           "meeting_id": meeting_id, **extra})


def test_registration_starts_the_check_and_shows_running_state(client):
    r = register(client, display_name="  Jan Zkušební ")
    assert r.status_code == 201
    body = r.json()
    assert body["case"]["readiness"] == "not_ready" and body["case"]["reason"] == "Probíhá úvodní kontrola"
    assert body["check_status"] == "running" and body["items"] == []
    assert body["patient"]["display_name"] == "Jan Zkušební"
    assert body["case"]["meeting"]["id"] == URO_MEETING

    done = client.get(f"/api/cases/{body['case']['id']}").json()  # the background check has run
    assert done["check_status"] == "done" and done["items"]
    assert done["case"]["reason"].startswith("Chybí:")
    offset = (date(2026, 10, 19) - date(2026, 5, 10)).days
    assert done["case"]["date_offset_days"] == offset and done["shifted"] is True
    with session_scope() as db:
        assert db.get(Case, body["case"]["id"]).group_id == "uro"


def test_duplicate_registration_is_rejected_without_a_second_case(client):
    assert register(client).status_code == 201
    r = register(client)
    assert r.status_code == 409 and r.json()["code"] == "duplicate_case"
    with session_scope() as db:
        assert db.query(Case).count() == 1
    assert register(client, meeting_id="MDT-general-20261023-1000").status_code == 201


def test_registration_validates_eligibility_and_inputs(client):
    wrong_group = register(client, group="lung")
    assert wrong_group.status_code == 422 and wrong_group.json()["code"] == "not_eligible"
    assert register(client, group="nope").json()["code"] == "unknown_group"
    assert register(client, meeting_id="MDT-missing").status_code == 404
    assert register(client, patient="PAC-NOPE").status_code == 404
    assert client.post("/api/cases", json={"patient_id": PATIENT}).status_code == 422
    assert client.post("/api/cases", json={"patient_id": "", "group_id": "uro", "meeting_id": URO_MEETING}
                       ).status_code == 422
    with session_scope() as db:
        db.get(Meeting, URO_MEETING).accepts_registrations = False
    closed = register(client)
    assert closed.status_code == 422 and closed.json()["code"] == "meeting_closed"
    with session_scope() as db:
        assert db.query(Case).count() == 0


def test_diagnosis_groups_and_eligible_meetings(client):
    groups = client.get("/api/diagnosis-groups").json()
    assert {"id": "uro", "label": "Urologické nádory"} in groups
    eligible = client.get("/api/meetings/eligible", params={"group": "uro", "from": "2026-10-20"}).json()
    assert [m["id"] for m in eligible[:2]] == ["MDT-general-20261023-1000", "MDT-uro-20261026-1400"]
    assert set(eligible[0]) == {"id", "label", "date", "time"}
    assert client.get("/api/meetings/eligible", params={"group": "nope"}).status_code == 422
    assert client.get("/api/meetings/eligible").status_code == 422
    assert client.get("/api/meetings/eligible", params={"group": "uro", "from": "2020-01-01"}).json()[0]["date"] \
        == TODAY.isoformat()


def test_dashboard_window_and_aggregation(client):
    empty = client.get("/api/dashboard").json()
    assert (empty["start"], empty["end"]) == ("2026-10-19", "2026-10-25") and len(empty["days"]) == 7
    assert empty["totals"]["meetings"] == 6 and empty["totals"]["cases"] == 0
    assert empty["totals"]["counts"] == {"ready": 0, "attention": 6, "not_ready": 0}
    assert empty["readiness"] == "attention" and "Žádní pacienti" in empty["reason"]
    weekend = empty["days"][5]
    assert weekend["date"] == "2026-10-24" and weekend["meetings"] == [] and weekend["readiness"] is None

    register(client)
    body = client.get("/api/dashboard", params={"start": "2026-10-19", "days": 7}).json()
    assert body["totals"] == {"meetings": 6, "cases": 1, "counts": {"ready": 0, "attention": 5, "not_ready": 1}}
    assert body["readiness"] == "not_ready"
    monday = body["days"][0]
    assert monday["readiness"] == "not_ready" and monday["meetings"][0]["case_count"] == 1
    assert monday["meetings"][0]["counts"]["not_ready"] == 1
    assert body["days"][1]["meetings"][0]["reason"] == "Žádní pacienti"
    assert client.get("/api/dashboard", params={"days": 0}).status_code == 422


def test_schedule_dates_cover_the_horizon_beyond_the_dashboard_window(client):
    register(client)
    dates = client.get("/api/schedule/dates").json()
    assert dates[0] == {"date": "2026-10-19", "readiness": "not_ready", "reason": dates[0]["reason"],
                        "meeting_count": 1, "case_count": 1}
    assert dates[0]["reason"].startswith("14:00 Uroonkologický MDT: Chybí:")
    assert len(dates) == 40 and dates[-1]["date"] == "2026-12-11"
    assert all(d["date"] not in ("2026-10-24", "2026-10-25") for d in dates)
    ranged = client.get("/api/schedule/dates", params={"from": "2026-10-21", "to": "2026-10-21"}).json()
    assert [(d["meeting_count"], d["readiness"]) for d in ranged] == [(2, "attention")]
    assert client.get("/api/schedule/dates", params={"from": "2026-10-21", "to": "2026-10-01"}).status_code == 422


def test_day_and_meeting_views_list_patient_rows(client):
    case_id = register(client).json()["case"]["id"]
    day = client.get("/api/days/2026-10-19").json()
    assert day["readiness"] == "not_ready" and day["counts"]["not_ready"] == 1
    row = day["meetings"][0]["cases"][0]
    assert row["id"] == case_id and row["patient_id"] == PATIENT and row["display_name"]
    assert row["diagnosis"].startswith("C61") and row["reason"].startswith("Chybí:")
    assert row["check_status"] == "done"

    detail = client.get(f"/api/meetings/{URO_MEETING}").json()
    assert detail["case_count"] == 1 and detail["cases"][0]["id"] == case_id
    assert detail["eligible_groups"] == ["uro"]

    wednesday = client.get("/api/days/2026-10-21").json()
    assert [m["time"] for m in wednesday["meetings"]] == ["12:30", "15:00"]
    assert {m["readiness"] for m in wednesday["meetings"]} == {"attention"}
    assert wednesday["meetings"][0]["reason"] == "Žádní pacienti" and wednesday["meetings"][0]["cases"] == []
    assert client.get("/api/days/2026-10-24").json()["meetings"] == []
    assert client.get("/api/days/not-a-date").status_code == 422
    assert client.get("/api/meetings/MDT-missing").status_code == 404


def test_patient_search_returns_badges_without_report_text(client):
    hit = client.get("/api/patients/search", params={"q": "test"}).json()
    assert [p["id"] for p in hit] == [PATIENT]
    p = hit[0]
    assert p["suggested_group"] == "uro" and p["has_imaging"] is True and p["has_documents"] is True
    assert p["diagnoses"][0]["code"] == "C61"
    assert "Srovnáno" not in str(hit) and "Kontrolní" not in str(hit)
    assert [x["id"] for x in client.get("/api/patients/search", params={"q": "c61"}).json()] == [PATIENT]
    assert client.get("/api/patients/search", params={"q": "zzz"}).json() == []
    assert client.get("/api/patients/search", params={"group": "lung"}).json() == []
    assert [x["id"] for x in client.get("/api/patients/search", params={"group": "uro"}).json()] == [PATIENT]
