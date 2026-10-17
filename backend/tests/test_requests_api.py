"""Request loop API with the IRIS production mocked (synthetic data only)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import requests as api
from app.app_db.models import AutopilotPolicy, Case, CaseResult, Meeting
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
        elif action == "CANCEL":
            self.requests[request_id]["state"] = "CANCELLED"
        elif action == "DELIVERY":
            ok = (payload or {}).get("modality", self.requests[request_id]["payload"]["modality"]) == \
                self.requests[request_id]["payload"]["modality"]
            self.requests[request_id]["state"] = "VERIFIED" if ok else "RECEIVED"
        return {"ok": True, "requestId": request_id, "state": self.requests[request_id]["state"]}

    def list(self, case_id=""):
        return [{"requestId": r, "itemId": v["payload"]["itemId"], "caseId": v["payload"]["caseId"],
                 "state": v["state"]} for r, v in self.requests.items()
                if not case_id or v["payload"]["caseId"] == case_id]

    def draft_ids(self, case_ids=None):
        return [r for r, v in self.requests.items() if v["state"] == "DRAFTED"
                and (not case_ids or v["payload"]["caseId"] in case_ids)]

    def get(self, request_id):
        if request_id not in self.requests:
            return None
        v = self.requests[request_id]
        return {"requestId": request_id, "state": v["state"], "sessionIds": "7,9", "messages": [], "provider": {"id": v["payload"].get("providerId", "")},
                "caseId": v["payload"]["caseId"], "itemId": v["payload"]["itemId"],
                "modality": v["payload"]["modality"], "targetDate": v["payload"]["targetDate"],
                "regions": v["payload"]["regions"]}

    def advance_time(self, hours):
        return {"offsetSeconds": hours * 3600}


@pytest.fixture(autouse=True)
def _reset_autopilot():
    def clear():
        with session_scope() as db:
            policy = db.get(AutopilotPolicy, 1)
            if policy is not None:
                db.delete(policy)

    clear()
    yield
    clear()


@pytest.fixture
def client_and_fake():
    fake = FakeProduction()
    test_app = create_app()
    test_app.dependency_overrides[api.production] = lambda: fake
    with TestClient(test_app) as client:
        yield client, fake


def _seed_case(site_id: str = "nnh", site_name: str = "NNH") -> str:
    item = {
        "id": "ITEM-TEST-1", "rule_ids": ["R1"], "reasons": ["test"], "modality": "PET", "regions": ["chest"],
        "target_date": {"year": 2025, "month": 5, "day": 12}, "availability": "not_found", "state": "missing",
        "holding_site_id": site_id, "holding_site_name": site_name,
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


def test_waive_records_actor_cancels_request_and_updates_readiness(client_and_fake):
    client, fake = client_and_fake
    case_id = _seed_case()
    client.post(f"/api/cases/{case_id}/requests")
    assert client.post("/api/items/ITEM-TEST-1/waive", json={"reason": "x", "coordinator": "K"}).status_code == 422
    out = client.post("/api/items/ITEM-TEST-1/waive", json={"reason": "Není potřeba", "coordinator": "Koordinátor"})
    data = out.json()
    assert out.status_code == 200 and data["actor"] == "Koordinátor" and data["cancelled_request"]
    assert fake.calls[-1][0] == "CANCEL"
    with session_scope() as db:
        case = db.get(Case, case_id)
        assert case.readiness != "not_ready"
    assert client.post("/api/items/ITEM-NOPE/waive", json={"reason": "Není potřeba", "coordinator": "K"}
                       ).status_code == 404


def test_delivery_without_hospital_study_uses_request_values_and_verifies(client_and_fake):
    client, fake = client_and_fake
    case_id = _seed_case()
    client.post(f"/api/cases/{case_id}/requests")
    rid = next(iter(fake.requests))
    client.post("/api/requests/approve-all", json={"coordinator": "K", "case_ids": [case_id]})
    wrong = client.post(f"/api/requests/{rid}/simulate-delivery", json={"modality": "CT"})
    assert wrong.json()["state"] == "RECEIVED"
    assert fake.calls[-1][2] == {"modality": "CT", "date": "2025-05-12", "region": "chest"}
    with session_scope() as db:
        # a delivery that failed the automatic check keeps the item missing
        case = db.get(Case, case_id)
        assert case.readiness == "not_ready" and case.readiness_reason.startswith("Chybí")
    early = client.post(f"/api/cases/{case_id}/items/ITEM-TEST-1/confirm", json={"coordinator": "K"})
    assert early.status_code == 422
    right = client.post(f"/api/requests/{rid}/simulate-delivery", json={})
    assert right.json()["state"] == "VERIFIED"
    with session_scope() as db:
        # verified automatically: ready without any coordinator click
        case = db.get(Case, case_id)
        assert (case.readiness, case.readiness_reason) == ("ready", "Všechna požadovaná vyšetření ověřena")
    # the optional sign-off stays harmless
    confirmed = client.post(f"/api/cases/{case_id}/items/ITEM-TEST-1/confirm", json={"coordinator": "K"})
    assert confirmed.status_code == 200 and confirmed.json()["confirmed"]
    with session_scope() as db:
        case = db.get(Case, case_id)
        assert (case.readiness, case.readiness_reason) == ("ready", "Všechna požadovaná vyšetření ověřena")


def test_overlay_marks_verified_delivery_ok_with_automatic_actor():
    from app.pipeline.schemas import CaseCheckResult, RequiredItem, Timeline
    from app.requests.overlay import AUTO_VERIFIER, overlay_result

    item = RequiredItem(id="ITEM-T", rule_ids=["R1"], reasons=["t"], modality="CT", regions=["chest"],
                        target_date={"year": 2025, "month": 5, "day": 12}, availability="not_found", state="missing")
    result = CaseCheckResult(patient_id="PAC-TEST-0001", timeline=Timeline(patient_id="PAC-TEST-0001"), items=[item])
    done = overlay_result(result, "done", {}, {"ITEM-T": {"requestId": "PACS-REQ-000001", "state": "VERIFIED"}})
    assert done.items[0].state == "ok" and done.items[0].availability == "available"
    assert AUTO_VERIFIER in done.items[0].note and done.readiness == "ready"
    failed = overlay_result(result, "done", {}, {"ITEM-T": {"requestId": "PACS-REQ-000001", "state": "RECEIVED"}})
    assert failed.items[0].state == "missing" and failed.readiness == "not_ready"


def test_case_detail_carries_request_state(client_and_fake):
    from app.requests import overlay

    client, fake = client_and_fake
    client.app.dependency_overrides[overlay.optional_client] = lambda: fake
    case_id = _seed_case()
    client.post(f"/api/cases/{case_id}/requests")
    detail = client.get(f"/api/cases/{case_id}").json()
    item = detail["items"][0]
    assert item["request"]["state"] == "DRAFTED" and detail["requests_available"] is True
    assert detail["case"]["reason"].startswith("Chybí")


def test_nightly_run_drafts_only_and_reports_summary(client_and_fake, monkeypatch):
    client, fake = client_and_fake
    case_id = _seed_case()
    monkeypatch.setattr(api, "run_case_check", lambda *a, **k: object())
    out = client.post("/api/demo/nightly-run", json={"days": 3}).json()
    assert out["cases_checked"] == 1 and out["drafts_created"] == 1 and out["drafts_pending"] == 1
    assert {c[0] for c in fake.calls} == {"DRAFT"}  # nothing approved or sent
    again = client.post("/api/demo/nightly-run", json={"days": 3}).json()
    assert again["drafts_created"] == 0 and again["drafts_pending"] == 1
    assert client.get("/api/demo/summary?days=7").json()["drafts_pending"] == 1
    assert out["meetings"][0]["cases"] == 1 and out["meetings"][0]["drafts_created"] == 1
    assert case_id

def test_request_is_shared_between_cases_of_one_patient(client_and_fake):
    from app.requests import overlay

    client, fake = client_and_fake
    client.app.dependency_overrides[overlay.optional_client] = lambda: fake
    case_id = _seed_case()
    with session_scope() as db:
        for obj in (db.get(CaseResult, "CASE-TEST-REQ2"), db.get(Case, "CASE-TEST-REQ2"), db.get(Meeting, "MDT-TEST-REQ2")):
            if obj:
                db.delete(obj)
        db.flush()
        db.add(Meeting(id="MDT-TEST-REQ2", date=date.today() + timedelta(days=5), time="10:00", label="T2",
                       eligible_groups=[]))
        db.add(Case(id="CASE-TEST-REQ2", patient_id="PAC-TEST-0001", meeting_id="MDT-TEST-REQ2", check_status="done"))
        db.flush()
        db.add(CaseResult(case_id="CASE-TEST-REQ2",
                          result=db.get(CaseResult, case_id).result))
    client.post(f"/api/cases/{case_id}/requests")
    assert client.post("/api/cases/CASE-TEST-REQ2/requests").json() == []  # no second draft for the same item
    assert [r["requestId"] for r in client.get("/api/cases/CASE-TEST-REQ2/requests").json()] == ["PACS-REQ-000100"]
    out = client.post("/api/requests/approve-all", json={"coordinator": "K", "case_ids": ["CASE-TEST-REQ2"]})
    assert out.json()["approved"] == 1
    detail = client.get("/api/cases/CASE-TEST-REQ2").json()
    assert detail["items"][0]["request"]["state"] == "SENT"


def test_acknowledged_issue_no_longer_blocks_readiness(client_and_fake):
    from app.app_db.models import IssueAck
    from app.pipeline.schemas import OpenIssue

    client, fake = client_and_fake
    case_id = _seed_case()
    issue = {"type": "data", "text": "2 odkazy bez data (synteticky test)"}
    with session_scope() as db:
        for ack in db.query(IssueAck).filter(IssueAck.case_id == case_id).all():
            db.delete(ack)
        row = db.get(CaseResult, case_id)
        row.result = {**row.result, "open_issues": [issue]}
    client.post("/api/items/ITEM-TEST-1/waive", json={"reason": "Není potřeba", "coordinator": "Koordinátor"})
    with session_scope() as db:
        assert db.get(Case, case_id).readiness == "attention"
    key = OpenIssue(**issue).key
    out = client.post(f"/api/cases/{case_id}/issues/{key}/acknowledge", json={"coordinator": "Koordinátor"})
    assert out.status_code == 200 and out.json()["readiness"] == "ready"
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["open_issues"][0]["acknowledged"] is True and detail["open_issues"][0]["key"] == key
    assert client.post(f"/api/cases/CASE-NOPE/issues/{key}/acknowledge", json={"coordinator": "K"}).status_code == 404


def test_autopilot_needs_a_name_to_be_enabled(client_and_fake):
    client, fake = client_and_fake
    assert client.get("/api/autopilot").json()["enabled"] is False
    assert client.put("/api/autopilot", json={"enabled": True, "coordinator": " "}).status_code == 422
    assert client.get("/api/autopilot").json()["enabled"] is False
    out = client.put("/api/autopilot", json={"enabled": True, "coordinator": "Koordinátor"}).json()
    assert out["enabled"] is True and out["actor"] == "Koordinátor" and out["changed_at"]
    off = client.put("/api/autopilot", json={"enabled": False}).json()
    assert off["enabled"] is False and off["actor"] == "Koordinátor"
    assert fake.calls == []


def test_drafts_stay_drafted_while_autopilot_is_off(client_and_fake):
    client, fake = client_and_fake
    out = client.post(f"/api/cases/{_seed_case()}/requests").json()
    assert out[0]["auto_approved"] is False
    assert [c[0] for c in fake.calls] == ["DRAFT"]


def test_autopilot_approves_new_drafts_with_known_site(client_and_fake):
    client, fake = client_and_fake
    client.put("/api/autopilot", json={"enabled": True, "coordinator": "Koordinátor"})
    out = client.post(f"/api/cases/{_seed_case()}/requests").json()
    assert out[0]["auto_approved"] is True
    action, _, payload, actor = fake.calls[-1]
    assert action == "APPROVE" and actor == "autopilot (zapnul Koordinátor)"
    assert payload == {"approvedBy": actor}
    assert [r["state"] for r in fake.requests.values()] == ["SENT"]


def test_autopilot_leaves_unknown_site_for_a_human(client_and_fake):
    client, fake = client_and_fake
    client.put("/api/autopilot", json={"enabled": True, "coordinator": "Koordinátor"})
    out = client.post(f"/api/cases/{_seed_case('unknown', 'Neznámé pracoviště')}/requests").json()
    assert out[0]["auto_approved"] is False
    assert [c[0] for c in fake.calls] == ["DRAFT"]
    assert [r["state"] for r in fake.requests.values()] == ["DRAFTED"]


def test_nightly_run_reports_auto_approved(client_and_fake, monkeypatch):
    client, fake = client_and_fake
    _seed_case()
    monkeypatch.setattr(api, "run_case_check", lambda *a, **k: object())
    client.put("/api/autopilot", json={"enabled": True, "coordinator": "Koordinátor"})
    out = client.post("/api/demo/nightly-run", json={"days": 3}).json()
    assert out["autopilot"] is True and out["auto_approved"] == 1
    assert out["drafts_created"] == 1 and out["drafts_pending"] == 0
    assert out["meetings"][0]["auto_approved"] == 1
    assert [c[0] for c in fake.calls] == ["DRAFT", "APPROVE"]


def test_enabling_autopilot_approves_waiting_drafts(client_and_fake):
    client, fake = client_and_fake
    client.post(f"/api/cases/{_seed_case()}/requests")
    out = client.put("/api/autopilot", json={"enabled": True, "coordinator": "Koordinátor"}).json()
    assert out["auto_approved"] == 1
    assert [r["state"] for r in fake.requests.values()] == ["SENT"]
