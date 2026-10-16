"""HL7 v2 messages of the simulated RIS (T086): builder plus a reference mapping to FHIR.

`build_orm` announces a planned exam (ORM^O01), `build_oru` a finished report (ORU^R01). All content is
synthetic. `map_orm` / `map_oru` are the Python mirror of the IRIS mapping `PacsComparator.HL7.Map`
(iris/src/PacsComparator/HL7/Map.cls): same field use, so the tests pin the contract and the simulator
can show what IRIS is expected to write.

Field use: PID-3.1 patient id | ORC-1 order control (NW/CA) | ORC-2 / OBR-2 placer order number |
OBR-3 filler order number | OBR-4 code^Czech text | OBR-24 modality (DICOM code) |
OBR-15.4 body regions (";" separated) | OBR-27.4 planned date | OBR-7 observation date |
OBR-25 result status | OBX-5 report text, one line per OBX.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

SIM_SYSTEM = "urn:pacs-comparator:simulation"
SOURCE_SYSTEM = "urn:pacs-comparator:hl7-source"
PLACER_SYSTEM = "urn:pacs-comparator:ris-placer-order"
FILLER_SYSTEM = "urn:pacs-comparator:ris-filler-order"
DCM = "http://dicom.nema.org/resources/ontology/DCM"
SENDING_APP = "RIS_SIM"
SENDING_FACILITY = "MOTOL_RIS_SIM"

# pipeline modality name -> DICOM modality code (OBR-24)
DICOM_CODES = {"CT": "CT", "MR": "MR", "PET": "PT", "RTG": "CR", "SONO": "US", "MAMO": "MG", "SCINT": "NM"}
_MODALITY_TEXT = {"PT": "PET", "CR": "RTG", "DX": "RTG", "US": "SONO", "MG": "MAMO", "NM": "SCINT"}
_ESCAPES = {"F": "|", "S": "^", "T": "&", "R": "~", "E": "\\", ".br": "\n"}


def escape(text: str) -> str:
    """HL7 escape for a field value; newlines become the \\.br\\ sequence."""
    out = text.replace("\\", "\\E\\").replace("|", "\\F\\").replace("^", "\\S\\")
    out = out.replace("&", "\\T\\").replace("~", "\\R\\")
    return out.replace("\r\n", "\n").replace("\n", "\\.br\\")


def unescape(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and (j := text.find("\\", i + 1)) != -1:
            out.append(_ESCAPES.get(text[i + 1 : j], ""))
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


@dataclass(frozen=True)
class Order:
    patient_id: str
    placer_order: str
    modality: str  # pipeline name: CT, MR, PET, RTG, SONO, MAMO, SCINT
    regions: tuple[str, ...]
    service_text: str
    planned_date: date | None = None
    control: str = "NW"  # NW new order, CA cancel


@dataclass(frozen=True)
class Report:
    patient_id: str
    filler_order: str
    modality: str
    service_text: str
    lines: tuple[str, ...]
    placer_order: str = ""
    observed: date | None = None
    status: str = "F"


def _stamp(now: datetime | None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d%H%M%S")


def _msh(message_type: str, control_id: str, now: datetime | None) -> str:
    return (f"MSH|^~\\&|{SENDING_APP}|{SENDING_FACILITY}|PACSCMP|MOTOL|{_stamp(now)}||{message_type}"
            f"|{control_id}|P|2.5")


def _pid(patient_id: str) -> str:
    return f"PID|1||{escape(patient_id)}^^^MOTOL^MR||SIMULACE^PACIENT"


def _hl7_date(value: date | None) -> str:
    return value.strftime("%Y%m%d") if value else ""


def build_orm(order: Order, now: datetime | None = None) -> str:
    """ORM^O01 as one string, segments separated by CR."""
    code = DICOM_CODES[order.modality]
    placer = escape(order.placer_order)
    segments = [
        _msh("ORM^O01", f"ORM{placer}", now),
        _pid(order.patient_id),
        f"ORC|{order.control}|{placer}||||||||{_stamp(now)}",
        (f"OBR|1|{placer}||{code}^{escape(order.service_text)}^L|||||||||||^^^{escape(';'.join(order.regions))}"
         f"|||||||||{code}|||^^^{_hl7_date(order.planned_date)}"),
    ]
    return "\r".join(segments) + "\r"


def build_oru(report: Report, now: datetime | None = None) -> str:
    """ORU^R01 as one string; every report line is its own OBX-5 (TX)."""
    code = DICOM_CODES[report.modality]
    filler = escape(report.filler_order)
    segments = [
        _msh("ORU^R01", f"ORU{filler}", now),
        _pid(report.patient_id),
        f"OBR|1|{escape(report.placer_order)}|{filler}|{code}^{escape(report.service_text)}^L|||{_hl7_date(report.observed)}"
        f"|||||||||||||||||{code}|{report.status}",
    ]
    segments += [f"OBX|{i}|TX|REPORT^Nález^L||{escape(line)}||||||{report.status}"
                 for i, line in enumerate(report.lines, 1)]
    return "\r".join(segments) + "\r"


# ---- parsing and reference mapping -------------------------------------------------------------------


def parse(message: str) -> list[list[str]]:
    """Segments of a message as lists of fields (field 0 is the segment name; MSH keeps its numbering)."""
    segments = [s for s in message.replace("\r\n", "\r").replace("\n", "\r").split("\r") if s]
    parsed = [s.split("|") for s in segments]
    for seg in parsed:
        if seg[0] == "MSH":
            seg.insert(1, "|")  # MSH-1 is the separator itself
    return parsed


def _field(segments: list[list[str]], name: str, number: int, component: int = 0, nth: int = 1) -> str:
    matches = [s for s in segments if s[0] == name]
    if len(matches) < nth or len(matches[nth - 1]) <= number:
        return ""
    value = matches[nth - 1][number]
    if component:
        parts = value.split("^")
        value = parts[component - 1] if len(parts) >= component else ""
    return unescape(value.strip())


def message_type(message: str) -> str:
    seg = parse(message)[0]
    return seg[9] if len(seg) > 9 else ""


def _fhir_date(value: str) -> str:
    value = value[:8]
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 and value.isdigit() else ""


def safe_id(value: str) -> str:
    return "RIS-" + "".join(c if c.isascii() and (c.isalnum() or c in "-.") else "-" for c in value)[:60]


def _meta(source_type: str) -> dict:
    return {"tag": [{"system": SIM_SYSTEM, "code": "simulated", "display": "Simulace"},
                    {"system": SOURCE_SYSTEM, "code": source_type, "display": "HL7 v2 ze simulovaného RIS"}]}


def map_orm(message: str) -> dict | None:
    """FHIR ServiceRequest of an ORM^O01; None without patient id or placer order number."""
    seg = parse(message)
    patient = _field(seg, "PID", 3, 1)
    placer = _field(seg, "ORC", 2, 1) or _field(seg, "OBR", 2, 1)
    if not patient or not placer:
        return None
    modality = _field(seg, "OBR", 24) or _field(seg, "OBR", 4, 1)
    resource: dict = {
        "resourceType": "ServiceRequest",
        "id": safe_id(placer),
        "meta": _meta("ORM^O01"),
        "identifier": [{"system": PLACER_SYSTEM, "value": placer}],
        "status": "revoked" if _field(seg, "ORC", 1) in ("CA", "DC") else "active",
        "intent": "order",
        "category": [{"coding": [{"system": "http://snomed.info/sct", "code": "363679005", "display": "Imaging"}]}],
        "code": {"coding": [{"system": DCM, "code": modality}], "text": _MODALITY_TEXT.get(modality, modality)},
        "subject": {"reference": f"Patient/{patient}"},
    }
    regions = [r.strip() for r in _field(seg, "OBR", 15, 4).split(";") if r.strip()]
    if regions:
        resource["bodySite"] = [{"text": r} for r in regions]
    planned = _fhir_date(_field(seg, "OBR", 27, 4)) or _fhir_date(_field(seg, "ORC", 7, 4))
    if planned:
        resource["occurrenceDateTime"] = planned
    if authored := _fhir_date(_field(seg, "MSH", 7)):
        resource["authoredOn"] = authored
    resource["requester"] = {"display": f"{_field(seg, 'MSH', 4)} (simulovaný RIS)"}
    if text := _field(seg, "OBR", 4, 2):
        resource["note"] = [{"text": f"Služba: {text} (HL7 v2 ORM^O01, simulace)"}]
    return resource


def map_oru(message: str) -> dict | None:
    """FHIR DiagnosticReport of an ORU^R01; None without patient id or filler order number."""
    seg = parse(message)
    patient = _field(seg, "PID", 3, 1)
    filler = _field(seg, "OBR", 3, 1)
    if not patient or not filler:
        return None
    placer = _field(seg, "OBR", 2, 1)
    modality = _field(seg, "OBR", 24) or _field(seg, "OBR", 4, 1)
    lines = [_field([s], "OBX", 5) for s in seg if s[0] == "OBX" and _field([s], "OBX", 2) in ("TX", "FT", "ST")]
    status = {"P": "preliminary", "C": "corrected", "A": "amended"}.get(_field(seg, "OBR", 25), "final")
    resource: dict = {
        "resourceType": "DiagnosticReport",
        "id": safe_id(filler),
        "meta": _meta("ORU^R01"),
        "identifier": [{"system": FILLER_SYSTEM, "value": filler}],
        "status": status,
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "RAD"}]}],
        "code": {"coding": [{"system": DCM, "code": modality}],
                 "text": _field(seg, "OBR", 4, 2) or _MODALITY_TEXT.get(modality, modality)},
        "subject": {"reference": f"Patient/{patient}"},
        "conclusion": "\n".join(lines),
    }
    if placer:
        resource["basedOn"] = [{"identifier": {"system": PLACER_SYSTEM, "value": placer}}]
    if effective := _fhir_date(_field(seg, "OBR", 7)) or _fhir_date(_field(seg, "MSH", 7)):
        resource["effectiveDateTime"] = effective
    return resource
