"""IrisFhirStore against a mocked FHIR server (httpx.MockTransport); synthetic resources only."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.config import Settings
from app.fhir_store import iris as iris_module
from app.fhir_store.base import FhirStoreError, PatientNotFound
from app.fhir_store.iris import PATIENT_TYPES, IrisFhirStore
from app.fhir_store.mappers import reference_to_observation
from app.pipeline.schemas import Evidence, PriorReference

BASE = "http://iris.test/fhir/r4"
PATIENT = "PAC-TEST-0001"


class FakeFhirServer:
    """Tiny in-memory FHIR server: read, search by `subject`, paging via `next` links, PUT."""

    def __init__(self, page_size: int = 2):
        self.resources: dict[tuple[str, str], dict] = {}
        self.requests: list[httpx.Request] = []
        self.page_size = page_size
        self.fail_next: list[int] = []  # statuses to answer before behaving normally

    def add(self, resource: dict) -> None:
        self.resources[(resource["resourceType"], resource["id"])] = resource

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0), json={"resourceType": "OperationOutcome", "issue": []})
        url = urlparse(str(request.url))
        parts = url.path.removeprefix("/fhir/r4/").split("/")
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        rtype = parts[0]
        if request.method == "PUT":
            body = json.loads(request.content)
            if body["id"] != parts[1]:
                return httpx.Response(400, json={"issue": [{"diagnostics": "id mismatch"}]})
            self.add({**body, "meta": {"versionId": "1"}})
            return httpx.Response(200, json=body)
        if len(parts) == 2:
            found = self.resources.get((rtype, parts[1]))
            return httpx.Response(200, json=found) if found else httpx.Response(404, json={})
        if query.get("_summary") == "count":
            total = sum(1 for (t, _) in self.resources if t == rtype)
            return httpx.Response(200, json={"resourceType": "Bundle", "total": total})
        subject = query.get("subject")
        matches = [
            r for (t, _), r in sorted(self.resources.items())
            if t == rtype and (subject is None or (r.get("subject") or {}).get("reference") == subject)
        ]
        start = int(query.get("_offset", 0))
        page = matches[start:start + self.page_size]
        links = []
        if start + self.page_size < len(matches):
            kept = "&".join(f"{k}={v}" for k, v in query.items() if k != "_offset")
            links.append({"relation": "next", "url": f"{BASE}/{rtype}?{kept}&_offset={start + self.page_size}"})
        return httpx.Response(200, json={
            "resourceType": "Bundle", "type": "searchset", "link": links,
            "entry": [{"resource": r, "search": {"mode": "match"}} for r in page],
        })


def make_store(server: FakeFhirServer, base: str = BASE + "/") -> IrisFhirStore:
    settings = Settings(data_dir=None, app_db_url="sqlite://", iris_fhir_base=base,  # type: ignore[arg-type]
                        iris_user="u", iris_password="p")
    client = httpx.Client(transport=httpx.MockTransport(server), auth=("u", "p"))
    return IrisFhirStore(settings, client)


def study(sid: str, patient: str = PATIENT) -> dict:
    return {"resourceType": "ImagingStudy", "id": sid, "status": "available",
            "subject": {"reference": f"Patient/{patient}"}}


@pytest.fixture
def server() -> FakeFhirServer:
    srv = FakeFhirServer()
    srv.add({"resourceType": "Patient", "id": PATIENT})
    srv.add({"resourceType": "Patient", "id": "PAC-TEST-0002"})
    for n in range(5):  # 5 resources with page size 2 -> three pages
        srv.add(study(f"STU-T{n}"))
    srv.add(study("STU-OTHER", patient="PAC-TEST-0002"))
    srv.add({"resourceType": "Condition", "id": "c1", "subject": {"reference": f"Patient/{PATIENT}"}})
    return srv


def test_resources_follow_paging_and_filter_by_patient(server):
    store = make_store(server)
    studies = store.imaging_studies(PATIENT)
    assert sorted(s["id"] for s in studies) == [f"STU-T{n}" for n in range(5)]
    assert [c["id"] for c in store.conditions(PATIENT)] == ["c1"]
    assert store.radiology_reports(PATIENT) == []
    searched = {r.url.path.rsplit("/", 1)[-1] for r in server.requests if r.url.params.get("subject")}
    assert searched == set(PATIENT_TYPES)
    assert all(r.headers["authorization"].startswith("Basic ") for r in server.requests)


def test_patient_bundle_is_cached_and_contains_patient(server):
    store = make_store(server)
    bundle = store.get_patient_bundle(PATIENT)
    assert bundle["entry"][0]["resource"]["id"] == PATIENT
    calls = len(server.requests)
    store.imaging_studies(PATIENT)
    store.conditions(PATIENT)
    assert len(server.requests) == calls


def test_list_patient_ids_and_count(server):
    store = make_store(server)
    assert store.list_patient_ids() == [PATIENT, "PAC-TEST-0002"]
    assert store.count("ImagingStudy") == 6


def test_unknown_or_malformed_patient_raises_not_found(server):
    store = make_store(server)
    with pytest.raises(PatientNotFound):
        store.get_patient_bundle("PAC-MISSING")
    calls = len(server.requests)
    with pytest.raises(PatientNotFound):
        store.get_patient_bundle("../metadata")
    assert len(server.requests) == calls  # the malformed id never reached the server


def test_update_is_put_by_id_and_create_assigns_id(server):
    store = make_store(server)
    sr = {"resourceType": "ServiceRequest", "id": "SR-1", "status": "active", "intent": "plan",
          "subject": {"reference": f"Patient/{PATIENT}"}}
    store.update(sr)
    store.update({**sr, "status": "completed"})
    assert server.resources[("ServiceRequest", "SR-1")]["status"] == "completed"
    assert sum(r.method == "PUT" for r in server.requests) == 2
    created = store.create({"resourceType": "Task", "status": "requested", "intent": "order"})
    assert created["id"] and ("Task", created["id"]) in server.resources
    found = store.search("ServiceRequest", {"subject": f"Patient/{PATIENT}"})
    assert [r["id"] for r in found] == ["SR-1"]
    with pytest.raises(FhirStoreError):
        store.update({"resourceType": "Task"})
    with pytest.raises(FhirStoreError):
        store.create({"id": "x"})


def test_transient_errors_are_retried_then_reported(server, monkeypatch):
    monkeypatch.setattr(iris_module, "_BACKOFF", 0)
    store = make_store(server)
    server.fail_next = [503, 429]
    assert store.count("Patient") == 2
    server.fail_next = [503] * 10
    with pytest.raises(FhirStoreError, match="HTTP 503"):
        store.count("Patient")


def test_rejected_write_is_a_store_error(server):
    store = make_store(server)
    server.fail_next = [400]
    with pytest.raises(FhirStoreError, match="HTTP 400"):
        store.update({"resourceType": "Task", "id": "T2"})


def test_transport_failure_is_a_store_error(monkeypatch):
    monkeypatch.setattr(iris_module, "_BACKOFF", 0)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    settings = Settings(data_dir=None, app_db_url="sqlite://", iris_fhir_base=BASE)  # type: ignore[arg-type]
    store = IrisFhirStore(settings, httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(FhirStoreError, match="unreachable"):
        store.count("Patient")


def test_missing_base_url_is_rejected():
    settings = Settings(data_dir=None, app_db_url="sqlite://", iris_fhir_base="")  # type: ignore[arg-type]
    with pytest.raises(FhirStoreError):
        IrisFhirStore(settings)


def test_imaging_reference_observation_is_valid_for_iris():
    """IRIS rejects derivedFrom -> DiagnosticReport and empty values; the mapper must avoid both."""
    ref = PriorReference(
        id="REF-1", patient_id=PATIENT, from_report_id="rep-STU-T1", modality="CT",
        evidence=Evidence(doc_id="rep-STU-T1", quote="srovnáno s CT", confidence=0.9),
    )
    obs = reference_to_observation(ref)
    assert obs["derivedFrom"] == [{"reference": "ImagingStudy/STU-T1"}]
    assert obs["focus"] == [{"reference": "DiagnosticReport/rep-STU-T1"}]
    assert all(c["valueString"] for c in obs["component"])
