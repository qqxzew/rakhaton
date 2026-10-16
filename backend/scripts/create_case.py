"""Developer helper: register a dataset patient on the next eligible materialized meeting and run the check.

Run from the backend directory:
    uv run python scripts/create_case.py --patient PAC-... [--group uro] [--run]
"""

from __future__ import annotations

import argparse
import sys

from app.app_db.models import Case
from app.app_db.repositories import create_case as insert_case
from app.app_db.repositories import ensure_meetings, find_case
from app.app_db.session import init_db, session_scope
from app.config import today
from app.fhir_store.factory import get_store
from app.llm.client import GatewayBackend, StructuredLlm
from app.pipeline.run import run_case_check
from app.scheduling.eligibility import eligible_meetings
from app.scheduling.meetings import group_for_codes


def create_case(patient_id: str, group_id: str | None = None) -> str:
    """Case id of the patient on the soonest meeting that accepts the group (created if missing)."""
    if group_id is None:
        bundle = get_store().conditions(patient_id)
        codes = [c["code"] for cond in bundle for c in cond.get("code", {}).get("coding", []) if c.get("code")]
        group_id = group_for_codes(codes)
    with session_scope() as db:
        ensure_meetings(db, today())
        meetings = eligible_meetings(db, group_id, today(), today())
        if not meetings:
            raise SystemExit(f"no upcoming meeting accepts group {group_id!r}")
        existing: Case | None = find_case(db, patient_id, meetings[0].id)
        if existing:
            return existing.id
        return insert_case(db, patient_id=patient_id, meeting_id=meetings[0].id, group_id=group_id).id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient", required=True)
    parser.add_argument("--group", default=None, help="diagnosis group id (default: from the patient's conditions)")
    parser.add_argument("--run", action="store_true", help="run the check now (uses the real LLM)")
    args = parser.parse_args()
    init_db()
    case_id = create_case(args.patient, args.group)
    print(f"case id: {case_id}", file=sys.stderr)
    if args.run:
        result = run_case_check(case_id, get_store(), StructuredLlm(GatewayBackend()))
        print("check failed" if result is None else f"readiness: {result.readiness}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
