"""Meeting and case persistence. Plain SQLAlchemy Core/ORM constructs only, so it runs on SQLite and IRIS SQL."""

from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.errors import ConflictError
from app.app_db.models import Case, Meeting
from app.scheduling.meetings import HORIZON_WEEKS, materialize_meetings

DUPLICATE_MESSAGE = "Pacient je k tomuto MDT již zaregistrován"


def ensure_meetings(db: Session, today: date, weeks: int = HORIZON_WEEKS) -> int:
    """Materialize the configured meetings for the next `weeks` weeks (idempotent); returns how many were added.

    Meetings before `today` stop accepting registrations.
    """
    specs = materialize_meetings(today, weeks)
    known = set(db.scalars(select(Meeting.id).where(Meeting.date >= today)))
    added = 0
    for spec in specs:
        if spec.id in known:
            continue
        try:
            with db.begin_nested():
                db.add(Meeting(id=spec.id, date=spec.date, time=spec.time, label=spec.label,
                               eligible_groups=list(spec.eligible_groups), accepts_registrations=True))
            added += 1
        except IntegrityError:
            continue  # created concurrently by another process
    db.execute(update(Meeting).where(Meeting.date < today, Meeting.accepts_registrations.is_(True))
               .values(accepts_registrations=False))
    return added


def get_meeting(db: Session, meeting_id: str) -> Meeting | None:
    return db.get(Meeting, meeting_id)


def list_meetings(db: Session, start: date, end: date) -> list[Meeting]:
    """Meetings with `start <= date <= end`, with their cases, ordered by date and time."""
    stmt = (select(Meeting).where(Meeting.date >= start, Meeting.date <= end)
            .options(selectinload(Meeting.cases).selectinload(Case.result))
            .order_by(Meeting.date, Meeting.time, Meeting.id))
    return list(db.scalars(stmt))


def list_cases_for_meeting(db: Session, meeting_id: str) -> list[Case]:
    stmt = (select(Case).where(Case.meeting_id == meeting_id)
            .options(selectinload(Case.result)).order_by(Case.created_at, Case.id))
    return list(db.scalars(stmt))


def find_case(db: Session, patient_id: str, meeting_id: str) -> Case | None:
    return db.scalars(select(Case).where(Case.patient_id == patient_id, Case.meeting_id == meeting_id)).first()


def case_id_for(patient_id: str, meeting_id: str) -> str:
    """Deterministic id, so a second insert of the same pair also collides on the primary key."""
    digest = hashlib.sha256(f"{patient_id}|{meeting_id}".encode()).hexdigest()[:16]
    return f"CASE-{digest}"


def create_case(db: Session, *, patient_id: str, meeting_id: str, group_id: str | None,
                display_name: str | None = None) -> Case:
    """Insert a case in the running state; the unique (patient, meeting) constraint makes duplicates atomic."""
    if find_case(db, patient_id, meeting_id) is not None:
        raise ConflictError(DUPLICATE_MESSAGE, code="duplicate_case")
    case = Case(id=case_id_for(patient_id, meeting_id), patient_id=patient_id, meeting_id=meeting_id,
                group_id=group_id, display_name=display_name, check_status="running")
    try:
        with db.begin_nested():
            db.add(case)
    except IntegrityError as exc:
        raise ConflictError(DUPLICATE_MESSAGE, code="duplicate_case") from exc
    return case
