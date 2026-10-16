"""FhirHospitalAdapter against mocked hospital FHIR endpoints; synthetic ids only."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from app.pipeline.availability_fhir import LOCATED_BY, FhirHospitalAdapter
from app.pipeline.schemas import Evidence, PartialDate, PriorReference, RequiredItem, Study
from tests.unit.fhir_fakes import FNM, HOMOLKA, HOSPITALS, NNH, FakeFhir, imaging_study

PATIENT = "PAC-TEST-0001"


CITED = PartialDate(year=2025, month=3, day=12)


def reference(modality: str = "PET", ref_date: PartialDate | None = CITED,
              site_text: str | None = None) -> PriorReference:
    return PriorReference(
        id="REF-1", patient_id=PATIENT, from_report_id="rep-STU-TEST", modality=modality,
        ref_date=ref_date, site_text=site_text,
        evidence=Evidence(doc_id="rep-STU-TEST", quote="ve srovnání s", confidence=0.9),
    )


def item(site_id: str = "unknown", site_name: str = "Neznámé pracoviště", modality: str = "PET") -> RequiredItem:
    return RequiredItem(
        id="ITEM-1", rule_ids=["R1"], reasons=["Srovnávací vyšetření"], modality=modality,
        target_date=PartialDate(year=2025, month=3, day=12), reference_id="REF-1", availability="not_found",
        state="missing", holding_site_id=site_id, holding_site_name=site_name, note="Uvedeno v nálezu",
    )


def run(fake: FakeFhir, it: RequiredItem, ref: PriorReference):
    adapter = FhirHospitalAdapter(client=fake.client(), targets=HOSPITALS)
    assert adapter.check(None, ref) == "not_found"
    items, issues = adapter.enrich([it])
    return items[0], issues


def test_internal_studies_keep_the_motol_pacs_flag():
    adapter = FhirHospitalAdapter(client=FakeFhir().client(), targets=HOSPITALS)
    study = Study(id="STU-TEST", patient_id=PATIENT, date=date(2025, 1, 1), modality="CT", pacs_flag="no")
    assert adapter.check(study, None) == "not_in_pacs"
    study = study.model_copy(update={"pacs_flag": "yes"})
    assert adapter.check(study, None) == "available"
    assert adapter.enrich([]) == ([], [])


def test_unknown_site_searches_all_hospitals_and_locates_the_holder():
    fake = FakeFhir()
    fake.add(FNM.base_url, imaging_study("SIM-1", PATIENT, "PT", "2025-03-12"))
    located, issues = run(fake, item(), reference())
    assert located.holding_site_id == "fnm"
    assert located.located_by == LOCATED_BY
    assert located.provider_study_ref == f"{FNM.base_url}/ImagingStudy/SIM-1"
    assert located.availability == "not_found"  # still absent from Motol
    assert issues == []
    searched = [urlparse(str(c.url)).path for c in fake.calls]
    assert searched[0].startswith("/nnh/") and any(p.startswith("/fnm/") for p in searched)


def test_resolved_holding_site_is_queried_first_and_alone_when_it_has_the_study():
    fake = FakeFhir()
    fake.add(FNM.base_url, imaging_study("SIM-1", PATIENT, "PT", "2025-03-12"))
    fake.add(NNH.base_url, imaging_study("SIM-2", PATIENT, "PT", "2025-03-12"))
    located, _ = run(fake, item("fnm", "FNM"), reference())
    assert located.holding_site_id == "fnm"
    assert [urlparse(str(c.url)).path.split("/")[1] for c in fake.calls] == ["fnm"]


def test_search_uses_subject_date_window_and_modality_filter():
    fake = FakeFhir()
    fake.add(NNH.base_url, imaging_study("SIM-CT", PATIENT, "CT", "2025-03-12"))  # wrong modality
    fake.add(NNH.base_url, imaging_study("SIM-LATE", PATIENT, "PT", "2025-03-20"))  # outside +-3 days
    fake.add(NNH.base_url, imaging_study("SIM-OTHER", "PAC-TEST-0002", "PT", "2025-03-12"))  # other patient
    fake.add(HOMOLKA.base_url, imaging_study("SIM-OK", PATIENT, "PT", "2025-03-14"))
    located, _ = run(fake, item(), reference())
    assert located.holding_site_id == "homolka"
    query = str(fake.calls[0].url)
    assert "subject=Patient%2FPAC-TEST-0001" in query
    assert "started=ge2025-03-09" in query and "started=le2025-03-15" in query


def test_month_precision_uses_the_whole_month_and_picks_the_closest_study():
    fake = FakeFhir()
    fake.add(NNH.base_url, imaging_study("SIM-FAR", PATIENT, "PT", "2025-03-02"))
    fake.add(NNH.base_url, imaging_study("SIM-NEAR", PATIENT, "PT", "2025-03-16"))
    ref = reference(ref_date=PartialDate(year=2025, month=3))
    located, _ = run(fake, item(), ref)
    assert located.provider_study_ref.endswith("SIM-NEAR")


def test_nobody_has_it_keeps_unknown_site_and_raises_an_open_issue():
    located, issues = run(FakeFhir(), item(), reference())
    assert located.holding_site_id == "unknown" and located.located_by is None
    assert "Žádná nemocnice" in (located.note or "")
    assert len(issues) == 1 and issues[0].item_id == "ITEM-1" and "nebyla nalezena" in issues[0].text


def test_known_site_without_the_study_falls_back_to_the_other_hospitals():
    fake = FakeFhir()
    fake.add(HOMOLKA.base_url, imaging_study("SIM-1", PATIENT, "PT", "2025-03-12"))
    located, _ = run(fake, item("fnm", "FNM"), reference())
    assert located.holding_site_id == "homolka"


def test_unreachable_endpoints_never_claim_that_nobody_has_the_study():
    fake = FakeFhir()
    fake.down = {urlparse(h.base_url).path for h in HOSPITALS}
    located, issues = run(fake, item(), reference())
    assert located.located_by is None and "Žádná nemocnice" not in (located.note or "")
    assert [i.text for i in issues if "nebyla nalezena" in i.text] == []


def test_one_unreachable_hospital_does_not_block_the_others():
    fake = FakeFhir()
    fake.down = {"/nnh/fhir/r4"}
    fake.add(FNM.base_url, imaging_study("SIM-1", PATIENT, "PT", "2025-03-12"))
    located, issues = run(fake, item(), reference())
    assert located.holding_site_id == "fnm"
    assert any("nnh" in i.text for i in issues)


def test_reference_without_date_is_not_searched():
    fake = FakeFhir()
    located, issues = run(fake, item(), reference(ref_date=None))
    assert located.located_by is None and issues == [] and fake.calls == []
