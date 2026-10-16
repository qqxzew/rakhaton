"""Rules engine: which prior studies does a planned examination need (R1 to R5)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.config import CONFIG_DIR
from app.pipeline.normalize import add_relative, regions_overlap
from app.pipeline.schemas import PartialDate, PlannedExam, PriorReference, Study, Timeline

COMPLEMENTARY = {"PET": ("CT",), "MR": ("CT",), "CT": ("PET", "MR")}


class Candidate(BaseModel):
    key: str
    rule_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    study_id: str | None = None
    reference_id: str | None = None
    modality: str = "UNKNOWN"
    regions: list[str] = Field(default_factory=list)
    target_date: PartialDate | None = None


def fmt_date(value: date | PartialDate | None) -> str:
    if value is None:
        return "bez data"
    if isinstance(value, PartialDate):
        if value.day:
            return f"{value.day}. {value.month}. {value.year}"
        return f"{value.month:02d}/{value.year}" if value.month else str(value.year)
    return f"{value.day}. {value.month}. {value.year}"


@lru_cache
def _load_yaml(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_rules_config(group_id: str | None = None, path: Path | None = None) -> dict[str, Any]:
    raw = _load_yaml(str(path or CONFIG_DIR / "rules.yaml"))
    rules = {name: dict(cfg) for name, cfg in raw.get("defaults", {}).items()}
    for name, override in (raw.get("groups", {}).get(group_id or "", {}) or {}).items():
        rules.setdefault(name, {}).update(override or {})
    return {"rules": rules, "reasons": raw.get("reasons", {})}


def _overlaps(item_regions: list[str], wanted: list[str], allow_unknown: bool) -> bool:
    if not wanted:
        return True
    if not item_regions:
        return allow_unknown
    return regions_overlap(item_regions, wanted)


class _Collector:
    def __init__(self) -> None:
        self.items: dict[str, Candidate] = {}

    def add(self, key: str, rule_id: str, reason: str, **fields: Any) -> None:
        cand = self.items.get(key)
        if cand is None:
            cand = Candidate(key=key, **fields)
            self.items[key] = cand
        if rule_id not in cand.rule_ids:
            cand.rule_ids.append(rule_id)
        if reason not in cand.reasons:
            cand.reasons.append(reason)

    def add_study(self, study: Study, rule_id: str, reason: str) -> None:
        self.add(f"study:{study.id}", rule_id, reason, study_id=study.id, modality=study.modality,
                 regions=study.regions,
                 target_date=PartialDate(year=study.date.year, month=study.date.month, day=study.date.day))

    def add_reference(self, ref: PriorReference, rule_id: str, reason: str) -> None:
        if ref.matched_study_id:
            self.items.setdefault(f"study:{ref.matched_study_id}", Candidate(
                key=f"study:{ref.matched_study_id}", study_id=ref.matched_study_id,
                modality=ref.modality, regions=ref.regions, target_date=ref.ref_date))
            cand = self.items[f"study:{ref.matched_study_id}"]
            cand.reference_id = cand.reference_id or ref.id
            if rule_id not in cand.rule_ids:
                cand.rule_ids.append(rule_id)
            if reason not in cand.reasons:
                cand.reasons.append(reason)
            return
        self.add(f"ref:{ref.id}", rule_id, reason, reference_id=ref.id, modality=ref.modality,
                 regions=ref.regions, target_date=ref.ref_date)


def compute_required(
    timeline: Timeline,
    references: list[PriorReference],
    planned: PlannedExam | None,
    reference_date: date,
    config: dict[str, Any] | None = None,
) -> list[Candidate]:
    """Required prior-study candidates, deduplicated with all rule ids and reasons preserved."""
    cfg = config or load_rules_config()
    rules, reasons = cfg["rules"], cfg["reasons"]
    modality = planned.modality if planned else "UNKNOWN"
    wanted = planned.regions if planned else []
    studies = [s for s in timeline.studies if s.source == "internal" and s.date < reference_date]
    study_by_report = {s.report_id: s for s in timeline.studies if s.report_id}
    out = _Collector()

    def enabled(rule: str) -> bool:
        return bool(rules.get(rule, {}).get("enabled", True))

    def ref_regions(ref: PriorReference) -> list[str]:
        if ref.regions:
            return ref.regions
        citing = study_by_report.get(ref.from_report_id)
        return citing.regions if citing else []

    def add_ref(ref: PriorReference, rule_id: str) -> None:
        when = ref.from_report_date
        out.add_reference(ref, rule_id, reasons["R1"].format(report_date=fmt_date(when)))

    if enabled("R1"):
        # Only the most recent report per (modality, region) is trusted to list the priors; older reports in
        # a chain cite studies that the newer report already covers. At most `max_per_group` priors are kept
        # per (cited modality, region).
        cap = int(rules.get("R1", {}).get("max_per_group", 2))
        latest_report: dict[tuple, str] = {}
        for study in sorted(studies, key=lambda s: (s.date, s.id), reverse=True):
            if study.report_id and _overlaps(study.regions, wanted, True):
                latest_report.setdefault((study.modality, tuple(study.regions)), study.report_id)
        latest_ids = set(latest_report.values())
        groups: dict[tuple, list[PriorReference]] = {}
        for ref in references:
            if ref.ref_date is None or ref.from_report_id not in latest_ids:
                continue
            if not _overlaps(ref_regions(ref), wanted, True):
                continue
            groups.setdefault((ref.modality, tuple(ref_regions(ref))), []).append(ref)
        for group in groups.values():
            for ref in sorted(group, key=lambda r: (r.ref_date.end_date(), r.id), reverse=True)[:cap]:
                add_ref(ref, "R1")

    def latest(candidates: list[Study]) -> list[Study]:
        return sorted(candidates, key=lambda s: (s.date, s.id), reverse=True)

    if enabled("R2") and modality not in ("UNKNOWN", "OTHER"):
        same = latest([s for s in studies if s.modality == modality and _overlaps(s.regions, wanted, True)])
        count = int(rules.get("R2", {}).get("count", 2))
        for index, study in enumerate(same[:count]):
            key = "R2" if index == 0 else "R2_previous"
            out.add_study(study, "R2", reasons[key].format(modality=study.modality))

    start = timeline.treatment.first_treatment
    if enabled("R3") and start is not None:
        before = latest([s for s in studies if s.date < start and _overlaps(s.regions, wanted, False)])
        if before:
            out.add_study(before[0], "R3", reasons["R3"])

    if enabled("R4"):
        window = int(rules.get("R4", {}).get("window_months", 12))
        for modal in COMPLEMENTARY.get(modality, ()):
            horizon = add_relative(reference_date, -window, "months") if modal in ("PET", "MR") else date.min
            pool = latest([s for s in studies if s.modality == modal and s.date >= horizon
                           and _overlaps(s.regions, wanted, False)])
            if pool:
                out.add_study(pool[0], "R4", reasons["R4"].format(modality=modal))
        if modality == "CT":
            cited = [r for r in references if r.modality in ("PET", "MR") and r.ref_date is not None
                     and not r.matched_study_id and _overlaps(ref_regions(r), wanted, False)
                     and r.ref_date.end_date() >= add_relative(reference_date, -window, "months")]
            if cited:
                newest = max(cited, key=lambda r: (r.ref_date.as_date(), r.id))
                out.add_reference(newest, "R4", reasons["R4"].format(modality=newest.modality))

    if enabled("R5") and timeline.mdt_dates:
        last_mdt = max(d for d in timeline.mdt_dates if d <= reference_date) \
            if any(d <= reference_date for d in timeline.mdt_dates) else None
        if last_mdt:
            before = latest([s for s in studies if s.date <= last_mdt and _overlaps(s.regions, wanted, True)])
            if before:
                out.add_study(before[0], "R5", reasons["R5"])

    return sorted(out.items.values(), key=lambda c: (c.target_date.as_date() if c.target_date else date.min,
                                                      c.key), reverse=True)
