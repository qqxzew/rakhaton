"""Choose the FhirStore implementation from settings."""

from __future__ import annotations

from app.config import get_settings
from app.fhir_store.base import FhirStore, FhirStoreError
from app.fhir_store.local import LocalBundleStore


def get_store() -> FhirStore:
    backend = get_settings().fhir_backend
    if backend == "local":
        return LocalBundleStore()
    if backend == "iris":
        from app.fhir_store.iris import IrisFhirStore

        return IrisFhirStore()
    raise FhirStoreError(f"FHIR_BACKEND={backend!r} is not available yet")
