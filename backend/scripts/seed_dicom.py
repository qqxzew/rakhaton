"""Seed the simulated DICOM PACS (Orthanc, one per AE) with synthetic studies (T087).

 - MOTOL: every internal study of the demo and review patients whose PACS flag is `yes`
   (flag `no` studies are deliberately NOT stored: that is the "not in PACS" gap; unknown ones are not stored).
 - NNH / HOMOLKA / FNM: the studies seeded earlier by seed_hospitals.py into the hospital FHIR endpoints
   (tagged urn:pacs-comparator:simulation|simulated), at the matching AE.
Objects are blank (no pixel data): PatientID = pseudonym, StudyDate, Modality, AccessionNumber,
StudyDescription "Simulovaná studie". Stored through the Orthanc REST API; rerunning is idempotent.
Output is counts only.

    uv run python scripts/seed_dicom.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from collections import Counter

import httpx
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.filewriter import dcmwrite
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from app.exchange.dicom import PacsNode, nodes
from app.exchange.hospitals import (
    DICOM_MODALITY,
    SIM_SYSTEM,
    hospitals,
    make_client,
    pipeline_modality,
    search_bundle,
)
from scripts.seed_hospitals import result_files

SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
UID_ROOT = "1.2.826.0.1.3680043.8.498."  # pydicom's documented example root, never a real one


def stable_uid(*parts: str) -> str:
    digest = int(hashlib.sha1("|".join(parts).encode()).hexdigest(), 16)
    return f"{UID_ROOT}{digest % 10**30}"


def build_dicom(patient_id: str, study_date: str, modality: str, accession: str, ae: str) -> bytes:
    study_uid = stable_uid(ae, accession, "study")
    sop_uid = stable_uid(ae, accession, "sop")
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SECONDARY_CAPTURE
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = generate_uid()
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = SECONDARY_CAPTURE
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = stable_uid(ae, accession, "series")
    ds.PatientID = patient_id
    ds.PatientName = "Simulace^Pacient"
    ds.StudyDate = study_date
    ds.Modality = modality
    ds.AccessionNumber = accession[-16:]  # VR SH allows 16 characters
    ds.StudyDescription = "Simulovaná studie"
    ds.SpecificCharacterSet = "ISO_IR 192"
    buf = io.BytesIO()
    dcmwrite(buf, ds, enforce_file_format=True)
    return buf.getvalue()


def collect_motol() -> list[tuple[str, str, str, str]]:
    """(patient, YYYYMMDD, DICOM modality, accession) of internal studies with PACS flag yes."""
    out: dict[str, tuple[str, str, str, str]] = {}
    for result in result_files():
        for study in result.timeline.studies:
            code = DICOM_MODALITY.get(study.modality)
            if study.source == "internal" and study.pacs_flag == "yes" and code:
                out[study.id] = (study.patient_id, f"{study.date:%Y%m%d}", code, study.id)
    return list(out.values())


def collect_hospitals() -> dict[str, list[tuple[str, str, str, str]]]:
    """Hospital-held simulated studies from the hospital FHIR endpoints, per hospital id."""
    client = make_client()
    out: dict[str, list[tuple[str, str, str, str]]] = {}
    for hospital in hospitals():
        rows: list[tuple[str, str, str, str]] = []
        for res in search_bundle(client, hospital.base_url, "ImagingStudy", [("_tag", f"{SIM_SYSTEM}|simulated")]):
            subject = res.get("subject", {}).get("reference", "").removeprefix("Patient/")
            code = next((c.get("code") for c in res.get("modality", []) if c.get("code")), None)
            accession = next((i.get("value") for i in res.get("identifier", [])), res["id"])
            started = str(res.get("started", ""))[:10].replace("-", "")
            if subject and code and len(started) == 8 and pipeline_modality(code):
                rows.append((subject, started, code, accession))
        out[hospital.id] = rows
    return out


def store(client: httpx.Client, node: PacsNode, rows: list[tuple[str, str, str, str]]) -> int:
    stored = 0
    for patient_id, study_date, code, accession in rows:
        resp = client.post(f"{node.rest}/instances", content=build_dicom(patient_id, study_date, code, accession,
                                                                         node.ae),
                           headers={"Content-Type": "application/dicom"})
        if resp.status_code >= 300:
            raise SystemExit(f"Orthanc {node.ae}: HTTP {resp.status_code} while storing")
        stored += 1
    return stored


def study_count(client: httpx.Client, node: PacsNode) -> int:
    return len(client.get(f"{node.rest}/studies").json())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pacs = nodes()
    plan: dict[str, list[tuple[str, str, str, str]]] = {"motol": collect_motol(), **collect_hospitals()}
    skipped = Counter()
    for result in result_files():
        for study in result.timeline.studies:
            if study.source == "internal" and study.pacs_flag != "yes":
                skipped[study.pacs_flag] += 1
    for node_id, rows in plan.items():
        print(f"{pacs[node_id].ae:8s} planned studies: {len(rows)}")
    print(f"Motol studies not stored on purpose: flag no={skipped['no']}, unknown={skipped['unknown']}")
    if args.dry_run:
        return 0
    with httpx.Client(timeout=60) as client:
        for node_id, rows in plan.items():
            node = pacs[node_id]
            store(client, node, rows)
            print(f"{node.ae:8s} stored/updated {len(rows)}, studies now in Orthanc: {study_count(client, node)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
