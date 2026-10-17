"""PACS availability through a DICOM C-FIND (T087): the study-level query of a real PACS, here against Orthanc.

Internal (Motol) studies are looked up at AE MOTOL by PatientID + StudyDate + ModalitiesInStudy: found means
`available`, not found `not_in_pacs` (an `unknown` dataset flag stays `unknown` when nothing is found).
References cited in a report but absent from Motol (`not_found`) are searched at the partner AEs
(NNH, HOMOLKA, FNM; the cited site first); the AE that answers becomes the holding site.
The C-FIND itself runs inside IRIS (PacsDicom.Api, EnsLib.DICOM) unless DICOM_CLIENT=pynetdicom.

This is the default adapter with the IRIS backend, so it must never break a check: when a PACS does not answer,
the item falls back to the dataset flag (Motol studies) or to the FHIR hospital endpoints (cited references), a
warning is logged (no patient ids) and `RequiredItem.availability_source` says which path produced the answer.
"""

from __future__ import annotations

from datetime import date

from app.config import get_settings
from app.exchange.dicom import MOTOL_ID, CFindClient, DicomMatch, PacsNode, default_client, nodes
from app.exchange.hospitals import (
    date_window,
    hospitals,
    provider,
    representative_date,
    search_imaging_studies,
)
from app.logging import get_logger
from app.pipeline.availability import AvailabilityAdapter, DatasetFlagAdapter
from app.pipeline.gaps import UNKNOWN_SITE_ID
from app.pipeline.rules import fmt_date
from app.pipeline.schemas import Availability, OpenIssue, PriorReference, RequiredItem, Study

log = get_logger(__name__)

LOCATED_BY = "dicom-cfind"
SOURCE_CFIND = "dicom-cfind"
SOURCE_FLAG = "dataset-flag"  # fallback: the PACS did not answer
SOURCE_FHIR = "fhir-search"  # fallback: the hospital FHIR endpoints answered instead of the PACS
SIMULATION_SUFFIX = "simulace"


class DicomAvailabilityAdapter(AvailabilityAdapter):
    def __init__(self, client: CFindClient | None = None, pacs: dict[str, PacsNode] | None = None,
                 fallback: AvailabilityAdapter | None = None, fhir_fallback: bool = True):
        self._client = client
        self._pacs = pacs
        self._refs: dict[str, PriorReference] = {}
        self._flag = DatasetFlagAdapter()
        self._fallback = fallback
        self._fhir_fallback = fhir_fallback
        self._study_source: dict[str, str] = {}  # study id -> availability_source
        self._down: set[str] = set()  # PACS ids that failed once in this run, not asked again

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

    @property
    def fallback(self) -> AvailabilityAdapter | None:
        """FHIR hospital adapter used when the partner PACS cannot be asked (IRIS FHIR backend only)."""
        if self._fallback is None and self._fhir_fallback and get_settings().fhir_backend == "iris":
            from app.pipeline.availability_fhir import FhirHospitalAdapter

            self._fallback = FhirHospitalAdapter()
        return self._fallback

    # --- AvailabilityAdapter ----------------------------------------------------------------

    def check(self, study: Study | None, reference: PriorReference | None) -> Availability:
        if study is None:
            if reference is not None:
                self._refs[reference.id] = reference
                if self.fallback is not None:
                    self.fallback.check(None, reference)
            return "not_found"
        if study.source == "received":
            return "available"
        window = (study.date, study.date)
        found: list[DicomMatch] | None = None
        if MOTOL_ID not in self._down:
            try:
                found = self.client.find(self.pacs[MOTOL_ID].ae, study.patient_id, window, study.modality)
            except Exception as exc:  # noqa: BLE001 - whatever goes wrong, the pipeline must go on
                log.warning("DICOM C-FIND failed, using the dataset flag",
                            extra={"fields": {"ae": MOTOL_ID, "error": type(exc).__name__}})
                self._down.add(MOTOL_ID)
        if found is None:
            self._study_source[study.id] = SOURCE_FLAG
            return self._flag.check(study, None)
        self._study_source[study.id] = SOURCE_CFIND
        if _matching(found, study.modality, window):
            return "available"
        return "unknown" if study.pacs_flag == "unknown" else "not_in_pacs"

    def enrich(self, items: list[RequiredItem]) -> tuple[list[RequiredItem], list[OpenIssue]]:
        items = [self._with_study_source(i) for i in items]
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
            if found is None and unreachable:
                # some or all partner PACS did not answer: the FHIR hospital endpoints may know the holder
                item, extra = self._fallback_locate(item)
                issues.extend(extra)
                if item.located_by:
                    out.append(item)
                    continue
            if found is None and len(unreachable) >= len(partners):
                out.append(item.model_copy(update={"availability_source": SOURCE_FLAG}))
                continue
            if found is None:
                label = f"{item.modality} {fmt_date(item.target_date)}"
                names = ", ".join(n.ae for n in partners)
                note = (f"{item.note or ''} Žádné PACS studii nenabízí (C-FIND: {names}; "
                        f"{SIMULATION_SUFFIX}).").strip()
                out.append(item.model_copy(update={"note": note, "availability_source": SOURCE_CFIND}))
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
                "availability_source": SOURCE_CFIND,
                "provider_study_ref": self._fhir_study_ref(node, ref),
                "note": f"{item.note or ''} Nalezeno DICOM C-FIND dotazem v PACS {node.ae} "
                        f"({SIMULATION_SUFFIX}).".strip(),
            }))
        if unreachable:
            issues.append(OpenIssue(type="data", text="Některé PACS nebyly dostupné: "
                                                      + ", ".join(sorted(unreachable))))
        return out, issues

    def _with_study_source(self, item: RequiredItem) -> RequiredItem:
        source = self._study_source.get(item.study_id or "")
        return item.model_copy(update={"availability_source": source}) if source else item

    def _fallback_locate(self, item: RequiredItem) -> tuple[RequiredItem, list[OpenIssue]]:
        fallback = self.fallback
        if fallback is None:
            return item, []
        try:
            (located,), issues = fallback.enrich([item])
        except Exception as exc:  # noqa: BLE001 - the fallback must not break the pipeline either
            log.warning("FHIR hospital fallback failed", extra={"fields": {"error": type(exc).__name__}})
            return item, []
        if not located.located_by:
            return item, []  # nothing found: keep the item as it was, the caller decides what to claim
        return located.model_copy(update={"availability_source": SOURCE_FHIR}), issues

    def _fhir_study_ref(self, node: PacsNode, ref: PriorReference) -> str | None:
        """FHIR ImagingStudy URL at the holding hospital: the delivery simulation (MHD) needs it. Best effort."""
        if not self._fhir_fallback or get_settings().fhir_backend != "iris":
            return None
        try:
            hospital = next((h for h in hospitals() if h.id == node.id), None)
            if hospital is None:
                return None
            window = date_window(ref.ref_date)
            wanted = representative_date(ref.ref_date)  # type: ignore[arg-type] - checked by the caller
            studies = search_imaging_studies(None, hospital, ref.patient_id, ref.modality, window)
            if not studies:
                return None
            best = min(studies, key=lambda s: abs(_started(s, wanted) - wanted))
            return f"{hospital.base_url}/ImagingStudy/{best['id']}"
        except Exception as exc:  # noqa: BLE001
            log.warning("FHIR study lookup after C-FIND failed", extra={"fields": {"ae": node.ae,
                                                                                  "error": type(exc).__name__}})
            return None

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
            if node.id in self._down:
                unreachable.add(node.id)
                continue
            try:
                found = self.client.find(node.ae, ref.patient_id, window, ref.modality)
            except Exception as exc:  # noqa: BLE001 - whatever goes wrong, the pipeline must go on
                log.warning("DICOM C-FIND failed", extra={"fields": {"ae": node.ae, "error": type(exc).__name__}})
                self._down.add(node.id)
                unreachable.add(node.id)
                continue
            hits = _matching(found, ref.modality, window)
            if hits:
                return node, min(hits, key=lambda m: abs(((m.study_date or wanted) - wanted).days))
        return None


def _started(study: dict, fallback: date) -> date:
    try:
        return date.fromisoformat(str(study.get("started", ""))[:10])
    except ValueError:
        return fallback


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
