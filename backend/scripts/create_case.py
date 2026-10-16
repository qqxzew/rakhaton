"""Developer helper: register a dataset patient on a placeholder meeting and run the check.

Used until US2 adds real scheduling. Run from the backend directory:
    uv run python scripts/create_case.py --patient PAC-... [--run]
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from app.app_db.models import Case, Meeting
from app.app_db.session import init_db, session_scope
from app.config import today
from app.fhir_store.factory import get_store
from app.llm.client import GatewayBackend, StructuredLlm
from app.pipeline.run import run_case_check

PLACEHOLDER_MEETING_ID = "MDT-DEV-PLACEHOLDER"


def ensure_placeholder_meeting() -> str:
    with session_scope() as db:
        if db.get(Meeting, PLACEHOLDER_MEETING_ID) is None:
            db.add(Meeting(
                id=PLACEHOLDER_MEETING_ID, date=today() + timedelta(days=2), time="10:00",
                label="Vývojový MDT (placeholder)", eligible_groups=[], accepts_registrations=True,
            ))
    return PLACEHOLDER_MEETING_ID


def create_case(patient_id: str) -> str:
    meeting_id = ensure_placeholder_meeting()
    case_id = f"CASE-{patient_id}"
    with session_scope() as db:
        exists = db.query(Case).filter_by(patient_id=patient_id, meeting_id=meeting_id).first()
        if exists:
            return exists.id
        db.add(Case(id=case_id, patient_id=patient_id, meeting_id=meeting_id))
    return case_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient", required=True)
    parser.add_argument("--run", action="store_true", help="run the check now (uses the real LLM)")
    args = parser.parse_args()
    init_db()
    case_id = create_case(args.patient)
    print(f"case id: {case_id}", file=sys.stderr)
    if args.run:
        result = run_case_check(case_id, get_store(), StructuredLlm(GatewayBackend()))
        print("check failed" if result is None else f"readiness: {result.readiness}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
