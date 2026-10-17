"""Modality checklist rule CHK and hospital discovery, synthetic data only."""

from __future__ import annotations

import copy
from datetime import date

from app.pipeline.availability import DatasetFlagAdapter
from app.pipeline.checklist import FoundStudy, discover_missing, plan_checklist
from app.pipeline.gaps import build_items
from app.pipeline.rules import compute_required, load_rules_config
from app.pipeline.schemas import (
    Evidence,
    PartialDate,
    PlannedExam,
    PriorReference,
    SourceDoc,
    Study,
    Timeline,
)

PID = "PAC-TEST-0001"
REF_DATE = date(2026, 5, 10)


def study(sid: str, d: str, modality: str, regions=("chest",), flag: str = "yes") -> Study:
    return Study(id=sid, patient_id=PID, date=date.fromisoformat(d), modality=modality, regions=list(regions),
                 pacs_flag=flag, report_id=f"rep-{sid}")


def cited(rid: str, modality: str, when: str, regions=()) -> PriorReference:
    return PriorReference(
        id=rid, patient_id=PID, from_report_id="rep-S2", from_report_date=date(2025, 9, 2), modality=modality,
        regions=list(regions), ref_date=PartialDate.from_iso(when),
        evidence=Evidence(doc_id="rep-S2", quote="q", confidence=0.9))


def planned(modality: str = "CT", regions=("chest", "abdomen", "pelvis")) -> PlannedExam:
    return PlannedExam(id="PLAN-1", patient_id=PID, modality=modality, regions=list(regions),
                       date=REF_DATE, source_doc_id="DOC",
                       evidence=Evidence(doc_id="DOC", quote="q", confidence=0.9))


def timeline(studies: list[Study]) -> Timeline:
    docs = [SourceDoc(id=s.report_id or s.id, kind="radiology_report", date=s.date, text="x") for s in studies]
    return Timeline(patient_id=PID, studies=studies, documents=docs)


def config(**chk) -> dict:
    cfg = copy.deepcopy(load_rules_config())
    for rule in ("R1", "R2", "R3", "R4", "R5"):
        cfg["rules"][rule]["enabled"] = False  # isolate CHK unless a test turns another rule on
    cfg["rules"]["CHK"].update(chk)
    return cfg


def chk_keys(cands) -> dict[str, list[str]]:
    return {c.key: c.rule_ids for c in cands if "CHK" in c.rule_ids}


STUDIES = [
    study("S0", "2024-01-01", "CT"),  # older than the 24 month lookback
    study("S1", "2025-03-10", "CT", ("chest", "abdomen", "pelvis")),
    study("S2", "2025-09-02", "CT", ("chest", "abdomen", "pelvis")),
    study("S3", "2026-01-14", "MR", ("pelvis",)),
]


def test_evidenced_modalities_become_chk_items_with_czech_reason():
    cands = compute_required(timeline(STUDIES), [], planned(), REF_DATE, config())
    assert chk_keys(cands) == {"study:S2": ["CHK"], "study:S3": ["CHK"]}  # latest CT and latest MR only
    by_key = {c.key: c for c in cands}
    assert by_key["study:S2"].reasons == ["Kontrolní seznam: poslední CT"]


def test_no_evidence_and_not_must_have_adds_nothing():
    cands = compute_required(timeline([study("S1", "2025-03-10", "CT")]), [], planned(), REF_DATE, config())
    assert set(chk_keys(cands)) == {"study:S1"}  # no RTG, MR or PET invented
    plan = plan_checklist(timeline([]), [], planned(), REF_DATE, config()["rules"]["CHK"])
    assert plan.picks == [] and plan.missing == []


def test_chk_dedupes_with_r2_and_merges_rule_ids_and_reasons():
    cfg = config()
    cfg["rules"]["R2"]["enabled"] = True
    cands = compute_required(timeline(STUDIES), [], planned(), REF_DATE, cfg)
    s2 = next(c for c in cands if c.key == "study:S2")
    assert set(s2.rule_ids) == {"R2", "CHK"}
    assert len(s2.reasons) == 2 and sum(c.key == "study:S2" for c in cands) == 1


def test_cited_reference_in_lookback_is_evidence_for_its_modality():
    refs = [cited("RP", "PET", "2025-05-12"), cited("RO", "PET", "2022-01-01")]
    cands = compute_required(timeline(STUDIES), refs, planned(), REF_DATE, config())
    assert chk_keys(cands)["ref:RP"] == ["CHK"] and "ref:RO" not in chk_keys(cands)


def test_rtg_is_limited_to_the_planned_region():
    studies = [study("X1", "2026-02-01", "RTG", ("chest",)), study("X2", "2026-03-01", "RTG", ("extremity",))]
    cands = compute_required(timeline(studies), [], planned("CT", ("chest",)), REF_DATE, config())
    assert set(chk_keys(cands)) == {"study:X1"}


def test_chk_can_be_disabled_and_lookback_is_configurable():
    assert chk_keys(compute_required(timeline(STUDIES), [], planned(), REF_DATE, config(enabled=False))) == {}
    short = compute_required(timeline(STUDIES), [], planned(), REF_DATE, config(lookback_months=3))
    assert chk_keys(short) == {}


def test_must_have_without_evidence_is_reported_missing_with_wanted_region():
    cfg = config(must_have=["PET", "RTG"])["rules"]["CHK"]
    plan = plan_checklist(timeline(STUDIES), [], planned("CT", ("pelvis",)), REF_DATE, cfg)
    assert plan.missing == ["RTG", "PET"] and plan.regions["RTG"] == ["pelvis"]
    assert plan.window == (date(2024, 5, 10), REF_DATE)


# ---- discovery -----------------------------------------------------------------------------

def missing_plan(modalities=("PET",)):
    cfg = config(must_have=list(modalities))["rules"]["CHK"]
    return plan_checklist(timeline(STUDIES), [], planned(), REF_DATE, cfg)


def base_items():
    tl = timeline(STUDIES)
    cands = compute_required(tl, [], planned(), REF_DATE, config())
    return build_items(PID, cands, tl.studies, [], DatasetFlagAdapter())


def found_at(site="nnh", when=date(2025, 11, 20)):
    return FoundStudy(site, "Nemocnice Na Homolce", when, "fhir-search", f"http://h/{site}/ImagingStudy/1")


def test_discovery_found_becomes_a_missing_item_with_holding_site():
    calls = []

    def factory():
        def find(pid, modality, window):
            calls.append((pid, modality, window))
            return found_at()
        return find

    items, issues = discover_missing(PID, missing_plan(), base_items(), [factory])
    new = next(i for i in items if "CHK" in i.rule_ids and i.modality == "PET")
    assert new.availability == "not_found" and new.state == "missing"
    assert new.holding_site_id == "nnh" and new.located_by == "fhir-search"
    assert new.target_date == PartialDate(year=2025, month=11, day=20)
    assert new.reasons == ["Kontrolní seznam: poslední PET-CT"] and new.simulated
    assert issues == [] and calls == [(PID, "PET", (date(2024, 5, 10), REF_DATE))]


def test_discovery_not_found_anywhere_is_an_open_issue_not_a_gap():
    def nobody_has_it():
        return lambda pid, modality, window: None

    items, issues = discover_missing(PID, missing_plan(), base_items(), [nobody_has_it])
    assert len(items) == len(base_items())
    assert [(i.type, i.text) for i in issues] == [("data", "PET-CT: nenalezeno v žádném PACS")]


def test_discovery_failures_never_raise():
    def broken_factory():
        raise RuntimeError("no endpoint")

    def raising_factory():
        def find(*args):
            raise RuntimeError("down")
        return find

    for factories in ([broken_factory], [raising_factory]):
        items, issues = discover_missing(PID, missing_plan(), base_items(), factories)
        assert len(items) == len(base_items())
        assert [i.text for i in issues] == ["Vyhledání chybějících studií u partnerských nemocnic nebylo dostupné"]


def test_discovery_falls_back_to_the_next_finder():
    def empty():
        return lambda pid, modality, window: None

    def dicom():
        return lambda pid, modality, window: found_at("fnm")

    items, issues = discover_missing(PID, missing_plan(), base_items(), [empty, dicom])
    assert next(i for i in items if i.modality == "PET").holding_site_id == "fnm" and issues == []


def test_discovery_is_skipped_without_finders_or_missing_modalities():
    items = base_items()
    assert discover_missing(PID, missing_plan(), items, []) == (items, [])
    assert discover_missing(PID, missing_plan(()), items, [lambda: (lambda *a: found_at())]) == (items, [])


def test_discovery_merges_into_an_item_for_the_same_study():
    items = base_items()
    mr = next(i for i in items if i.study_id == "S3")
    items = [i.model_copy(update={"modality": "PET"}) if i.id == mr.id else i for i in items]
    out, _ = discover_missing(PID, missing_plan(), items, [lambda: (lambda *a: found_at("fnm", date(2026, 1, 14)))])
    assert len(out) == len(items)
    assert "CHK" in next(i for i in out if i.id == mr.id).rule_ids
