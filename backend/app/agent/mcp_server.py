"""MCP server (FastMCP) exposing the IRIS tools. Run: `uv run python -m app.agent.mcp_server [--http]`.

Default transport is stdio; `--http` serves streamable HTTP on port 8115 (path /mcp).
"""

from __future__ import annotations

import argparse
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.agent import tools

mcp = FastMCP("pacs-comparator-iris", host="127.0.0.1", port=8115)


@mcp.tool()
def fhir_search(resource_type: str, params: dict[str, str] | None = None, endpoint: str = "motol") -> dict[str, Any]:
    """Read-only FHIR search. endpoint: motol (default) or the simulated hospitals nnh, homolka, fnm."""
    return tools.call_tool("fhir_search", {"resource_type": resource_type, "params": params, "endpoint": endpoint})


@mcp.tool()
def sql_query(sql: str) -> dict[str, Any]:
    """Read-only SELECT on IRIS SQL (max 50 rows). Anything but SELECT is rejected."""
    return tools.call_tool("sql_query", {"sql": sql})


@mcp.tool()
def vector_search(patient_id: str, query: str, top: int = 5) -> dict[str, Any]:
    """Semantic search over one patient's report chunks (IRIS Vector Search)."""
    return tools.call_tool("vector_search", {"patient_id": patient_id, "query": query, "top": top})


@mcp.tool()
def case_overview(case_id: str) -> dict[str, Any]:
    """Case view model: readiness, planned exam, required studies with reasons, availability and evidence."""
    return tools.call_tool("case_overview", {"case_id": case_id})


@mcp.tool()
def request_status(request_id: str) -> dict[str, Any]:
    """Status of an outgoing request (not available until the request production is merged)."""
    return tools.call_tool("request_status", {"request_id": request_id})


@mcp.tool()
def create_task_draft(patient_id: str, description: str, modality: str = "", body_region: str = "",
                      study_date: str = "", case_id: str = "") -> dict[str, Any]:
    """Create a FHIR Task in status draft. Never sends anything; a coordinator approves in the app."""
    return tools.call_tool("create_task_draft", {
        "patient_id": patient_id, "description": description, "modality": modality,
        "body_region": body_region, "study_date": study_date, "case_id": case_id})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="streamable HTTP on port 8115 instead of stdio")
    args = parser.parse_args()
    mcp.run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
