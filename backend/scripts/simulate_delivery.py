"""Demo: a simulated hospital delivers a requested study to Motol through IHE MHD (ITI-65) (T080).

Takes a required item (id from the pipeline result), locates the holding hospital with FHIR search
(T079), lets that hospital POST a Provide Document Bundle to Motol's FHIR endpoint in IRIS and then
finds the delivery again by request id. Prints ids, HTTP status and study metadata, no patient data.

    uv run python scripts/simulate_delivery.py --item ITEM-... [--request-id PACS-REQ-000123]
    uv run python scripts/simulate_delivery.py --list      # items that can be delivered
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date

from app.config import get_settings
from app.exchange.hospitals import HospitalError, make_client, provider, request
from app.exchange.mhd import DeliveryRequest, find_delivery, provide_document_bundle
from app.pipeline.availability_fhir import FhirHospitalAdapter
from app.pipeline.schemas import CaseCheckResult, RequiredItem


def load_results() -> list[CaseCheckResult]:
    folder = get_settings().data_dir / "review"
    return [CaseCheckResult.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


def locate(result: CaseCheckResult, item: RequiredItem) -> RequiredItem | None:
    """Run the FHIR hospital lookup for one item; None when no hospital holds the study."""
    ref = next((r for r in result.references if r.id == item.reference_id), None)
    if ref is None or item.availability != "not_found":
        return None
    adapter = FhirHospitalAdapter()
    adapter.check(None, ref)
    located, _ = adapter.enrich([item])
    return located[0] if located[0].located_by else None


def request_id_for(item_id: str) -> str:
    return f"PACS-REQ-{int(hashlib.sha1(item_id.encode()).hexdigest(), 16) % 900000 + 100000}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item", help="required item id (ITEM-...)")
    parser.add_argument("--request-id", help="default: derived from the item id")
    parser.add_argument("--list", action="store_true", help="list deliverable items and exit")
    args = parser.parse_args(argv)

    results = load_results()
    candidates: list[tuple[CaseCheckResult, RequiredItem, RequiredItem]] = []
    for result in results:
        for item in result.items:
            located = locate(result, item)
            if located:
                candidates.append((result, item, located))
    if args.list or not args.item:
        for _, item, located in candidates:
            print(f"{item.id}  {item.modality:5s} -> {located.holding_site_id}")
        return 0

    match = next(((r, i, loc) for r, i, loc in candidates if i.id == args.item), None)
    if match is None:
        print("item not found or not held by any simulated hospital", file=sys.stderr)
        return 2
    result, item, located = match
    hospital_provider = provider(located.holding_site_id or "")
    client = make_client()

    study = request(client, "GET", located.provider_study_ref or "").json()
    study_date = date.fromisoformat(str(study["started"])[:10])
    req = DeliveryRequest(
        request_id=args.request_id or request_id_for(item.id), patient_id=result.patient_id,
        modality=item.modality, study_date=study_date, provider_study_ref=located.provider_study_ref or "",
    )
    try:
        response = provide_document_bundle(hospital_provider, req, client=client)
        delivery = find_delivery(req.request_id, client=client)
    except HospitalError as exc:
        print(f"delivery failed: {exc}", file=sys.stderr)
        return 1
    statuses = [e.get("response", {}).get("status") for e in response.get("entry", [])]
    print(f"provider: {located.holding_site_id} ({located.holding_site_name}, simulace)")
    print(f"request: {req.request_id}")
    print(f"ITI-65 bundle accepted: HTTP {response.get('_http_status')}, entry statuses {statuses}")
    if delivery is None:
        print("find_delivery: NOT FOUND", file=sys.stderr)
        return 1
    print(f"find_delivery: DocumentReference/{delivery.document_id}, SubmissionSet List/{delivery.submission_set_id}")
    print(f"  referenced study: {delivery.modality} {delivery.study_date} at {delivery.provider_id}")
    ok = delivery.modality == item.modality and delivery.study_date == study_date
    print("  matches request:", "yes" if ok else "NO")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
