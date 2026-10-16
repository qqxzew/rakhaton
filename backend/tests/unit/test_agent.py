from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.agent import chat as chat_mod
from app.agent import tools
from app.agent.chat import ChatModel, ModelTurn, _ToolsUnsupported, is_advice_request, run_chat
from app.api import agent as agent_api
from app.app_db.models import Case, Meeting
from app.app_db.session import session_scope
from app.main import create_app


class ScriptedModel(ChatModel):
    def __init__(self, turns, native=True):
        self.turns = list(turns)
        self.seen: list[list[dict]] = []
        self.native_tools = native

    def step(self, messages, specs):
        self.seen.append(list(messages))
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


@pytest.fixture
def fake_tools(monkeypatch):
    calls = []

    def fake(name, args):
        calls.append((name, args))
        return {"case": {"items": []}, "sources": ["CASE-1", "ITEM-9"]}

    monkeypatch.setattr(tools, "call_tool", fake)
    return calls


def _call(name="case_overview", **args):
    return ModelTurn(tool_calls=[{"id": "c1", "name": name, "arguments": args}])


def test_native_tool_loop_lists_tools_and_sources(fake_tools):
    model = ScriptedModel([_call(case_id="OTHER"), ModelTurn(text=json.dumps(
        {"answer": "Chybí PET/CT.", "sources": ["ITEM-9", "invented"]}))])
    result = run_chat("CASE-1", "PAC-TEST-0001", "Které snímky chybí?", model)
    assert result.answer == "Chybí PET/CT." and result.mode == "native"
    assert [c["name"] for c in result.tools_called] == ["case_overview"]
    assert result.sources == ["ITEM-9"]
    assert fake_tools[0][1]["case_id"] == "CASE-1"  # pinned to the case, not what the model asked for


def test_patient_id_is_pinned_for_vector_search(fake_tools):
    model = ScriptedModel([_call("vector_search", patient_id="PAC-OTHER", query="srovnání"),
                           ModelTurn(text="hotovo")])
    result = run_chat("CASE-1", "PAC-TEST-0001", "q", model)
    assert fake_tools[0][1]["patient_id"] == "PAC-TEST-0001"
    assert result.answer == "hotovo"


def test_fallback_to_json_plan_when_tools_unsupported(fake_tools):
    model = ScriptedModel([
        _ToolsUnsupported(),
        ModelTurn(text=json.dumps({"tool_calls": [{"name": "case_overview", "arguments": {"case_id": "x"}}]})),
        ModelTurn(text=json.dumps({"answer": "ok", "sources": ["CASE-1"]})),
    ], native=False)
    result = run_chat("CASE-1", "PAC-TEST-0001", "Proč je potřeba toto CT?", model)
    assert result.mode == "json-plan" and result.sources == ["CASE-1"]
    assert "case_overview" in model.seen[-1][0]["content"]


def test_json_protocol_is_used_from_the_start_when_model_has_no_native_tools(fake_tools):
    model = ScriptedModel([ModelTurn(text=json.dumps({"answer": "ok", "sources": []}))], native=False)
    result = run_chat("CASE-1", "PAC-TEST-0001", "q", model)
    assert result.mode == "json-plan" and "Tool protocol" in model.seen[0][0]["content"]


@pytest.mark.parametrize("question", ["Jak mám léčit tohoto pacienta?", "Jaká je diagnóza?", "Doporuč léčbu"])
def test_treatment_and_diagnosis_questions_are_refused_without_llm(question):
    model = ScriptedModel([])
    result = run_chat("CASE-1", "PAC-TEST-0001", question, model)
    assert result.refused and result.tools_called == [] and result.answer == chat_mod.REFUSAL


def test_normal_questions_are_not_refused():
    assert not is_advice_request("Proč je potřeba toto CT?")
    assert not is_advice_request("Které snímky chybí a kde jsou?")


def test_step_limit_returns_message(fake_tools):
    model = ScriptedModel([_call()] * chat_mod.MAX_STEPS)
    result = run_chat("CASE-1", "PAC-TEST-0001", "q", model)
    assert "limitu" in result.answer and len(result.tools_called) == chat_mod.MAX_STEPS


@pytest.mark.parametrize("sql", ["DELETE FROM x", "SELECT 1; DROP TABLE x", "UPDATE t SET a=1", "",
                                 "SELECT * INTO t2 FROM t", "CALL foo()", "/* x */ INSERT INTO t VALUES (1)"])
def test_sql_query_rejects_non_select(sql):
    with pytest.raises(tools.ToolError):
        tools.validate_select(sql)
    assert "error" in tools.call_tool("sql_query", {"sql": sql})


def test_sql_query_runs_select_with_row_limit():
    with session_scope() as db:
        db.add(Meeting(id="MDT-T", date=date(2026, 10, 20), time="10:00", label="L",
                       eligible_groups=[], accepts_registrations=True))
    out = tools.sql_query("SELECT id FROM meeting WHERE id = 'MDT-T'", limit=5)
    assert out["rows"] == [["MDT-T"]] and out["truncated"] is False


def test_fhir_search_validates_input():
    assert "error" in tools.call_tool("fhir_search", {"resource_type": "Patient/../x"})
    assert "error" in tools.call_tool("fhir_search", {"resource_type": "Patient", "endpoint": "nowhere"})
    assert "error" in tools.call_tool("fhir_search", {"resource_type": "Patient", "params": {"a b": "1"}})


def test_vector_search_reports_missing_index(monkeypatch):
    from app.search import vector_store as vs

    def boom():
        raise RuntimeError("no IRIS in unit tests")

    monkeypatch.setattr(vs, "connect", boom)
    out = tools.vector_search("PAC-TEST-0001", "q")
    assert out["available"] is False and out["results"] == []


def test_vector_search_uses_iris_index(monkeypatch):
    from datetime import date as _date

    from app.search import vector_store as vs

    class FakeConn:
        def close(self):
            pass

    hit = vs.Hit("DiagnosticReport", "rep-TEST-1", 0, _date(2026, 1, 2), "CT", "synthetic text", 0.91)
    monkeypatch.setattr(vs, "connect", lambda: FakeConn())
    monkeypatch.setattr(vs, "search", lambda conn, query, patient_id=None, top_k=5, **kw: [hit])
    out = tools.vector_search("PAC-TEST-0001", "q", top=3)
    assert out["available"] is True
    assert out["sources"] == ["rep-TEST-1"] and out["results"][0]["score"] == 0.91


def test_request_status_stub_and_unknown_tool():
    assert tools.request_status("PACS-REQ-000001")["available"] is False
    assert "error" in tools.call_tool("nope", {})


def test_create_task_draft_puts_draft_task(monkeypatch):
    sent = {}

    class Resp:
        status_code = 201

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def put(self, url, json=None, headers=None):
            sent.update(url=url, body=json)
            return Resp()

    monkeypatch.setattr(tools, "_fhir_client", lambda: Client())
    out = tools.create_task_draft("PAC-TEST-0001", "Vyžádat PET/CT", modality="PET")
    assert out["status"] == "draft" and out["sent"] is False
    assert sent["body"]["status"] == "draft" and sent["body"]["resourceType"] == "Task"
    assert sent["url"].endswith(f"/Task/{out['task_id']}")


def test_case_overview_unknown_case():
    assert tools.call_tool("case_overview", {"case_id": "NOPE"})["error"] == "case not found"


def test_chat_endpoint():
    model = ScriptedModel([ModelTurn(text=json.dumps({"answer": "odpověď", "sources": []}))])
    app = create_app()
    app.dependency_overrides[agent_api.get_chat_model] = lambda: model
    with TestClient(app) as c:
        with session_scope() as db:
            db.add(Meeting(id="MDT-A", date=date(2026, 10, 20), time="10:00", label="L",
                           eligible_groups=["uro"], accepts_registrations=True))
            db.add(Case(id="CASE-A", patient_id="PAC-TEST-0001", meeting_id="MDT-A"))
        ok = c.post("/api/agent/chat", json={"case_id": "CASE-A", "question": "Proč?"})
        assert ok.status_code == 200 and ok.json()["answer"] == "odpověď"
        missing = c.post("/api/agent/chat", json={"case_id": "NOPE", "question": "Proč?"})
        assert missing.status_code == 404
