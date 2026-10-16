"""Load per-patient FHIR R4 transaction bundles from data/raw/fhir into the IRIS FHIR server.

Bundles use PUT with the dataset ids, so ids (patient pseudonyms, rep-STU-... reports) are kept and
the app reads the same ids from IRIS as from the local files. Observations (all of them are lab
results in this dataset) are skipped by default: the pipeline does not use them and they are ~90% of
all resources; --include-labs keeps them. A failing transaction is retried resource by resource.

    uv run python scripts/load_iris.py --all            # demo patients first, then every other patient
    uv run python scripts/load_iris.py --demo --limit 300
    uv run python scripts/load_iris.py --patients <id> <id>

Patient data stays local: bundles go only to the IRIS container on this machine.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from app.config import get_settings


def patients_with_imaging(raw_dir: Path) -> list[str]:
    path = raw_dir / "vysetreni.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        ids = {row["pseudonym"] for row in csv.DictReader(f, delimiter=";")}
    return sorted(ids)


def demo_patients(data_dir: Path) -> list[str]:
    path = data_dir / "demo_patients.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for key in ("patients", "candidates"):
        for entry in doc.get(key, []):
            pid = entry.get("patient_id") if isinstance(entry, dict) else entry
            if pid and pid not in out:
                out.append(pid)
    return out


def prepare_bundle(path: Path, include_labs: bool) -> bytes:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if not include_labs:
        bundle["entry"] = [
            e for e in bundle.get("entry", [])
            if e["resource"]["resourceType"] != "Observation"
        ]
    return json.dumps(bundle, ensure_ascii=False).encode("utf-8")


HEADERS = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}


def _send(client: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    """One HTTP call with a few retries on transport errors and 5xx/429."""
    for attempt in range(4):
        try:
            resp = client.request(method, url, headers=HEADERS, **kw)
        except httpx.TransportError:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(2 * (attempt + 1))
            continue
        return resp
    raise AssertionError("unreachable")


def post_bundle(client: httpx.Client, base: str, body: bytes) -> tuple[int, str]:
    """POST the transaction; if it fails, PUT the resources one by one (idempotent, ids are kept)."""
    try:
        resp = _send(client, "POST", base, content=body)
    except httpx.TransportError as exc:
        return 599, type(exc).__name__
    if resp.status_code < 300:
        return resp.status_code, ""
    bundle = json.loads(body)
    bad = 0
    for e in bundle.get("entry", []):
        res = e["resource"]
        url = f"{base}/{res['resourceType']}/{res['id']}"
        try:
            r = _send(client, "PUT", url, content=json.dumps(res, ensure_ascii=False).encode("utf-8"))
        except httpx.TransportError:
            bad += 1
            continue
        if r.status_code >= 300:
            bad += 1
            print(f"  resource {res['resourceType']}: HTTP {r.status_code} {r.text[:160]}", file=sys.stderr)
    if bad:
        return 207, f"{bad} resources failed after transaction HTTP {resp.status_code}"
    return 200, ""


def main() -> None:
    s = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patients", nargs="*", default=[])
    parser.add_argument("--demo", action="store_true", help="include data/demo_patients.json")
    parser.add_argument("--limit", type=int, default=0, help="add N patients with imaging")
    parser.add_argument("--all", action="store_true", help="every patient bundle (demo patients first)")
    parser.add_argument("--include-labs", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    base = s.iris_fhir_base.rstrip("/")
    if not base:
        raise SystemExit("IRIS_FHIR_BASE is not set")
    fhir_dir = s.raw_dir / "fhir"

    selected: list[str] = list(args.patients)
    if args.demo or args.all:
        selected += [p for p in demo_patients(s.data_dir) if p not in selected]
    if args.all:
        everyone = sorted(p.stem for p in fhir_dir.glob("PAC-*.json"))
        selected += [p for p in everyone if p not in selected]
    if args.limit:
        target = len(selected) + args.limit
        for pid in patients_with_imaging(s.raw_dir):
            if len(selected) >= target:
                break
            if pid not in selected:
                selected.append(pid)
    if not selected:
        raise SystemExit("nothing selected: use --patients, --demo or --limit")

    auth = (s.iris_user or "SuperUser", s.iris_password or "SYS")
    ok = failed = 0
    started = time.monotonic()
    with httpx.Client(auth=auth, timeout=600) as client, ThreadPoolExecutor(args.workers) as pool:
        futures = {}
        for pid in selected:
            path = fhir_dir / f"{pid}.json"
            if not path.exists():
                print(f"missing bundle file (index {selected.index(pid)})", file=sys.stderr)
                failed += 1
                continue
            body = prepare_bundle(path, args.include_labs)
            futures[pool.submit(post_bundle, client, base, body)] = pid
        for n, fut in enumerate(as_completed(futures), 1):
            status, err = fut.result()
            if status < 300:
                ok += 1
            else:
                failed += 1
                # never print patient ids at info level; the index is enough to retry
                print(f"bundle {n}: HTTP {status} {err}", file=sys.stderr)
            if n % 25 == 0:
                print(f"{n}/{len(futures)} done", file=sys.stderr)
    print(f"loaded {ok}, failed {failed}, {time.monotonic() - started:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
