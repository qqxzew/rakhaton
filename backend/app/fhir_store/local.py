"""File-based FhirStore: reads per-patient transaction bundles, writes derived resources as JSON.

Dataset bundles live in data/raw/fhir/PAC-*.json (read only). Derived resources are written to
data/fhir_out/<ResourceType>/<id>.json. Both locations are git-ignored.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import OrderedDict
from pathlib import Path

from app.config import Settings, get_settings
from app.fhir_store.base import FhirStore, FhirStoreError, PatientNotFound, Resource, is_test_upload

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_BUNDLE_CACHE_SIZE = 64

_UPLOAD_TYPES = {"ImagingStudy", "DiagnosticReport"}


class LocalBundleStore(FhirStore):
    def __init__(self, fhir_dir: Path | None = None, out_dir: Path | None = None,
                 settings: Settings | None = None):
        s = settings or get_settings()
        self.fhir_dir = fhir_dir or (s.raw_dir / "fhir")
        self.out_dir = out_dir or s.fhir_out_dir
        self._bundles: OrderedDict[str, Resource] = OrderedDict()

    def list_patient_ids(self) -> list[str]:
        return sorted(p.stem for p in self.fhir_dir.glob("PAC-*.json"))

    def _bundle_path(self, patient_id: str) -> Path:
        if not _SAFE_ID.match(patient_id):
            raise PatientNotFound(f"invalid patient id: {patient_id!r}")
        return self.fhir_dir / f"{patient_id}.json"

    def get_patient_bundle(self, patient_id: str) -> Resource:
        cached = self._bundles.get(patient_id)
        if cached is not None:
            self._bundles.move_to_end(patient_id)
            return cached
        path = self._bundle_path(patient_id)
        if not path.exists():
            raise PatientNotFound(f"patient bundle not found: {patient_id}")
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FhirStoreError(f"cannot read bundle for {patient_id}: {type(exc).__name__}") from exc
        self._bundles[patient_id] = bundle
        if len(self._bundles) > _BUNDLE_CACHE_SIZE:
            self._bundles.popitem(last=False)
        return bundle

    def resources(self, patient_id: str, resource_type: str) -> list[Resource]:
        bundle = self.get_patient_bundle(patient_id)
        found = [
            e["resource"]
            for e in bundle.get("entry", [])
            if e.get("resource", {}).get("resourceType") == resource_type
        ]
        if resource_type not in _UPLOAD_TYPES:
            return found
        # test reports uploaded from the UI live next to our derived resources
        subject = f"Patient/{patient_id}"
        return found + [r for r in self.search(resource_type, {"subject": subject}) if is_test_upload(r)]

    def _out_path(self, resource_type: str, resource_id: str) -> Path:
        if not _SAFE_ID.match(resource_type) or not _SAFE_ID.match(resource_id):
            raise FhirStoreError("invalid resource type or id")
        return self.out_dir / resource_type / f"{resource_id}.json"

    def _write(self, resource: Resource) -> Resource:
        path = self._out_path(resource["resourceType"], resource["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(resource, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        return resource

    def create(self, resource: Resource) -> Resource:
        if "resourceType" not in resource:
            raise FhirStoreError("resource has no resourceType")
        resource = {**resource, "id": resource.get("id") or uuid.uuid4().hex}
        return self._write(resource)

    def update(self, resource: Resource) -> Resource:
        if "resourceType" not in resource or "id" not in resource:
            raise FhirStoreError("update needs resourceType and id")
        return self._write(resource)

    def delete(self, resource_type: str, resource_id: str) -> None:
        self._out_path(resource_type, resource_id).unlink(missing_ok=True)

    def forget(self, patient_id: str) -> None:
        self._bundles.pop(patient_id, None)

    def search(self, resource_type: str, params: dict[str, str] | None = None) -> list[Resource]:
        folder = self.out_dir / resource_type
        if not folder.exists():
            return []
        found = []
        for path in sorted(folder.glob("*.json")):
            resource = json.loads(path.read_text(encoding="utf-8"))
            if all(_matches(resource, k, v) for k, v in (params or {}).items()):
                found.append(resource)
        return found


def _matches(resource: Resource, key: str, expected: str) -> bool:
    if key == "_id":
        return resource.get("id") == expected
    value = resource.get(key)
    if isinstance(value, dict):
        return value.get("reference") == expected or value.get("id") == expected
    if isinstance(value, list):
        return any(
            (isinstance(v, dict) and v.get("reference") == expected) or v == expected for v in value
        )
    return value == expected
