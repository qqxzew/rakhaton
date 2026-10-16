"""DicomAvailabilityAdapter and the C-FIND helpers with a mocked DICOM client; synthetic ids only."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.exchange.dicom import (
    CFindClient,
    DicomError,
    DicomMatch,
    PacsNode,
    date_range,
    parse_dicom_date,
    parse_matches,
)
from app.pipeline.availability_dicom import LOCATED_BY, DicomAvailabilityAdapter
from app.pipeline.schemas import Evidence, PartialDate, PriorReference, RequiredItem, Study

PATIENT = "PAC-TEST-0001"
PACS = {
    "motol": PacsNode("motol", "MOTOL", "localhost", 1, "http://x"),
    "nnh": PacsNode("nnh", "NNH", "localhost", 2, "http://x"),
    "homolka": PacsNode("homolka", "HOMOLKA", "localhost", 3, "http://x"),
    "fnm": PacsNode("fnm", "FNM", "localhost", 4, "http://x"),
}


class FakeClient(CFindClient):
    def __init__(self, data: dict[str, list[DicomMatch]] | None = None, down: set[str] | None = None):
        self.data = data or {}
        self.down = down or set()
        self.calls: list[tuple[str, str, tuple[date, date] | None, str | None]] = []

    def find(self, ae, patient_id, window, modality):
        self.calls.append((ae, patient_id, window, modality))
        if ae in self.down:
            raise DicomError("down")
        return [m for m in self.data.get(ae, []) if m.patient_id == patient_id]


def match(ae: str, modality: str, day: date, accession: str = "ACC-1") -> DicomMatch:
    return DicomMatch(PATIENT, day, modality, accession, ae)


def study(flag: str = "yes", day: date = date(2025, 1, 10), modality: str = "CT") -> Study:
    return Study(id="STU-TEST", patient_id=PATIENT, date=day, modality=modality, pacs_flag=flag)


CITED = PartialDate(year=2025, month=3, day=12)


def reference(ref_date: PartialDate = CITED, modality: str = "PET"):
    return PriorReference(id="REF-1", patient_id=PATIENT, from_report_id="rep-TEST", modality=modality,
                          ref_date=ref_date, evidence=Evidence(doc_id="rep-TEST", quote="srovnání", confidence=0.9))


def item(site_id: str = "unknown") -> RequiredItem:
    return RequiredItem(
        id="ITEM-1", rule_ids=["R1"], reasons=["Srovnávací vyšetření"], modality="PET",
        target_date=PartialDate(year=2025, month=3, day=12), reference_id="REF-1", availability="not_found",
        state="missing", holding_site_id=site_id, holding_site_name="Neznámé pracoviště", note="Uvedeno v nálezu")


def adapter(client: FakeClient) -> DicomAvailabilityAdapter:
    return DicomAvailabilityAdapter(client=client, pacs=PACS)


def test_internal_study_found_at_motol_is_available():
    client = FakeClient({"MOTOL": [match("MOTOL", "CT", date(2025, 1, 10))]})
    assert adapter(client).check(study(), None) == "available"
    assert client.calls == [("MOTOL", PATIENT, (date(2025, 1, 10), date(2025, 1, 10)), "CT")]


def test_internal_study_missing_in_pacs_is_not_in_pacs_unless_flag_unknown():
    assert adapter(FakeClient()).check(study("no"), None) == "not_in_pacs"
    assert adapter(FakeClient()).check(study("yes"), None) == "not_in_pacs"
    assert adapter(FakeClient()).check(study("unknown"), None) == "unknown"


def test_pacs_down_falls_back_to_the_dataset_flag():
    client = FakeClient(down={"MOTOL"})
    assert adapter(client).check(study("yes"), None) == "available"
    assert adapter(client).check(study("no"), None) == "not_in_pacs"


def test_wrong_modality_or_date_in_the_answer_is_not_a_hit():
    wrong = FakeClient({"MOTOL": [match("MOTOL", "MR", date(2025, 1, 10)), match("MOTOL", "CT", date(2025, 2, 1))]})
    assert adapter(wrong).check(study(), None) == "not_in_pacs"


def test_received_study_is_available_without_a_query():
    client = FakeClient()
    received = study().model_copy(update={"source": "received"})
    assert adapter(client).check(received, None) == "available"
    assert client.calls == []


def test_reference_without_study_is_not_found_and_holder_is_located_at_partner_ae():
    client = FakeClient({"FNM": [match("FNM", "PET", date(2025, 3, 12), "SIM-FNM-1")]})
    a = adapter(client)
    assert a.check(None, reference()) == "not_found"
    items, issues = a.enrich([item()])
    assert issues == []
    assert items[0].holding_site_id == "fnm" and items[0].located_by == LOCATED_BY
    assert items[0].provider_study_ref == "dicom://FNM/SIM-FNM-1"
    assert [c[0] for c in client.calls] == ["NNH", "HOMOLKA", "FNM"]  # Motol is never asked for partner studies
    assert client.calls[0][2] == (date(2025, 3, 9), date(2025, 3, 15))


def test_resolved_site_is_asked_first():
    client = FakeClient({"HOMOLKA": [match("HOMOLKA", "PET", date(2025, 3, 13))]})
    a = adapter(client)
    a.check(None, reference())
    items, _ = a.enrich([item("homolka")])
    assert items[0].holding_site_id == "homolka"
    assert [c[0] for c in client.calls] == ["HOMOLKA"]


def test_nobody_has_it_gives_an_open_issue_and_keeps_the_site_unknown():
    a = adapter(FakeClient())
    a.check(None, reference())
    items, issues = a.enrich([item()])
    assert items[0].holding_site_id == "unknown" and items[0].located_by is None
    assert len(issues) == 1 and issues[0].item_id == "ITEM-1"


def test_all_pacs_unreachable_claims_nothing():
    a = adapter(FakeClient(down={"NNH", "HOMOLKA", "FNM"}))
    a.check(None, reference())
    items, issues = a.enrich([item()])
    assert items[0] == item()
    assert len(issues) == 1 and "nebyly dostupné" in issues[0].text


def test_enrich_without_references_is_a_noop():
    assert adapter(FakeClient()).enrich([]) == ([], [])


def test_parse_matches_and_helpers():
    payload = json.dumps({"outcome": "OK", "message": "", "matches": [
        {"patientId": PATIENT, "studyDate": "20250312", "modalities": "PT", "accession": "A1"}]})
    (m,) = parse_matches(payload, "NNH")
    assert (m.patient_id, m.study_date, m.modality, m.accession, m.ae) == (PATIENT, date(2025, 3, 12), "PET", "A1", "NNH")
    with pytest.raises(DicomError):
        parse_matches(json.dumps({"outcome": "ERROR", "message": "boom", "matches": []}), "NNH")
    assert parse_dicom_date("2025031") is None and parse_dicom_date("20251341") is None
    assert date_range((date(2025, 3, 9), date(2025, 3, 15))) == "20250309-20250315"
    assert date_range(None) == ""
