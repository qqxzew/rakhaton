"""Application-only state (meetings, cases, cached check results). Clinical facts live in FHIR."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from datetime import date as Date
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy import Date as SqlDate
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

CHECK_STATUSES = ("pending", "running", "done", "failed")
READINESS_STATES = ("not_ready", "attention", "ready")


class JsonText(TypeDecorator):
    """JSON stored as text, so the same models work on SQLite and on IRIS SQL (which has no JSON type)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "iris":  # Text maps to VARCHAR(65535) there; case results can be larger
            from sqlalchemy_iris import LONGVARCHAR

            return dialect.type_descriptor(LONGVARCHAR())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if hasattr(value, "read"):  # IRIS returns long text as a stream
            value = value.read()
        return json.loads(value) if value != "" else None


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Meeting(Base):
    __tablename__ = "meeting"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[Date] = mapped_column(SqlDate, index=True)
    time: Mapped[str] = mapped_column(String(5))
    label: Mapped[str] = mapped_column(String(200))
    eligible_groups: Mapped[list[str]] = mapped_column(JsonText, default=list)
    accepts_registrations: Mapped[bool] = mapped_column(Boolean, default=True)

    cases: Mapped[list[Case]] = relationship(back_populates="meeting")


class Case(Base):
    __tablename__ = "case"
    __table_args__ = (
        UniqueConstraint("patient_id", "meeting_id", name="uq_case_patient_meeting"),
        CheckConstraint(_in_list("check_status", CHECK_STATUSES), name="ck_case_check_status"),
        CheckConstraint(_in_list("readiness", READINESS_STATES), name="ck_case_readiness"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meeting.id"))
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    planned_exam_override: Mapped[dict | None] = mapped_column(JsonText, nullable=True)
    reference_date: Mapped[Date | None] = mapped_column(SqlDate, nullable=True)
    date_offset_days: Mapped[int] = mapped_column(Integer, default=0)
    check_status: Mapped[str] = mapped_column(String(16), default="pending")
    readiness: Mapped[str] = mapped_column(String(16), default="not_ready")
    readiness_reason: Mapped[str] = mapped_column(String(400), default="Probíhá úvodní kontrola")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="cases")
    result: Mapped[CaseResult | None] = relationship(back_populates="case", uselist=False)


class CaseResult(Base):
    """Latest successful pipeline output of a case, kept so it stays visible if a recheck fails."""

    __tablename__ = "case_result"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), primary_key=True)
    result: Mapped[dict] = mapped_column(JsonText)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped[Case] = relationship(back_populates="result")


class IssueAck(Base):
    """A coordinator acknowledged an open issue (who, when, optional note). Keys are stable hashes of the
    issue type and text, so an acknowledgement survives pipeline reruns."""

    __tablename__ = "issue_ack"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), primary_key=True)
    issue_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    note: Mapped[str] = mapped_column(String(400), default="")
    actor: Mapped[str] = mapped_column(String(100))
    acked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ItemWaiver(Base):
    """A coordinator's decision that a required item is not needed (who, when, why). Item ids are stable
    hashes, so a waiver survives pipeline reruns."""

    __tablename__ = "item_waiver"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str] = mapped_column(String(400))
    actor: Mapped[str] = mapped_column(String(100))
    waived_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AutopilotPolicy(Base):
    """Standing approval policy (one row, id 1): while enabled, drafted requests with a known holding site
    are approved without a click. Who switched it on and when is the approval record (spec rule 3)."""

    __tablename__ = "autopilot_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    actor: Mapped[str] = mapped_column(String(100), default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
