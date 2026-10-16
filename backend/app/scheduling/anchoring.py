"""Demo date anchoring: pipeline dates stay in the patient's own frame, the UI applies one offset per case."""

from __future__ import annotations

from datetime import date, timedelta


def compute_offset(meeting_date: date, reference_date: date | None, fallback: int = 0) -> int:
    """Days to add to patient dates so the case's reference date lands on the meeting date."""
    return (meeting_date - reference_date).days if reference_date is not None else fallback


def shift_date(day: date, offset: int) -> date:
    return day + timedelta(days=offset)


def shift_iso(day: date, offset: int) -> str:
    return shift_date(day, offset).isoformat()


def unshift_date(shown: date, offset: int) -> date:
    """A date the coordinator typed in the UI, back in the patient's own frame."""
    return shown - timedelta(days=offset)
