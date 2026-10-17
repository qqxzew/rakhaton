"""Match cited prior studies to the patient's internal studies."""

from __future__ import annotations

from datetime import timedelta

from app.pipeline.normalize import regions_overlap
from app.pipeline.schemas import PriorReference, Study

DAY_TOLERANCE = timedelta(days=3)


def _modality_compatible(ref_modality: str, study_modality: str) -> bool:
    if "UNKNOWN" in (ref_modality, study_modality):
        return True
    return ref_modality == study_modality


def _score(ref: PriorReference, study: Study) -> tuple[int, int, int] | None:
    """Lower tuple is better; None means no match."""
    if ref.ref_date is None or not _modality_compatible(ref.modality, study.modality):
        return None
    pd = ref.ref_date
    if pd.precision == "day":
        delta = abs(study.date - pd.as_date())
        if delta > DAY_TOLERANCE:
            return None
        date_rank, distance = (0 if delta.days == 0 else 1), delta.days
    elif pd.precision == "month":
        if (study.date.year, study.date.month) != (pd.year, pd.month):
            return None
        date_rank, distance = 2, abs(study.date.day - 15)
    else:
        return None
    if ref.regions and study.regions:
        if not regions_overlap(ref.regions, study.regions):
            return None
        region_rank = 0
    else:
        region_rank = 1
    return date_rank, region_rank, distance


def match_references(references: list[PriorReference], studies: list[Study]) -> list[PriorReference]:
    internal = [s for s in studies if s.source == "internal"]
    matched: list[PriorReference] = []
    for ref in references:
        candidates = [
            s for s in internal
            if ref.from_report_date is None or s.date < ref.from_report_date
        ]
        scored = [(sc, s) for s in candidates if (sc := _score(ref, s)) is not None]
        flags = list(ref.flags)
        if not scored:
            matched.append(ref.model_copy(update={"matched_study_id": None}))
            continue
        scored.sort(key=lambda x: (x[0], x[1].date, x[1].id))
        best_score, best = scored[0]
        if best_score[1] == 1 and "region_unverified" not in flags:
            flags.append("region_unverified")
        matched.append(ref.model_copy(update={"matched_study_id": best.id, "flags": flags}))
    return matched
