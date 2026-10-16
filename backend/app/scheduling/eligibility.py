"""Diagnosis-group eligibility and server-side registration checks. Eligibility comes only from configuration."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ConflictError, NotFoundError, ValidationFailed
from app.app_db.models import Meeting
from app.app_db.repositories import DUPLICATE_MESSAGE, find_case, get_meeting
from app.scheduling.meetings import get_group


def accepts(meeting: Meeting, group_id: str, today: date) -> bool:
    return meeting.accepts_registrations and meeting.date >= today and group_id in (meeting.eligible_groups or [])


def eligible_meetings(db: Session, group_id: str, from_date: date, today: date) -> list[Meeting]:
    """Meetings on or after `from_date` that accept registrations of the group, soonest first."""
    stmt = (select(Meeting).where(Meeting.date >= max(from_date, today))
            .order_by(Meeting.date, Meeting.time, Meeting.id))
    return [m for m in db.scalars(stmt) if accepts(m, group_id, today)]


def validate_registration(db: Session, patient_id: str, group_id: str, meeting_id: str, today: date) -> Meeting:
    """Raise the API error matching the first violated rule, otherwise return the meeting."""
    if get_group(group_id) is None:
        raise ValidationFailed("Neznámá diagnostická skupina", code="unknown_group")
    meeting = get_meeting(db, meeting_id)
    if meeting is None:
        raise NotFoundError("MDT nebylo nalezeno")
    if group_id not in (meeting.eligible_groups or []):
        raise ValidationFailed("MDT nepřijímá pacienty této diagnostické skupiny", code="not_eligible")
    if not meeting.accepts_registrations or meeting.date < today:
        raise ValidationFailed("MDT již nepřijímá registrace", code="meeting_closed")
    if find_case(db, patient_id, meeting_id) is not None:
        raise ConflictError(DUPLICATE_MESSAGE, code="duplicate_case")
    return meeting
