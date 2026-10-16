"""Select demo patients (CLAUDE.md section 13) and write them to the git-ignored data/demo_patients.json.

Stage 1 scans every patient with cheap deterministic features (no language model). Stage 2 runs the real
pipeline on the best candidates (cached) and keeps those that satisfy all demo criteria. Only counts and
ids are written, never report text. Run from the backend directory:
    uv run python scripts/pick_demo_patients.py --count 5 [--no-llm]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass

from app.config import get_settings
from app.fhir_store.base import FhirStore
from app.fhir_store.factory import get_store
from app.llm.client import GatewayBackend, StructuredLlm
from app.logging import configure_logging
from app.pipeline.extract_planned import candidate_documents
from app.pipeline.normalize import fold
from app.pipeline.run import run_patient_check
from app.pipeline.timeline import build_timeline

URO_PREFIXES = ("C61", "C64", "C65", "C66", "C67")
EXTERNAL_PLAN = re.compile(
    r"(?:plan|kontrol|objedn|doporuc)[^.\n]{0,100}\b(?:nnh|homolk|vfn|ikem|bulovk|thomayer|fnm)\b"
)
DATED_COMPARISON = re.compile(r"srovn|porovn|oproti")
DATE = re.compile(r"\b\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*\d{2,4}\b")


@dataclass
class Features:
    patient_id: str
    uro: bool
    not_in_pacs_studies: int
    dated_comparison_reports: int
    plan_candidate_docs: int
    external_plan_docs: int

    @property
    def eligible(self) -> bool:
        return self.not_in_pacs_studies > 0 and self.dated_comparison_reports > 0 and self.plan_candidate_docs > 0

    @property
    def score(self) -> int:
        return (3 if self.uro else 0) + (2 if self.external_plan_docs else 0) + min(self.not_in_pacs_studies, 2) \
            + min(self.dated_comparison_reports, 2)


def scan_patient(store: FhirStore, patient_id: str) -> Features:
    timeline = build_timeline(store, patient_id)
    reports = [d for d in timeline.documents if d.kind == "radiology_report"]
    dated = 0
    for doc in reports:
        folded = fold(doc.text)
        if DATED_COMPARISON.search(folded) and DATE.search(folded):
            dated += 1
    candidates = candidate_documents(timeline.documents)
    external = sum(1 for d in candidates if EXTERNAL_PLAN.search(fold(d.text)))
    return Features(
        patient_id=patient_id,
        uro=any(code.startswith(URO_PREFIXES) for code in timeline.diagnoses),
        not_in_pacs_studies=sum(1 for s in timeline.studies if s.pacs_flag == "no"),
        dated_comparison_reports=dated,
        plan_candidate_docs=len(candidates),
        external_plan_docs=external,
    )


def verify(store: FhirStore, llm: StructuredLlm, patient_id: str) -> dict | None:
    """Run the real pipeline; None unless the demo criteria hold."""
    result = run_patient_check(patient_id, store, llm)
    gaps = [i for i in result.items if i.availability == "not_found"]
    not_in_pacs = [i for i in result.items if i.availability == "not_in_pacs"]
    if result.planned_exam is None or not gaps or not not_in_pacs:
        return None
    return {
        "patient_id": patient_id,
        "planned_modality": result.planned_exam.modality,
        "planned_external_site": bool(result.planned_exam.site_text),
        "items": len(result.items),
        "not_found": len(gaps),
        "not_in_pacs": len(not_in_pacs),
        "readiness": result.readiness,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--max-verify", type=int, default=30, help="most candidates to run the LLM on")
    parser.add_argument("--no-llm", action="store_true", help="only write stage 1 candidates")
    args = parser.parse_args()
    configure_logging()

    store = get_store()
    features = []
    ids = store.list_patient_ids()
    for index, pid in enumerate(ids, 1):
        features.append(scan_patient(store, pid))
        if index % 300 == 0:
            print(f"scanned {index}/{len(ids)}", file=sys.stderr)
    eligible = sorted((f for f in features if f.eligible), key=lambda f: (-f.score, f.patient_id))
    print(f"stage 1: {len(eligible)} eligible of {len(features)} patients", file=sys.stderr)

    out_path = get_settings().data_dir / "demo_patients.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.no_llm:
        payload = {"stage": 1, "candidates": [asdict(f) for f in eligible[: args.max_verify]]}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 0

    llm = StructuredLlm(GatewayBackend())
    selected: list[dict] = []
    tried = 0
    for feat in eligible[: args.max_verify]:
        tried += 1
        verdict = verify(store, llm, feat.patient_id)
        print(f"verified {tried}: {'ok' if verdict else 'rejected'}", file=sys.stderr)
        if verdict:
            selected.append({**verdict, "stage1_score": feat.score, "uro": feat.uro})
        if len(selected) >= args.count:
            break
    payload = {"stage": 2, "patients": selected, "tried": tried}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"selected {len(selected)} demo patients -> {out_path}", file=sys.stderr)
    return 0 if selected else 1


if __name__ == "__main__":
    raise SystemExit(main())
