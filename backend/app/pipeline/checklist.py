"""Modality checklist (rule CHK): every patient should have CT, MR, RTG and PET-CT material prepared.

`plan_checklist` is pure. For every checklist modality the patient has evidence of (an internal study or a
cited reference inside the lookback window) or that the group lists as `must_have`, it picks the latest
known study; a must-have modality with nothing known is returned in `missing`. `discover_missing` then asks
the simulated partner hospitals (FHIR search, optionally DICOM C-FIND) whether they hold such a study.
Nothing here ever raises into the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.logging import get_logger
from app.pipeline.normalize import add_relative, regions_overlap
from app.pipeline.schemas import OpenIssue, PartialDate, PlannedExam, PriorReference, RequiredItem, Study, Timeline

log = get_logger(__name__)

RULE_ID = "CHK"
DEFAULT_MODALITIES = ("CT", "MR", "RTG", "PET")
DEFAULT_LOOKBACK_MONTHS = 24
DEFAULT_RTG_REGIONS = ["chest"]
LABELS = {"PET": "PET-CT"}
SIMULATION_SUFFIX = "simulace"


def modality_label(modality: str) -> str:
    return LABELS.get(modality, modality)


@dataclass
class ChecklistPick:
    modality: str
    study: Study | None = None
    reference: PriorReference | None = None

    @property
    def when(self) -> date:
        return self.study.date if self.study else self.reference.ref_date.as_date()  # type: ignore[union-attr]


@dataclass
class ChecklistPlan:
    picks: list[ChecklistPick] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # must-have modalities with no known study
    window: tuple[date, date] | None = None
    regions: dict[str, list[str]] = field(default_factory=dict)  # wanted regions per missing modality


def checklist_regions(modality: str, planned: PlannedExam | None) -> list[str]:
    """RTG is limited to the region of the planned exam (chest when unknown); other modalities are not."""
    if modality != "RTG":
        return []
    return list(planned.regions) if planned and planned.regions else list(DEFAULT_RTG_REGIONS)


def plan_checklist(
    timeline: Timeline,
    references: list[PriorReference],
    planned: PlannedExam | None,
    reference_date: date,
    cfg: dict[str, Any] | None,
) -> ChecklistPlan:
    cfg = cfg or {}
    plan = ChecklistPlan()
    if not cfg.get("enabled", True):
        return plan
    modalities = [str(m).upper() for m in cfg.get("modalities", DEFAULT_MODALITIES)]
    must_have = {str(m).upper() for m in cfg.get("must_have", [])}
    horizon = add_relative(reference_date, -int(cfg.get("lookback_months", DEFAULT_LOOKBACK_MONTHS)), "months")
    plan.window = (horizon, reference_date)
    studies = [s for s in timeline.studies if s.source == "internal" and horizon <= s.date < reference_date]
    # Matched references point at internal studies that are already in `studies` (or outside the window).
    cited = [r for r in references if r.ref_date is not None and r.date_valid and r.matched_study_id is None
             and horizon <= r.ref_date.end_date() and r.ref_date.as_date() < reference_date]

    for modality in dict.fromkeys(modalities + sorted(must_have)):
        wanted = checklist_regions(modality, planned)
        pool: list[ChecklistPick] = [
            ChecklistPick(modality, study=s) for s in studies
            if s.modality == modality and (not wanted or not s.regions or regions_overlap(s.regions, wanted))
        ] + [
            ChecklistPick(modality, reference=r) for r in cited
            if r.modality == modality and (not wanted or not r.regions or regions_overlap(r.regions, wanted))
        ]
        if pool:
            plan.picks.append(max(pool, key=lambda p: (p.when, p.study.id if p.study else p.reference.id)))  # type: ignore[union-attr]
        elif modality in must_have:
            plan.missing.append(modality)
            plan.regions[modality] = wanted
    return plan


# --- discovery -------------------------------------------------------------------------------

@dataclass(frozen=True)
class FoundStudy:
    site_id: str
    site_name: str
    study_date: date
    located_by: str
    provider_ref: str | None = None


# (patient id, pipeline modality, (from, to)) -> latest matching study or None. Raises when nobody could be asked.
Finder = Callable[[str, str, tuple[date, date]], "FoundStudy | None"]
FinderFactory = Callable[[], Finder]


def fhir_finder() -> Finder:
    from app.exchange.hospitals import HospitalError, hospitals, make_client, search_imaging_studies
    from app.pipeline.availability_fhir import LOCATED_BY

    targets = hospitals()
    client = make_client()

    def find(patient_id: str, modality: str, window: tuple[date, date]) -> FoundStudy | None:
        best: FoundStudy | None = None
        reachable = 0
        for hospital in targets:
            try:
                studies = search_imaging_studies(client, hospital, patient_id, modality, window)
            except HospitalError as exc:
                log.warning("checklist FHIR search failed", extra={"fields": {"hospital": hospital.id,
                                                                              "error": str(exc)}})
                continue
            reachable += 1
            for study in studies:
                try:
                    when = date.fromisoformat(str(study.get("started", ""))[:10])
                except ValueError:
                    continue
                if best is None or when > best.study_date:
                    best = FoundStudy(hospital.id, hospital.name, when, LOCATED_BY,
                                      f"{hospital.base_url}/ImagingStudy/{study.get('id')}")
        if best is None and not reachable:
            raise RuntimeError("no hospital FHIR endpoint reachable")
        return best

    return find


def dicom_finder() -> Finder:
    from app.exchange.dicom import MOTOL_ID, DicomError, default_client, nodes
    from app.exchange.hospitals import provider
    from app.pipeline.availability_dicom import LOCATED_BY

    partners = [n for n in nodes().values() if n.id != MOTOL_ID]
    client = default_client()

    def find(patient_id: str, modality: str, window: tuple[date, date]) -> FoundStudy | None:
        best: FoundStudy | None = None
        reachable = 0
        for node in partners:
            try:
                matches = client.find(node.ae, patient_id, window, modality)
            except DicomError as exc:
                log.warning("checklist C-FIND failed", extra={"fields": {"ae": node.ae, "error": str(exc)}})
                continue
            reachable += 1
            for m in matches:
                if m.study_date is None or not window[0] <= m.study_date <= window[1]:
                    continue
                if m.modality not in (modality, None):
                    continue
                if best is None or m.study_date > best.study_date:
                    best = FoundStudy(node.id, (provider(node.id) or {}).get("name") or node.ae, m.study_date,
                                      LOCATED_BY, f"dicom://{node.ae}/{m.accession or ''}".rstrip("/"))
        if best is None and not reachable:
            raise RuntimeError("no PACS node reachable")
        return best

    return find


def default_finders() -> list[FinderFactory]:
    """FHIR hospital search with the IRIS backend; DICOM C-FIND as well when AVAILABILITY_ADAPTER=dicom."""
    from app.config import get_settings

    settings = get_settings()
    if settings.fhir_backend != "iris":
        return []
    finders = [fhir_finder]
    if settings.availability_adapter == "dicom":
        finders.append(dicom_finder)
    return finders


def _built(factory: FinderFactory) -> Finder | None:
    try:
        return factory()
    except Exception as exc:  # noqa: BLE001 - discovery must never break the pipeline
        log.warning("checklist finder unavailable", extra={"fields": {"error": type(exc).__name__}})
        return None


def discover_missing(
    patient_id: str,
    plan: ChecklistPlan,
    items: list[RequiredItem],
    finders: list[FinderFactory] | None = None,
) -> tuple[list[RequiredItem], list[OpenIssue]]:
    """Return `items` extended by hospital studies found for the must-have modalities, plus open issues.

    `finders` are factories (so a failing setup is caught here); None selects the defaults for the backend.
    """
    if not plan.missing or plan.window is None:
        return items, []
    factories = default_finders() if finders is None else finders
    if not factories:
        return items, []
    from app.pipeline.gaps import item_id
    from app.pipeline.rules import fmt_date

    built = [f for f in (_built(factory) for factory in factories) if f is not None]
    out = list(items)
    issues: list[OpenIssue] = []
    unavailable = not built
    for modality in plan.missing:
        label = modality_label(modality)
        found: FoundStudy | None = None
        asked = 0
        for finder in built:
            try:
                found = finder(patient_id, modality, plan.window)
                asked += 1
            except Exception as exc:  # noqa: BLE001 - a failing search is skipped, never raised
                log.warning("checklist discovery failed", extra={"fields": {"error": type(exc).__name__}})
                continue
            if found:
                break
        if found is None:
            if asked:
                issues.append(OpenIssue(type="data", text=f"{label}: nenalezeno v žádném PACS"))
            else:
                unavailable = True
            continue
        target = PartialDate(year=found.study_date.year, month=found.study_date.month, day=found.study_date.day)
        reason = f"Kontrolní seznam: poslední {label}"
        twin = next((i for i in out if i.modality == modality and i.target_date == target), None)
        if twin is not None:  # the same study is already required by another rule
            out[out.index(twin)] = twin.model_copy(update={
                "rule_ids": [*twin.rule_ids, RULE_ID] if RULE_ID not in twin.rule_ids else twin.rule_ids,
                "reasons": [*twin.reasons, reason] if reason not in twin.reasons else twin.reasons})
            continue
        out.append(RequiredItem(
            id=item_id(patient_id, f"chk:{modality}:{found.site_id}:{target.iso}"),
            rule_ids=[RULE_ID], reasons=[reason], modality=modality,
            regions=plan.regions.get(modality, []), target_date=target,
            availability="not_found", state="missing",
            holding_site_id=found.site_id, holding_site_name=found.site_name,
            located_by=found.located_by, provider_study_ref=found.provider_ref,
            note=f"{label} {fmt_date(target)} nalezeno u: {found.site_name} ({SIMULATION_SUFFIX}).",
        ))
    if unavailable:
        issues.append(OpenIssue(type="data", text="Vyhledání chybějících studií u partnerských nemocnic "
                                                  "nebylo dostupné"))
    return out, issues
