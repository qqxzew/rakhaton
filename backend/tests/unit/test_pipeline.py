from __future__ import annotations

from datetime import date

import pytest

from app.llm.schemas import LlmReference
from app.pipeline.availability import DatasetFlagAdapter
from app.pipeline.extract_planned import choose_planned_exam
from app.pipeline.extract_priors import build_reference, needs_llm
from app.pipeline.gaps import build_items, resolve_site
from app.pipeline.match import match_references
from app.pipeline.normalize import (
    add_relative,
    clean_regions,
    normalize_modality,
    normalize_regions,
    parse_partial_date,
    parse_relative,
    regions_overlap,
)
from app.pipeline.readiness import compute_readiness, worst
from app.pipeline.rules import compute_required, load_rules_config
from app.pipeline.schemas import (
    Evidence,
    OpenIssue,
    PartialDate,
    PlannedExam,
    PriorReference,
    QuoteError,
    SourceDoc,
    Study,
    Timeline,
    TreatmentMilestones,
    locate_quote,
)

PID = "PAC-TEST-0001"


def study(sid: str, d: str, modality: str = "CT", regions=("chest",), flag: str = "yes", report: str | None = None):
    return Study(id=sid, patient_id=PID, date=date.fromisoformat(d), modality=modality,
                 regions=list(regions), pacs_flag=flag, report_id=report)


def reference(rid: str, modality: str, ref: str | None, *, regions=("chest",), report="rep-A",
              report_date: str = "2025-09-02", conf: float = 0.9) -> PriorReference:
    return PriorReference(
        id=rid, patient_id=PID, from_report_id=report, from_report_date=date.fromisoformat(report_date),
        modality=modality, regions=list(regions), ref_date=PartialDate.from_iso(ref) if ref else None,
        evidence=Evidence(doc_id=report, quote="q", confidence=conf),
    )


# ---- dates ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text,iso", [
    ("3. 4. 26", "2026-04-03"),
    ("23. 7. 2025", "2025-07-23"),
    ("ze dne 12.5.2025", "2025-05-12"),
    ("11/2025", "2025-11"),
    ("03/25", "2025-03"),
    ("2025-04-09", "2025-04-09"),
])
def test_parse_partial_date(text, iso):
    assert parse_partial_date(text).iso == iso


@pytest.mark.parametrize("text", ["", None, "žádné datum", "31. 2. 2025", "13/2025"])
def test_parse_partial_date_rejects_garbage(text):
    assert parse_partial_date(text) is None


def test_partial_date_month_end():
    assert PartialDate.from_iso("2025-02").end_date() == date(2025, 2, 28)
    assert PartialDate.from_iso("2025-12").end_date() == date(2025, 12, 31)


@pytest.mark.parametrize("text,expected", [
    ("kontrolní CT za 3 měsíce", (3, "months")),
    ("kontrola za 6m", (6, "months")),
    ("rtg plic za 2 týdny", (2, "weeks")),
    ("za 1 rok", (1, "years")),
    ("bez termínu", None),
])
def test_parse_relative(text, expected):
    assert parse_relative(text) == expected


def test_add_relative_clamps_month_end():
    assert add_relative(date(2025, 11, 30), 3, "months") == date(2026, 2, 28)
    assert add_relative(date(2026, 1, 15), -12, "months") == date(2025, 1, 15)


# ---- normalization -------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("CT", "CT"), ("MRI", "MR"), ("PET/CT", "PET"), ("PET-CT", "PET"), ("rtg", "RTG"),
    ("USG", "SONO"), ("MAMO", "MAMO"), ("kostní scan", "SCINT"), ("KAT1", "OTHER"), (None, "UNKNOWN"),
    ("CT hrudníku", "CT"), ("MR pánve - staging", "MR"),
])
def test_normalize_modality(text, expected):
    assert normalize_modality(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("CT hrudníku, břicha a pánve", ["chest", "abdomen", "pelvis"]),
    ("HBMP", ["chest", "abdomen", "pelvis"]),
    ("ORL", ["head", "neck"]),
    ("MR mozku", ["brain"]),
    ("Prsa oboustranně", ["breast"]),
    ("Obrazek prstu", []),
    ("RTG páteře L5", ["spine"]),
])
def test_normalize_regions(text, expected):
    assert normalize_regions(text) == expected


def test_clean_regions_drops_unknown_vocabulary():
    assert clean_regions(["chest", "hrudník", "nonsense"]) == ["chest"]


def test_regions_overlap_rules():
    assert regions_overlap(["chest"], ["chest", "abdomen"])
    assert not regions_overlap(["head"], ["chest"])
    assert regions_overlap(["whole_body"], ["pelvis"])
    assert not regions_overlap([], ["chest"])


# ---- quote validation ----------------------------------------------------------------------

def test_locate_quote_exact_and_whitespace_insensitive():
    text = "Řádek jedna.\r\nSrovnáno  s CT z 3. 4. 2025.\nKonec."
    assert locate_quote(text, "Srovnáno s CT z 3. 4. 2025.") is not None
    start, end = locate_quote(text, "Srovnáno s CT z 3. 4. 2025.")
    assert text[start:end].startswith("Srovnáno")
    assert locate_quote(text, "Tohle tam není") is None


def test_evidence_from_source_rejects_missing_quote():
    with pytest.raises(QuoteError):
        Evidence.from_source("doc", "neexistuje", 0.9, "jiný text")
    ev = Evidence.from_source("doc", "Srovnáno s CT", 0.9, "Text: Srovnáno  s CT z minula")
    assert ev.verify_against("Text: Srovnáno  s CT z minula")


def test_build_reference_drops_when_quote_and_date_missing():
    report = SourceDoc(id="rep-A", kind="radiology_report", date=date(2025, 9, 2), text="Text bez odkazu.")
    raw = LlmReference(modality="CT", quote="vymyšleno", confidence=0.9)
    assert build_reference(raw, report, PID) is None


def test_build_reference_repairs_quote_with_low_confidence():
    report = SourceDoc(id="rep-A", kind="radiology_report", date=date(2025, 9, 2),
                       text="Úvod.\nSrovnáno s CT z 10. 3. 2025 beze změn.\nKonec.")
    raw = LlmReference(modality="CT", date_text="10. 3. 2025", date_iso="2025-03-10",
                       quote="vymyšlená citace", confidence=0.95)
    ref = build_reference(raw, report, PID)
    assert ref is not None and "quote_repaired" in ref.flags
    assert ref.evidence.confidence <= 0.3 and report.text.find(ref.evidence.quote) >= 0


def test_build_reference_flags_implausible_dates():
    report = SourceDoc(id="rep-A", kind="radiology_report", date=date(2025, 9, 2), text="Srovnáno s CT z 3. 4. 2026.")
    future = build_reference(LlmReference(modality="CT", date_text="3. 4. 2026", date_iso="2026-04-03",
                                          quote="Srovnáno s CT z 3. 4. 2026.", confidence=0.9), report, PID)
    assert future is not None and not future.date_valid
    old_report = SourceDoc(id="rep-B", kind="radiology_report", date=date(2025, 9, 2), text="Srovnáno s CT z 3. 4. 2001.")
    old = build_reference(LlmReference(modality="CT", date_text="3. 4. 2001", date_iso="2001-04-03",
                                       quote="Srovnáno s CT z 3. 4. 2001.", confidence=0.9), old_report, PID)
    assert old is not None and not old.date_valid


def test_prefilter():
    assert needs_llm("Ve srovnání s předchozím CT.")
    assert needs_llm("vyšetření z 3. 4. 2025")
    assert not needs_llm("Normální nález bez dalších údajů.")


# ---- matching ------------------------------------------------------------------------------

def test_matching_date_tolerance():
    studies = [study("S1", "2025-03-10")]
    exact = reference("R1", "CT", "2025-03-10")
    near = reference("R2", "CT", "2025-03-13")
    far = reference("R3", "CT", "2025-03-14")
    out = {r.id: r.matched_study_id for r in match_references([exact, near, far], studies)}
    assert out == {"R1": "S1", "R2": "S1", "R3": None}


def test_matching_month_precision_and_modality_and_region():
    studies = [study("S1", "2025-03-10", "CT", ("chest",))]
    month = reference("R1", "CT", "2025-03")
    other_month = reference("R2", "CT", "2025-04")
    wrong_modality = reference("R3", "MR", "2025-03")
    wrong_region = reference("R4", "CT", "2025-03", regions=("head",))
    unknown_region = reference("R5", "CT", "2025-03", regions=())
    out = {r.id: r for r in match_references([month, other_month, wrong_modality, wrong_region, unknown_region], studies)}
    assert out["R1"].matched_study_id == "S1"
    assert out["R2"].matched_study_id is None
    assert out["R3"].matched_study_id is None
    assert out["R4"].matched_study_id is None
    assert out["R5"].matched_study_id == "S1" and "region_unverified" in out["R5"].flags


def test_matching_requires_study_before_citing_report_and_ignores_undated():
    studies = [study("S1", "2025-09-02")]
    same_day = reference("R1", "CT", "2025-09-02", report_date="2025-09-02")
    undated = reference("R2", "CT", None)
    out = {r.id: r.matched_study_id for r in match_references([same_day, undated], studies)}
    assert out == {"R1": None, "R2": None}


def test_pet_reference_never_matches_internal_without_pet():
    out = match_references([reference("R1", "PET", "2025-03-10")], [study("S1", "2025-03-10", "CT")])
    assert out[0].matched_study_id is None


# ---- rules R1-R5 ---------------------------------------------------------------------------

def planned(modality: str = "CT", regions=("chest", "abdomen", "pelvis"), when: str = "2026-05-10") -> PlannedExam:
    return PlannedExam(id="PLAN-1", patient_id=PID, modality=modality, regions=list(regions),
                       date=date.fromisoformat(when), source_doc_id="DOC", evidence=Evidence(
                           doc_id="DOC", quote="q", confidence=0.9))


def base_timeline(**kw) -> Timeline:
    studies = [
        study("S1", "2025-03-10", "CT", ("chest", "abdomen", "pelvis"), report="rep-S1"),
        study("S2", "2025-09-02", "CT", ("chest", "abdomen", "pelvis"), "no", report="rep-S2"),
        study("S3", "2026-01-14", "MR", ("pelvis",), "unknown", report="rep-S3"),
        study("S0", "2024-01-01", "CT", ("chest", "abdomen", "pelvis"), report="rep-S0"),
    ]
    docs = [SourceDoc(id=f"rep-{s.id}", kind="radiology_report", date=s.date, text="x") for s in studies]
    defaults = dict(patient_id=PID, studies=studies, documents=docs,
                    mdt_dates=[date(2025, 10, 1)],
                    treatment=TreatmentMilestones(first_treatment=date(2025, 4, 1)))
    defaults.update(kw)
    return Timeline(**defaults)


def by_rule(cands, rule):
    return {c.key for c in cands if rule in c.rule_ids}


def test_rules_r2_latest_and_second_latest_same_modality():
    cands = compute_required(base_timeline(), [], planned(), date(2026, 5, 10), load_rules_config())
    assert by_rule(cands, "R2") == {"study:S2", "study:S1"}


def test_rules_r3_baseline_before_treatment_start():
    cands = compute_required(base_timeline(), [], planned(), date(2026, 5, 10), load_rules_config())
    assert by_rule(cands, "R3") == {"study:S1"}


def test_rules_r4_complementary_modality_within_window():
    cands = compute_required(base_timeline(), [], planned("CT"), date(2026, 5, 10), load_rules_config())
    assert by_rule(cands, "R4") == {"study:S3"}
    pet_planned = compute_required(base_timeline(), [], planned("PET"), date(2026, 5, 10), load_rules_config())
    assert by_rule(pet_planned, "R4") == {"study:S2"}


def test_rules_r4_ignores_mr_older_than_window():
    timeline = base_timeline()
    cands = compute_required(timeline, [], planned("CT"), date(2027, 6, 1), load_rules_config())
    assert by_rule(cands, "R4") == set()


def test_rules_r5_study_closest_before_last_mdt():
    cands = compute_required(base_timeline(), [], planned(), date(2026, 5, 10), load_rules_config())
    assert by_rule(cands, "R5") == {"study:S2"}


def test_rules_r1_includes_references_of_latest_report_and_dedupes_with_matched_study():
    refs = match_references([
        reference("RA", "CT", "2025-03-10", regions=("chest", "abdomen", "pelvis"), report="rep-S2"),
        reference("RB", "PET", "2025-05-12", regions=(), report="rep-S2"),
    ], base_timeline().studies)
    cands = compute_required(base_timeline(), refs, planned(), date(2026, 5, 10), load_rules_config())
    assert by_rule(cands, "R1") == {"study:S1", "ref:RB"}
    s1 = next(c for c in cands if c.key == "study:S1")
    assert {"R1", "R2", "R3"} <= set(s1.rule_ids) and len(s1.reasons) >= 3


def test_rules_can_be_disabled_per_group(tmp_path):
    cfg = tmp_path / "rules.yaml"
    cfg.write_text("defaults:\n  R2: {enabled: true, count: 2}\n  R3: {enabled: true}\n"
                   "groups:\n  uro:\n    R3: {enabled: false}\n"
                   "reasons:\n  R1: a {report_date}\n  R2: a {modality}\n  R2_previous: b {modality}\n  R3: c\n"
                   "  R4: d {modality}\n  R5: e\n",
                   encoding="utf-8")
    uro = load_rules_config("uro", cfg)
    other = load_rules_config("lung", cfg)
    assert uro["rules"]["R3"]["enabled"] is False and other["rules"]["R3"]["enabled"] is True
    cands = compute_required(base_timeline(), [], planned(), date(2026, 5, 10), uro)
    assert by_rule(cands, "R3") == set()


def test_rules_without_planned_exam_only_use_modality_independent_rules():
    cands = compute_required(base_timeline(), [], None, date(2026, 5, 10), load_rules_config())
    assert by_rule(cands, "R2") == set()
    assert by_rule(cands, "R3") == {"study:S1"}


# ---- availability, gaps and readiness ------------------------------------------------------

def test_availability_mapping_and_items():
    timeline = base_timeline()
    refs = match_references([reference("RB", "PET", "2025-05-12", regions=(), report="rep-S2")], timeline.studies)
    cands = compute_required(timeline, refs, planned(), date(2026, 5, 10), load_rules_config())
    items = {i.study_id or i.reference_id: i for i in build_items(PID, cands, timeline.studies, refs,
                                                                   DatasetFlagAdapter())}
    assert items["S1"].availability == "available" and items["S1"].state == "ok"
    assert items["S2"].availability == "not_in_pacs" and items["S2"].state == "missing"
    assert items["S3"].availability == "unknown" and items["S3"].state == "attention"
    assert items["RB"].availability == "not_found" and items["RB"].state == "missing"


def test_unmatched_reference_with_bad_date_is_attention_not_gap():
    timeline = base_timeline()
    bad = reference("RX", "CT", "2030-01-01", report="rep-S2")
    bad = bad.model_copy(update={"date_valid": False})
    items = build_items(PID, compute_required(timeline, [bad], planned(), date(2026, 5, 10),
                                              load_rules_config()), timeline.studies, [bad], DatasetFlagAdapter())
    item = next(i for i in items if i.reference_id == "RX")
    assert item.state == "attention" and not item.date_valid


def test_resolve_site_by_alias():
    assert resolve_site("Nemocnice Na Homolce (NNH)")[0] == "nnh"
    assert resolve_site("neznámá soukromá klinika")[0] == "unknown"
    assert resolve_site(None)[0] == "unknown"


def _item(state: str, modality: str = "CT"):
    from app.pipeline.schemas import RequiredItem
    return RequiredItem(id=f"i-{state}", rule_ids=["R2"], reasons=["x"], modality=modality,
                        availability={"ok": "available", "attention": "unknown", "missing": "not_found"}[state],
                        state=state, target_date=PartialDate.from_iso("2025-05"), holding_site_name="NNH")


def test_readiness_precedence():
    assert compute_readiness("running", [], []) == ("not_ready", "Probíhá úvodní kontrola")
    assert compute_readiness("failed", [_item("ok")], [])[0] == "not_ready"
    state, reason = compute_readiness("done", [_item("attention"), _item("missing"), _item("ok")], [])
    assert state == "not_ready" and reason.startswith("Chybí: CT 05/2025")
    assert compute_readiness("done", [_item("attention"), _item("ok")], [])[0] == "attention"
    assert compute_readiness("done", [_item("ok")], [OpenIssue(type="time_gap", text="mezera")]) == ("attention", "mezera")
    assert compute_readiness("done", [], []) == ("attention", "Nenalezena žádná předchozí vyšetření")
    assert compute_readiness("done", [_item("ok")], []) == ("ready", "Všechna požadovaná vyšetření ověřena")
    waived = _item("missing").model_copy(update={"waived": True})
    assert compute_readiness("done", [waived], [])[0] == "ready"


def test_worst_state():
    assert worst(["ready", "attention", "not_ready"]) == "not_ready"
    assert worst(["ready", "attention"]) == "attention"
    assert worst([]) == "attention"


# ---- planned exam choice -------------------------------------------------------------------

def exam(when: str | None, modality="CT", kind="imaging", doc_date="2026-02-10", eid="P") -> PlannedExam:
    return PlannedExam(id=eid, patient_id=PID, modality=modality, regions=["chest"],
                       date=date.fromisoformat(when) if when else None, kind=kind, source_doc_id="d",
                       source_doc_date=date.fromisoformat(doc_date),
                       evidence=Evidence(doc_id="d", quote="q", confidence=0.9))


def test_choose_planned_exam_prefers_earliest_upcoming():
    exams = [exam("2026-08-01", eid="A"), exam("2026-05-01", eid="B"), exam("2025-01-01", eid="C")]
    assert choose_planned_exam(exams, date(2026, 2, 10)).id == "B"


def test_choose_planned_exam_falls_back_to_latest_and_skips_rt_planning():
    assert choose_planned_exam([exam("2025-01-01", eid="C"), exam("2025-06-01", eid="D")], date(2026, 2, 10)).id == "D"
    assert choose_planned_exam([exam("2026-05-01", kind="rt_planning", eid="R"),
                                exam("2026-06-01", eid="I")], date(2026, 2, 10)).id == "I"
    assert choose_planned_exam([exam("2026-05-01", kind="rt_planning", eid="R")], date(2026, 2, 10)).id == "R"
    assert choose_planned_exam([exam(None, modality="UNKNOWN", kind="mdt")], None) is None
