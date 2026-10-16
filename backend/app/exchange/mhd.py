"""IHE MHD delivery of a requested study (T080).

A simulated provider "sends" the study by submitting an IHE MHD ITI-65 *Provide Document Bundle*
to Motol's FHIR endpoint in IRIS: a transaction Bundle with a SubmissionSet `List` and a
`DocumentReference` whose `context.related` points to the provider's ImagingStudy and whose identifier
carries our request id (PACS-REQ-...). The attachment is a short synthetic delivery note, never report
text. `find_delivery` is the receiving side: it searches Motol for that request id and returns the
referenced study (modality, date), ready for verification against the request.

Messages carry the request id and study metadata only, no patient identifiers (hard rule 8); the
patient is referenced as a FHIR subject inside the hospital's own system.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.exchange.hospitals import (
    FHIR_JSON,
    SIM_SYSTEM,
    Hospital,
    HospitalError,
    hospitals,
    make_client,
    motol_base,
    pipeline_modality,
    request,
    search_bundle,
    sim_tag,
)

REQUEST_ID_SYSTEM = "urn:pacs-comparator:request-id"
MHD = "https://profiles.ihe.net/ITI/MHD/StructureDefinition"
MHD_LIST_TYPES = "https://profiles.ihe.net/ITI/MHD/CodeSystem/MHDlistTypes"
SOURCE_ID_EXT = f"{MHD}/ihe-sourceId"
DESIGNATION_EXT = f"{MHD}/ihe-designationType"


@dataclass(frozen=True)
class DeliveryRequest:
    """What the provider is asked to deliver and which request it answers."""

    request_id: str  # PACS-REQ-000123
    patient_id: str  # pseudonymous id, used as FHIR subject only
    modality: str
    study_date: date
    provider_study_ref: str  # absolute reference to the provider's ImagingStudy


@dataclass(frozen=True)
class Delivery:
    request_id: str
    document_id: str | None
    submission_set_id: str | None
    provider_id: str | None
    study_ref: str
    modality: str | None
    study_date: date | None


def _provider_hospital(provider: dict | Hospital) -> Hospital:
    if isinstance(provider, Hospital):
        return provider
    for hospital in hospitals():
        if hospital.id == provider["id"]:
            return hospital
    raise HospitalError(f"provider {provider.get('id')!r} has no simulated FHIR endpoint")


def delivery_note(req: DeliveryRequest, hospital: Hospital) -> str:
    """Short synthetic note; request id and study metadata only."""
    return (f"Simulovaná dodávka studie pro žádost {req.request_id}. Odesílatel: {hospital.name}. "
            f"Modalita {req.modality}, datum studie {req.study_date.isoformat()}. "
            "Syntetická zpráva bez klinického obsahu.")


def build_provide_document_bundle(
    provider: dict | Hospital, req: DeliveryRequest, now: datetime | None = None
) -> dict[str, Any]:
    """IHE MHD ITI-65 Provide Document Bundle (transaction) for one delivered study."""
    hospital = _provider_hospital(provider)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc_full = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'doc|' + req.request_id)}"
    set_full = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'set|' + req.request_id)}"
    request_identifier = {"system": REQUEST_ID_SYSTEM, "value": req.request_id}
    subject = {"reference": f"Patient/{req.patient_id}"}
    note = delivery_note(req, hospital).encode("utf-8")
    document = {
        "resourceType": "DocumentReference",
        "meta": {"profile": [f"{MHD}/IHE.MHD.Minimal.DocumentReference"], "tag": [sim_tag()]},
        "masterIdentifier": {"system": "urn:ietf:rfc:3986", "value": doc_full},
        "identifier": [request_identifier],
        "status": "current",
        "type": {"text": "Delivery note for requested imaging study"},
        "category": [{"coding": [{"system": "http://loinc.org", "code": "18748-4",
                                  "display": "Diagnostic imaging study"}]}],
        "subject": subject,
        "date": stamp,
        "description": f"Dodávka studie k žádosti {req.request_id} (simulace)",
        "content": [{"attachment": {
            "contentType": "text/plain", "language": "cs", "title": f"{req.request_id} delivery note",
            "data": base64.b64encode(note).decode("ascii"),
        }}],
        "context": {
            "related": [{"reference": req.provider_study_ref}],
            "period": {"start": req.study_date.isoformat()},
        },
    }
    submission_set = {
        "resourceType": "List",
        "meta": {"profile": [f"{MHD}/IHE.MHD.Comprehensive.SubmissionSet"], "tag": [sim_tag()]},
        "extension": [{
            "url": SOURCE_ID_EXT,
            "valueIdentifier": {"value": f"urn:pacs-comparator:provider:{hospital.id}"},
        }],
        "identifier": [request_identifier,
                       {"use": "official", "system": "urn:ietf:rfc:3986",
                        "value": set_full}],
        "status": "current",
        "mode": "working",
        "title": f"Submission set {req.request_id}",
        "code": {"coding": [{"system": MHD_LIST_TYPES, "code": "submissionset"}]},
        "subject": subject,
        "date": stamp,
        "entry": [{"item": {"reference": doc_full}}],
    }
    # ifNoneExist makes redelivery of the same request idempotent: one document per request id.
    cond = f"identifier={REQUEST_ID_SYSTEM}|{req.request_id}"
    return {
        "resourceType": "Bundle",
        "meta": {"profile": [f"{MHD}/IHE.MHD.Provide.Bundle"]},
        "type": "transaction",
        "entry": [
            {"fullUrl": set_full, "resource": submission_set,
             "request": {"method": "POST", "url": "List", "ifNoneExist": cond}},
            {"fullUrl": doc_full, "resource": document,
             "request": {"method": "POST", "url": "DocumentReference", "ifNoneExist": cond}},
        ],
    }


def provide_document_bundle(
    provider: dict | Hospital, req: DeliveryRequest, client: httpx.Client | None = None,
    base: str | None = None,
) -> dict[str, Any]:
    """Build the ITI-65 bundle and POST it to Motol's FHIR endpoint. Returns the transaction response."""
    bundle = build_provide_document_bundle(provider, req)
    client = client or make_client()
    resp = request(client, "POST", (base or motol_base()).rstrip("/"), json=bundle,
                   headers={"Content-Type": FHIR_JSON})
    if resp.status_code >= 300:
        raise HospitalError(f"MHD Provide Document Bundle rejected: HTTP {resp.status_code}")
    out = resp.json() if resp.content else {}
    out["_http_status"] = resp.status_code
    return out


def _by_request(client: httpx.Client, base: str, resource_type: str, request_id: str) -> list[dict]:
    return search_bundle(client, base, resource_type, [("identifier", f"{REQUEST_ID_SYSTEM}|{request_id}")])


def find_delivery(
    request_id: str, client: httpx.Client | None = None, base: str | None = None
) -> Delivery | None:
    """Search Motol for DocumentReference / SubmissionSet List carrying the request id; resolve the study."""
    client = client or make_client()
    base = (base or motol_base()).rstrip("/")
    documents = _by_request(client, base, "DocumentReference", request_id)
    if not documents:
        return None
    document = documents[0]
    lists = _by_request(client, base, "List", request_id)
    related = next((r.get("reference") for r in document.get("context", {}).get("related", [])
                    if "ImagingStudy/" in (r.get("reference") or "")), None)
    if not related:
        return None
    hospital = next((h for h in hospitals() if related.startswith(h.base_url + "/")), None)
    modality = study_date = None
    if hospital is not None:  # only dereference references that point at a known simulated hospital
        resp = request(client, "GET", related)
        if resp.status_code < 300:
            study = resp.json()
            for coding in study.get("modality", []):
                modality = pipeline_modality(coding.get("code")) or modality
            started = str(study.get("started", ""))[:10]
            study_date = date.fromisoformat(started) if len(started) == 10 else None
    return Delivery(request_id=request_id, document_id=document.get("id"),
                    submission_set_id=lists[0].get("id") if lists else None,
                    provider_id=hospital.id if hospital else None, study_ref=related,
                    modality=modality, study_date=study_date)


__all__ = ["Delivery", "DeliveryRequest", "SIM_SYSTEM", "build_provide_document_bundle", "find_delivery",
           "provide_document_bundle"]
