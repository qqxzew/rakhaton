"""Case detail view model: pipeline result -> JSON for the UI, with presentation-only date shifting."""

from __future__ import annotations

import hashlib
from datetime import date

from app.api.schemas import (
    CaseDetail,
    CaseSummary,
    Diagnosis,
    EvidenceView,
    HoldingSite,
    MeetingView,
    OpenIssueView,
    PatientView,
    PlannedExamView,
    RequiredItemView,
    TimelineEntry,
)
from app.app_db.models import Case
from app.config import today
from app.pipeline.availability import AvailabilityAdapter, DatasetFlagAdapter
from app.pipeline.rules import fmt_date
from app.pipeline.schemas import CaseCheckResult, PartialDate, Study
from app.scheduling.anchoring import compute_offset, shift_iso

_FIRST_F = ["Jana", "Eva", "Marie", "Hana", "Lenka", "Petra", "Alena", "Věra", "Zuzana", "Ivana"]
_FIRST_M = ["Jan", "Petr", "Josef", "Pavel", "Martin", "Tomáš", "Jiří", "Karel", "Milan", "Václav"]
_LAST = ["Novák", "Svoboda", "Dvořák", "Černý", "Procházka", "Kučera", "Veselý", "Horák", "Němec", "Marek"]

_ICD_TEXT = {
    "C34": "Zhoubný novotvar průdušky a plic",
    "C50": "Zhoubný novotvar prsu",
    "C61": "Zhoubný novotvar prostaty",
    "C64": "Zhoubný novotvar ledviny",
    "C67": "Zhoubný novotvar močového měchýře",
    "C18": "Zhoubný novotvar tlustého střeva",
    "C20": "Zhoubný novotvar konečníku",
    "C25": "Zhoubný novotvar slinivky břišní",
    "C16": "Zhoubný novotvar žaludku",
    "C22": "Zhoubný novotvar jater",
}


def fictional_name(patient_id: str, sex: str | None) -> str:
    """A generated display name; linking to records is always by pseudonym, never by this name."""
    digest = hashlib.sha256(patient_id.encode()).digest()
    firsts = _FIRST_F if (sex or "").lower().startswith("f") else _FIRST_M
    last = _LAST[digest[1] % len(_LAST)]
    if firsts is _FIRST_F:
        last = last.removesuffix("ý") + "á" if last.endswith("ý") else last + "ová"
    return f"{firsts[digest[0] % len(firsts)]} {last}"


def age_band(birth_year: int | None) -> str:
    if not birth_year:
        return "neznámý"
    age = today().year - birth_year
    low = (age // 10) * 10
    return f"{low}–{low + 9}"


def _shift(day: date, offset: int) -> str:
    return shift_iso(day, offset)


def diagnosis_label(code: str) -> str:
    return f"{code} {_ICD_TEXT.get(code[:3], f'Diagnóza {code}')}"


def _partial(pd: PartialDate | None, offset: int) -> tuple[str | None, str | None]:
    if pd is None:
        return None, None
    anchor = pd.as_date() if pd.day else date(pd.year, pd.month or 6, 15)
    return _shift(anchor, offset), pd.precision


def _study_availability(study: Study, adapter: AvailabilityAdapter):
    return adapter.check(study, None)


def _timeline(result: CaseCheckResult, offset: int, adapter: AvailabilityAdapter) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    for s in result.timeline.studies:
        entries.append(TimelineEntry(
            kind="study", date=_shift(s.date, offset), modality=s.modality, regions=s.regions,
            label=s.headline or f"{s.modality} {fmt_date(s.date)}",
            availability=_study_availability(s, adapter), study_id=s.id, doc_id=s.report_id,
        ))
    for ref in result.references:
        if ref.matched_study_id or ref.ref_date is None:
            continue
        shown, _ = _partial(ref.ref_date, offset)
        entries.append(TimelineEntry(
            kind="referenced", date=shown or "", modality=ref.modality, regions=ref.regions,
            label=f"Zmíněno v nálezu: {ref.modality}" + (f" ({ref.site_text})" if ref.site_text else ""),
            availability="not_found", study_id=None, doc_id=ref.from_report_id,
        ))
    t = result.timeline.treatment
    for label, d in (("Zahájení systémové léčby", t.first_systemic), ("Operace", t.first_surgery),
                     ("Zahájení radioterapie", t.first_radiotherapy)):
        if d:
            entries.append(TimelineEntry(kind="treatment", date=_shift(d, offset), modality=None,
                                         regions=[], label=label, availability=None,
                                         study_id=None, doc_id=None))
    for d in result.timeline.mdt_dates:
        entries.append(TimelineEntry(kind="mdt", date=_shift(d, offset), modality=None, regions=[],
                                     label="Onkologické MDT", availability=None, study_id=None, doc_id=None))
    entries.sort(key=lambda e: (e.date, e.kind))
    return entries


def _evidence(item_evidence) -> EvidenceView | None:
    if item_evidence is None:
        return None
    return EvidenceView(quote=item_evidence.quote, doc_id=item_evidence.doc_id,
                        confidence=item_evidence.confidence)


def build_case_detail(case: Case, result: CaseCheckResult, adapter: AvailabilityAdapter | None = None,
                      display_name: str | None = None) -> CaseDetail:
    adapter = adapter or DatasetFlagAdapter()
    offset = compute_offset(case.meeting.date, result.reference_date, case.date_offset_days)

    items: list[RequiredItemView] = []
    for item in result.items:
        shown, precision = _partial(item.target_date, offset)
        items.append(RequiredItemView(
            id=item.id, reasons=item.reasons, modality=item.modality, regions=item.regions,
            target_date=shown, target_date_precision=precision,
            availability=item.availability, state="ok" if item.waived else item.state,
            holding_site=HoldingSite(id=item.holding_site_id, name=item.holding_site_name or "")
            if item.holding_site_id else None,
            holding_site_basis=item.holding_site_basis,
            evidence=_evidence(item.evidence), simulated=item.simulated, note=item.note,
        ))

    planned = result.planned_exam
    planned_view = PlannedExamView(
        modality="MDT" if planned.kind == "mdt" else planned.modality, regions=planned.regions,
        date=_shift(planned.date, offset) if planned.date else None, site=planned.site_text,
        quote=planned.evidence.quote, source_doc_id=planned.source_doc_id,
        confidence=planned.evidence.confidence,
    ) if planned else None

    tl = result.timeline
    patient = PatientView(
        id=case.patient_id,
        display_name=display_name or case.display_name or fictional_name(case.patient_id, tl.sex),
        sex=tl.sex or "neznámé", age_band=age_band(tl.birth_year),
        diagnoses=[Diagnosis(code=c, text=_ICD_TEXT.get(c[:3], f"Diagnóza {c}")) for c in tl.diagnoses],
    )
    meeting = case.meeting
    return CaseDetail(
        case=CaseSummary(
            id=case.id,
            meeting=MeetingView(id=meeting.id, label=meeting.label, date=meeting.date.isoformat(),
                                time=meeting.time),
            readiness=case.readiness, reason=case.readiness_reason, date_offset_days=offset,
        ),
        patient=patient, planned_exam=planned_view, timeline=_timeline(result, offset, adapter),
        items=items,
        open_issues=[OpenIssueView(type=("data" if i.type == "no_priors" else i.type), text=i.text)
                     for i in result.open_issues],
        check_status=case.check_status, notes=result.notes,
    )
