"""Assemble a per-patient timeline from FHIR resources."""

from __future__ import annotations

import base64
import binascii
import re
from datetime import date

from app.fhir_store.base import FhirStore, Resource
from app.pipeline.normalize import (
    fold,
    normalize_modality,
    report_headline,
    study_regions_from_report,
)
from app.pipeline.schemas import SourceDoc, Study, Timeline, TreatmentMilestones

PACS_EXTENSION = "dostupnost-pacs"
NOTE_LOINC = {"34109-9", "11488-4", "34108-1", "34111-5", "18842-5", "11504-8"}
PRESCRIPTION_LOINC = "57833-6"
SURGICAL_NOTE_LOINC = "11504-8"

_RT = re.compile(r"radioterap|ozarov|ozareni|brachyter|\brt\b")
_SURGERY = re.compile(r"operac|resekc|excize|exstirpac|ektomi|amputac|laparotom|torakotom")


def to_date(value: str | None) -> date | None:
    if not value or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def decode_attachment(resource: Resource, field: str = "content") -> str:
    """Full text of a DocumentReference (content) or DiagnosticReport (presentedForm)."""
    entries = resource.get(field) or []
    for entry in entries:
        attachment = entry.get("attachment", entry)
        data = attachment.get("data")
        if not data:
            continue
        try:
            return base64.b64decode(data).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            continue
    return ""


def report_text(report: Resource) -> str:
    return report.get("conclusion") or decode_attachment(report, "presentedForm")


def _coding(resource: Resource, key: str) -> list[dict]:
    return (resource.get(key) or {}).get("coding") or []


def _study_id(study: Resource) -> str:
    for ident in study.get("identifier", []):
        if ident.get("value"):
            return ident["value"]
    return study["id"]


def _pacs(study: Resource) -> tuple[str, str | None]:
    for ext in study.get("extension", []):
        if ext.get("url", "").endswith(PACS_EXTENSION):
            values = {e.get("url"): e for e in ext.get("extension", [])}
            flag = values.get("dostupne", {}).get("valueBoolean")
            source = values.get("zdroj", {}).get("valueString")
            return ("yes" if flag else "no" if flag is False else "unknown"), source
    return "unknown", None


def build_studies(store: FhirStore, patient_id: str) -> tuple[list[Study], list[SourceDoc]]:
    reports = {r["id"]: r for r in store.radiology_reports(patient_id)
               if any(c.get("code") == "RAD" for cat in r.get("category", []) for c in cat.get("coding", []))}
    studies: list[Study] = []
    docs: list[SourceDoc] = []
    for res in store.imaging_studies(patient_id):
        sid = _study_id(res)
        study_date = to_date(res.get("started"))
        if study_date is None:
            continue
        report = reports.get(f"rep-{sid}")
        text = report_text(report) if report else ""
        modality_coding = (res.get("modality") or [{}])[0]
        modality = normalize_modality(modality_coding.get("code"))
        if modality == "UNKNOWN" and text:
            modality = normalize_modality(report_headline(text))
        flag, source = _pacs(res)
        studies.append(Study(
            id=sid, patient_id=patient_id, date=study_date, modality=modality,
            regions=study_regions_from_report(text, modality) if text else [],
            site=modality_coding.get("display"), pacs_flag=flag, pacs_source=source,
            report_id=report["id"] if report else None,
            headline=report_headline(text) if text else None,
        ))
        if report:
            docs.append(SourceDoc(
                id=report["id"], kind="radiology_report",
                date=to_date(report.get("effectiveDateTime")) or study_date, text=text,
                department=modality_coding.get("display"), type_label="Radiologický nález",
            ))
    studies.sort(key=lambda s: (s.date, s.id))
    return studies, docs


def _doc_kind(resource: Resource, text: str) -> str:
    codes = {c.get("code") for c in _coding(resource, "type")}
    displays = " ".join(fold(c.get("display") or "") for c in _coding(resource, "type"))
    if "mdt" in displays or text.lstrip().lower().startswith("onkologie mdt") or "závěr mdt" in text.lower():
        return "mdt"
    if PRESCRIPTION_LOINC in codes:
        return "other"
    if codes & NOTE_LOINC:
        return "clinical_note"
    return "other"


def build_documents(store: FhirStore, patient_id: str) -> list[SourceDoc]:
    seen: set[tuple] = set()
    docs: list[SourceDoc] = []
    for res in store.clinical_documents(patient_id):
        text = decode_attachment(res)
        if not text.strip():
            continue
        doc_date = to_date(res.get("date"))
        type_codes = tuple(c.get("code") for c in _coding(res, "type"))
        key = (doc_date, type_codes, text[:300])
        if key in seen:
            continue
        seen.add(key)
        label = next((c.get("display") for c in _coding(res, "type")[1:] if c.get("display")), None) \
            or next((c.get("display") for c in _coding(res, "type") if c.get("display")), None)
        docs.append(SourceDoc(
            id=res["id"], kind=_doc_kind(res, text), date=doc_date, text=text,
            department=(res.get("custodian") or {}).get("display"), type_label=label,
        ))
    docs.sort(key=lambda d: (d.date or date.min, d.id))
    return docs


def _atc(resource: Resource) -> str | None:
    for c in (resource.get("medicationCodeableConcept") or {}).get("coding", []):
        if c.get("system", "").endswith("atc"):
            return c.get("code")
    return None


def build_treatment(store: FhirStore, patient_id: str, docs: list[SourceDoc]) -> TreatmentMilestones:
    systemic: list[date] = []
    surgery: list[date] = []
    rt: list[date] = []
    for res in store.resources(patient_id, "MedicationAdministration") + \
            store.resources(patient_id, "MedicationRequest"):
        atc = _atc(res) or ""
        d = to_date(res.get("effectiveDateTime") or res.get("authoredOn"))
        if d and atc.startswith(("L01", "L02")):
            systemic.append(d)
    for res in store.resources(patient_id, "Procedure"):
        d = to_date(res.get("performedDateTime"))
        display = fold(" ".join(c.get("display") or "" for c in _coding(res, "code")))
        if not d or not display:
            continue
        if _RT.search(display):
            rt.append(d)
        elif _SURGERY.search(display):
            surgery.append(d)
    for doc in docs:
        if not doc.date:
            continue
        if doc.type_label and "radioterap" in fold(doc.type_label):
            rt.append(doc.date)
        if doc.type_label and "operac" in fold(doc.type_label):
            surgery.append(doc.date)
    used = []
    if systemic:
        used.append("systemic therapy: administrations/prescriptions with ATC L01 or L02")
    if surgery:
        used.append("surgery: procedure or operation-note labels")
    if rt:
        used.append("radiotherapy: procedure or radiotherapy prescription labels")
    firsts = [min(x) for x in (systemic, surgery, rt) if x]
    return TreatmentMilestones(
        first_systemic=min(systemic) if systemic else None,
        last_systemic=max(systemic) if systemic else None,
        first_surgery=min(surgery) if surgery else None,
        first_radiotherapy=min(rt) if rt else None,
        first_treatment=min(firsts) if firsts else None,
        used=used,
    )


def build_timeline(store: FhirStore, patient_id: str) -> Timeline:
    studies, report_docs = build_studies(store, patient_id)
    note_docs = build_documents(store, patient_id)
    patients = store.resources(patient_id, "Patient")
    patient = patients[0] if patients else {}
    birth = (patient.get("birthDate") or "")[:4]
    diagnoses = sorted({
        c["code"] for cond in store.conditions(patient_id) for c in _coding(cond, "code") if c.get("code")
    })
    all_docs = sorted(report_docs + note_docs, key=lambda d: (d.date or date.min, d.id))
    return Timeline(
        patient_id=patient_id, studies=studies, documents=all_docs,
        mdt_dates=sorted({d.date for d in note_docs if d.kind == "mdt" and d.date}),
        treatment=build_treatment(store, patient_id, note_docs),
        diagnoses=diagnoses, sex=patient.get("gender"),
        birth_year=int(birth) if birth.isdigit() else None,
        birth_band=next((x.get("valueString") for x in patient.get("extension", [])
                         if str(x.get("url", "")).endswith("/rok-narozeni-pasmo")), None),
    )
