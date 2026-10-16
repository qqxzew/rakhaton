"""Schedule endpoints: dashboard, scheduled dates, day and meeting views, diagnosis groups, eligible meetings."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.case_views import diagnosis_label, fictional_name
from app.api.errors import NotFoundError, ValidationFailed
from app.api.schemas import (
    CaseRow,
    Dashboard,
    DashboardDay,
    DashboardTotals,
    DayView,
    DiagnosisGroupView,
    EligibleMeeting,
    MeetingDetail,
    MeetingSummary,
    ReadinessCounts,
    ScheduleDate,
)
from app.app_db.models import Case, Meeting
from app.app_db.repositories import get_meeting, list_cases_for_meeting, list_meetings
from app.app_db.session import get_db
from app.config import today
from app.scheduling.aggregation import (
    Aggregate,
    Counts,
    dashboard_aggregate,
    day_aggregate,
    meeting_aggregate,
)
from app.scheduling.eligibility import eligible_meetings
from app.scheduling.meetings import HORIZON_WEEKS, get_group, load_diagnosis_groups

router = APIRouter(prefix="/api", tags=["schedule"])

MAX_RANGE_DAYS = 366


def _counts(c: Counts) -> ReadinessCounts:
    return ReadinessCounts(ready=c.ready, attention=c.attention, not_ready=c.not_ready)


def _case_row(case: Case) -> CaseRow:
    timeline = (case.result.result.get("timeline") if case.result else None) or {}
    diagnoses = timeline.get("diagnoses") or []
    return CaseRow(
        id=case.id, patient_id=case.patient_id,
        display_name=case.display_name or fictional_name(case.patient_id, timeline.get("sex")),
        diagnosis=diagnosis_label(diagnoses[0]) if diagnoses else None,
        readiness=case.readiness, reason=case.readiness_reason, check_status=case.check_status,
    )


def _meeting_aggregate(cases: list[Case]) -> Aggregate:
    return meeting_aggregate([(c.readiness, c.readiness_reason) for c in cases])


def _summary(meeting: Meeting, cases: list[Case], agg: Aggregate) -> dict:
    return dict(
        id=meeting.id, label=meeting.label, date=meeting.date.isoformat(), time=meeting.time,
        readiness=agg.state, reason=agg.reason, case_count=len(cases), counts=_counts(agg.counts),
        eligible_groups=list(meeting.eligible_groups or []), accepts_registrations=meeting.accepts_registrations,
    )


def _detail(meeting: Meeting, cases: list[Case]) -> MeetingDetail:
    return MeetingDetail(**_summary(meeting, cases, _meeting_aggregate(cases)),
                         cases=[_case_row(c) for c in cases])


def _by_day(meetings: list[Meeting]) -> dict[date, list[tuple[Meeting, Aggregate]]]:
    days: dict[date, list[tuple[Meeting, Aggregate]]] = {}
    for m in meetings:
        days.setdefault(m.date, []).append((m, _meeting_aggregate(m.cases)))
    return days


def _day_aggregate(entries: list[tuple[Meeting, Aggregate]]) -> Aggregate | None:
    """Counts are per meeting; the reason names the worst meeting."""
    return day_aggregate([(a.state, f"{m.time} {m.label}: {a.reason}") for m, a in entries])


@router.get("/dashboard", response_model=Dashboard)
def get_dashboard(start: date | None = None, days: int = Query(7, ge=1, le=31),
                  db: Session = Depends(get_db)) -> Dashboard:
    first = start or today()
    last = first + timedelta(days=days - 1)
    grouped = _by_day(list_meetings(db, first, last))
    day_views: list[DashboardDay] = []
    aggregates: list[Aggregate | None] = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        entries = grouped.get(day, [])
        agg = _day_aggregate(entries)
        aggregates.append(agg)
        day_views.append(DashboardDay(
            date=day.isoformat(), readiness=agg.state if agg else None, reason=agg.reason if agg else None,
            meetings=[MeetingSummary(**_summary(m, m.cases, a)) for m, a in entries],
        ))
    total = dashboard_aggregate(aggregates)
    return Dashboard(
        start=first.isoformat(), end=last.isoformat(), days=day_views,
        totals=DashboardTotals(
            meetings=sum(len(v) for v in grouped.values()),
            cases=sum(len(m.cases) for v in grouped.values() for m, _ in v),
            counts=_counts(total.counts if total else Counts()),
        ),
        readiness=total.state if total else None, reason=total.reason if total else None,
    )


@router.get("/schedule/dates", response_model=list[ScheduleDate])
def schedule_dates(from_: date | None = Query(None, alias="from"), to: date | None = None,
                   db: Session = Depends(get_db)) -> list[ScheduleDate]:
    first = from_ or today()
    last = to or first + timedelta(weeks=HORIZON_WEEKS) - timedelta(days=1)
    if last < first or (last - first).days > MAX_RANGE_DAYS:
        raise ValidationFailed("Neplatný rozsah dat")
    result = []
    for day, entries in sorted(_by_day(list_meetings(db, first, last)).items()):
        agg = _day_aggregate(entries)
        assert agg is not None
        result.append(ScheduleDate(date=day.isoformat(), readiness=agg.state, reason=agg.reason,
                                   meeting_count=len(entries), case_count=sum(len(m.cases) for m, _ in entries)))
    return result


@router.get("/days/{day}", response_model=DayView)
def get_day(day: date, db: Session = Depends(get_db)) -> DayView:
    entries = _by_day(list_meetings(db, day, day)).get(day, [])
    agg = _day_aggregate(entries)
    return DayView(
        date=day.isoformat(), readiness=agg.state if agg else None, reason=agg.reason if agg else None,
        counts=_counts(agg.counts if agg else Counts()),
        meetings=[_detail(m, sorted(m.cases, key=lambda c: (c.created_at, c.id))) for m, _ in entries],
    )


@router.get("/diagnosis-groups", response_model=list[DiagnosisGroupView])
def diagnosis_groups() -> list[DiagnosisGroupView]:
    return [DiagnosisGroupView(id=g.id, label=g.label) for g in load_diagnosis_groups()]


# Registered before /meetings/{meeting_id} so "eligible" is not read as an id.
@router.get("/meetings/eligible", response_model=list[EligibleMeeting])
def eligible(group: str, from_: date | None = Query(None, alias="from"),
             db: Session = Depends(get_db)) -> list[EligibleMeeting]:
    if get_group(group) is None:
        raise ValidationFailed("Neznámá diagnostická skupina", code="unknown_group")
    today_ = today()
    return [EligibleMeeting(id=m.id, label=m.label, date=m.date.isoformat(), time=m.time)
            for m in eligible_meetings(db, group, from_ or today_, today_)]


@router.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting_detail(meeting_id: str, db: Session = Depends(get_db)) -> MeetingDetail:
    meeting = get_meeting(db, meeting_id)
    if meeting is None:
        raise NotFoundError("MDT nebylo nalezeno")
    return _detail(meeting, list_cases_for_meeting(db, meeting_id))
