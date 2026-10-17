"""Czech modality, region and date normalization."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from app.pipeline.schemas import PartialDate

REGION_ORDER = ["head", "brain", "neck", "chest", "abdomen", "pelvis", "spine", "breast",
                "extremity", "whole_body"]


def fold(text: str) -> str:
    """Lower-case and strip diacritics."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


_MODALITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PET", re.compile(r"\bpet(?:\s*[-/]?\s*(?:ct|mr))?\b")),
    ("SCINT", re.compile(r"scinti|scint\b|\bspect\b|kostni scan|izotop")),
    ("MAMO", re.compile(r"\bmamo|\bmamograf")),
    ("MR", re.compile(r"\bmri?\b|magnetick")),
    ("CT", re.compile(r"\bct\b|pocitacov[a-z]* tomograf|\bhrct\b")),
    ("SONO", re.compile(r"\bsono|\busg?\b|\buz\b|ultrazvuk|ultrason")),
    ("RTG", re.compile(r"\brtg\b|\brdg\b|\bskiagraf|rentgen")),
    ("ANGIO", re.compile(r"angiograf|\bptd\b|\bptc\b|koronarograf")),
]


def normalize_modality(text: str | None) -> str:
    """Map free text or a dataset modality code to CT, MR, PET, RTG, SONO, MAMO, SCINT, ANGIO,
    OTHER or UNKNOWN."""
    if not text:
        return "UNKNOWN"
    folded = fold(text).strip()
    exact = {"ct": "CT", "mr": "MR", "mri": "MR", "pet": "PET", "pet/ct": "PET", "pet-ct": "PET",
             "rtg": "RTG", "rdg": "RTG", "sono": "SONO", "usg": "SONO", "uz": "SONO",
             "mamo": "MAMO", "mg": "MAMO", "scint": "SCINT", "angio": "ANGIO",
             "kat1": "OTHER", "kat2": "OTHER", "arytmo": "OTHER", "unknown": "UNKNOWN"}
    if folded in exact:
        return exact[folded]
    for name, pattern in _MODALITY_PATTERNS:
        if pattern.search(folded):
            return name
    return "UNKNOWN"


_REGION_PATTERNS: list[tuple[tuple[str, ...], re.Pattern[str]]] = [
    (("chest", "abdomen", "pelvis"), re.compile(r"\bhbmp\b")),
    (("head", "neck"), re.compile(r"\borl\b")),
    (("brain",), re.compile(r"mozk|mozec|intrakran|neurokran")),
    (("head",), re.compile(r"lebk|\bhlav|hlavy")),
    (("neck",), re.compile(r"\bkrk|\bkrcn|\bkrku")),
    (("chest",), re.compile(r"hrud|plic|thorax|mediastin")),
    (("abdomen",), re.compile(r"brich|brisn|abdom|jater|ledvin|pankreat|slezin|zlucn")),
    (("pelvis",), re.compile(r"panev|panv|prostat")),
    (("spine",), re.compile(r"\bpater|\b(?:th|l|c|s)\d{1,2}\b|paterni")),
    (("breast",), re.compile(r"\bprs(?!t)|\bprsa|mamograf|\bmamo\b")),
    (("whole_body",), re.compile(r"celotel|whole.?body|\bcelkov")),
    (("extremity",), re.compile(r"koncetin|koleno|kolen|ramen|stehn|predlokt|loket|zapesti|kycl")),
]


def normalize_regions(text: str | None) -> list[str]:
    if not text:
        return []
    folded = fold(text)
    found: set[str] = set()
    for regions, pattern in _REGION_PATTERNS:
        if pattern.search(folded):
            found.update(regions)
    return [r for r in REGION_ORDER if r in found]


def clean_regions(values: list[str] | None) -> list[str]:
    """Keep only vocabulary regions from an LLM-provided list, mapping synonyms."""
    out: set[str] = set()
    for v in values or []:
        key = fold(v).strip().replace(" ", "_")
        if key in REGION_ORDER:
            out.add(key)
        else:
            out.update(normalize_regions(v))
    return [r for r in REGION_ORDER if r in out]


def regions_overlap(a: list[str], b: list[str]) -> bool:
    if not a or not b:
        return False
    aa, bb = set(a), set(b)
    if "whole_body" in aa or "whole_body" in bb:
        return True
    if "brain" in aa and "head" in bb or "head" in aa and "brain" in bb:
        return True
    return bool(aa & bb)


def report_headline(text: str) -> str:
    """First non-empty line of a report; it usually names the study type and body region."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


def study_regions_from_report(text: str, modality: str | None = None) -> list[str]:
    regions = normalize_regions(report_headline(text))
    if not regions and modality == "MAMO":
        return ["breast"]
    return regions


_DATE_DMY = re.compile(r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4}|\d{2})(?!\d)")
_DATE_MY = re.compile(r"(?<![\d.])(\d{1,2})\s*[/.]\s*(\d{4}|\d{2})(?!\d)")
_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?:-(\d{2}))?(?!\d)")


def _year(text: str) -> int:
    value = int(text)
    return 2000 + value if len(text) == 2 else value


def parse_partial_date(text: str | None) -> PartialDate | None:
    """Parse '3. 4. 26', '23. 7. 2025', '11/2025' or an ISO date; None if not understood."""
    if not text:
        return None
    text = text.strip()
    try:
        if m := _DATE_ISO.search(text):
            return PartialDate(year=int(m[1]), month=int(m[2]), day=int(m[3]) if m[3] else None)
        if m := _DATE_DMY.search(text):
            return PartialDate(year=_year(m[3]), month=int(m[2]), day=int(m[1]))
        if m := _DATE_MY.search(text):
            return PartialDate(year=_year(m[2]), month=int(m[1]))
    except ValueError:
        return None
    return None


_REL = re.compile(
    r"za\s*(?:cca\s*)?(\d{1,2})\s*(m(?:ĕs|ěs)?\w*|mes\w*|m\b|t[yý]d\w*|týd\w*|let|rok\w*|r\b|dn[iyů]\w*)",
    re.IGNORECASE,
)


def parse_relative(text: str | None) -> tuple[int, str] | None:
    """'za 3 měsíce', 'za 6m', 'za 2 týdny' -> (value, unit)."""
    if not text:
        return None
    m = _REL.search(text)
    if not m:
        return None
    value = int(m[1])
    unit_raw = fold(m[2])
    if unit_raw.startswith("m"):
        return value, "months"
    if unit_raw.startswith("t"):
        return value, "weeks"
    if unit_raw.startswith(("l", "r")):
        return value, "years"
    return value, "days"


def add_relative(start: date, value: int, unit: str) -> date:
    if unit == "days":
        return start + timedelta(days=value)
    if unit == "weeks":
        return start + timedelta(weeks=value)
    if unit == "years":
        return _add_months(start, 12 * value)
    return _add_months(start, value)


def _add_months(start: date, months: int) -> date:
    total = start.year * 12 + (start.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    last_day = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day))
