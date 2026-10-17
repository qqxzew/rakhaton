"""IHE MHD ITI-65 delivery and lookup against a mocked Motol endpoint; synthetic ids only."""

from __future__ import annotations

import base64
from datetime import date

import pytest

from app.exchange.hospitals import SIM_SYSTEM, HospitalError
from app.exchange.mhd import (
    REQUEST_ID_SYSTEM,
    DeliveryRequest,
    build_provide_document_bundle,
    find_delivery,
    provide_document_bundle,
)
from tests.unit.fhir_fakes import FNM, HOSPITALS, MOTOL, FakeFhir, imaging_study

REQ = DeliveryRequest(
    request_id="PACS-REQ-000123", patient_id="PAC-TEST-0001", modality="PET",
    study_date=date(2025, 3, 12), provider_study_ref=f"{FNM.base_url}/ImagingStudy/SIM-1",
)


@pytest.fixture(autouse=True)
def _hospital_urls(monkeypatch: pytest.MonkeyPatch):
    from app.exchange import mhd

    monkeypatch.setattr(mhd, "hospitals", lambda: HOSPITALS)


def test_bundle_is_an_iti65_transaction_with_submission_set_and_document():
    bundle = build_provide_document_bundle(FNM, REQ)
    assert bundle["type"] == "transaction"
    assert bundle["meta"]["profile"][0].endswith("IHE.MHD.Provide.Bundle")
    set_entry, doc_entry = bundle["entry"]
    submission_set, document = set_entry["resource"], doc_entry["resource"]
    assert submission_set["resourceType"] == "List"
    assert submission_set["meta"]["profile"][0].endswith("IHE.MHD.Comprehensive.SubmissionSet")
    assert submission_set["code"]["coding"][0]["code"] == "submissionset"
    assert submission_set["entry"][0]["item"]["reference"] == doc_entry["fullUrl"]
    assert document["resourceType"] == "DocumentReference"
    assert document["meta"]["profile"][0].endswith("IHE.MHD.Minimal.DocumentReference")
    assert document["context"]["related"] == [{"reference": REQ.provider_study_ref}]
    assert {"system": REQUEST_ID_SYSTEM, "value": REQ.request_id} in document["identifier"]
    assert {"system": REQUEST_ID_SYSTEM, "value": REQ.request_id} in submission_set["identifier"]
    for entry in bundle["entry"]:
        assert entry["request"]["method"] == "POST"
        assert any(t["system"] == SIM_SYSTEM and t["code"] == "simulated" for t in entry["resource"]["meta"]["tag"])


def test_attachment_is_a_short_synthetic_note_with_request_id_and_no_patient_identifier():
    document = build_provide_document_bundle(FNM, REQ)["entry"][1]["resource"]
    note = base64.b64decode(document["content"][0]["attachment"]["data"]).decode("utf-8")
    assert REQ.request_id in note and "Simulovaná" in note and len(note) < 300
    assert "PAC-" not in note
    assert "PAC-" not in document["description"]


def test_provide_document_bundle_posts_to_motol_and_find_delivery_resolves_the_study():
    fake = FakeFhir()
    fake.add(FNM.base_url, imaging_study("SIM-1", REQ.patient_id, "PT", "2025-03-12"))
    client = fake.client()
    response = provide_document_bundle(FNM, REQ, client=client, base=MOTOL)
    assert response["_http_status"] == 200
    post = next(c for c in fake.calls if c.method == "POST")
    assert str(post.url) == MOTOL

    delivery = find_delivery(REQ.request_id, client=client, base=MOTOL)
    assert delivery is not None
    assert (delivery.modality, delivery.study_date, delivery.provider_id) == ("PET", date(2025, 3, 12), "fnm")
    assert delivery.document_id and delivery.submission_set_id


def test_find_delivery_returns_none_for_unknown_request():
    assert find_delivery("PACS-REQ-999999", client=FakeFhir().client(), base=MOTOL) is None


def test_find_delivery_does_not_dereference_references_outside_the_known_hospitals():
    fake = FakeFhir()
    req = DeliveryRequest(**{**REQ.__dict__, "provider_study_ref": "http://evil.example/ImagingStudy/X"})
    provide_document_bundle(FNM, req, client=fake.client(), base=MOTOL)
    delivery = find_delivery(req.request_id, client=fake.client(), base=MOTOL)
    assert delivery is not None and delivery.modality is None and delivery.study_date is None
    assert all("evil.example" not in str(c.url) for c in fake.calls)


def test_rejected_transaction_raises():
    fake = FakeFhir()
    fake.reject_transactions = True
    with pytest.raises(HospitalError):
        provide_document_bundle(FNM, REQ, client=fake.client(), base=MOTOL)


def test_unknown_provider_has_no_simulated_endpoint():
    with pytest.raises(HospitalError):
        build_provide_document_bundle({"id": "plzen"}, REQ)
