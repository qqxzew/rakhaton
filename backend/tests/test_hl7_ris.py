"""Unit tests of the simulated-RIS HL7 v2 builder and its FHIR mapping (synthetic data only)."""

from __future__ import annotations

from datetime import date, datetime

from app.exchange.hl7 import (
    SIM_SYSTEM,
    Order,
    Report,
    build_orm,
    build_oru,
    escape,
    map_orm,
    map_oru,
    message_type,
    parse,
    safe_id,
    unescape,
)

NOW = datetime(2027, 3, 1, 8, 30, 0)
ORDER = Order("PAC-TEST-0001", "TEST-ORD-1", "PET", ("chest", "abdomen", "pelvis"), "PET/CT celého těla",
              date(2027, 3, 20))
REPORT = Report("PAC-TEST-0001", "TEST-RPT-1", "CT", "CT břicha", ("První řádek | s rourou", "Druhý řádek"),
                placer_order="TEST-ORD-1", observed=date(2027, 2, 27))


def test_orm_structure() -> None:
    message = build_orm(ORDER, NOW)
    segments = parse(message)
    assert [s[0] for s in segments] == ["MSH", "PID", "ORC", "OBR"]
    assert message_type(message) == "ORM^O01"
    assert message.endswith("\r") and "\n" not in message


def test_orm_maps_to_service_request() -> None:
    sr = map_orm(build_orm(ORDER, NOW))
    assert sr["resourceType"] == "ServiceRequest"
    assert sr["id"] == "RIS-TEST-ORD-1"
    assert sr["subject"] == {"reference": "Patient/PAC-TEST-0001"}
    assert sr["status"] == "active" and sr["intent"] == "order"
    assert sr["code"]["coding"][0]["code"] == "PT" and sr["code"]["text"] == "PET"
    assert [b["text"] for b in sr["bodySite"]] == ["chest", "abdomen", "pelvis"]
    assert sr["occurrenceDateTime"] == "2027-03-20"
    assert sr["authoredOn"] == "2027-03-01"
    assert sr["identifier"][0]["value"] == "TEST-ORD-1"
    assert {"system": SIM_SYSTEM, "code": "simulated", "display": "Simulace"} in sr["meta"]["tag"]


def test_orm_cancel_is_revoked() -> None:
    cancelled = Order("PAC-TEST-0001", "TEST-ORD-2", "CT", ("chest",), "CT hrudníku", control="CA")
    assert map_orm(build_orm(cancelled, NOW))["status"] == "revoked"


def test_orm_without_planned_date_or_regions() -> None:
    bare = Order("PAC-TEST-0001", "TEST-ORD-3", "MR", (), "MR mozku")
    sr = map_orm(build_orm(bare, NOW))
    assert "occurrenceDateTime" not in sr and "bodySite" not in sr


def test_oru_maps_to_diagnostic_report() -> None:
    message = build_oru(REPORT, NOW)
    assert message_type(message) == "ORU^R01"
    dr = map_oru(message)
    assert dr["resourceType"] == "DiagnosticReport"
    assert dr["id"] == "RIS-TEST-RPT-1"
    assert dr["status"] == "final"
    assert dr["category"][0]["coding"][0]["code"] == "RAD"
    assert dr["conclusion"] == "První řádek | s rourou\nDruhý řádek"
    assert dr["effectiveDateTime"] == "2027-02-27"
    assert dr["basedOn"][0]["identifier"]["value"] == "TEST-ORD-1"
    assert dr["subject"] == {"reference": "Patient/PAC-TEST-0001"}
    assert {"system": SIM_SYSTEM, "code": "simulated", "display": "Simulace"} in dr["meta"]["tag"]


def test_oru_preliminary_status() -> None:
    prelim = Report("PAC-TEST-0001", "TEST-RPT-2", "MR", "MR mozku", ("x",), status="P")
    assert map_oru(build_oru(prelim, NOW))["status"] == "preliminary"


def test_missing_identifiers_are_not_mapped() -> None:
    no_patient = build_orm(ORDER, NOW).replace("PAC-TEST-0001", "")
    assert map_orm(no_patient) is None
    no_filler = build_oru(REPORT, NOW).replace("TEST-RPT-1", "")
    assert map_oru(no_filler) is None


def test_escape_round_trip() -> None:
    text = "a|b^c&d~e\\f\ng"
    assert unescape(escape(text)) == text
    assert "|" not in escape(text) and "\n" not in escape(text)


def test_safe_id_keeps_fhir_characters_only() -> None:
    assert safe_id("A B/1") == "RIS-A-B-1"
    assert len(safe_id("x" * 100)) == 64
