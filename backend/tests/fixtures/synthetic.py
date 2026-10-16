"""Hand-written synthetic data. Nothing here comes from the real dataset."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from app.llm.client import LlmBackend

PATIENT = "PAC-TEST-0001"

REPORT_1 = "CT hrudníku, břicha a pánve\nBez srovnávacího vyšetření.\nZávěr: stacionární nález."
REPORT_2 = (
    "CT hrudníku, břicha a pánve\n"
    "Ve srovnání s CT z 10. 3. 2025 beze změn. Srovnáno s PET/CT z NNH ze dne 12. 5. 2025.\n"
    "Závěr: bez progrese."
)
REPORT_3 = "MR pánve\nBez srovnání s dřívějším vyšetřením.\nZávěr: bez nálezu."
NOTE = "Pacient v dobrém stavu. Kontrolní CT hrudníku, břicha a pánve za 3 měsíce. Další kontrola onkologie."
MDT_NOTE = "Onkologie MDT\nZávěr MDT: pokračovat v léčbě."


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def imaging_study(sid: str, started: str, modality: str, pacs: bool | None) -> dict:
    res = {
        "resourceType": "ImagingStudy", "id": sid, "status": "available",
        "subject": {"reference": f"Patient/{PATIENT}"},
        "identifier": [{"system": "urn:test", "value": sid}],
        "started": f"{started}T00:00:00+02:00",
        "modality": [{"system": "urn:test", "code": modality, "display": f"Test pracoviště {modality}"}],
    }
    if pacs is not None:
        res["extension"] = [{
            "url": "urn:test/StructureDefinition/dostupnost-pacs",
            "extension": [{"url": "dostupne", "valueBoolean": pacs}, {"url": "zdroj", "valueString": "test"}],
        }]
    return res


def radiology_report(sid: str, effective: str, text: str) -> dict:
    return {
        "resourceType": "DiagnosticReport", "id": f"rep-{sid}", "status": "final",
        "category": [{"coding": [{"system": "urn:test", "code": "RAD"}]}],
        "code": {"coding": [{"system": "urn:test", "code": "18748-4"}]},
        "subject": {"reference": f"Patient/{PATIENT}"},
        "effectiveDateTime": f"{effective}T00:00:00+02:00",
        "conclusion": text,
        "presentedForm": [{"contentType": "text/plain", "data": b64(text)}],
    }


def document(doc_id: str, date: str, text: str, loinc: str = "34109-9", extra_display: str | None = None) -> dict:
    coding = [{"system": "http://loinc.org", "code": loinc, "display": "Note"}]
    if extra_display:
        coding.append({"system": "urn:test", "code": "X", "display": extra_display})
    return {
        "resourceType": "DocumentReference", "id": doc_id, "status": "current",
        "type": {"coding": coding}, "subject": {"reference": f"Patient/{PATIENT}"},
        "date": f"{date}T00:00:00+02:00",
        "content": [{"attachment": {"contentType": "text/plain", "data": b64(text),
                                    "size": len(text.encode("utf-8"))}}],
        "custodian": {"display": "Test oddělení"},
    }


def synthetic_bundle() -> dict:
    entries = [
        {"resource": {"resourceType": "Patient", "id": PATIENT, "gender": "male", "birthDate": "1960"}},
        {"resource": {"resourceType": "Condition", "id": "cond-1", "subject": {"reference": f"Patient/{PATIENT}"},
                      "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "C61"}]}}},
        {"resource": imaging_study("STU-TEST-0001", "2025-03-10", "CT", True)},
        {"resource": imaging_study("STU-TEST-0002", "2025-09-02", "CT", False)},
        {"resource": imaging_study("STU-TEST-0003", "2026-01-14", "MR", None)},
        {"resource": radiology_report("STU-TEST-0001", "2025-03-10", REPORT_1)},
        {"resource": radiology_report("STU-TEST-0002", "2025-09-02", REPORT_2)},
        {"resource": radiology_report("STU-TEST-0003", "2026-01-14", REPORT_3)},
        {"resource": document("DOC-TEST-0001", "2026-02-10", NOTE)},
        {"resource": document("DOC-TEST-0002", "2025-10-01", MDT_NOTE, "11488-4", "Onkologie MDT test")},
        {"resource": {
            "resourceType": "MedicationAdministration", "id": "med-1", "status": "completed",
            "subject": {"reference": f"Patient/{PATIENT}"}, "effectiveDateTime": "2025-04-01T00:00:00+02:00",
            "medicationCodeableConcept": {"coding": [{"system": "http://www.whocc.no/atc", "code": "L02AE02"}]},
        }},
    ]
    return {"resourceType": "Bundle", "id": PATIENT, "type": "transaction", "entry": entries}


def write_bundle(fhir_dir: Path, bundle: dict | None = None) -> None:
    bundle = bundle or synthetic_bundle()
    fhir_dir.mkdir(parents=True, exist_ok=True)
    (fhir_dir / f"{bundle['id']}.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")


class ScriptedBackend(LlmBackend):
    """Returns canned JSON chosen by a substring of the user message; records every call."""

    def __init__(self, priors: dict[str, dict] | None = None, planned: dict[str, dict] | None = None):
        self.priors = priors or {}
        self.planned = planned or {}
        self.calls: list[tuple[str, str]] = []

    def complete(self, model: str, messages: list[dict], max_tokens: int, json_mode: bool) -> str:
        system, user = messages[0]["content"], messages[1]["content"]
        kind = "priors" if "PRIOR imaging" in system else "planned"
        self.calls.append((kind, model))
        table = self.priors if kind == "priors" else self.planned
        for needle, payload in table.items():
            if needle in user:
                return json.dumps(payload, ensure_ascii=False)
        return json.dumps({"references": []} if kind == "priors" else {"planned": []})


def default_backend() -> ScriptedBackend:
    return ScriptedBackend(
        priors={
            "Srovnáno s PET/CT z NNH": {"references": [
                {"modality": "CT", "regions": ["chest", "abdomen", "pelvis"], "date_text": "10. 3. 2025",
                 "date_iso": "2025-03-10", "site_text": None,
                 "quote": "Ve srovnání s CT z 10. 3. 2025 beze změn.", "confidence": 0.95},
                {"modality": "PET/CT", "regions": [], "date_text": "12. 5. 2025", "date_iso": "2025-05-12",
                 "site_text": "NNH", "quote": "Srovnáno s PET/CT z NNH ze dne 12. 5. 2025.", "confidence": 0.9},
                {"modality": "CT", "regions": [], "date_text": "1. 1. 2024", "date_iso": "2024-01-01",
                 "site_text": None, "quote": "Tato věta v nálezu vůbec není.", "confidence": 0.9},
            ]},
        },
        planned={
            "Kontrolní CT hrudníku": {"planned": [
                {"modality": "CT", "regions": ["chest", "abdomen", "pelvis"], "date_iso": None,
                 "relative": {"value": 3, "unit": "months"}, "site_text": None, "kind": "imaging",
                 "quote": "Kontrolní CT hrudníku, břicha a pánve za 3 měsíce.", "confidence": 0.9},
            ]},
        },
    )
