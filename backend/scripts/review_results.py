"""Summarize pipeline JSON files from data/review/ and verify that every quote is in its source.

Prints counts only (no report text). Patient ids are hidden unless --show-ids is given.
    uv run python scripts/review_results.py [--dir data/review] [--show-ids]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from app.config import get_settings
from app.fhir_store.factory import get_store
from app.pipeline.schemas import CaseCheckResult
from app.pipeline.timeline import build_documents, build_studies


def source_texts(store, patient_id: str) -> dict[str, str]:
    _, report_docs = build_studies(store, patient_id)
    return {d.id: d.text for d in report_docs + build_documents(store, patient_id)}


def check(store, result: CaseCheckResult) -> tuple[int, int]:
    texts = source_texts(store, result.patient_id)
    evidences = [r.evidence for r in result.references]
    evidences += [i.evidence for i in result.items if i.evidence]
    if result.planned_exam:
        evidences.append(result.planned_exam.evidence)
    bad = sum(1 for e in evidences if e.doc_id not in texts or texts[e.doc_id].find(e.quote) < 0)
    return len(evidences), bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(get_settings().data_dir / "review"))
    parser.add_argument("--show-ids", action="store_true")
    args = parser.parse_args()
    store = get_store()
    total_bad = 0
    for index, path in enumerate(sorted(Path(args.dir).glob("*.json")), 1):
        result = CaseCheckResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
        n, bad = check(store, result)
        total_bad += bad
        states = Counter(i.state for i in result.items)
        avail = Counter(i.availability for i in result.items)
        planned = result.planned_exam
        label = result.patient_id if args.show_ids else f"P{index}"
        planned_text = "-" if not planned else (
            f"{planned.modality}/{planned.kind}/date={bool(planned.date)}/site={bool(planned.site_text)}")
        print(
            f"{label}: studies={len(result.timeline.studies)} refs={len(result.references)} "
            f"matched={sum(1 for r in result.references if r.matched_study_id)} "
            f"flagged={sum(1 for r in result.references if r.flags)} planned={planned_text} "
            f"items={dict(states)} availability={dict(avail)} readiness={result.readiness} "
            f"issues={[i.type for i in result.open_issues]} quotes={n} quotes_not_in_source={bad}"
        )
    print(f"quotes not found in source: {total_bad}", file=sys.stderr)
    return 1 if total_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
