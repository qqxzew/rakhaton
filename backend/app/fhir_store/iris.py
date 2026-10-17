"""FhirStore backed by the InterSystems IRIS for Health FHIR R4 server (REST).

Dataset resources are loaded into IRIS by scripts/load_iris.py with their original ids, so this
store returns the same ids and content as LocalBundleStore. Derived resources (ServiceRequest,
Observation imaging-reference, Provenance, Task, Communication, AuditEvent) are written with PUT
by id, which makes reruns idempotent.

Only interactions listed in the server's CapabilityStatement are used: read, search-type, update,
create, and a transaction-free paging over searchset links.
"""

from __future__ import annotations

import re
import time
import uuid
from collections import OrderedDict
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.fhir_store.base import FhirStore, FhirStoreError, PatientNotFound, Resource
from app.iris_resources import fhir_client

# Clinical resource types the pipeline reads per patient (lab Observations are not loaded).
PATIENT_TYPES = (
    "ImagingStudy",
    "DiagnosticReport",
    "DocumentReference",
    "Condition",
    "Procedure",
    "MedicationAdministration",
    "MedicationRequest",
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_PAGE = 500
_CACHE_SIZE = 64
_RETRY_STATUS = (429, 502, 503, 504)
_RETRIES = 3
_BACKOFF = 0.5  # seconds, multiplied by the attempt number


class IrisFhirStore(FhirStore):
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        s = settings or get_settings()
        self.base = s.iris_fhir_base.rstrip("/")
        if not self.base:
            raise FhirStoreError("IRIS_FHIR_BASE is not set")
        self._client = client or fhir_client(self.base, s)
        self._bundles: OrderedDict[str, Resource] = OrderedDict()

    # --- HTTP helpers -----------------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """One HTTP call; retries a few times on transport errors and 429/502/503/504."""
        for attempt in range(_RETRIES + 1):
            last = attempt == _RETRIES
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                if last:
                    raise FhirStoreError(f"IRIS FHIR unreachable: {type(exc).__name__}") from exc
            else:
                if resp.status_code not in _RETRY_STATUS or last:
                    return resp
            time.sleep(_BACKOFF * (attempt + 1))
        raise AssertionError("unreachable")

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Resource:
        resp = self._request("GET", url, params=params)
        if resp.status_code == 404:
            raise PatientNotFound("resource not found in IRIS")
        if resp.status_code >= 300:
            raise FhirStoreError(f"IRIS FHIR GET failed: HTTP {resp.status_code}")
        return resp.json()

    def _search_all(self, resource_type: str, params: dict[str, Any]) -> list[Resource]:
        out: list[Resource] = []
        bundle = self._get(f"{self.base}/{resource_type}", {**params, "_count": _PAGE})
        while True:
            out += [
                e["resource"] for e in bundle.get("entry", [])
                if e.get("search", {}).get("mode", "match") == "match" and "resource" in e
            ]
            nxt = next((link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"), None)
            if not nxt:
                return out
            bundle = self._get(nxt)

    # --- FhirStore --------------------------------------------------------------------------

    def capability(self) -> Resource:
        return self._get(f"{self.base}/metadata")

    def count(self, resource_type: str) -> int:
        """Number of resources of a type, via `_summary=count`."""
        return int(self._get(f"{self.base}/{resource_type}", {"_summary": "count"}).get("total", 0))

    def list_patient_ids(self) -> list[str]:
        return sorted(r["id"] for r in self._search_all("Patient", {"_elements": "id"}))

    def get_patient_bundle(self, patient_id: str) -> Resource:
        if not _SAFE_ID.match(patient_id):
            raise PatientNotFound(f"invalid patient id: {patient_id!r}")
        cached = self._bundles.get(patient_id)
        if cached is not None:
            self._bundles.move_to_end(patient_id)
            return cached
        patient = self._get(f"{self.base}/Patient/{patient_id}")
        entries = [{"resource": patient}]
        for rtype in PATIENT_TYPES:
            for r in self._search_all(rtype, {"subject": f"Patient/{patient_id}"}):
                entries.append({"resource": r})
        bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}
        self._bundles[patient_id] = bundle
        if len(self._bundles) > _CACHE_SIZE:
            self._bundles.popitem(last=False)
        return bundle

    def resources(self, patient_id: str, resource_type: str) -> list[Resource]:
        bundle = self.get_patient_bundle(patient_id)
        return [
            e["resource"] for e in bundle["entry"]
            if e["resource"].get("resourceType") == resource_type
        ]

    def _put(self, resource: Resource) -> Resource:
        url = f"{self.base}/{resource['resourceType']}/{resource['id']}"
        resp = self._request("PUT", url, json=resource, headers={"Content-Type": "application/fhir+json"})
        if resp.status_code >= 300:
            raise FhirStoreError(f"IRIS FHIR PUT {resource['resourceType']} failed: HTTP {resp.status_code} "
                                 f"{_outcome_text(resp)}")
        return resp.json() if resp.content else resource

    def create(self, resource: Resource) -> Resource:
        if "resourceType" not in resource:
            raise FhirStoreError("resource has no resourceType")
        return self._put({**resource, "id": resource.get("id") or uuid.uuid4().hex})

    def update(self, resource: Resource) -> Resource:
        if "resourceType" not in resource or "id" not in resource:
            raise FhirStoreError("update needs resourceType and id")
        return self._put(resource)

    def search(self, resource_type: str, params: dict[str, str] | None = None) -> list[Resource]:
        return self._search_all(resource_type, dict(params or {}))

    def delete(self, resource_type: str, resource_id: str) -> None:
        resp = self._request("DELETE", f"{self.base}/{resource_type}/{resource_id}")
        if resp.status_code >= 300 and resp.status_code not in (404, 410):
            raise FhirStoreError(f"IRIS FHIR DELETE {resource_type} failed: HTTP {resp.status_code} "
                                 f"{_outcome_text(resp)}")

    def forget(self, patient_id: str) -> None:
        self._bundles.pop(patient_id, None)


def _outcome_text(resp: httpx.Response) -> str:
    try:
        issues = resp.json().get("issue", [])
        return "; ".join(i.get("diagnostics") or i.get("details", {}).get("text", "") for i in issues)[:300]
    except ValueError:
        return ""
