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
from app.pipeline.availability import AvailabilityAdapter, DatasetFlagAdapter, default_adapter
from app.pipeline.availability_dicom import (
    LOCATED_BY,
    SOURCE_CFIND,
    SOURCE_FHIR,
    SOURCE_FLAG,
    DicomAvailabilityAdapter,
)
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


def adapter(client: FakeClient, fallback: AvailabilityAdapter | None = None) -> DicomAvailabilityAdapter:
    return DicomAvailabilityAdapter(client=client, pacs=PACS, fallback=fallback, fhir_fallback=False)


class BoomClient(CFindClient):
    """Fails with something that is not a DicomError (IRIS Native API raises its own types)."""

    def __init__(self):
        self.calls = 0

    def find(self, ae, patient_id, window, modality):
        self.calls += 1
        raise ConnectionRefusedError("orthanc is down")


class FakeFhirFallback(AvailabilityAdapter):
    def __init__(self):
        self.registered: list[str] = []

    def check(self, study, reference):
        if reference is not None:
            self.registered.append(reference.id)
        return "not_found"

    def enrich(self, items):
        return [i.model_copy(update={"holding_site_id": "fnm", "holding_site_name": "FNM", "located_by": "fhir-search"})
                for i in items], []


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
    assert items[0].provider_study_ref is None  # the FHIR ImagingStudy URL is looked up only with the IRIS backend
    assert items[0].availability_source == SOURCE_CFIND
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
    assert items[0] == item().model_copy(update={"availability_source": SOURCE_FLAG})
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


def _settings(monkeypatch, adapter_name: str | None, backend: str | None):
    from app.config import get_settings

    for key, value in (("AVAILABILITY_ADAPTER", adapter_name), ("FHIR_BACKEND", backend)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


def test_dicom_is_the_default_with_the_iris_backend(monkeypatch):
    try:
        assert _settings(monkeypatch, None, None).availability_adapter == "dicom"
        assert isinstance(default_adapter(), DicomAvailabilityAdapter)
        assert _settings(monkeypatch, None, "local").availability_adapter == "dataset_flag"
        assert isinstance(default_adapter(), DatasetFlagAdapter)
        assert _settings(monkeypatch, "fhir_hospitals", "iris").availability_adapter == "fhir_hospitals"
    finally:
        monkeypatch.undo()
        from app.config import get_settings

        get_settings.cache_clear()


def test_availability_source_is_recorded_on_the_items():
    client = FakeClient({"MOTOL": [match("MOTOL", "CT", date(2025, 1, 10))]})
    a = adapter(client)
    assert a.check(study(), None) == "available"
    internal = RequiredItem(id="I1", rule_ids=["R2"], reasons=["x"], modality="CT", study_id="STU-TEST",
                            availability="available", state="ok")
    (enriched,), _ = a.enrich([internal])
    assert enriched.availability_source == SOURCE_CFIND


def test_cfind_error_of_any_type_falls_back_to_the_flag_and_does_not_ask_again():
    client = BoomClient()
    a = adapter(client)
    assert a.check(study("yes"), None) == "available"
    assert a.check(study("no", day=date(2025, 2, 1)), None) == "not_in_pacs"
    assert client.calls == 1  # the PACS is marked down for the rest of the run
    internal = RequiredItem(id="I1", rule_ids=["R2"], reasons=["x"], modality="CT", study_id="STU-TEST",
                            availability="available", state="ok")
    (enriched,), _ = a.enrich([internal])
    assert enriched.availability_source == SOURCE_FLAG


def test_partner_pacs_down_falls_back_to_the_fhir_hospitals():
    fallback = FakeFhirFallback()
    a = adapter(BoomClient(), fallback)
    assert a.check(None, reference()) == "not_found"
    assert fallback.registered == ["REF-1"]
    items, issues = a.enrich([item()])
    assert items[0].holding_site_id == "fnm" and items[0].availability_source == SOURCE_FHIR
    assert items[0].located_by == "fhir-search"
    assert any("nebyly dostupné" in i.text for i in issues)


def test_partner_pacs_down_and_nobody_answers_keeps_the_item_unclaimed():
    class Empty(FakeFhirFallback):
        def enrich(self, items):
            return items, []

    a = adapter(BoomClient(), Empty())
    a.check(None, reference())
    items, _ = a.enrich([item()])
    assert items[0].located_by is None and items[0].availability_source == SOURCE_FLAG
    assert items[0].holding_site_id == "unknown"


def test_a_failing_fallback_never_breaks_enrich():
    class Broken(FakeFhirFallback):
        def enrich(self, items):
            raise RuntimeError("fhir down")

    a = adapter(BoomClient(), Broken())
    a.check(None, reference())
    items, issues = a.enrich([item()])
    assert items[0].located_by is None and len(issues) == 1


def test_health_reports_pacs_status(monkeypatch):
    from app.api import health

    _settings(monkeypatch, "dataset_flag", "local")
    try:
        assert health._check_pacs()["status"] == "skipped"
        _settings(monkeypatch, "dicom", "local")
        monkeypatch.setattr(health, "_probe_orthanc", lambda rest: True)
        monkeypatch.setattr(health, "_probe_cfind", lambda ae: True)
        ok = health._check_pacs()
        assert ok["status"] == "ok" and ok["cfind"] is True and set(ok["orthanc"]) == {"MOTOL", "NNH", "HOMOLKA", "FNM"}
        monkeypatch.setattr(health, "_probe_orthanc", lambda rest: not rest.endswith("8052"))
        degraded = health._check_pacs()
        assert degraded["status"] == "error" and degraded["orthanc"]["NNH"] is False
    finally:
        monkeypatch.undo()
        from app.config import get_settings

        get_settings.cache_clear()
