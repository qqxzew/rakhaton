"""Extract the planned examination of a case from clinical notes."""

from __future__ import annotations

import hashlib
import re
from datetime import date

from app.llm.client import StructuredLlm
from app.llm.schemas import LlmPlannedExam, PlannedExtraction
from app.pipeline.normalize import (
    add_relative,
    clean_regions,
    fold,
    normalize_modality,
    parse_partial_date,
    parse_relative,
)
from app.pipeline.schemas import Evidence, PlannedExam, SourceDoc, locate_quote

_PREFILTER = re.compile(
    r"kontrol|doporuc|plan|objedn|indikov|doplnit|dovysetr|restaging|"
    r"za\s*\d+\s*(mes|m\b|tyd|let)|\bpet\b|\bmr\b|\bct\b|mdt"
)
MAX_DOCS = 6


def needs_llm(text: str) -> bool:
    return bool(_PREFILTER.search(fold(text)))


def candidate_documents(documents: list[SourceDoc]) -> list[SourceDoc]:
    """Newest-first clinical notes and MDT documents that look like they plan an examination."""
    notes = [d for d in documents if d.kind in ("clinical_note", "mdt") and needs_llm(d.text)]
    notes.sort(key=lambda d: (d.date or date.min, d.id), reverse=True)
    return notes[:MAX_DOCS]


def _exam_id(doc_id: str, quote: str, modality: str) -> str:
    return "PLAN-" + hashlib.sha1(f"{doc_id}|{quote}|{modality}".encode()).hexdigest()[:12]


def build_planned_exam(raw: LlmPlannedExam, doc: SourceDoc, patient_id: str) -> PlannedExam | None:
    span = locate_quote(doc.text, raw.quote)
    if span is None:
        return None
    quote = doc.text[span[0]:span[1]]
    modality = normalize_modality(raw.modality)
    kind = raw.kind
    if "planovaci" in fold(quote):
        kind = "rt_planning"

    exam_date: date | None = None
    relative_text: str | None = None
    explicit = parse_partial_date(raw.date_iso)
    if explicit is not None and explicit.day:
        exam_date = explicit.as_date()
    elif explicit is not None and explicit.month and doc.date is not None:
        exam_date = explicit.end_date()
    rel = (raw.relative.value, raw.relative.unit) if raw.relative else parse_relative(quote)
    if exam_date is None and rel and doc.date is not None:
        exam_date = add_relative(doc.date, rel[0], rel[1])
    if rel:
        relative_text = f"za {rel[0]} {rel[1]}"

    return PlannedExam(
        id=_exam_id(doc.id, quote, modality),
        patient_id=patient_id,
        modality=modality,
        regions=clean_regions(raw.regions),
        date=exam_date,
        relative_text=relative_text,
        site_text=raw.site_text,
        kind=kind,
        source_doc_id=doc.id,
        source_doc_date=doc.date,
        evidence=Evidence(doc_id=doc.id, quote=quote, confidence=raw.confidence),
    )


def extract_planned_exams(
    llm: StructuredLlm, documents: list[SourceDoc], patient_id: str
) -> tuple[list[PlannedExam], list[str]]:
    exams: list[PlannedExam] = []
    notes: list[str] = []
    seen: set[str] = set()
    for doc in candidate_documents(documents):
        user_text = (
            f"Document date: {doc.date.isoformat() if doc.date else 'unknown'}\n"
            f"Document type: {doc.type_label or doc.kind}\n"
            f"Text:\n<<<\n{doc.text}\n>>>"
        )
        result = llm.run("extract_planned", user_text, PlannedExtraction, contains_report_text=True)
        for raw in result.planned:
            exam = build_planned_exam(raw, doc, patient_id)
            if exam is None:
                notes.append("dropped a planned exam whose quote is not in the source text")
                continue
            if exam.id not in seen:
                seen.add(exam.id)
                exams.append(exam)
    return exams, notes


PRIMARY_MODALITIES = ("CT", "MR", "PET")


def _tier(exam: PlannedExam) -> int | None:
    """0: CT/MR/PET and MDT (the customer's task); 1: other imaging (RTG, SONO, ...); 2: RT planning CT."""
    if exam.kind == "mdt":
        return 0
    if exam.kind == "imaging" and exam.modality in PRIMARY_MODALITIES:
        return 0
    if exam.kind == "imaging" and exam.modality not in ("UNKNOWN", "OTHER"):
        return 1
    if exam.kind == "rt_planning":
        return 2
    return None


def choose_planned_exam(exams: list[PlannedExam], latest_doc_date: date | None) -> PlannedExam | None:
    """Pick the planned exam of a case.

    CT, MR, PET and MDT plans come first. RTG, SONO and other imaging are used only when nothing in that
    group exists, and radiotherapy planning CT only when nothing else exists. Within the chosen group:
    the earliest exam on or after the latest document date, else the latest one overall.
    """
    for tier in (0, 1, 2):
        pool = [e for e in exams if _tier(e) == tier]
        if pool:
            return _pick(pool, latest_doc_date)
    return None


def _pick(usable: list[PlannedExam], latest_doc_date: date | None) -> PlannedExam:
    dated = [e for e in usable if e.date is not None]
    if latest_doc_date is not None:
        upcoming = [e for e in dated if e.date >= latest_doc_date]
        if upcoming:
            return min(upcoming, key=lambda e: (e.date, e.id))
    if dated:
        return max(dated, key=lambda e: (e.date, e.id))
    return max(usable, key=lambda e: (e.source_doc_date or date.min, e.id))
