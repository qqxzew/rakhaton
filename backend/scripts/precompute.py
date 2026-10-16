"""Precompute pipeline results so the UI and the demo are instant (all output under data/cache/).

Uses the cached language-model results, so reruns are free. Run from the backend directory:
    uv run python scripts/precompute.py [--demo] [--patients PAC-A PAC-B] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.fhir_store.factory import get_store
from app.llm.client import GatewayBackend, LlmError, StructuredLlm
from app.logging import configure_logging
from app.pipeline.run import run_patient_check
from app.pipeline.timeline import build_timeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="patients from data/demo_patients.json")
    parser.add_argument("--patients", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=0, help="also the first N patients that have imaging")
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    store = get_store()

    ids: list[str] = list(args.patients)
    if args.demo:
        data = json.loads((settings.data_dir / "demo_patients.json").read_text(encoding="utf-8"))
        ids += [p["patient_id"] for p in data.get("patients", [])]
    if args.limit:
        for pid in store.list_patient_ids():
            if len(ids) >= args.limit + len(args.patients):
                break
            if pid not in ids and build_timeline(store, pid).studies:
                ids.append(pid)

    llm = StructuredLlm(GatewayBackend())
    out_dir = settings.cache_dir / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for index, pid in enumerate(dict.fromkeys(ids), 1):
        try:
            result = run_patient_check(pid, store, llm)
        except LlmError as exc:
            failed += 1
            print(f"{index}: failed ({type(exc).__name__})", file=sys.stderr)
            continue
        (out_dir / f"{pid}.json").write_text(result.model_dump_json(indent=1), encoding="utf-8")
        print(f"{index}: {result.readiness}, {len(result.items)} items", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
