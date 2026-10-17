"""Project the FHIR repository into SQL with the IRIS for Health FHIR SQL Builder (FSB).

Drives the same REST interface as the FSB web UI (/csp/fhirsql/) and creates, idempotently and with the
prefix `pacs`: credentials `pacsCreds`, repository `pacsRepo` (the /fhir/r4 endpoint), analysis, transform
specification `pacsSpec` and projection package `PacsProjection`. The tables are plain SQL tables in the
FHIRSERVER namespace (PacsProjection.ImagingStudy, ...) and are what /api/stats reads.

    uv run python scripts/sql_projection_setup.py [--rebuild] [--status]

A rerun finds the existing objects and only launches a new projection when none exists. After new FHIR
data was written, refresh the tables with `--rebuild` (deletes and recreates our projection, spec and
analysis only).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import httpx

from app.config import get_settings

PREFIX = "pacs"
CREDENTIALS = f"{PREFIX}Creds"
REPOSITORY = f"{PREFIX}Repo"
SPEC_NAME = f"{PREFIX}Spec"
PACKAGE = "PacsProjection"
LOCAL = "https://rakathon.local/fhir/StructureDefinition"
PACS_EXT = f"{LOCAL}/dostupnost-pacs"
QUOTE_EXT = f"{LOCAL}/source-quote"
CONFIDENCE_EXT = f"{LOCAL}/extraction-confidence"


def col(name: str, path: str, length: int = 100, index: bool = False, type_: str = "String") -> dict[str, Any]:
    return {"name": name, "type": type_, "path": path, "index": index, "dataIndex": False, "length": length}


def component(code: str) -> str:
    return f"Observation.component.where(code.text='{code}').valueString"


# One SQL table per resource type. Repeating elements are flattened by FSB into one column.
RESOURCES: list[dict[str, Any]] = [
    {"resourceType": "ImagingStudy", "columns": [
        col("Patient", "ImagingStudy.subject.reference", 64, True),
        col("Status", "ImagingStudy.status", 20),
        col("Started", "ImagingStudy.started", 40, True),
        col("Modality", "ImagingStudy.modality.code", 20, True),
        col("Accession", "ImagingStudy.identifier.value", 64),
        col("PacsAvailable", f"ImagingStudy.extension.where(url='{PACS_EXT}').extension"
                              ".where(url='dostupne').valueBoolean", 10, True),
        col("PacsSource", f"ImagingStudy.extension.where(url='{PACS_EXT}').extension"
                          ".where(url='zdroj').valueString", 100),
    ]},
    {"resourceType": "DiagnosticReport", "columns": [
        col("Patient", "DiagnosticReport.subject.reference", 64, True),
        col("Status", "DiagnosticReport.status", 20),
        col("Category", "DiagnosticReport.category.coding.code", 20, True),
        col("Code", "DiagnosticReport.code.coding.code", 30),
        col("Issued", "DiagnosticReport.issued", 40),
        col("Effective", "DiagnosticReport.effectiveDateTime", 40, True),
    ]},
    {"resourceType": "ServiceRequest", "columns": [
        col("Patient", "ServiceRequest.subject.reference", 64, True),
        col("Status", "ServiceRequest.status", 20),
        col("Intent", "ServiceRequest.intent", 20),
        col("Modality", "ServiceRequest.code.coding.code", 20, True),
        col("BodySite", "ServiceRequest.bodySite.text", 100),
        col("Occurrence", "ServiceRequest.occurrenceDateTime", 40),
        col("Performer", "ServiceRequest.performer.display", 100),
        col("Confidence", f"ServiceRequest.extension.where(url='{CONFIDENCE_EXT}').valueDecimal", 10, type_="%Numeric"),
    ]},
    {"resourceType": "Task", "columns": [
        col("Patient", "Task.for.reference", 64, True),
        col("Status", "Task.status", 30, True),
        col("BusinessStatus", "Task.businessStatus.text", 40, True),
        col("Intent", "Task.intent", 20),
        col("Owner", "Task.owner.display", 100),
        col("OwnerRef", "Task.owner.reference", 100),
        col("Recipient", "Task.restriction.recipient.display", 100, True),
        col("DueDate", "Task.restriction.period.end", 40),
        col("Focus", "Task.focus.reference", 100),
        col("Description", "Task.description", 200),
        col("Authored", "Task.authoredOn", 40),
    ]},
    {"resourceType": "Observation", "columns": [
        col("Patient", "Observation.subject.reference", 64, True),
        col("Status", "Observation.status", 20),
        col("Category", "Observation.category.coding.code", 40, True),
        col("Code", "Observation.code.text", 100),
        col("Focus", "Observation.focus.reference", 100),
        col("DerivedFrom", "Observation.derivedFrom.reference", 100),
        col("Modality", component("modality"), 20, True),
        col("BodyRegion", component("body region"), 100),
        col("RefDate", component("referenced date"), 20),
        col("HoldingSite", component("holding site"), 100),
        col("Confidence", f"Observation.extension.where(url='{CONFIDENCE_EXT}').valueDecimal", 10, type_="%Numeric"),
    ]},
    {"resourceType": "Provenance", "columns": [
        col("Target", "Provenance.target.reference", 100, True),
        col("Recorded", "Provenance.recorded", 40),
        col("Agent", "Provenance.agent.who.display", 100),
        col("Entity", "Provenance.entity.what.reference", 100),
        col("Quote", f"Provenance.extension.where(url='{QUOTE_EXT}').valueString", 250),
        col("Confidence", f"Provenance.extension.where(url='{CONFIDENCE_EXT}').valueDecimal", 10, type_="%Numeric"),
    ]},
]


class Fsb:
    """Minimal client of the FSB REST API (the same one the /csp/fhirsql/ UI uses)."""

    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self.http = httpx.Client(base_url=f"http://{host}:{port}/csp/fhirsql/api/ui", auth=(user, password),
                                 timeout=120.0, headers={"Accept": "application/json"})

    def call(self, method: str, path: str, body: Any = None, **params: Any) -> Any:
        response = self.http.request(method, path, json=body, params=params or None)
        if response.status_code >= 400:
            raise SystemExit(f"FSB {method} {path} -> HTTP {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else {}

    def list(self, path: str) -> list[dict[str, Any]]:
        data = self.call("GET", f"/{path}/")
        return data if isinstance(data, list) else []


def log(message: str) -> None:
    print(message, file=sys.stderr)


def ensure_credentials(fsb: Fsb, user: str, password: str) -> None:
    if any(item.get("systemName") == CREDENTIALS for item in fsb.list("credentials")):
        return
    fsb.call("POST", "/credentials", {"systemName": CREDENTIALS, "username": user, "password": password})
    log(f"created credentials {CREDENTIALS}")


def ensure_repository(fsb: Fsb, fhir_path: str) -> int:
    for item in fsb.list("fhirrepository"):
        if item.get("name") == REPOSITORY:
            return int(item["id"])
    body = {"name": REPOSITORY, "hostname": "localhost", "port": "52773", "repositoryURL": fhir_path,
            "credentialsId": CREDENTIALS, "sslConfig": ""}
    data = fsb.call("POST", "/fhirrepository", body)
    items = data if isinstance(data, list) else [data]
    found = [item for item in items if item.get("name") == REPOSITORY]
    log(f"created repository {REPOSITORY} ({fhir_path})")
    return int(found[-1]["id"])


def wait_status(fetch, done: set[str], what: str, timeout: int) -> dict[str, Any]:
    start = time.monotonic()
    while True:
        item = fetch()
        status = str(item.get("status", "")).lower()
        if status in done:
            return item
        if status in {"failed", "error", "errored"}:
            raise SystemExit(f"{what} failed: {item}")
        if time.monotonic() - start > timeout:
            raise SystemExit(f"{what} did not finish in {timeout}s (status {status!r})")
        time.sleep(3)


def ensure_analysis(fsb: Fsb, repo_id: int, timeout: int) -> int:
    existing = [a for a in fsb.list("analysis") if int(a.get("fhirRepositoryId") or 0) == repo_id]
    if existing:
        analysis = existing[-1]
    else:
        data = fsb.call("POST", "/analysis", {"fhirRepositoryId": repo_id, "selectivityPercentage": 100})
        analysis = (data[-1] if isinstance(data, list) else data)
        log("analysis started")
    task_id = analysis.get("id") or analysis.get("TASKID")
    wait_status(lambda: fsb.call("GET", "/analysis", ID=task_id), {"completed", "complete", "success"},
                "analysis", timeout)
    return int(task_id)


def ensure_spec(fsb: Fsb, analysis_id: int) -> int:
    matches = [s for s in fsb.list("transformspec") if s.get("name") == SPEC_NAME]
    if matches:
        return int(max(matches, key=lambda s: int(s["id"]))["id"])
    payload = {"name": SPEC_NAME, "scanId": analysis_id, "description": "PACS comparator statistics",
               "resources": RESOURCES}
    data = fsb.call("POST", "/transformspec", payload)
    found = [s for s in (data if isinstance(data, list) else [data]) if s.get("name") == SPEC_NAME]
    if not found:
        raise SystemExit("transform specification was not created")
    log(f"created transform specification {SPEC_NAME}")
    return int(max(found, key=lambda s: int(s["id"]))["id"])


def ensure_projection(fsb: Fsb, repo_id: int, spec_id: int, user: str, timeout: int) -> dict[str, Any]:
    matches = [p for p in fsb.list("projection") if p.get("packageName") == PACKAGE]
    if matches:
        projection = matches[-1]
    else:
        body = {"name": f"{PREFIX}Projection", "fhirRepositoryId": repo_id, "specificationId": spec_id,
                "packageName": PACKAGE, "users": [user]}
        data = fsb.call("POST", "/projection", body)
        items = [p for p in (data if isinstance(data, list) else [data]) if p.get("packageName") == PACKAGE]
        projection = items[-1]
        log(f"projection {PACKAGE} launched")
    return wait_status(lambda: fsb.call("GET", "/projection", ID=projection["id"]),
                       {"active", "completed", "complete", "success"}, "projection", timeout)


def teardown(fsb: Fsb) -> None:
    """Remove only the objects this script owns (projection first, then spec, analysis, repository)."""
    for item in fsb.list("projection"):
        if item.get("packageName") == PACKAGE:
            fsb.call("DELETE", "/projection", ID=item["id"])
    for item in fsb.list("transformspec"):
        if item.get("name") == SPEC_NAME:
            fsb.call("DELETE", "/transformspec", ID=item["id"])
    repo_ids = {int(r["id"]) for r in fsb.list("fhirrepository") if r.get("name") == REPOSITORY}
    for item in fsb.list("analysis"):
        if int(item.get("fhirRepositoryId") or 0) in repo_ids:
            fsb.call("DELETE", "/analysis", ID=item.get("id") or item.get("TASKID"))
    log("removed existing pacs* projection, specification and analysis")


def restore_search_limit(host: str, user: str, password: str) -> None:
    """Creating the repository/analysis resets MaxSearchResults of /fhir/r4 to 1000; set it back."""
    import iris
    from iris_setup import ENDPOINT, raise_search_limit

    conn = iris.createConnection(host, 1972, "FHIRSERVER", user, password)
    try:
        raise_search_limit(iris.createIRIS(conn), ENDPOINT)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--web-port", type=int, default=52773)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--fhir-path", default="/fhir/r4")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--rebuild", action="store_true", help="delete and recreate projection, spec, analysis")
    parser.add_argument("--status", action="store_true", help="print what exists and exit")
    args = parser.parse_args()
    settings = get_settings()
    user = args.user or settings.iris_user or "SuperUser"
    password = args.password or settings.iris_password or "SYS"
    fsb = Fsb(args.host, args.web_port, user, password)

    if args.status:
        print(json.dumps({
            "repositories": [r.get("name") for r in fsb.list("fhirrepository")],
            "specs": [s.get("name") for s in fsb.list("transformspec")],
            "projections": [(p.get("packageName"), p.get("status")) for p in fsb.list("projection")],
        }))
        return
    if args.rebuild:
        teardown(fsb)
    ensure_credentials(fsb, user, password)
    repo_id = ensure_repository(fsb, args.fhir_path)
    analysis_id = ensure_analysis(fsb, repo_id, args.timeout)
    spec_id = ensure_spec(fsb, analysis_id)
    projection = ensure_projection(fsb, repo_id, spec_id, user, args.timeout)
    restore_search_limit(args.host, user, password)
    print(f"projection {projection.get('packageName')} status={projection.get('status')}")


if __name__ == "__main__":
    main()
