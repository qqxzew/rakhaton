"""Check that DICOM C-FIND results agree with the dataset flags and the hospital FHIR endpoints (T087).

For the demo and review patients (saved pipeline results):
 1. every internal required study: C-FIND at MOTOL vs the dataset PACS flag
    (found <=> flag yes; flag no must be absent; unknown flag must be absent too);
 2. every `not_found` required reference: the AE that answers C-FIND vs the hospital that holds the study
    in the FHIR endpoints (same seed), including the ones nobody holds.
Output is counts only.

    uv run python scripts/check_dicom.py [--client iris|pynetdicom]
"""

from __future__ import annotations

import argparse
import sys

from app.exchange.dicom import IrisCFindClient, PynetdicomCFindClient
from app.pipeline.availability_dicom import DicomAvailabilityAdapter
from app.pipeline.availability_fhir import FhirHospitalAdapter
from app.pipeline.schemas import CaseCheckResult
from scripts.seed_hospitals import result_files


def dicom_vs_flag(results: list[CaseCheckResult], dicom: DicomAvailabilityAdapter) -> tuple[int, int, list[str]]:
    total = agree = 0
    problems: list[str] = []
    for result in results:
        studies = {s.id: s for s in result.timeline.studies}
        for item in result.items:
            study = studies.get(item.study_id or "")
            if study is None or study.source != "internal":
                continue
            total += 1
            got = dicom.check(study, None)
            expected = {"yes": "available", "no": "not_in_pacs", "unknown": "unknown"}[study.pacs_flag]
            # an unknown flag is not stored in the simulated PACS: C-FIND finds nothing -> stays unknown
            if got == expected:
                agree += 1
            else:
                problems.append(f"flag={study.pacs_flag} cfind={got}")
    return total, agree, problems


def holders(results: list[CaseCheckResult], adapter) -> dict[str, str | None]:
    """item key -> holding site id found by the adapter (None = nobody)."""
    found: dict[str, str | None] = {}
    for result in results:
        refs = {r.id: r for r in result.references}
        todo = [i for i in result.items if i.availability == "not_found"]
        for item in todo:
            ref = refs.get(item.reference_id or "")
            if ref:
                adapter.check(None, ref)
        enriched, _ = adapter.enrich(todo)
        for original, new in zip(todo, enriched, strict=True):
            located = new.located_by is not None
            found[f"{result.patient_id}|{original.id}"] = new.holding_site_id if located else None
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["iris", "pynetdicom"], default="iris")
    args = parser.parse_args(argv)
    client = IrisCFindClient() if args.client == "iris" else PynetdicomCFindClient()
    results = result_files()
    print(f"patients checked: {len(results)} (C-FIND client: {args.client})")

    total, agree, problems = dicom_vs_flag(results, DicomAvailabilityAdapter(client=client))
    print(f"internal required studies: {total}, C-FIND agrees with dataset flag: {agree}, differs: {total - agree}")
    for p in problems:
        print(f"  differs: {p}")

    via_dicom = holders(results, DicomAvailabilityAdapter(client=client))
    via_fhir = holders(results, FhirHospitalAdapter())
    same = sum(1 for k, v in via_fhir.items() if via_dicom.get(k) == v)
    located = sum(1 for v in via_dicom.values() if v)
    print(f"not_found references: {len(via_fhir)}, located by C-FIND: {located}, "
          f"found by FHIR: {sum(1 for v in via_fhir.values() if v)}, nobody holds: "
          f"{sum(1 for v in via_dicom.values() if not v)}")
    print(f"same holder (C-FIND AE vs FHIR hospital): {same} of {len(via_fhir)}")
    return 0 if not problems and same == len(via_fhir) else 1


if __name__ == "__main__":
    sys.exit(main())
