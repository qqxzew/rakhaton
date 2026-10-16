"""Turn required-study candidates into items: availability, gap class, holding site, open issues."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from functools import lru_cache

from app.config import CONFIG_DIR
from app.pipeline.availability import AvailabilityAdapter
from app.pipeline.normalize import fold, regions_overlap
from app.pipeline.rules import Candidate, fmt_date
from app.pipeline.schemas import (
    OpenIssue,
    PlannedExam,
    PriorReference,
    RequiredItem,
    Study,
    Timeline,
)

GAP_NOT_IN_PACS = "Studie existuje, snímky nejsou v PACS"
GAP_NOT_FOUND = "Uvedeno v nálezu, ale nenalezeno"
UNKNOWN_SITE_ID = "unknown"
UNKNOWN_SITE_NAME = "Neznámé pracoviště"
FOLLOW_UP_MONTHS = 6


@lru_cache
def load_providers() -> list[dict]:
    return json.loads((CONFIG_DIR / "providers.json").read_text(encoding="utf-8"))


def resolve_site(site_text: str | None) -> tuple[str, str]:
    """Match free text against provider aliases; falls back to the unknown site."""
    if site_text:
        folded = fold(site_text)
        for provider in load_providers():
            for alias in provider.get("aliases", []):
                if re.search(rf"(?<!\w){re.escape(fold(alias))}(?!\w)", folded):
                    return provider["id"], provider["name"]
    return UNKNOWN_SITE_ID, UNKNOWN_SITE_NAME


def item_id(patient_id: str, key: str) -> str:
    return "ITEM-" + hashlib.sha1(f"{patient_id}|{key}".encode()).hexdigest()[:12]


def build_items(
    patient_id: str,
    candidates: list[Candidate],
    studies: list[Study],
    references: list[PriorReference],
    adapter: AvailabilityAdapter,
) -> list[RequiredItem]:
    study_by_id = {s.id: s for s in studies}
    ref_by_id = {r.id: r for r in references}
    items: list[RequiredItem] = []
    for cand in candidates:
        study = study_by_id.get(cand.study_id) if cand.study_id else None
        ref = ref_by_id.get(cand.reference_id) if cand.reference_id else None
        availability = adapter.check(study, ref)
        low_conf = bool(ref and study is None and ref.low_confidence)
        date_valid = ref.date_valid if (ref and study is None) else True

        if availability == "available":
            state = "ok"
        elif availability == "unknown" or low_conf or not date_valid:
            state = "attention"
        else:
            state = "missing"

        site_id = site_name = None
        note = None
        if availability == "not_in_pacs":
            site_id, site_name = "motol", (study.site if study and study.site else "FN Motol")
            note = GAP_NOT_IN_PACS
        elif availability == "not_found":
            site_id, site_name = resolve_site(ref.site_text if ref else None)
            note = GAP_NOT_FOUND
        elif availability == "unknown":
            note = "Dostupnost snímků v PACS není známa"
        if low_conf:
            note = "Nízká jistota extrakce, vyžaduje ověření"
        if not date_valid:
            note = "Datum v nálezu je nepravděpodobné (možný překlep)"

        items.append(RequiredItem(
            id=item_id(patient_id, cand.key),
            rule_ids=cand.rule_ids,
            reasons=cand.reasons,
            modality=cand.modality,
            regions=cand.regions,
            target_date=cand.target_date,
            study_id=cand.study_id,
            reference_id=cand.reference_id,
            availability=availability,
            state=state,
            holding_site_id=site_id,
            holding_site_name=site_name,
            evidence=ref.evidence if ref else None,
            low_confidence=low_conf,
            date_valid=date_valid,
            note=note,
        ))
    return items


def open_issues(
    timeline: Timeline,
    references: list[PriorReference],
    items: list[RequiredItem],
    planned: PlannedExam | None,
    reference_date: date,
) -> list[OpenIssue]:
    issues: list[OpenIssue] = []
    if not planned:
        issues.append(OpenIssue(
            type="data", text="Plánované vyšetření nebylo v dokumentaci nalezeno, zadejte ho ručně"))
    for item in items:
        label = f"{item.modality} {fmt_date(item.target_date)}"
        if item.low_confidence:
            issues.append(OpenIssue(type="low_confidence", item_id=item.id,
                                    text=f"Nízká jistota u položky {label}"))
        if not item.date_valid:
            issues.append(OpenIssue(type="date_typo", item_id=item.id,
                                    text=f"Nepravděpodobné datum odkazu {label}, žádost se nevytváří automaticky"))
        if item.availability == "unknown":
            issues.append(OpenIssue(type="data", item_id=item.id,
                                    text=f"Neznámá dostupnost snímků v PACS: {label}"))
    undated = [r for r in references if r.ref_date is None]
    if undated:
        issues.append(OpenIssue(type="data", text=f"{len(undated)} odkazů na předchozí vyšetření bez data "
                                                   "nelze automaticky přiřadit"))
    for ref in references:
        if "quote_repaired" in ref.flags:
            issues.append(OpenIssue(type="low_confidence",
                                    text="Citace odkazu byla dohledána podle data, ověřte ji ručně"))
            break
    wanted = planned.regions if planned else []
    same_region = [s for s in timeline.studies
                   if s.source == "internal" and s.date < reference_date
                   and (not wanted or not s.regions or regions_overlap(s.regions, wanted))]
    if same_region:
        latest = max(s.date for s in same_region)
        months = (reference_date.year - latest.year) * 12 + reference_date.month - latest.month
        if months > FOLLOW_UP_MONTHS:
            issues.append(OpenIssue(type="time_gap",
                                    text=f"Poslední vyšetření oblasti je staré {months} měsíců"))
    return issues
