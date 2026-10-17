"""Synthetic resources for the simulated partner hospitals. Template text only, never real report text."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from app.exchange.hospitals import (
    DCM,
    SIM_ACCESSION_SYSTEM,
    Hospital,
    dicom_modality,
    sim_tag,
)

REPORT_TEXT = "Simulovaná studie pro demo. Syntetický nález bez klinického obsahu."
MODALITY_LABEL = {"CT": "CT", "MR": "MR", "PET": "PET/CT", "RTG": "RTG", "SONO": "SONO", "MAMO": "MAMO",
                  "SCINT": "Scintigrafie"}


def digest(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def left_unseeded(key: str, salt: str = "", one_in: int = 5) -> bool:
    """Deterministic: roughly one reference in `one_in` is held by nobody (the "nobody has it" case)."""
    return int(digest("unseeded", salt, key), 16) % one_in == 0


def assign_hospital(key: str, candidates: list[Hospital]) -> Hospital:
    """Deterministic hash assignment of a holding hospital when the cited site is unknown."""
    return candidates[int(digest("holder", key), 16) % len(candidates)]


def study_id(hospital_id: str, key: str) -> str:
    return f"SIM-{hospital_id.upper()}-{digest(hospital_id, key)[:10]}"


def synthetic_patient(patient_id: str, tag_code: str = "simulated") -> dict[str, Any]:
    """The hospital's own Patient record: same pseudonymous id, no demographics."""
    return {"resourceType": "Patient", "id": patient_id, "meta": {"tag": [sim_tag("simulated")]}, "active": True}


def synthetic_study(
    hospital: Hospital, patient_id: str, key: str, modality: str, started: date, tag_code: str = "simulated"
) -> dict[str, Any]:
    sid = study_id(hospital.id, key)
    code = dicom_modality(modality) or "OT"
    tags = [sim_tag("simulated")] + ([sim_tag(tag_code)] if tag_code != "simulated" else [])
    return {
        "resourceType": "ImagingStudy",
        "id": sid,
        "meta": {"tag": tags},
        "identifier": [{"system": SIM_ACCESSION_SYSTEM, "value": sid}],
        "status": "available",
        "subject": {"reference": f"Patient/{patient_id}"},
        "started": started.isoformat(),
        "modality": [{"system": DCM, "code": code, "display": MODALITY_LABEL.get(modality, modality)}],
        "description": f"{MODALITY_LABEL.get(modality, modality)} (simulace, {hospital.name})",
    }


def synthetic_report(
    hospital: Hospital, patient_id: str, key: str, modality: str, started: date
) -> dict[str, Any]:
    sid = study_id(hospital.id, key)
    return {
        "resourceType": "DiagnosticReport",
        "id": f"rep-{sid}",
        "meta": {"tag": [sim_tag("simulated")]},
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "RAD"}]}],
        "code": {"text": f"{MODALITY_LABEL.get(modality, modality)} (simulace)"},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": started.isoformat(),
        "issued": f"{started.isoformat()}T12:00:00Z",
        "imagingStudy": [{"reference": f"ImagingStudy/{sid}"}],
        "conclusion": REPORT_TEXT,
    }
