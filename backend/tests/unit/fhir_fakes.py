"""Shared in-memory FHIR server for hospital tests (httpx.MockTransport). Synthetic resources only."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx

from app.exchange.hospitals import Hospital

NNH = Hospital("nnh", "Nemocnice Na Homolce", "http://iris.test/nnh/fhir/r4")
HOMOLKA = Hospital("homolka", "Homolka, druhé pracoviště (simulace)", "http://iris.test/homolka/fhir/r4")
FNM = Hospital("fnm", "FNM", "http://iris.test/fnm/fhir/r4")
HOSPITALS = [NNH, HOMOLKA, FNM]
MOTOL = "http://iris.test/fhir/r4"


def imaging_study(sid: str, patient: str, code: str, started: str) -> dict:
    return {"resourceType": "ImagingStudy", "id": sid, "status": "available", "started": started,
            "subject": {"reference": f"Patient/{patient}"}, "modality": [{"code": code}]}


class FakeFhir:
    """Routes by path prefix; supports search with subject/started/identifier, read, transaction POST."""

    def __init__(self) -> None:
        self.data: dict[str, list[dict]] = {}  # key = base path + "|" + resource type
        self.calls: list[httpx.Request] = []
        self.down: set[str] = set()  # base paths that answer 503
        self.reject_transactions = False

    def add(self, base: str, resource: dict) -> None:
        self.data.setdefault(f"{urlparse(base).path}|{resource['resourceType']}", []).append(resource)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = urlparse(str(request.url))
        bases = [urlparse(h.base_url).path for h in HOSPITALS] + [urlparse(MOTOL).path]
        base = next((b for b in bases if url.path.startswith(b)), None)
        if base is None or base in self.down:
            return httpx.Response(503, json={})
        rest = url.path[len(base):].strip("/")
        query = parse_qs(url.query)
        if request.method == "POST" and rest == "":
            if self.reject_transactions:
                return httpx.Response(400, json={"resourceType": "OperationOutcome", "issue": []})
            bundle = json.loads(request.content)
            entries = []
            for entry in bundle["entry"]:
                resource = {**entry["resource"], "id": f"gen{len(self.data) + len(entries)}"}
                self.add(base, resource)
                entries.append({"response": {"status": "201"}})
            return httpx.Response(200, json={"resourceType": "Bundle", "type": "transaction-response",
                                             "entry": entries})
        parts = rest.split("/")
        if request.method == "GET" and len(parts) == 2:
            for res in self.data.get(f"{base}|{parts[0]}", []):
                if res["id"] == parts[1]:
                    return httpx.Response(200, json=res)
            return httpx.Response(404, json={})
        if request.method == "GET" and len(parts) == 1:
            found = []
            for res in self.data.get(f"{base}|{parts[0]}", []):
                if "subject" in query and res["subject"]["reference"] != query["subject"][0]:
                    continue
                started = str(res.get("started", ""))[:10]
                if any(v.startswith("ge") and started < v[2:] for v in query.get("started", [])):
                    continue
                if any(v.startswith("le") and started > v[2:] for v in query.get("started", [])):
                    continue
                if "identifier" in query:
                    system, _, value = query["identifier"][0].partition("|")
                    if not any(i.get("system") == system and i.get("value") == value
                               for i in res.get("identifier", [])):
                        continue
                found.append(res)
            return httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset",
                                             "entry": [{"resource": r, "search": {"mode": "match"}}
                                                       for r in found]})
        return httpx.Response(405, json={})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))
