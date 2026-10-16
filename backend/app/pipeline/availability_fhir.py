"""PACS availability with real FHIR calls to the simulated hospital endpoints in IRIS (T079).

Internal (Motol) studies keep using the dataset PACS flag. A required study that is cited in a report
but absent from Motol (`not_found`) is looked up with FHIR search in the partner hospitals:

    GET <hospital>/ImagingStudy?subject=Patient/<id>&started=ge<from>&started=le<to>

first at the hospital named in the report, otherwise at all of them. The hospital that really has the
study becomes the holding site (`located_by="fhir-search"`), which resolves "Neznámé pracoviště".
Availability for Motol stays `not_found`. If nobody has the study, the holding site stays unknown and an
open issue says so. The hospitals are a simulation (hard rule 5), the calls are real FHIR REST.
"""

from __future__ import annotations

from datetime import date

import httpx

from app.exchange.hospitals import (
    Hospital,
    HospitalError,
    date_window,
    hospitals,
    make_client,
    representative_date,
    search_imaging_studies,
)
from app.logging import get_logger
from app.pipeline.availability import AvailabilityAdapter, DatasetFlagAdapter
from app.pipeline.gaps import UNKNOWN_SITE_ID
from app.pipeline.rules import fmt_date
from app.pipeline.schemas import Availability, OpenIssue, PriorReference, RequiredItem, Study

log = get_logger(__name__)

LOCATED_BY = "fhir-search"
SIMULATION_SUFFIX = "simulace"


class FhirHospitalAdapter(AvailabilityAdapter):
    def __init__(self, client: httpx.Client | None = None, targets: list[Hospital] | None = None):
        self._flag = DatasetFlagAdapter()
        self._client = client
        self._targets = targets
        self._refs: dict[str, PriorReference] = {}

    # --- AvailabilityAdapter ----------------------------------------------------------------

    def check(self, study: Study | None, reference: PriorReference | None) -> Availability:
        availability = self._flag.check(study, reference)
        if availability == "not_found" and reference is not None:
            self._refs[reference.id] = reference
        return availability

    def enrich(self, items: list[RequiredItem]) -> tuple[list[RequiredItem], list[OpenIssue]]:
        wanted = {i.id for i in items if i.availability == "not_found" and i.reference_id in self._refs}
        if not wanted:
            return items, []
        targets = self._targets if self._targets is not None else hospitals()
        client = self._client or make_client()
        issues: list[OpenIssue] = []
        out: list[RequiredItem] = []
        unreachable: set[str] = set()
        for item in items:
            ref = self._refs.get(item.reference_id or "") if item.id in wanted else None
            if ref is None or ref.ref_date is None:
                out.append(item)
                continue
            found = self._locate(client, targets, item, ref, unreachable)
            if found is None and len(unreachable) >= len(targets):
                out.append(item)  # nothing could be asked, so nothing can be claimed
                continue
            if found is None:
                names = ", ".join(h.name for h in targets)
                label = f"{item.modality} {fmt_date(item.target_date)}"
                note = (f"{item.note or ''} Žádná nemocnice studii nenabízí (prohledáno: {names}; "
                        f"{SIMULATION_SUFFIX}).").strip()
                out.append(item.model_copy(update={"note": note}))
                issues.append(OpenIssue(
                    type="data", item_id=item.id,
                    text=f"Studie {label} nebyla nalezena u žádné spolupracující nemocnice, "
                         "držitele je potřeba dohledat ručně"))
                continue
            hospital, study = found
            out.append(item.model_copy(update={
                "holding_site_id": hospital.id,
                "holding_site_name": hospital.name,
                "located_by": LOCATED_BY,
                "provider_study_ref": f"{hospital.base_url}/ImagingStudy/{study['id']}",
                "note": f"{item.note or ''} Nalezeno vyhledáním ve FHIR u: {hospital.name} "
                        f"({SIMULATION_SUFFIX}).".strip(),
            }))
        if unreachable:
            issues.append(OpenIssue(type="data", text="Některé nemocniční FHIR endpointy nebyly dostupné: "
                                                      + ", ".join(sorted(unreachable))))
        return out, issues

    # --- search -----------------------------------------------------------------------------

    @staticmethod
    def _ordered(targets: list[Hospital], preferred_id: str | None) -> list[Hospital]:
        """The resolved holding site first; an unknown site means all hospitals in configured order."""
        if not preferred_id or preferred_id == UNKNOWN_SITE_ID:
            return list(targets)
        return sorted(targets, key=lambda h: h.id != preferred_id)

    def _locate(
        self, client: httpx.Client, targets: list[Hospital], item: RequiredItem, ref: PriorReference,
        unreachable: set[str],
    ) -> tuple[Hospital, dict] | None:
        window = date_window(ref.ref_date)
        wanted_day = representative_date(ref.ref_date)  # type: ignore[arg-type] - checked by the caller
        for hospital in self._ordered(targets, item.holding_site_id):
            try:
                studies = search_imaging_studies(client, hospital, ref.patient_id, ref.modality, window)
            except HospitalError as exc:
                log.warning("hospital FHIR search failed", extra={"fields": {"hospital": hospital.id,
                                                                            "error": str(exc)}})
                unreachable.add(hospital.id)
                continue
            if studies:
                return hospital, min(studies, key=lambda s: abs((_started(s, wanted_day) - wanted_day).days))
        return None


def _started(study: dict, fallback: date) -> date:
    try:
        return date.fromisoformat(str(study.get("started", ""))[:10])
    except ValueError:
        return fallback
