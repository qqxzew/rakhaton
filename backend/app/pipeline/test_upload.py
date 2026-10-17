"""Test radiology reports uploaded from the patient view, to show the live pipeline on new input.

An upload becomes a synthetic ImagingStudy plus its DiagnosticReport (category RAD, text in `conclusion`),
written to the FHIR store and tagged `urn:pacs-comparator:simulation|test-upload`. The normal case check then
reads it like any other report: the LLM extracts the cited priors, matching and rules run as usual.

The coordinator sees shifted dates (section 8.3), so the dates typed in the text are moved back into the
patient's own frame before storing. The template only uses dates of the patient's own studies and fixed
synthetic wording; it never copies report text.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

from app.fhir_store.base import TEST_UPLOAD_TAG, Resource
from app.pipeline.normalize import regions_overlap
from app.pipeline.schemas import PlannedExam, Study

PACS_EXT = "https://rakathon.local/fhir/StructureDefinition/dostupnost-pacs"
SITE_LABEL = "Testovací nahrání (simulace)"
_DICOM = {"CT": "CT", "MR": "MR", "PET": "PT", "RTG": "DX", "SONO": "US", "MAMO": "MG", "SCINT": "NM"}
_LABEL = {"PET": "PET/CT", "SONO": "SONO", "RTG": "RTG", "MAMO": "MAMO", "SCINT": "scintigrafie"}
_REGION_CS = {"head": "hlavy", "brain": "mozku", "neck": "krku", "chest": "hrudníku", "abdomen": "břicha",
              "pelvis": "pánve", "spine": "páteře", "extremity": "končetiny", "breast": "prsů",
              "whole_body": "celého těla"}
_DMY = re.compile(r"(?<![\d.])(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4}|\d{2})(?![\d])")
UPLOAD_MODALITIES = tuple(_DICOM)


def fmt(day: date) -> str:
    return f"{day.day}. {day.month}. {day.year}"


def shift_text_dates(text: str, days: int) -> str:
    """Move every full date written as `d. m. yyyy` / `d.m.yy` by `days`; other text stays as is."""

    def repl(m: re.Match[str]) -> str:
        year = int(m.group(3))
        year = year + 2000 if year < 100 else year
        try:
            day = date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return m.group(0)
        return fmt(day + timedelta(days=days))

    return _DMY.sub(repl, text) if days else text


def study_id_for(patient_id: str, report_date: date, text: str) -> str:
    digest = hashlib.sha1(f"{patient_id}|{report_date}|{text}".encode()).hexdigest()[:10].upper()
    return f"TEST-{digest}"


def build_resources(patient_id: str, text: str, report_date: date, modality: str) -> list[Resource]:
    """ImagingStudy + DiagnosticReport for one uploaded report (patient's own date frame)."""
    sid = study_id_for(patient_id, report_date, text)
    meta = {"tag": [{"system": TEST_UPLOAD_TAG[0], "code": TEST_UPLOAD_TAG[1], "display": SITE_LABEL},
                    {"system": TEST_UPLOAD_TAG[0], "code": "simulated"}]}
    subject = {"reference": f"Patient/{patient_id}"}
    study = {
        "resourceType": "ImagingStudy", "id": sid, "meta": meta, "status": "available", "subject": subject,
        "identifier": [{"system": "urn:pacs-comparator:test-upload", "value": sid}],
        "started": report_date.isoformat(),
        "modality": [{"system": "http://dicom.nema.org/resources/ontology/DCM",
                      "code": _DICOM.get(modality, "OT"), "display": SITE_LABEL}],
        "extension": [{"url": PACS_EXT, "extension": [
            {"url": "dostupne", "valueBoolean": True},
            {"url": "zdroj", "valueString": "testovací nahrání (simulace)"}]}],
    }
    report = {
        "resourceType": "DiagnosticReport", "id": f"rep-{sid}", "meta": meta, "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "RAD"}]}],
        "code": {"text": "Radiologický nález (testovací nahrání)"}, "subject": subject,
        "effectiveDateTime": report_date.isoformat(), "issued": f"{report_date.isoformat()}T12:00:00Z",
        "imagingStudy": [{"reference": f"ImagingStudy/{sid}"}],
        "conclusion": text,
    }
    return [study, report]


def default_report_date(studies: list[Study], reference_date: date | None, today_in_frame: date) -> date:
    """Newest report of the patient (so R1 reads it), but still before the planned exam."""
    latest = max((s.date for s in studies), default=None)
    day = max(today_in_frame, latest + timedelta(days=1)) if latest else today_in_frame
    if reference_date and day >= reference_date:
        day = reference_date - timedelta(days=1)
    return day


def _regions_cs(regions: list[str]) -> str:
    words = [_REGION_CS[r] for r in regions if r in _REGION_CS] or ["hrudníku", "břicha", "pánve"]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " a " + words[-1]


def template_text(studies: list[Study], planned: PlannedExam | None, report_date: date, offset: int) -> tuple[str, str]:
    """A synthetic report citing one internal prior and one external PET/CT, dates in the UI frame."""
    modality = planned.modality if planned and planned.modality in ("CT", "MR") else "CT"
    regions = (planned.regions if planned else []) or ["chest", "abdomen", "pelvis"]
    earlier = [s for s in studies if s.date < report_date]
    prior = (max((s for s in earlier if s.modality == modality and regions_overlap(s.regions, regions)),
                 key=lambda s: s.date, default=None)
             or max(earlier, key=lambda s: s.date, default=None))
    external = report_date - timedelta(days=150)
    shown = lambda d: fmt(d + timedelta(days=offset))  # noqa: E731
    lines = [f"{modality} {_regions_cs(regions)} s k. l. (testovací nález, syntetický text)", ""]
    if prior:
        label = _LABEL.get(prior.modality, prior.modality)
        lines.append(f"Ve srovnání s předchozím {label} z {shown(prior.date)} je nález stacionární.")
    lines.append(f"Srovnáno také s PET/CT z {shown(external)} (Nemocnice Na Homolce), "
                 "bez nových ložiskových změn.")
    lines += ["", "Závěr: Stacionární nález, bez známek progrese."]
    return "\n".join(lines), modality
