"""Propose internal studies for cited priors WITHOUT a date ("ve srovnání s předchozím CT").

The citing report is used as the query; the most similar EARLIER radiology reports of the same patient
(same modality family, compatible region) are found with IRIS Vector Search. The best one above a
threshold becomes a low-confidence proposal: the reference keeps `matched_study_id = None`, and the
required item is "requires attention" with the similar report id and the score as evidence. A proposal
is never treated as a confirmed match.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from app.config import get_settings
from app.logging import get_logger
from app.pipeline.gaps import item_id
from app.pipeline.normalize import regions_overlap
from app.pipeline.rules import fmt_date
from app.pipeline.schemas import (
    OpenIssue,
    PlannedExam,
    PriorReference,
    RequiredItem,
    SourceDoc,
    Study,
    Timeline,
)
from app.search.vector_store import REPORT, VectorBackend

log = get_logger(__name__)

MIN_SCORE = float(os.environ.get("VECTOR_MIN_SCORE", "0.55"))
TOP_K = 12
QUERY_CHARS = 500
LOOKBACK_DAYS = 365
RULE_ID = "V1"
_FAMILY = {"CT": "CT/PET", "PET": "CT/PET"}


def default_backend() -> VectorBackend | None:
    """IRIS Vector Search when the IRIS backend is used (VECTOR_MATCH=off disables it)."""
    if os.environ.get("VECTOR_MATCH", "").strip().lower() == "off" or get_settings().fhir_backend != "iris":
        return None
    from app.search.vector_store import IrisVectorBackend

    return IrisVectorBackend()


def _family(modality: str) -> str:
    return _FAMILY.get(modality, modality)


def _compatible(ref_modality: str, study_modality: str) -> bool:
    return "UNKNOWN" in (ref_modality, study_modality) or _family(ref_modality) == _family(study_modality)


def _propose(ref: PriorReference, citing: SourceDoc, citing_study: Study | None, studies: list[Study],
             backend: VectorBackend) -> PriorReference:
    before = ref.from_report_date or citing.date
    by_report = {s.report_id: s for s in studies
                 if s.source == "internal" and s.report_id and (before is None or s.date < before)}
    if not by_report:
        return ref
    hits = backend.search(citing.text[:QUERY_CHARS], patient_id=ref.patient_id, source_type=REPORT,
                          before=before, top_k=TOP_K)
    wanted = ref.regions or (citing_study.regions if citing_study else [])
    best: tuple[float, date, Study] | None = None
    seen: set[str] = set()
    for hit in hits:
        study = by_report.get(hit.source_id)
        if study is None or hit.source_id in seen or not _compatible(ref.modality, study.modality):
            continue
        seen.add(hit.source_id)
        if wanted and study.regions and not regions_overlap(wanted, study.regions):
            continue
        if hit.score >= MIN_SCORE and (best is None or (hit.score, study.date) > best[:2]):
            best = (hit.score, study.date, study)
    if best is None:
        return ref
    return ref.model_copy(update={
        "proposed_study_id": best[2].id, "proposed_report_id": best[2].report_id,
        "proposed_score": round(best[0], 3), "flags": [*ref.flags, "vector_proposed"],
    })


def propose_undated_matches(references: list[PriorReference], timeline: Timeline,
                            backend: VectorBackend | None) -> tuple[list[PriorReference], list[str]]:
    """Add proposals to undated, unmatched references. Backend errors never break the pipeline."""
    if backend is None:
        return references, []
    docs = {d.id: d for d in timeline.documents}
    by_report = {s.report_id: s for s in timeline.studies if s.report_id}
    out: list[PriorReference] = []
    notes: list[str] = []
    for ref in references:
        citing = docs.get(ref.from_report_id)
        if ref.ref_date is not None or ref.matched_study_id or citing is None:
            out.append(ref)
            continue
        try:
            out.append(_propose(ref, citing, by_report.get(citing.id), timeline.studies, backend))
        except Exception as exc:  # noqa: BLE001 - optional enrichment
            log.warning("vector search failed", extra={"fields": {"error": type(exc).__name__}})
            notes.append("vector search unavailable")
            out.append(ref)
    return out, notes


def proposal_items(references: list[PriorReference], items: list[RequiredItem], timeline: Timeline,
                   planned: PlannedExam | None, reference_date: date, adapter) -> tuple[list[RequiredItem],  # noqa: ANN001
                                                                                      list[OpenIssue]]:
    """One 'requires attention' item per proposed study that no other rule already requires."""
    studies = {s.id: s for s in timeline.studies}
    taken = {i.study_id for i in items if i.study_id}
    horizon = reference_date - timedelta(days=LOOKBACK_DAYS)
    wanted = planned.regions if planned else []
    new: dict[str, RequiredItem] = {}
    issues: list[OpenIssue] = []
    for ref in references:
        study = studies.get(ref.proposed_study_id or "")
        if study is None or study.id in taken:
            continue
        if ref.from_report_date and not horizon <= ref.from_report_date <= reference_date:
            continue
        if wanted and study.regions and not regions_overlap(wanted, study.regions):
            continue
        reason = (f"Odkaz na předchozí vyšetření bez data v nálezu z {fmt_date(ref.from_report_date)}, "
                  "navržená shoda podle podobnosti nálezů")
        if study.id in new:
            if reason not in new[study.id].reasons:
                new[study.id].reasons.append(reason)
            continue
        label = f"{study.modality} {fmt_date(study.date)}"
        note = (f"Navržená shoda: {label} (podobný nález, skóre {ref.proposed_score:.2f}), "
                "nízká jistota, ověřte ručně")
        item = RequiredItem(
            id=item_id(ref.patient_id, f"vector:{study.id}"), rule_ids=[RULE_ID], reasons=[reason],
            modality=study.modality, regions=study.regions, target_date=_partial(study.date),
            study_id=study.id, reference_id=ref.id, availability=adapter.check(study, ref), state="attention",
            evidence=ref.evidence, low_confidence=True, note=note,
            proposed_report_id=ref.proposed_report_id, similarity_score=ref.proposed_score,
        )
        new[study.id] = item
        issues.append(OpenIssue(type="low_confidence", item_id=item.id,
                                text=f"Odkaz bez data přiřazen jen podle podobnosti nálezů: {label}"))
    return [*items, *new.values()], issues


def _partial(day: date):  # noqa: ANN202
    from app.pipeline.schemas import PartialDate

    return PartialDate(year=day.year, month=day.month, day=day.day)
