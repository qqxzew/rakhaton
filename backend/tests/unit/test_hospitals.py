"""Simulated hospitals: configuration, synthetic resources, date windows. No real data."""

from __future__ import annotations

from datetime import date

from app.exchange.hospitals import (
    SIM_SYSTEM,
    date_window,
    dicom_modality,
    hospitals,
    pipeline_modality,
    representative_date,
)
from app.exchange.synthetic import (
    REPORT_TEXT,
    assign_hospital,
    left_unseeded,
    synthetic_patient,
    synthetic_report,
    synthetic_study,
)
from app.pipeline.schemas import PartialDate
from tests.unit.fhir_fakes import HOSPITALS


def test_hospitals_come_from_providers_json_and_exclude_motol():
    found = {h.id: h.base_url for h in hospitals()}
    assert set(found) >= {"nnh", "homolka", "fnm"}
    assert "motol" not in found
    assert found["nnh"].endswith("/nnh/fhir/r4") and found["fnm"].endswith("/fnm/fhir/r4")


def test_date_windows_follow_citation_precision():
    assert date_window(PartialDate(year=2025, month=3, day=12)) == (date(2025, 3, 9), date(2025, 3, 15))
    assert date_window(PartialDate(year=2025, month=2)) == (date(2025, 2, 1), date(2025, 2, 28))
    assert date_window(PartialDate(year=2025)) == (date(2025, 1, 1), date(2025, 12, 31))
    assert date_window(None) is None


def test_representative_date_lies_inside_the_search_window():
    for target in (PartialDate(year=2025, month=3, day=12), PartialDate(year=2025, month=3), PartialDate(year=2025)):
        start, end = date_window(target)
        assert start <= representative_date(target) <= end


def test_modality_mapping_roundtrip():
    assert dicom_modality("PET") == "PT" and pipeline_modality("PT") == "PET"
    assert dicom_modality("RTG") == "CR" and pipeline_modality("DX") == "RTG"
    assert dicom_modality("UNKNOWN") is None


def test_synthetic_resources_are_labeled_simulated_and_hold_template_text_only():
    patient = synthetic_patient("PAC-TEST-0001")
    study = synthetic_study(HOSPITALS[0], "PAC-TEST-0001", "k", "PET", date(2025, 3, 12), "simulated-holding-site")
    report = synthetic_report(HOSPITALS[0], "PAC-TEST-0001", "k", "PET", date(2025, 3, 12))
    for resource in (patient, study, report):
        assert any(t["system"] == SIM_SYSTEM and t["code"] == "simulated" for t in resource["meta"]["tag"])
    assert any(t["code"] == "simulated-holding-site" for t in study["meta"]["tag"])
    assert report["conclusion"] == REPORT_TEXT and "Simulovaná" in REPORT_TEXT
    assert study["modality"][0]["code"] == "PT" and study["started"] == "2025-03-12"
    assert study["id"].startswith("SIM-") and not study["id"].startswith("STU-")
    assert report["imagingStudy"] == [{"reference": f"ImagingStudy/{study['id']}"}]


def test_assignment_and_unseeded_selection_are_deterministic():
    assert assign_hospital("k1", HOSPITALS) == assign_hospital("k1", HOSPITALS)
    assert {assign_hospital(f"k{i}", HOSPITALS).id for i in range(40)} == {"nnh", "homolka", "fnm"}
    flags = [left_unseeded(f"k{i}", "s", 5) for i in range(500)]
    assert flags == [left_unseeded(f"k{i}", "s", 5) for i in range(500)]
    assert 60 < sum(flags) < 140  # about one in five
