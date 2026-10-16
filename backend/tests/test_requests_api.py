"""Request loop API with the IRIS production mocked (synthetic data only)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import requests as api
from app.app_db.models import Case, CaseResult, Meeting
from app.app_db.session import session_scope
from app.main import create_app
from app.requests.production_client import ProductionError, sync_files, visual_trace_url


class FakeProduction:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.requests: dict[str, dict] = {}

    def submit(self, action, request_id="", payload=None, actor="system"):
        self.calls.append((action, request_id, payload, actor))
        if action == "DRAFT":
            request_id = f"PACS-REQ-{len(self.requests) + 100:06d}"
            self.requests[request_id] = {"state": "DRAFTED", "payload": payload}
        elif action == "APPROVE":
            self.requests[request_id]["state"] = "SENT"
        return {"ok": True, "requestId": request_id, "state": self.requests[request_id]["state"]}

    def list(self, case_id=""):
        return list(self.requests)

    def draft_ids(self, case_ids=None):
        return [r for r, v in self.requests.items() if v["state"] == "DRAFTED"]

    def get(self, request_id):
        if request_id not in self.requests:
            return None
        return {"requestId": request_id, "state": self.requests[request_id]["state"], "sessionIds": "7,9",
                "messages": [], "provider": {}}

    def advance_time(self, hours):
        return {"offsetSeconds": hours * 3600}


@pytest.fixture
def client_and_fake():
    fake = FakeProduction()
    test_app = create_app()
    test_app.dependency_overrides[api.production] = lambda: fake
    with TestClient(test_app) as client:
        yield client, fake


def _seed_case() -> str:
    item = {
        "id": "ITEM-TEST-1", "rule_ids": ["R1"], "reasons": ["test"], "modality": "PET", "regions": ["chest"],
        "target_date": {"year": 2025, "month": 5, "day": 12}, "availability": "not_found", "state": "missing",
        "holding_site_id": "nnh", "holding_site_name": "NNH",
    }
    result = {"patient_id": "PAC-TEST-0001", "timeline": {"patient_id": "PAC-TEST-0001"}, "items": [item]}
    with session_scope() as db:
        for obj in (db.get(CaseResult, "CASE-TEST-REQ"), db.get(Case, "CASE-TEST-REQ"), db.get(Meeting, "MDT-TEST-REQ")):
            if obj:
                db.delete(obj)
        db.flush()
        db.add(Meeting(id="MDT-TEST-REQ", date=date.today() + timedelta(days=3), time="14:00", label="T",
                       eligible_groups=[]))
        db.add(Case(id="CASE-TEST-REQ", patient_id="PAC-TEST-0001", meeting_id="MDT-TEST-REQ", check_status="done"))
        db.flush()
        db.add(CaseResult(case_id="CASE-TEST-REQ", result=result))
    return "CASE-TEST-REQ"


def test_visual_trace_url():
    assert visual_trace_url(42).endswith("EnsPortal.VisualTrace.zen?SESSIONID=42")


def test_approve_requires_coordinator(client_and_fake):
    client, fake = client_and_fake
    assert client.post("/api/requests/PACS-REQ-000100/approve", json={}).status_code == 422
    assert fake.calls == []


def test_drafts_carry_minimum_data_and_do_not_send(client_and_fake):
    client, fake = client_and_fake
    case_id = _seed_case()
    out = client.post(f"/api/cases/{case_id}/requests")
    assert out.status_code == 200
    assert [c[0] for c in fake.calls] == ["DRAFT"]
    payload = fake.calls[0][2]
    assert payload["itemId"] == "ITEM-TEST-1" and payload["modality"] == "PET"
    assert "name" not in " ".join(payload)  # no name or diagnosis fields travel with the draft
    assert fake.requests and all(r["state"] == "DRAFTED" for r in fake.requests.values())


def test_approve_all_records_coordinator(client_and_fake):
    client, fake = client_and_fake
    client.post(f"/api/cases/{_seed_case()}/requests")
    out = client.post("/api/requests/approve-all", json={"coordinator": "Koordinátor"})
    assert out.json()["approved"] == 1
    action, _, payload, actor = fake.calls[-1]
    assert (action, actor, payload) == ("APPROVE", "Koordinátor", {"approvedBy": "Koordinátor"})


def test_request_detail_has_visual_trace_links(client_and_fake):
    client, fake = client_and_fake
    client.post(f"/api/cases/{_seed_case()}/requests")
    rid = next(iter(fake.requests))
    data = client.get(f"/api/requests/{rid}").json()
    assert len(data["visualTrace"]) == 2 and client.get("/api/requests/PACS-REQ-999999").status_code == 404


def test_advance_time_validates_hours(client_and_fake):
    client, _ = client_and_fake
    assert client.post("/api/demo/advance-time", json={"hours": 0}).status_code == 422
    assert client.post("/api/demo/advance-time", json={"hours": 25}).status_code == 200


def test_production_down_is_503(client_and_fake):
    client, fake = client_and_fake

    def boom(*a, **k):
        raise ProductionError("down")

    fake.submit = boom
    r = client.post("/api/requests/PACS-REQ-000100/approve", json={"coordinator": "A"})
    assert r.status_code == 503 and r.json()["code"] == "dependency_unavailable"


def test_sync_files_writes_outbox_and_voice(tmp_path):
    class Audio:
        def audio(self, _):
            return b"mp3"

    request = {"requestId": "PACS-REQ-000100", "provider": {"email": "x@example.test"}, "messages": [
        {"id": 1, "kind": "email", "direction": "out", "subject": "S", "body": "B", "hasAudio": False},
        {"id": 2, "kind": "voice_call", "direction": "out", "subject": "V", "body": "B", "hasAudio": True}]}
    sync_files(request, Audio(), tmp_path)
    assert (tmp_path / "outbox" / "PACS-REQ-000100-1.eml").read_text(encoding="utf-8").startswith("Subject: S")
    assert (tmp_path / "voice" / "PACS-REQ-000100.mp3").read_bytes() == b"mp3"
