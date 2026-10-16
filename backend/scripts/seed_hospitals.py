"""Seed the simulated partner hospitals (IRIS FHIR endpoints) with synthetic studies (T078).

For the demo patients (data/demo_patients.json) and the review patients (data/review/*.json) the
pipeline's required items that are `not_found` (cited in a radiology report, absent from Motol) get a
synthetic Patient + ImagingStudy + DiagnosticReport in the endpoint of the holding hospital:
 - the cited site decides the hospital when it matches a hospital endpoint;
 - otherwise the hospital is assigned by hash and labeled `simulated-holding-site`;
 - about one in five references is deliberately left unseeded ("nobody has it").
Everything is tagged urn:pacs-comparator:simulation|simulated and uses template report text only.
Nothing is ever written to the Motol endpoint. Output is counts only.

    uv run python scripts/seed_hospitals.py [--dry-run] [--salt X] [--one-in 5]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date

import httpx

from app.config import get_settings
from app.exchange.hospitals import (
    FHIR_JSON,
    SIM_SYSTEM,
    Hospital,
    HospitalError,
    hospitals,
    make_client,
    motol_base,
    representative_date,
    request,
)
from app.exchange.synthetic import (
    assign_hospital,
    left_unseeded,
    synthetic_patient,
    synthetic_report,
    synthetic_study,
)
from app.pipeline.gaps import resolve_site
from app.pipeline.schemas import CaseCheckResult, PartialDate


def result_files() -> list[CaseCheckResult]:
    """Saved pipeline results of the demo and review patients (run_review.py writes them)."""
    data_dir = get_settings().data_dir
    results: list[CaseCheckResult] = []
    for path in sorted((data_dir / "review").glob("*.json")):
        results.append(CaseCheckResult.model_validate_json(path.read_text(encoding="utf-8")))
    return results


def missing_references(result: CaseCheckResult) -> list[dict]:
    """not_found items with what a synthetic study needs: key, modality, cited date, cited site text."""
    refs = {r.id: r for r in result.references}
    out: list[dict] = []
    for item in result.items:
        if item.availability != "not_found":
            continue
        ref = refs.get(item.reference_id or "")
        target: PartialDate | None = (ref.ref_date if ref else None) or item.target_date
        if target is None:
            continue
        out.append({"key": f"{result.patient_id}|{item.reference_id or item.id}",
                    "patient_id": result.patient_id, "modality": ref.modality if ref else item.modality,
                    "target": target, "site_text": ref.site_text if ref else None})
    return out


def put(client: httpx.Client, base: str, resource: dict) -> None:
    url = f"{base}/{resource['resourceType']}/{resource['id']}"
    resp = request(client, "PUT", url, json=resource, headers={"Content-Type": FHIR_JSON})
    if resp.status_code >= 300:
        raise HospitalError(f"PUT {resource['resourceType']} failed: HTTP {resp.status_code}")


def count(client: httpx.Client, base: str, resource_type: str, tagged: bool = False) -> int:
    params = {"_summary": "count"}
    if tagged:
        params["_tag"] = f"{SIM_SYSTEM}|simulated"
    resp = request(client, "GET", f"{base}/{resource_type}", params=params)
    if resp.status_code >= 300:
        raise HospitalError(f"count {resource_type} failed: HTTP {resp.status_code}")
    return int(resp.json().get("total", 0))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--salt", default="e", help="changes which references stay unseeded")
    parser.add_argument("--one-in", type=int, default=5, help="leave 1 of N references unseeded")
    args = parser.parse_args(argv)

    targets = hospitals()
    if not targets:
        raise SystemExit("no providers with fhir_base in config/providers.json")
    by_id = {h.id: h for h in targets}
    client = make_client()

    planned: list[tuple[Hospital, dict, str]] = []  # (hospital, reference, tag code)
    unseeded = 0
    total = 0
    for result in result_files():
        for ref in missing_references(result):
            total += 1
            if left_unseeded(ref["key"], args.salt, args.one_in):
                unseeded += 1
                continue
            site_id, _ = resolve_site(ref["site_text"])
            if site_id in by_id:
                planned.append((by_id[site_id], ref, "simulated"))
            else:
                planned.append((assign_hospital(ref["key"], targets), ref, "simulated-holding-site"))

    per_hospital: Counter[str] = Counter()
    for hospital, ref, tag in planned:
        per_hospital[hospital.id] += 1
        if args.dry_run:
            continue
        started: date = representative_date(ref["target"])
        pid = ref["patient_id"]
        put(client, hospital.base_url, synthetic_patient(pid, tag))
        put(client, hospital.base_url, synthetic_study(hospital, pid, ref["key"], ref["modality"], started, tag))
        put(client, hospital.base_url, synthetic_report(hospital, pid, ref["key"], ref["modality"], started))

    print(f"not_found references: {total}, seeded: {len(planned)}, left unseeded on purpose: {unseeded}"
          f"{' (dry run)' if args.dry_run else ''}")
    if args.dry_run:
        for hid, n in sorted(per_hospital.items()):
            print(f"  planned {hid}: {n}")
        return 0
    for h in targets:
        print(f"  {h.id:8s} {h.base_url}: Patient={count(client, h.base_url, 'Patient')} "
              f"ImagingStudy={count(client, h.base_url, 'ImagingStudy')} "
              f"(simulated-tagged {count(client, h.base_url, 'ImagingStudy', tagged=True)}) "
              f"DiagnosticReport={count(client, h.base_url, 'DiagnosticReport')}")
    motol = motol_base()
    leaked = count(client, motol, "ImagingStudy", tagged=True)
    print(f"  motol    {motol}: simulated-tagged ImagingStudy={leaked} (must be 0)")
    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(main())
