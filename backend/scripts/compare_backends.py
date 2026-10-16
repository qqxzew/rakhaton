"""Compare what LocalBundleStore and IrisFhirStore return for the same patients (counts only in output).

    uv run python scripts/compare_backends.py [--all | --review]

Resources are compared after dropping the server-added `meta` element; list order is ignored.
With --pipeline the full pipeline result of every review patient is compared too (cached LLM results
are reused; missing ones call the gateway sequentially).
"""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.fhir_store.iris import PATIENT_TYPES, IrisFhirStore
from app.fhir_store.local import LocalBundleStore


def _canon(resource: dict) -> str:
    return json.dumps({k: v for k, v in resource.items() if k != "meta"}, sort_keys=True, ensure_ascii=False)


def review_patients() -> list[str]:
    ids: list[str] = []
    for path in sorted((get_settings().data_dir / "review").glob("*.json")):
        pid = json.loads(path.read_text(encoding="utf-8")).get("patient_id")
        if pid and pid not in ids:
            ids.append(pid)
    return ids


def _strip(value, volatile=("computed_at", "generated_at", "checked_at")):
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in volatile}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def compare_pipeline(ids: list[str]) -> int:
    from app.llm.client import GatewayBackend, StructuredLlm
    from app.pipeline.run import run_patient_check

    llm = StructuredLlm(GatewayBackend())
    diffs = 0
    for i, pid in enumerate(ids, 1):
        results = []
        for store in (LocalBundleStore(), IrisFhirStore()):
            results.append(_strip(json.loads(run_patient_check(pid, store, llm).model_dump_json())))
        same = results[0] == results[1]
        diffs += not same
        print(f"pipeline patient {i}/{len(ids)}: {'identical' if same else 'DIFFERENT'}", file=sys.stderr)
        if not same:
            for key in results[0]:
                if results[0][key] != results[1].get(key):
                    print(f"  differs in field {key!r}", file=sys.stderr)
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--pipeline", action="store_true", help="also compare pipeline results")
    args = parser.parse_args()
    local, iris = LocalBundleStore(), IrisFhirStore()
    ids = local.list_patient_ids() if args.all else review_patients()
    if args.all and sorted(ids) != iris.list_patient_ids():
        print("patient id lists differ", file=sys.stderr)
        return 1
    diffs = checked = 0
    for pid in ids:
        for rtype in ("Patient", *PATIENT_TYPES):
            a = sorted(_canon(r) for r in local.resources(pid, rtype))
            b = sorted(_canon(r) for r in iris.resources(pid, rtype))
            checked += 1
            if a != b:
                diffs += 1
                print(f"difference in {rtype}: local {len(a)} vs iris {len(b)} resources", file=sys.stderr)
    print(f"patients {len(ids)}, type comparisons {checked}, differences {diffs}", file=sys.stderr)
    if args.pipeline:
        diffs += compare_pipeline(review_patients())
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
