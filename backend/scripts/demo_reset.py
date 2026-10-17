"""Reset the demo to a clean, known state (IRIS SQL app state + request production state).

1. Backs up every row of the app tables and of the production request tables to
   data/backup/demo_state_<timestamp>.json (git-ignored).
2. Deletes all cases, results, waivers and issue acknowledgements, all ad-hoc meetings that are not part of
   the configured MDT schedule, and all requests/events/messages of the request production.
3. Registers the demo patients (data/demo_patients.json) on the nearest eligible MDT in the next 7 days,
   runs their checks (LLM cache makes this fast), then runs the nightly preparation so the dashboard shows
   drafted requests waiting for approval.

FHIR resources already written (Task, Communication, AuditEvent, ...) are kept as the audit trail.

    uv run python scripts/demo_reset.py            # backup + reset + seed
    uv run python scripts/demo_reset.py --no-seed  # backup + reset only
Output: counts only, never pseudonyms.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.app_db.session import get_engine
from app.config import get_settings, today

APP_TABLES = ["issue_ack", "item_waiver", "case_result", '"case"']
REQ_SCHEMA = "PacsComparator_Req"


def _rows(conn, table: str) -> list[dict]:
    res = conn.execute(text(f"SELECT * FROM {table}"))
    cols = list(res.keys())
    return [{c: (v.isoformat() if isinstance(v, (date, datetime)) else v) for c, v in zip(cols, r, strict=True)}
            for r in res.fetchall()]


def _jsonable(value):
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(bytes(value))} bytes>"
    return str(value)


def backup_and_reset(engine) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = get_settings().data_dir / "backup"
    out.mkdir(parents=True, exist_ok=True)
    dump: dict[str, list] = {}
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        req_tables = [r[0] for r in conn.execute(text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = :s"), {"s": REQ_SCHEMA})]
        for t in APP_TABLES + ["meeting"] + [f"{REQ_SCHEMA}.{t}" for t in req_tables]:
            try:
                dump[t] = _rows(conn, t)
            except Exception as exc:  # noqa: BLE001 - a missing table is fine
                dump[t] = [f"unreadable: {type(exc).__name__}"]
        (out / f"demo_state_{stamp}.json").write_text(
            json.dumps(dump, ensure_ascii=False, indent=1, default=_jsonable), encoding="utf-8")
        for t in APP_TABLES:
            counts[t] = conn.execute(text(f"DELETE FROM {t}")).rowcount
        counts["meeting(ad hoc)"] = conn.execute(text(
            "DELETE FROM meeting WHERE id NOT LIKE 'MDT-%-2%'")).rowcount
        for t in req_tables:
            counts[f"{REQ_SCHEMA}.{t}"] = conn.execute(text(f"DELETE FROM {REQ_SCHEMA}.{t}")).rowcount
    print(f"backup written: data/backup/demo_state_{stamp}.json", file=sys.stderr)
    return counts


def seed(client: TestClient) -> dict:
    demo = json.loads((get_settings().data_dir / "demo_patients.json").read_text(encoding="utf-8"))
    ids = [p["patient_id"] for p in demo.get("patients", [])]
    horizon = today() + timedelta(days=7)
    added = 0
    for pid in ids:
        hits = client.get("/api/patients/search", params={"q": pid}).json()
        group = hits[0]["suggested_group"] if hits else "other"
        meetings = client.get("/api/meetings/eligible", params={"group": group}).json()
        meetings = meetings if isinstance(meetings, list) else meetings.get("meetings", [])
        soon = [m for m in meetings if today() <= date.fromisoformat(m["date"]) <= horizon] or meetings
        if not soon:
            continue
        r = client.post("/api/cases", json={"patient_id": pid, "group_id": group, "meeting_id": soon[0]["id"]})
        added += r.status_code == 201
    nightly = client.post("/api/demo/nightly-run", json={"days": 7}).json()
    return {"cases_added": added, "nightly": {k: nightly.get(k) for k in ("drafts_created", "failed", "cases")
                                              if k in nightly}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-seed", action="store_true")
    args = ap.parse_args()
    from app.main import create_app

    print(json.dumps({"deleted": backup_and_reset(get_engine())}, indent=1))
    if not args.no_seed:
        with TestClient(create_app()) as client:  # in-process, same IRIS and production as the real app
            print(json.dumps(seed(client), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
