"""Diagnosis groups and recurring MDT templates, materialized into concrete meetings (CLAUDE.md section 8)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from app.config import CONFIG_DIR

HORIZON_WEEKS = 8


@dataclass(frozen=True)
class DiagnosisGroup:
    id: str
    label: str
    icd_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class MeetingTemplate:
    template: str
    label: str
    weekday: int  # ISO: 1 = Monday ... 7 = Sunday
    time: str
    groups: tuple[str, ...]


@dataclass(frozen=True)
class MeetingSpec:
    id: str
    date: date
    time: str
    label: str
    eligible_groups: tuple[str, ...]


@lru_cache
def _read_json(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_diagnosis_groups(path: Path | None = None) -> list[DiagnosisGroup]:
    raw = _read_json(str(path or CONFIG_DIR / "diagnosis_groups.json"))
    return [DiagnosisGroup(g["id"], g["label"], tuple(g.get("icd_prefixes", []))) for g in raw]


def get_group(group_id: str) -> DiagnosisGroup | None:
    return next((g for g in load_diagnosis_groups() if g.id == group_id), None)


def group_for_codes(codes: list[str]) -> str:
    """Default group of a patient from ICD-10 codes; the first configured match wins, else `other`."""
    for group in load_diagnosis_groups():
        if any(code.upper().startswith(prefix) for code in codes for prefix in group.icd_prefixes):
            return group.id
    return "other"


def load_templates(path: Path | None = None) -> list[MeetingTemplate]:
    raw = _read_json(str(path or CONFIG_DIR / "mdt_schedule.json"))
    return [
        MeetingTemplate(t["template"], t["label"], int(t["weekday"]), t["time"], tuple(t["groups"]))
        for t in raw
    ]


def meeting_id(template: str, day: date, time: str) -> str:
    return f"MDT-{template}-{day:%Y%m%d}-{time.replace(':', '')}"


def materialize_meetings(start: date, weeks: int = HORIZON_WEEKS,
                         templates: list[MeetingTemplate] | None = None) -> list[MeetingSpec]:
    """Concrete meetings for `weeks` weeks beginning at `start` (inclusive), ordered by date and time."""
    templates = templates if templates is not None else load_templates()
    specs: list[MeetingSpec] = []
    for offset in range(weeks * 7):
        day = start + timedelta(days=offset)
        for t in templates:
            if day.isoweekday() == t.weekday:
                specs.append(MeetingSpec(meeting_id(t.template, day, t.time), day, t.time, t.label, t.groups))
    specs.sort(key=lambda s: (s.date, s.time, s.id))
    return specs
