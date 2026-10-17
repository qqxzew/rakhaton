"""Request and waiver overlay on a stored case result.

The pipeline result says what is required and what PACS has. The IRIS production knows which requests were
verified, and app_db knows which items a coordinator waived. This module merges the three and recomputes
the case readiness (CLAUDE.md 9.9). It never changes a request; the lifecycle stays in the production.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.app_db.models import Case, IssueAck, ItemWaiver
from app.config import get_settings
from app.logging import get_logger
from app.pipeline.readiness import compute_readiness
from app.pipeline.schemas import CaseCheckResult
from app.requests.production_client import ProductionClient, ProductionError, get_client

log = get_logger(__name__)

DONE_STATES = ("VERIFIED", "CLOSED")


def optional_client() -> ProductionClient | None:
    """The production lives in IRIS; with local files (tests, fallback) there is none."""
    return get_client() if get_settings().fhir_backend == "iris" else None


def _seq(row: dict) -> int:
    digits = "".join(ch for ch in str(row.get("requestId", "")) if ch.isdigit())
    return int(digits or 0)


def latest_by_item(rows: list[dict]) -> dict[str, dict]:
    """Newest request per item; a cancelled request only counts when there is no other one."""
    out: dict[str, dict] = {}
    for row in sorted(rows, key=_seq):
        item_id = row.get("itemId")
        if not item_id:
            continue
        current = out.get(item_id)
        if current is None or row.get("state") != "CANCELLED" or current.get("state") == "CANCELLED":
            out[item_id] = row
    return out


def waivers_for(db: Session, case_id: str) -> dict[str, ItemWaiver]:
    rows = db.scalars(select(ItemWaiver).where(ItemWaiver.case_id == case_id)).all()
    return {w.item_id: w for w in rows}


def acks_for(db: Session, case_id: str) -> dict[str, IssueAck]:
    rows = db.scalars(select(IssueAck).where(IssueAck.case_id == case_id)).all()
    return {a.issue_key: a for a in rows}


def overlay_result(result: CaseCheckResult, check_status: str, waivers: dict[str, ItemWaiver],
                   requests: dict[str, dict], acks: dict[str, IssueAck] | None = None) -> CaseCheckResult:
    """Copy of the result with waivers and verified deliveries applied and readiness recomputed."""
    items = []
    for item in result.items:
        update: dict = {}
        waiver = waivers.get(item.id)
        if waiver is not None:
            update.update(waived=True, note=f"Odpuštěno: {waiver.reason}")
        req = requests.get(item.id)
        if req is not None and req.get("state") in DONE_STATES:
            update.update(availability="available", state="ok",
                          note=f"Doručeno a ověřeno ({req.get('requestId')}, simulace)")
        items.append(item.model_copy(update=update) if update else item)
    settled = {i.id for i in items if i.waived or (requests.get(i.id) or {}).get("state") in DONE_STATES}
    issues = []
    for issue in result.open_issues:
        if issue.item_id and issue.item_id in settled:
            continue
        ack = (acks or {}).get(issue.key)
        if ack is not None:
            note = f"{ack.actor}: {ack.note}" if ack.note else ack.actor
            issue = issue.model_copy(update={"acknowledged": True, "ack_note": note})
        issues.append(issue)
    pending = any(r.get("state") == "DRAFTED" for r in requests.values())
    open_issues = [i for i in issues if not i.acknowledged]
    readiness, reason = compute_readiness(check_status, items, open_issues, pending_approval=pending)
    return result.model_copy(update={"items": items, "open_issues": issues, "readiness": readiness,
                                     "readiness_reason": reason})


def requests_for_case(client: ProductionClient, case: Case) -> dict[str, dict]:
    """Newest request per item of the case. Item ids are patient-scoped and the production keeps one request
    per item, so a request drafted from another case of the same patient (another MDT) serves this case too."""
    own = latest_by_item(client.list(case.id))
    wanted = {i.get("id") for i in ((case.result.result or {}).get("items", []) if case.result else [])}
    if wanted - set(own):
        shared = latest_by_item([r for r in client.list("") if r.get("itemId") in wanted - set(own)])
        own.update(shared)
    return own


def refresh_case(db: Session, case: Case, client: ProductionClient | None
                 ) -> tuple[CaseCheckResult | None, dict[str, dict] | None]:
    """Apply the overlay to a case and store its readiness. Request map is None when the production
    is not reachable (waivers still apply)."""
    if case.result is None:
        return None, None
    requests: dict[str, dict] | None = None
    if client is not None:
        try:
            requests = requests_for_case(client, case)
        except ProductionError as exc:
            log.warning("production unavailable for overlay", extra={"fields": {"error": str(exc)[:120]}})
    result = overlay_result(CaseCheckResult.model_validate(case.result.result), case.check_status,
                            waivers_for(db, case.id), requests or {}, acks_for(db, case.id))
    if case.check_status == "done" and (client is None or requests is not None):
        case.readiness, case.readiness_reason = result.readiness, result.readiness_reason[:400]
    return result, requests


def refresh_case_id(case_id: str, client: ProductionClient | None = None) -> None:
    """Best-effort refresh in its own session (after a pipeline run or a request action)."""
    from app.app_db.session import session_scope

    try:
        with session_scope() as db:
            case = db.get(Case, case_id)
            if case is not None:
                refresh_case(db, case, client)
    except Exception as exc:  # noqa: BLE001 - readiness from the pipeline stays in place
        log.warning("case overlay failed", extra={"fields": {"error": type(exc).__name__}})
