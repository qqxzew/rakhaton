"""Extract references to prior imaging studies from radiology report text (core AI step)."""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

from app.llm.client import StructuredLlm
from app.llm.schemas import LlmReference, PriorExtraction
from app.pipeline.normalize import clean_regions, fold, normalize_modality, parse_partial_date
from app.pipeline.schemas import Evidence, PartialDate, PriorReference, SourceDoc, locate_quote

_PREFILTER = re.compile(
    r"srovn|porovn|oproti|predchoz|minul|\b\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*\d{2,4}\b"
    r"|\bnnh\b|homolk|\bfnm\b|\bvfn\b|\bikem\b|bulovk|thomayer|plzen|\bbrno\b|extern",
)
MAX_AGE_DAYS = 15 * 366


def needs_llm(text: str) -> bool:
    return bool(_PREFILTER.search(fold(text)))


def _sentence_around(source: str, needle: str) -> str | None:
    pos = source.find(needle)
    if pos < 0:
        return None
    start = max(source.rfind("\n", 0, pos), source.rfind(". ", 0, pos)) + 1
    ends = [i for i in (source.find("\n", pos), source.find(". ", pos)) if i >= 0]
    end = min(ends) + 1 if ends else len(source)
    sentence = source[start:end].strip()
    return sentence[:200] if sentence else None


def _reference_id(report_id: str, quote: str, date_iso: str | None, modality: str) -> str:
    digest = hashlib.sha1(f"{report_id}|{quote}|{date_iso}|{modality}".encode()).hexdigest()[:12]
    return f"REF-{digest}"


def build_reference(
    raw: LlmReference, report: SourceDoc, patient_id: str, *, now: date | None = None
) -> PriorReference | None:
    """Validate one model-proposed reference; None when it cannot be tied to the source text."""
    flags: list[str] = []
    confidence = raw.confidence
    span = locate_quote(report.text, raw.quote)
    if span is not None:
        quote = report.text[span[0]:span[1]]
    else:
        repaired = _sentence_around(report.text, raw.date_text) if raw.date_text else None
        if repaired is None:
            return None
        quote = repaired
        confidence = min(confidence, 0.3)
        flags.append("quote_repaired")

    ref_date: PartialDate | None = None
    from_text = parse_partial_date(raw.date_text)
    from_iso = None
    if raw.date_iso:
        try:
            from_iso = PartialDate.from_iso(raw.date_iso)
        except (ValueError, IndexError):
            flags.append("invalid_date_iso")
    ref_date = from_text or from_iso
    if from_text and from_iso and from_text != from_iso:
        flags.append("date_adjusted")

    modality = normalize_modality(raw.modality)
    date_valid = True
    if ref_date is not None:
        report_date = report.date or now
        too_late = report_date is not None and ref_date.as_date() > report_date
        too_old = report_date is not None and (report_date - ref_date.end_date()) > timedelta(days=MAX_AGE_DAYS)
        if too_late or too_old:
            date_valid = False
            flags.append("date_implausible")

    return PriorReference(
        id=_reference_id(report.id, quote, ref_date.iso if ref_date else None, modality),
        patient_id=patient_id,
        from_report_id=report.id,
        from_report_date=report.date,
        modality=modality,
        regions=clean_regions(raw.regions),
        ref_date=ref_date,
        ref_date_text=raw.date_text,
        site_text=raw.site_text,
        evidence=Evidence(doc_id=report.id, quote=quote, confidence=confidence),
        date_valid=date_valid,
        flags=flags,
    )


def extract_references(
    llm: StructuredLlm, report: SourceDoc, patient_id: str, modality: str | None = None
) -> tuple[list[PriorReference], list[str]]:
    """References cited by one radiology report, plus short notes about dropped items."""
    if not needs_llm(report.text):
        return [], []
    user_text = (
        f"Report date: {report.date.isoformat() if report.date else 'unknown'}\n"
        f"Report modality: {modality or 'unknown'}\n"
        f"Report text:\n<<<\n{report.text}\n>>>"
    )
    result = llm.run("extract_priors", user_text, PriorExtraction, contains_report_text=True)
    refs: list[PriorReference] = []
    notes: list[str] = []
    seen: set[str] = set()
    for raw in result.references:
        ref = build_reference(raw, report, patient_id)
        if ref is None:
            notes.append("dropped a reference whose quote is not in the source text")
            continue
        if ref.id in seen:
            continue
        seen.add(ref.id)
        refs.append(ref)
    return refs, notes
