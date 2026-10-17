"""PACS availability through a DICOM C-FIND (T087): the study-level query of a real PACS, here against Orthanc.

Internal (Motol) studies are looked up at AE MOTOL by PatientID + StudyDate + ModalitiesInStudy: found means
`available`, not found `not_in_pacs` (an `unknown` dataset flag stays `unknown` when nothing is found).
References cited in a report but absent from Motol (`not_found`) are searched at the partner AEs
(NNH, HOMOLKA, FNM; the cited site first); the AE that answers becomes the holding site.
The C-FIND itself runs inside IRIS (PacsDicom.Api, EnsLib.DICOM) unless DICOM_CLIENT=pynetdicom.
"""

from __future__ import annotations

from datetime import date

from app.exchange.dicom import MOTOL_ID, CFindClient, DicomError, DicomMatch, PacsNode, default_client, nodes
from app.exchange.hospitals import date_window, provider, representative_date
from app.logging import get_logger
from app.pipeline.availability import AvailabilityAdapter
from app.pipeline.gaps import UNKNOWN_SITE_ID
from app.pipeline.rules import fmt_date
from app.pipeline.schemas import Availability, OpenIssue, PriorReference, RequiredItem, Study

log = get_logger(__name__)

LOCATED_BY = "dicom-cfind"
SIMULATION_SUFFIX = "simulace"


class DicomAvailabilityAdapter(AvailabilityAdapter):
    def __init__(self, client: CFindClient | None = None, pacs: dict[str, PacsNode] | None = None):
        self._client = client
        self._pacs = pacs
        self._refs: dict[str, PriorReference] = {}

    @property
    def client(self) -> CFindClient:
        if self._client is None:
            self._client = default_client()
        return self._client

    @property
    def pacs(self) -> dict[str, PacsNode]:
        if self._pacs is None:
            self._pacs = nodes()
        return self._pacs

    # --- AvailabilityAdapter ----------------------------------------------------------------

    def check(self, study: Study | None, reference: PriorReference | None) -> Availability:
        if study is None:
            if reference is not None:
                self._refs[reference.id] = reference
            return "not_found"
        if study.source == "received":
            return "available"
        window = (study.date, study.date)
        try:
            found = self.client.find(self.pacs[MOTOL_ID].ae, study.patient_id, window, study.modality)
        except DicomError as exc:
            log.warning("DICOM C-FIND failed", extra={"fields": {"ae": MOTOL_ID, "error": str(exc)}})
            return {"yes": "available", "no": "not_in_pacs"}.get(study.pacs_flag, "unknown")
        if _matching(found, study.modality, window):
            return "available"
        return "unknown" if study.pacs_flag == "unknown" else "not_in_pacs"

    def enrich(self, items: list[RequiredItem]) -> tuple[list[RequiredItem], list[OpenIssue]]:
        wanted = {i.id for i in items if i.availability == "not_found" and i.reference_id in self._refs}
        if not wanted:
            return items, []
        partners = [n for n in self.pacs.values() if n.id != MOTOL_ID]
        issues: list[OpenIssue] = []
        out: list[RequiredItem] = []
        unreachable: set[str] = set()
        for item in items:
            ref = self._refs.get(item.reference_id or "") if item.id in wanted else None
            if ref is None or ref.ref_date is None:
                out.append(item)
                continue
            found = self._locate(partners, item, ref, unreachable)
            if found is None and len(unreachable) >= len(partners):
                out.append(item)
                continue
            if found is None:
                label = f"{item.modality} {fmt_date(item.target_date)}"
                names = ", ".join(n.ae for n in partners)
                note = (f"{item.note or ''} Žádné PACS studii nenabízí (C-FIND: {names}; "
                        f"{SIMULATION_SUFFIX}).").strip()
                out.append(item.model_copy(update={"note": note}))
                issues.append(OpenIssue(
                    type="data", item_id=item.id,
                    text=f"Studie {label} nebyla nalezena C-FIND dotazem u žádného partnerského PACS, "
                         "držitele je potřeba dohledat ručně"))
                continue
            node, match = found
            out.append(item.model_copy(update={
                "holding_site_id": node.id,
                "holding_site_name": (provider(node.id) or {}).get("name") or node.ae,
                "located_by": LOCATED_BY,
                "provider_study_ref": f"dicom://{node.ae}/{match.accession or ''}".rstrip("/"),
                "note": f"{item.note or ''} Nalezeno DICOM C-FIND dotazem v PACS {node.ae} "
                        f"({SIMULATION_SUFFIX}).".strip(),
            }))
        if unreachable:
            issues.append(OpenIssue(type="data", text="Některé PACS nebyly dostupné: "
                                                      + ", ".join(sorted(unreachable))))
        return out, issues

    # --- search -----------------------------------------------------------------------------

    @staticmethod
    def _ordered(nodes_: list[PacsNode], preferred_id: str | None) -> list[PacsNode]:
        if not preferred_id or preferred_id == UNKNOWN_SITE_ID:
            return list(nodes_)
        return sorted(nodes_, key=lambda n: n.id != preferred_id)

    def _locate(self, partners: list[PacsNode], item: RequiredItem, ref: PriorReference,
                unreachable: set[str]) -> tuple[PacsNode, DicomMatch] | None:
        window = date_window(ref.ref_date)
        wanted = representative_date(ref.ref_date)  # type: ignore[arg-type] - checked by the caller
        for node in self._ordered(partners, item.holding_site_id):
            try:
                found = self.client.find(node.ae, ref.patient_id, window, ref.modality)
            except DicomError as exc:
                log.warning("DICOM C-FIND failed", extra={"fields": {"ae": node.ae, "error": str(exc)}})
                unreachable.add(node.id)
                continue
            hits = _matching(found, ref.modality, window)
            if hits:
                return node, min(hits, key=lambda m: abs(((m.study_date or wanted) - wanted).days))
        return None


def _matching(found: list[DicomMatch], modality: str | None, window: tuple[date, date] | None) -> list[DicomMatch]:
    """Client-side filter as a safeguard: PACS differ in how strictly they honour range/modality matching."""
    hits = []
    for m in found:
        if window and (m.study_date is None or not window[0] <= m.study_date <= window[1]):
            continue
        if modality and modality not in ("UNKNOWN", "OTHER") and m.modality not in (modality, None):
            continue
        hits.append(m)
    return hits
