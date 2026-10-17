"""Embed report and note chunks locally and store them in IRIS (Vector Search table).

Reads patients through the configured FhirStore (use FHIR_BACKEND=iris to read from IRIS FHIR).

    uv run python scripts/index_vectors.py --demo
    uv run python scripts/index_vectors.py --all
    uv run python scripts/index_vectors.py --query "srovnání s předchozím CT hrudníku" --top 5

Query output prints only scores, source types and dates; never patient ids or text.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from app.config import get_settings
from app.fhir_store.base import FhirStoreError
from app.fhir_store.factory import get_store
from app.search import vector_store as vs


def demo_ids() -> list[str]:
    path = get_settings().data_dir / "demo_patients.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for key in ("patients", "candidates"):
        for e in doc.get(key, []):
            pid = e.get("patient_id") if isinstance(e, dict) else e
            if pid and pid not in out:
                out.append(pid)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--all", action="store_true", help="every patient in the store")
    parser.add_argument("--patients", nargs="*", default=[])
    parser.add_argument("--status", action="store_true", help="print index counts only")
    parser.add_argument("--resume", action="store_true", help="skip patients that already have chunks")
    parser.add_argument("--query")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    if args.status:
        conn = vs.connect()
        try:
            print(vs.counts(conn), file=sys.stderr)
        finally:
            conn.close()
        return

    if args.query:
        conn = vs.connect()
        try:
            for h in vs.search(conn, args.query, top_k=args.top):
                print(f"{h.score:.3f} {h.source_type} {h.doc_date}", file=sys.stderr)
        finally:
            conn.close()
        return

    store = get_store()
    ids = list(args.patients)
    if args.demo:
        ids += [p for p in demo_ids() if p not in ids]
    if args.all:
        try:
            all_ids = store.list_patient_ids()
        except FhirStoreError:  # IRIS refuses an unfiltered Patient search above its result limit
            from app.fhir_store.local import LocalBundleStore

            all_ids = LocalBundleStore().list_patient_ids()
        ids += [p for p in all_ids if p not in ids]
    if not ids:
        raise SystemExit("nothing selected: use --demo, --all or --patients")
    started = time.monotonic()
    conn = vs.connect()
    try:
        vs.ensure_table(conn)
        done: set[str] = set()
        if args.resume:
            cur = conn.cursor()
            cur.execute(f"SELECT DISTINCT PatientId FROM {vs.TABLE}")
            done = {r[0] for r in cur.fetchall()}
        total = 0
        for n, pid in enumerate(ids, 1):
            if pid in done:
                continue
            total += vs.index_patient(conn, store, pid)
            if n % 10 == 0:
                print(f"{n}/{len(ids)} patients, {total} chunks", file=sys.stderr)
    finally:
        conn.close()
    print(f"processed {len(ids)} patients, {total} new chunks, {time.monotonic() - started:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
