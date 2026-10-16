"""Read-mostly tools over IRIS shared by the MCP server and the chat agent (IRIS Core Track, T089).

Every tool returns a JSON-serialisable dict with a `sources` list (ids the answer may cite).
Nothing here sends anything outside: `create_task_draft` only writes a FHIR Task in status `draft`;
approval and sending stay in the app (hard rule 3).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

MAX_ROWS = 50
MAX_FHIR_ENTRIES = 20
_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_PARAM_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|call|exec|execute|merge|replace|"
    r"load|set|into|lock|kill|use)\b",
    re.IGNORECASE,
)


class ToolError(ValueError):
    """Invalid tool input (reported back to the caller, never raised through the API)."""


# --- FHIR ---------------------------------------------------------------------------------------


def _fhir_base(endpoint: str) -> str:
    """Absolute FHIR base for `motol` or a simulated hospital id (nnh, homolka, fnm)."""
    from app.exchange.hospitals import hospitals, motol_base

    if endpoint in ("", "motol"):
        return motol_base()
    for h in hospitals():
        if h.id == endpoint:
            return h.base_url
    raise ToolError(f"unknown endpoint {endpoint!r}")


def _fhir_client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(auth=(s.iris_user or "SuperUser", s.iris_password or "SYS"), timeout=30,
                        headers={"Accept": "application/fhir+json"})


def _brief(resource: dict[str, Any]) -> dict[str, Any]:
    """Compact, metadata-oriented view of a resource (keeps the answer small)."""
    keep = ("resourceType", "id", "status", "started", "effectiveDateTime", "issued", "date", "intent",
            "modality", "code", "category", "subject", "basedOn", "focus", "businessStatus", "description",
            "conclusion", "meta", "identifier", "restriction")
    return {k: resource[k] for k in keep if k in resource}


def fhir_search(resource_type: str, params: dict[str, str] | None = None, endpoint: str = "motol") -> dict:
    """Read-only FHIR search on Motol (`motol`) or a simulated hospital (`nnh`, `homolka`, `fnm`)."""
    if not _SAFE.match(resource_type):
        raise ToolError("invalid resource type")
    query: dict[str, str] = {}
    for key, value in (params or {}).items():
        if not _PARAM_KEY.match(str(key)):
            raise ToolError(f"invalid search parameter {key!r}")
        query[str(key)] = str(value)
    query["_count"] = str(min(int(query.get("_count", MAX_FHIR_ENTRIES)), MAX_FHIR_ENTRIES))
    base = _fhir_base(endpoint)
    with _fhir_client() as client:
        resp = client.get(f"{base}/{resource_type}", params=query)
    if resp.status_code >= 300:
        raise ToolError(f"FHIR search failed: HTTP {resp.status_code}")
    bundle = resp.json()
    entries = [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
    return {
        "endpoint": endpoint or "motol",
        "simulated": endpoint not in ("", "motol"),
        "total": bundle.get("total"),
        "resources": [_brief(r) for r in entries[:MAX_FHIR_ENTRIES]],
        "sources": [f"{r.get('resourceType')}/{r.get('id')}" for r in entries[:MAX_FHIR_ENTRIES]],
    }


# --- IRIS SQL -----------------------------------------------------------------------------------


def validate_select(sql: str) -> str:
    """Accept exactly one SELECT/WITH statement; reject everything else."""
    stripped = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql or "", flags=re.DOTALL).strip().rstrip(";").strip()
    if not stripped:
        raise ToolError("empty SQL")
    if ";" in stripped:
        raise ToolError("only a single statement is allowed")
    if not re.match(r"^(select|with)\b", stripped, re.IGNORECASE):
        raise ToolError("only SELECT statements are allowed")
    bad = _FORBIDDEN_SQL.search(stripped)
    if bad:
        raise ToolError(f"keyword {bad.group(0).upper()!r} is not allowed in read-only SQL")
    return stripped


def sql_query(sql: str, limit: int = MAX_ROWS) -> dict:
    """Read-only SELECT on the IRIS SQL database (app state and any IRIS tables), capped at `limit` rows."""
    from app.app_db.session import get_engine

    statement = validate_select(sql)
    cap = max(1, min(int(limit), MAX_ROWS))
    with get_engine().connect() as conn:
        result = conn.execute(text(statement))
        columns = list(result.keys())
        rows = result.fetchmany(cap + 1)
    truncated = len(rows) > cap
    return {
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows[:cap]],
        "truncated": truncated,
        "sources": ["iris-sql"],
    }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


# --- Vector search ------------------------------------------------------------------------------


def vector_search(patient_id: str, query: str, top: int = 5) -> dict:
    """Semantic search over the patient's report chunks (IRIS Vector Search, index built by D1:
    app/search/vector_store.py, table PacsVector.ReportChunk, same local multilingual model)."""
    from app.search import vector_store as vs

    if not _SAFE.match(patient_id):
        raise ToolError("invalid patient id")
    top = max(1, min(int(top), 10))
    try:
        conn = vs.connect()
        try:
            hits = vs.search(conn, query, patient_id=patient_id, top_k=top)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - index missing or IRIS/embedding unavailable
        log.info("vector index not available", extra={"fields": {"error": type(exc).__name__}})
        return {"available": False, "message": f"index not available ({vs.TABLE})",
                "results": [], "sources": []}
    results = [{"report_id": h.source_id, "source_type": h.source_type,
                "date": h.doc_date.isoformat() if h.doc_date else None,
                "text": h.text, "score": h.score} for h in hits]
    return {"available": True, "results": results, "sources": [r["report_id"] for r in results]}


# --- App views ----------------------------------------------------------------------------------


def case_overview(case_id: str) -> dict:
    """The case view model used by the UI (readiness, planned exam, required items with evidence)."""
    from app.api.case_views import build_case_detail
    from app.app_db.models import Case
    from app.app_db.session import session_scope
    from app.pipeline.schemas import CaseCheckResult, Timeline

    with session_scope() as db:
        case = db.get(Case, case_id)
        if case is None:
            raise ToolError("case not found")
        if case.result:
            result = CaseCheckResult.model_validate(case.result.result)
        else:
            result = CaseCheckResult(patient_id=case.patient_id, timeline=Timeline(patient_id=case.patient_id),
                                     readiness=case.readiness, readiness_reason=case.readiness_reason)
        detail = build_case_detail(case, result).model_dump(mode="json")
    sources = [case_id] + [i["id"] for i in detail["items"]]
    return {"case": detail, "sources": sources}


def request_status(request_id: str) -> dict:
    """Stub until the request production is merged; replace this one function then."""
    return {"available": False, "request_id": request_id,
            "message": "request status is not available yet", "sources": []}


# --- Drafts -------------------------------------------------------------------------------------


def create_task_draft(patient_id: str, description: str, modality: str = "", body_region: str = "",
                      study_date: str = "", case_id: str = "") -> dict:
    """Create a FHIR Task with status `draft` in Motol's IRIS. Never sends anything; approval stays in the app."""
    if not _SAFE.match(patient_id):
        raise ToolError("invalid patient id")
    if not description.strip():
        raise ToolError("description is required")
    task_id = f"draft-{uuid.uuid4().hex[:12]}"
    task: dict[str, Any] = {
        "resourceType": "Task",
        "id": task_id,
        "meta": {"tag": [{"system": "urn:pacs-comparator:simulation", "code": "agent-draft",
                          "display": "Koncept vytvořený asistentem, vyžaduje schválení"}]},
        "status": "draft",
        "intent": "proposal",
        "businessStatus": {"text": "DRAFTED"},
        "description": description.strip()[:500],
        "for": {"reference": f"Patient/{patient_id}"},
        "authoredOn": datetime.now(UTC).isoformat(timespec="seconds"),
        "requester": {"display": "PACS Komparátor asistent (software)"},
        "input": [{"type": {"text": k}, "valueString": v} for k, v in
                  (("modality", modality), ("body_region", body_region), ("study_date", study_date),
                   ("case_id", case_id)) if v],
    }
    base = _fhir_base("motol")
    with _fhir_client() as client:
        resp = client.put(f"{base}/Task/{task_id}", json=task, headers={"Content-Type": "application/fhir+json"})
    if resp.status_code >= 300:
        raise ToolError(f"Task draft was not created: HTTP {resp.status_code}")
    return {"task_id": task_id, "status": "draft", "sent": False,
            "note": "Koncept čeká na schválení koordinátorem v aplikaci.", "sources": [f"Task/{task_id}"]}


TOOL_FUNCTIONS = {
    "fhir_search": fhir_search,
    "sql_query": sql_query,
    "vector_search": vector_search,
    "case_overview": case_overview,
    "request_status": request_status,
    "create_task_draft": create_task_draft,
}

_OBJ = "object"
TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "fhir_search", "description": "Read-only FHIR search. endpoint: motol (default) or nnh, homolka, fnm "
     "(simulated hospitals). Example: resource_type=ImagingStudy, params={subject: 'Patient/<id>'}.",
     "parameters": {"type": _OBJ, "properties": {"resource_type": {"type": "string"},
                                                  "params": {"type": _OBJ, "additionalProperties": {"type": "string"}},
                                                  "endpoint": {"type": "string"}},
                    "required": ["resource_type"]}},
    {"name": "sql_query", "description": "Read-only SELECT on IRIS SQL (max 50 rows).",
     "parameters": {"type": _OBJ, "properties": {"sql": {"type": "string"}}, "required": ["sql"]}},
    {"name": "vector_search", "description": "Semantic search over one patient's report chunks.",
     "parameters": {"type": _OBJ, "properties": {"patient_id": {"type": "string"}, "query": {"type": "string"},
                                                  "top": {"type": "integer"}},
                    "required": ["patient_id", "query"]}},
    {"name": "case_overview", "description": "Case view model: readiness, planned exam, required studies "
     "with reasons, availability, holding site and evidence quotes.",
     "parameters": {"type": _OBJ, "properties": {"case_id": {"type": "string"}}, "required": ["case_id"]}},
    {"name": "request_status", "description": "Status of an outgoing request (PACS-REQ-...).",
     "parameters": {"type": _OBJ, "properties": {"request_id": {"type": "string"}}, "required": ["request_id"]}},
    {"name": "create_task_draft", "description": "Create a draft FHIR Task (never sent; needs approval in the app).",
     "parameters": {"type": _OBJ, "properties": {"patient_id": {"type": "string"}, "description": {"type": "string"},
                                                  "modality": {"type": "string"}, "body_region": {"type": "string"},
                                                  "study_date": {"type": "string"}, "case_id": {"type": "string"}},
                    "required": ["patient_id", "description"]}},
]


def call_tool(name: str, arguments: dict[str, Any]) -> dict:
    """Run a tool; input errors come back as {"error": ...} so the model can recover."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"unknown tool {name!r}", "sources": []}
    try:
        return func(**arguments)
    except ToolError as exc:
        return {"error": str(exc), "sources": []}
    except TypeError as exc:
        return {"error": f"bad arguments: {exc}", "sources": []}
    except Exception as exc:  # noqa: BLE001
        log.warning("tool failed", extra={"fields": {"tool": name, "error": type(exc).__name__}})
        return {"error": f"tool failed ({type(exc).__name__})", "sources": []}
