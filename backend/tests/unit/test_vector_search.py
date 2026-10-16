from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.api import search as search_api
from app.main import create_app
from app.pipeline.availability import DatasetFlagAdapter
from app.pipeline.schemas import (
    Evidence,
    PartialDate,
    PlannedExam,
    PriorReference,
    RequiredItem,
    SourceDoc,
    Study,
    Timeline,
)
from app.search.undated import MIN_SCORE, proposal_items, propose_undated_matches
from app.search.vector_store import Hit, split_text

PID = "PAC-TEST-0001"


class FakeVector:
    """Returns canned hits and records the filters it was called with."""

    def __init__(self, hits: list[Hit] | Exception):
        self.hits, self.calls = hits, []

    def search(self, query, patient_id=None, source_type=None, before=None, top_k=5):
        self.calls.append({"patient_id": patient_id, "source_type": source_type, "before": before})
        if isinstance(self.hits, Exception):
            raise self.hits
        return [h for h in self.hits if before is None or h.doc_date is None or h.doc_date < before]


def hit(source_id: str, score: float, d: str = "2025-01-10") -> Hit:
    return Hit("DiagnosticReport", source_id, 0, date.fromisoformat(d), "CT", "synthetic text", score)


def study(sid: str, d: str, modality: str = "CT", regions=("chest",), flag: str = "yes"):
    return Study(id=sid, patient_id=PID, date=date.fromisoformat(d), modality=modality,
                 regions=list(regions), pacs_flag=flag, report_id=f"rep-{sid}")


def undated_ref(modality: str = "CT", regions=("chest",)) -> PriorReference:
    return PriorReference(
        id="REF-1", patient_id=PID, from_report_id="rep-NOW", from_report_date=date(2025, 6, 1),
        modality=modality, regions=list(regions), ref_date=None,
        evidence=Evidence(doc_id="rep-NOW", quote="ve srovnání s předchozím CT", confidence=0.8),
    )


def timeline(*studies: Study) -> Timeline:
    now = study("NOW", "2025-06-01")
    doc = SourceDoc(id="rep-NOW", kind="radiology_report", date=now.date, text="Synthetic report text.")
    return Timeline(patient_id=PID, studies=[*studies, now], documents=[doc])


def test_proposes_best_similar_earlier_study():
    tl = timeline(study("A", "2025-01-10"), study("B", "2025-03-01"))
    backend = FakeVector([hit("rep-A", 0.62), hit("rep-B", 0.81, "2025-03-01")])
    refs, notes = propose_undated_matches([undated_ref()], tl, backend)
    assert notes == []
    ref = refs[0]
    assert ref.matched_study_id is None  # a proposal is never a confirmed match
    assert (ref.proposed_study_id, ref.proposed_report_id, ref.proposed_score) == ("B", "rep-B", 0.81)
    assert "vector_proposed" in ref.flags
    call = backend.calls[0]
    assert call["patient_id"] == PID and call["source_type"] == "DiagnosticReport"
    assert call["before"] == date(2025, 6, 1)


def test_no_proposal_below_threshold_or_for_wrong_modality_or_region():
    tl = timeline(study("A", "2025-01-10", "MR"), study("B", "2025-03-01", regions=("head",)),
                  study("C", "2025-02-01"))
    hits = [hit("rep-A", 0.9), hit("rep-B", 0.9), hit("rep-C", MIN_SCORE - 0.01)]
    refs, _ = propose_undated_matches([undated_ref()], tl, FakeVector(hits))
    assert refs[0].proposed_study_id is None


def test_ct_and_pet_are_one_modality_family():
    tl = timeline(study("P", "2025-02-01", "PET"))
    refs, _ = propose_undated_matches([undated_ref("CT")], tl, FakeVector([hit("rep-P", 0.7)]))
    assert refs[0].proposed_study_id == "P"


def test_dated_references_are_left_alone_and_backend_errors_are_contained():
    tl = timeline(study("A", "2025-01-10"))
    dated = undated_ref().model_copy(update={"ref_date": PartialDate.from_iso("2025-01-10")})
    backend = FakeVector([hit("rep-A", 0.9)])
    refs, _ = propose_undated_matches([dated], tl, backend)
    assert refs[0].proposed_study_id is None and backend.calls == []
    refs, notes = propose_undated_matches([undated_ref()], tl, FakeVector(RuntimeError("down")))
    assert refs[0].proposed_study_id is None and notes == ["vector search unavailable"]
    assert propose_undated_matches([undated_ref()], tl, None)[1] == []


def planned() -> PlannedExam:
    return PlannedExam(id="PLAN", patient_id=PID, modality="CT", regions=["chest"], source_doc_id="d",
                       evidence=Evidence(doc_id="d", quote="q", confidence=0.9))


def test_proposal_becomes_attention_item_with_similarity_evidence():
    tl = timeline(study("A", "2025-03-01"))
    refs, _ = propose_undated_matches([undated_ref()], tl, FakeVector([hit("rep-A", 0.77, "2025-03-01")]))
    items, issues = proposal_items(refs, [], tl, planned(), date(2025, 7, 1), DatasetFlagAdapter())
    assert len(items) == 1 and len(issues) == 1 and issues[0].type == "low_confidence"
    item = items[0]
    assert item.state == "attention" and item.low_confidence and item.rule_ids == ["V1"]
    assert (item.study_id, item.proposed_report_id, item.similarity_score) == ("A", "rep-A", 0.77)
    assert item.availability == "available" and "0.77" in (item.note or "")


def test_proposal_not_duplicated_when_study_already_required_or_too_old():
    tl = timeline(study("A", "2025-03-01"))
    refs, _ = propose_undated_matches([undated_ref()], tl, FakeVector([hit("rep-A", 0.77, "2025-03-01")]))
    existing = RequiredItem(id="I", rule_ids=["R2"], reasons=["x"], modality="CT", study_id="A",
                            availability="available", state="ok")
    items, issues = proposal_items(refs, [existing], tl, planned(), date(2025, 7, 1), DatasetFlagAdapter())
    assert items == [existing] and issues == []
    items, _ = proposal_items(refs, [], tl, planned(), date(2027, 1, 1), DatasetFlagAdapter())
    assert items == []


def test_split_text_chunks():
    assert split_text("  ") == [] and split_text("short") == ["short"]
    parts = split_text("a" * 1100)
    assert len(parts) == 3 and "".join(parts) == "a" * 1100


def test_search_endpoint_hides_text_by_default():
    fake = FakeVector([hit("rep-A", 0.9), Hit("DiagnosticReport", "rep-A", 1, date(2025, 1, 10), "CT", "t", 0.8),
                       hit("rep-B", 0.7)])
    app = create_app()
    app.dependency_overrides[search_api.get_vector_backend] = lambda: fake
    with TestClient(app) as client:
        body = client.get("/api/search/reports", params={"patient_id": PID, "q": "srovnání", "top": 5}).json()
        assert [h["id"] for h in body["hits"]] == ["rep-A", "rep-B"]
        assert all(h["text"] is None for h in body["hits"]) and body["hits"][0]["score"] == 0.9
        with_text = client.get("/api/search/reports", params={"patient_id": PID, "q": "srovnání",
                                                             "include_text": "true"}).json()
        assert with_text["hits"][0]["text"] == "synthetic text"
        assert client.get("/api/search/reports", params={"patient_id": "a b", "q": "xx"}).status_code == 422
