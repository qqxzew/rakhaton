"""Scheduling unit tests on synthetic data: materialization, eligibility, duplicates, anchoring, aggregation."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import ConflictError, NotFoundError, ValidationFailed
from app.app_db import repositories
from app.app_db.models import Base, Case, Meeting
from app.app_db.repositories import create_case, ensure_meetings, list_meetings
from app.app_db.session import make_engine
from app.scheduling.aggregation import (
    dashboard_aggregate,
    day_aggregate,
    meeting_aggregate,
)
from app.scheduling.anchoring import compute_offset, shift_date, shift_iso, unshift_date
from app.scheduling.eligibility import eligible_meetings, validate_registration
from app.scheduling.meetings import (
    MeetingTemplate,
    group_for_codes,
    load_diagnosis_groups,
    materialize_meetings,
)

TODAY = date(2026, 10, 19)  # a Monday
PATIENT = "PAC-TEST-0001"


@pytest.fixture
def db(tmp_path) -> Session:
    engine = make_engine(f"sqlite:///{(tmp_path / 'sched.db').as_posix()}")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def schedule(db: Session) -> Session:
    ensure_meetings(db, TODAY)
    db.commit()
    return db


def test_materialization_covers_eight_weeks_with_stable_ids():
    specs = materialize_meetings(TODAY)
    assert len(specs) == 6 * 8
    assert specs[0].date == TODAY and specs[-1].date <= date(2026, 12, 13)
    uro = next(s for s in specs if s.id == "MDT-uro-20261019-1400")
    assert uro.eligible_groups == ("uro",) and uro.label == "Uroonkologický MDT"
    assert [(s.date, s.time) for s in specs] == sorted((s.date, s.time) for s in specs)


def test_materialization_follows_templates_and_allows_several_meetings_per_day():
    templates = [MeetingTemplate("a", "A", 3, "09:00", ("uro",)), MeetingTemplate("b", "B", 3, "11:00", ("gi",))]
    specs = materialize_meetings(TODAY, weeks=1, templates=templates)
    assert [s.id for s in specs] == ["MDT-a-20261021-0900", "MDT-b-20261021-1100"]


def test_ensure_meetings_is_idempotent_and_closes_past_meetings(schedule: Session):
    assert ensure_meetings(schedule, TODAY) == 0
    count = len(list_meetings(schedule, TODAY, date(2027, 1, 1)))
    assert count == 48
    schedule.add(Meeting(id="MDT-old", date=date(2026, 10, 1), time="10:00", label="Old",
                         eligible_groups=["uro"], accepts_registrations=True))
    schedule.commit()
    ensure_meetings(schedule, TODAY)
    assert schedule.get(Meeting, "MDT-old").accepts_registrations is False
    assert schedule.get(Meeting, "MDT-uro-20261019-1400").accepts_registrations is True


def test_group_defaults_from_icd_codes():
    assert group_for_codes(["C61"]) == "uro"
    assert group_for_codes(["c34.1"]) == "lung"
    assert group_for_codes(["Z00"]) == "other"
    assert {g.id for g in load_diagnosis_groups()} >= {"uro", "lung", "breast", "gi", "hn", "cns", "other"}


def test_eligible_meetings_only_list_configured_open_future_meetings(schedule: Session):
    schedule.add(Meeting(id="MDT-closed", date=date(2026, 10, 20), time="08:00", label="Closed",
                         eligible_groups=["uro"], accepts_registrations=False))
    schedule.commit()
    found = eligible_meetings(schedule, "uro", TODAY, TODAY)
    assert found[0].id == "MDT-uro-20261019-1400"
    assert all("uro" in m.eligible_groups and m.accepts_registrations for m in found)
    assert "MDT-closed" not in {m.id for m in found}
    assert {m.label for m in found} == {"Uroonkologický MDT", "Obecný onkologický MDT"}
    assert eligible_meetings(schedule, "lung", date(2026, 10, 24), TODAY)[0].id == "MDT-lung-20261027-1300"
    assert eligible_meetings(schedule, "uro", date(2026, 1, 1), TODAY)[0].date == TODAY  # never the past
    assert eligible_meetings(schedule, "unknown", TODAY, TODAY) == []


def test_validate_registration_rejects_each_violation(schedule: Session):
    ok = validate_registration(schedule, PATIENT, "uro", "MDT-uro-20261019-1400", TODAY)
    assert ok.id == "MDT-uro-20261019-1400"
    with pytest.raises(ValidationFailed) as unknown_group:
        validate_registration(schedule, PATIENT, "nope", "MDT-uro-20261019-1400", TODAY)
    assert unknown_group.value.code == "unknown_group"
    with pytest.raises(NotFoundError):
        validate_registration(schedule, PATIENT, "uro", "MDT-missing", TODAY)
    with pytest.raises(ValidationFailed) as not_eligible:
        validate_registration(schedule, PATIENT, "lung", "MDT-uro-20261019-1400", TODAY)
    assert not_eligible.value.code == "not_eligible"
    with pytest.raises(ValidationFailed) as closed:
        validate_registration(schedule, PATIENT, "uro", "MDT-uro-20261019-1400", date(2026, 10, 20))
    assert closed.value.code == "meeting_closed"
    schedule.get(Meeting, "MDT-uro-20261019-1400").accepts_registrations = False
    with pytest.raises(ValidationFailed):
        validate_registration(schedule, PATIENT, "uro", "MDT-uro-20261019-1400", TODAY)


def test_duplicate_case_is_rejected_by_check_and_by_constraint(schedule: Session, monkeypatch):
    first = create_case(schedule, patient_id=PATIENT, meeting_id="MDT-uro-20261019-1400", group_id="uro")
    schedule.commit()
    assert first.check_status == "running" and first.readiness == "not_ready" and first.id.startswith("CASE-")
    with pytest.raises(ConflictError) as dup:
        create_case(schedule, patient_id=PATIENT, meeting_id="MDT-uro-20261019-1400", group_id="uro")
    assert dup.value.code == "duplicate_case"
    with pytest.raises(ConflictError):
        validate_registration(schedule, PATIENT, "uro", "MDT-uro-20261019-1400", TODAY)

    # a concurrent request that passed the read check must still be stopped by the unique constraint
    monkeypatch.setattr(repositories, "find_case", lambda *_: None)
    schedule.expunge_all()  # as in a separate request: nothing of the first insert is in this session
    with pytest.raises(ConflictError):
        create_case(schedule, patient_id=PATIENT, meeting_id="MDT-uro-20261019-1400", group_id="uro")
    schedule.commit()
    assert schedule.query(Case).count() == 1

    other = create_case(schedule, patient_id=PATIENT, meeting_id="MDT-general-20261023-1000", group_id="uro")
    schedule.commit()
    assert other.id != first.id and schedule.query(Case).count() == 2


def test_anchoring_applies_one_offset_and_keeps_patient_dates_unchanged():
    reference, meeting = date(2026, 5, 10), date(2026, 10, 20)
    offset = compute_offset(meeting, reference)
    assert offset == 163
    assert shift_date(reference, offset) == meeting and shift_iso(reference, offset) == "2026-10-20"
    patient_date = date(2025, 3, 10)
    assert unshift_date(shift_date(patient_date, offset), offset) == patient_date
    assert (shift_date(date(2025, 3, 12), offset) - shift_date(patient_date, offset)).days == 2
    assert compute_offset(meeting, None, fallback=7) == 7


def test_meeting_aggregate_uses_worst_case_and_flags_empty_meetings():
    empty = meeting_aggregate([])
    assert (empty.state, empty.reason, empty.counts.total) == ("attention", "Žádní pacienti", 0)
    mixed = meeting_aggregate([("ready", "ok"), ("attention", "check"), ("not_ready", "Chybí: CT"), ("not_ready", "x")])
    assert (mixed.state, mixed.reason) == ("not_ready", "Chybí: CT")
    assert (mixed.counts.ready, mixed.counts.attention, mixed.counts.not_ready) == (1, 1, 2)
    assert meeting_aggregate([("ready", "ok"), ("ready", "ok")]).state == "ready"
    assert meeting_aggregate([("ready", "ok"), ("attention", "check")]).state == "attention"


def test_day_and_dashboard_aggregation_counts_meetings():
    assert day_aggregate([]) is None and dashboard_aggregate([None, None]) is None
    monday = day_aggregate([("ready", "a"), ("attention", "b")])
    tuesday = day_aggregate([("not_ready", "c")])
    assert monday is not None and tuesday is not None
    assert monday.state == "attention" and (monday.counts.ready, monday.counts.attention) == (1, 1)
    total = dashboard_aggregate([monday, None, tuesday])
    assert total is not None and (total.state, total.reason) == ("not_ready", "c")
    assert (total.counts.ready, total.counts.attention, total.counts.not_ready, total.counts.total) == (1, 1, 1, 3)
    assert dashboard_aggregate([day_aggregate([("ready", "ok")])]).state == "ready"
