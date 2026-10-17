"""Simulated partner hospitals as FHIR R4 endpoints in IRIS (IRIS Core Track, T078).

Every hospital is a separate FHIR endpoint on the same IRIS server (see scripts/iris_setup.py). Their
content is synthetic and always labeled `urn:pacs-comparator:simulation|simulated` (hard rule 5 of
CLAUDE.md); it never contains real report text.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import CONFIG_DIR, Settings, get_settings
from app.iris_resources import fhir_client
from app.pipeline.schemas import PartialDate

SIM_SYSTEM = "urn:pacs-comparator:simulation"
DCM = "http://dicom.nema.org/resources/ontology/DCM"
SIM_ACCESSION_SYSTEM = "urn:pacs-comparator:simulated-accession"
FHIR_JSON = "application/fhir+json"

# Pipeline modality -> DICOM modality code (DCM). PET/CT is acquired as PT.
DICOM_MODALITY = {"CT": "CT", "MR": "MR", "PET": "PT", "RTG": "CR", "SONO": "US", "MAMO": "MG", "SCINT": "NM"}
_FROM_DICOM = {v: k for k, v in DICOM_MODALITY.items()} | {"DX": "RTG", "PET": "PET"}
_RETRY_STATUS = (429, 502, 503, 504)


class HospitalError(RuntimeError):
    """A hospital endpoint answered with an error or could not be reached."""


@dataclass(frozen=True)
class Hospital:
    id: str
    name: str
    base_url: str  # absolute FHIR base, e.g. http://localhost:52773/nnh/fhir/r4


def sim_tag(code: str = "simulated") -> dict[str, Any]:
    """meta.tag entry marking a resource as simulation data."""
    return {"system": SIM_SYSTEM, "code": code,
            "display": {"simulated": "Simulace", "simulated-holding-site": "Simulace: přiřazené pracoviště"}.get(
                code, code)}


def dicom_modality(modality: str) -> str | None:
    return DICOM_MODALITY.get(modality)


def pipeline_modality(code: str | None) -> str | None:
    return _FROM_DICOM.get((code or "").upper())


@lru_cache
def _providers() -> list[dict]:
    return json.loads((CONFIG_DIR / "providers.json").read_text(encoding="utf-8"))


def _origin(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


def motol_base(settings: Settings | None = None) -> str:
    return (settings or get_settings()).iris_fhir_base.rstrip("/")


def hospitals(settings: Settings | None = None) -> list[Hospital]:
    """Simulated partner hospitals (providers with their own `fhir_base`; Motol itself is excluded)."""
    origin = _origin(motol_base(settings))
    motol_path = next((p.get("fhir_base") for p in _providers() if p["id"] == "motol"), "/fhir/r4")
    return [
        Hospital(p["id"], p["name"], origin + p["fhir_base"].rstrip("/"))
        for p in _providers()
        if p.get("fhir_base") and p["fhir_base"] != motol_path
    ]


def provider(provider_id: str) -> dict | None:
    return next((p for p in _providers() if p["id"] == provider_id), None)


def make_client(settings: Settings | None = None, base: str | None = None) -> httpx.Client:
    return fhir_client(base or motol_base(settings), settings)


def request(client: httpx.Client, method: str, url: str, retries: int = 3, **kwargs: Any) -> httpx.Response:
    """One HTTP call; retries on transport errors and 429/5xx."""
    for attempt in range(retries + 1):
        last = attempt == retries
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            if last:
                raise HospitalError(f"FHIR endpoint unreachable: {type(exc).__name__}") from exc
        else:
            if resp.status_code not in _RETRY_STATUS or last:
                return resp
        time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable")


def search_bundle(client: httpx.Client, base: str, resource_type: str, params: list[tuple[str, str]]) -> list[dict]:
    """All `match` entries of a search, following `next` links."""
    out: list[dict] = []
    resp = request(client, "GET", f"{base}/{resource_type}", params=[*params, ("_count", "200")])
    while True:
        if resp.status_code >= 300:
            raise HospitalError(f"FHIR search {resource_type} failed: HTTP {resp.status_code}")
        bundle = resp.json()
        out += [e["resource"] for e in bundle.get("entry", [])
                if e.get("search", {}).get("mode", "match") == "match" and "resource" in e]
        nxt = next((link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"), None)
        if not nxt:
            return out
        resp = request(client, "GET", nxt)


def date_window(target: PartialDate | None, tolerance_days: int = 3) -> tuple[date, date] | None:
    """Search window of a cited date: day precision -> +-3 days, month -> the month, year -> the year."""
    if target is None:
        return None
    if target.precision == "day":
        d = target.as_date()
        return d - timedelta(days=tolerance_days), d + timedelta(days=tolerance_days)
    return target.as_date(), target.end_date()


def representative_date(target: PartialDate) -> date:
    """The date a synthetic study gets for a cited date: exact day, else mid-month / mid-year."""
    if target.precision == "day":
        return target.as_date()
    if target.precision == "month":
        return date(target.year, target.month, 15)
    return date(target.year, 7, 1)


def search_imaging_studies(
    client: httpx.Client | None, hospital: Hospital, patient_id: str, modality: str | None,
    window: tuple[date, date] | None
) -> list[dict]:
    """`ImagingStudy?subject=Patient/<id>&started=ge..&started=le..` (modality filtered client side).

    The modality filter is applied here as well as on the server because partner systems code PET and
    radiograph studies differently (PT/PET, CR/DX).
    """
    params: list[tuple[str, str]] = [("subject", f"Patient/{patient_id}")]
    if window:
        params += [("started", f"ge{window[0].isoformat()}"), ("started", f"le{window[1].isoformat()}")]
    found = search_bundle(client or make_client(base=hospital.base_url), hospital.base_url, "ImagingStudy", params)
    if not modality or modality in ("UNKNOWN", "OTHER"):
        return found
    return [r for r in found if _study_modality(r) in (modality, None)]


def _study_modality(study: dict) -> str | None:
    for coding in study.get("modality", []):
        code = pipeline_modality(coding.get("code"))
        if code:
            return code
    return None
