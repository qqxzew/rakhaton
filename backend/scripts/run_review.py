"""Run the pipeline on the demo patients plus N random patients with imaging, for human review (T073).

Everything is written under the git-ignored data/review/ directory. Cached LLM results make reruns free.
    uv run python scripts/run_review.py [--random 5] [--seed 20261017]
Then: uv run python scripts/review_results.py
"""

from __future__ import annotations

import argparse
import json
import random
import sys

from app.config import get_settings
from app.fhir_store.factory import get_store
from app.llm.client import GatewayBackend, LlmError, StructuredLlm
from app.logging import configure_logging
from app.pipeline.run import run_patient_check
from app.pipeline.timeline import build_studies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--random", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261017)
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    store = get_store()

    demo = json.loads((settings.data_dir / "demo_patients.json").read_text(encoding="utf-8"))
    demo_ids = [p["patient_id"] for p in demo.get("patients", [])]

    rng = random.Random(args.seed)
    ids = store.list_patient_ids()
    rng.shuffle(ids)
    random_ids: list[str] = []
    for pid in ids:
        if len(random_ids) >= args.random:
            break
        if pid not in demo_ids and build_studies(store, pid)[0]:
            random_ids.append(pid)

    out_dir = settings.data_dir / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    llm = StructuredLlm(GatewayBackend())
    failed = 0
    for label, group in (("demo", demo_ids), ("random", random_ids)):
        for index, pid in enumerate(group, 1):
            try:
                result = run_patient_check(pid, store, llm)
            except LlmError as exc:
                failed += 1
                print(f"{label} {index}: failed ({type(exc).__name__})", file=sys.stderr)
                continue
            (out_dir / f"{label}{index}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
            print(f"{label} {index}: {result.readiness}, {len(result.items)} items", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
