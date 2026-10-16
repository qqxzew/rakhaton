"""scripts/load_iris.py: labs are skipped, a failing transaction falls back to per-resource PUT."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import load_iris  # noqa: E402

BASE = "http://iris.test/fhir/r4"


def bundle_bytes() -> bytes:
    entries = [
        {"resource": {"resourceType": "Patient", "id": "PAC-TEST-0001"}, "request": {"method": "PUT"}},
        {"resource": {"resourceType": "Observation", "id": "lab-1"}, "request": {"method": "PUT"}},
        {"resource": {"resourceType": "ImagingStudy", "id": "STU-T1"}, "request": {"method": "PUT"}},
    ]
    return json.dumps({"resourceType": "Bundle", "type": "transaction", "entry": entries}).encode()


def test_prepare_bundle_skips_lab_observations(tmp_path):
    path = tmp_path / "PAC-TEST-0001.json"
    path.write_bytes(bundle_bytes())
    kept = json.loads(load_iris.prepare_bundle(path, include_labs=False))["entry"]
    assert [e["resource"]["resourceType"] for e in kept] == ["Patient", "ImagingStudy"]
    all_kept = json.loads(load_iris.prepare_bundle(path, include_labs=True))["entry"]
    assert len(all_kept) == 3


def test_transaction_success_is_a_single_post():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json={"resourceType": "Bundle"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert load_iris.post_bundle(client, BASE, bundle_bytes()) == (200, "")
    assert calls == ["POST"]


def test_failed_transaction_falls_back_to_put_per_resource(monkeypatch):
    monkeypatch.setattr(load_iris.time, "sleep", lambda _s: None)
    puts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(400, text="reference problem")
        puts.append(request.url.path)
        return httpx.Response(200 if "ImagingStudy" not in request.url.path else 400, text="bad")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        status, message = load_iris.post_bundle(client, BASE, bundle_bytes())
    assert status == 207 and "1 resources failed" in message
    assert puts == ["/fhir/r4/Patient/PAC-TEST-0001", "/fhir/r4/Observation/lab-1", "/fhir/r4/ImagingStudy/STU-T1"]


def test_retry_on_server_busy(monkeypatch):
    monkeypatch.setattr(load_iris.time, "sleep", lambda _s: None)
    answers = [503, 429, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(answers.pop(0), json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert load_iris.post_bundle(client, BASE, bundle_bytes())[0] == 200
