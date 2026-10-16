"""Simulated DICOM PACS (Orthanc containers, docker-compose.dicom.yml) and the C-FIND clients (T087).

One Orthanc per hospital application entity (AE). The IRIS production in namespace PACSDICOM is the
primary C-FIND client (PacsDicom.Api.CFind through the IRIS Native API); pynetdicom is the fallback
(`DICOM_CLIENT=pynetdicom`). All PACS here are simulations (hard rule 5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.config import CONFIG_DIR, get_settings
from app.exchange.hospitals import DICOM_MODALITY, pipeline_modality

CONFIG_FILE = CONFIG_DIR / "dicom.json"
MOTOL_ID = "motol"


class DicomError(RuntimeError):
    pass


@dataclass(frozen=True)
class DicomMatch:
    patient_id: str
    study_date: date | None
    modality: str | None  # pipeline modality (CT, MR, PET, RTG ...)
    accession: str | None
    ae: str


@dataclass(frozen=True)
class PacsNode:
    id: str
    ae: str
    host: str
    port: int
    rest: str


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def nodes() -> dict[str, PacsNode]:
    cfg = load_config()
    return {k: PacsNode(k, v["ae"], v["host"], int(v["port"]), v["rest"]) for k, v in cfg["pacs"].items()}


def local_aet() -> str:
    return load_config()["local_aet"]


def dicom_modality(modality: str) -> str | None:
    return DICOM_MODALITY.get(modality)


def to_pipeline_modality(code: str | None) -> str | None:
    return pipeline_modality((code or "").split("\\")[0])


def parse_dicom_date(value: str | None) -> date | None:
    value = (value or "").strip()
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def date_range(window: tuple[date, date] | None) -> str:
    """DICOM range matching 'YYYYMMDD-YYYYMMDD'; empty means any date."""
    if window is None:
        return ""
    return f"{window[0]:%Y%m%d}-{window[1]:%Y%m%d}"


def parse_matches(payload: str, ae: str) -> list[DicomMatch]:
    """Parse the JSON returned by PacsDicom.Api.CFind (IRIS) or the pynetdicom fallback."""
    data = json.loads(payload)
    if data.get("outcome") != "OK":
        raise DicomError(f"C-FIND {ae} failed: {data.get('message') or data.get('outcome')}")
    return [
        DicomMatch(
            patient_id=m.get("patientId", ""),
            study_date=parse_dicom_date(m.get("studyDate")),
            modality=to_pipeline_modality(m.get("modalities") or m.get("modality")),
            accession=m.get("accession") or None,
            ae=ae,
        )
        for m in data.get("matches", [])
    ]


class CFindClient:
    """Study-level C-FIND against one AE. Subclasses: IrisCFindClient, PynetdicomCFindClient."""

    def find(self, ae: str, patient_id: str, window: tuple[date, date] | None, modality: str | None
             ) -> list[DicomMatch]:
        raise NotImplementedError


class IrisCFindClient(CFindClient):
    """C-FIND executed inside IRIS (PacsDicom.BS.Api -> BP -> BO on EnsLib.DICOM), called via the Native API."""

    def __init__(self, host: str = "localhost", port: int | None = None, user: str | None = None,
                 password: str | None = None):
        cfg = load_config()
        settings = get_settings()
        self._args = (host, port or int(cfg.get("iris_port", 1972)), cfg.get("iris_namespace", "PACSDICOM"),
                      user or settings.iris_user or "SuperUser", password or settings.iris_password or "SYS")
        self._conn: Any = None
        self._irispy: Any = None

    def _api(self) -> Any:
        if self._irispy is None:
            import iris

            self._conn = iris.createConnection(*self._args)
            self._irispy = iris.createIRIS(self._conn)
        return self._irispy

    def find(self, ae: str, patient_id: str, window: tuple[date, date] | None, modality: str | None
             ) -> list[DicomMatch]:
        try:
            payload = self._api().classMethodValue(
                "PacsDicom.Api", "CFind", ae, patient_id, date_range(window),
                (dicom_modality(modality) or "") if modality else "")
        except Exception as exc:  # the Native API raises its own error types
            self._irispy = None
            raise DicomError(f"IRIS C-FIND call failed: {type(exc).__name__}") from exc
        return parse_matches(payload, ae)


class PynetdicomCFindClient(CFindClient):
    """Fallback: the same query from Python (pynetdicom) when the IRIS production is not running."""

    def __init__(self) -> None:
        self._nodes = {n.ae: n for n in nodes().values()}

    def find(self, ae: str, patient_id: str, window: tuple[date, date] | None, modality: str | None
             ) -> list[DicomMatch]:
        from pydicom.dataset import Dataset
        from pynetdicom import AE
        from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind

        node = self._nodes[ae]
        query = Dataset()
        query.QueryRetrieveLevel = "STUDY"
        query.PatientID = patient_id
        query.StudyDate = date_range(window)
        query.ModalitiesInStudy = (dicom_modality(modality) or "") if modality else ""
        query.AccessionNumber = ""
        query.StudyInstanceUID = ""
        client = AE(ae_title=local_aet())
        client.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        assoc = client.associate(node.host, node.port, ae_title=node.ae)
        if not assoc.is_established:
            raise DicomError(f"association with {ae} was not established")
        matches: list[DicomMatch] = []
        try:
            for status, ident in assoc.send_c_find(query, StudyRootQueryRetrieveInformationModelFind):
                if status and status.Status in (0xFF00, 0xFF01) and ident is not None:
                    matches.append(DicomMatch(
                        patient_id=str(ident.get("PatientID", "")),
                        study_date=parse_dicom_date(str(ident.get("StudyDate", ""))),
                        modality=to_pipeline_modality(str(ident.get("ModalitiesInStudy", "") or "")),
                        accession=str(ident.get("AccessionNumber", "")) or None, ae=ae))
        finally:
            assoc.release()
        return matches


def default_client() -> CFindClient:
    choice = get_settings().dicom_client
    return PynetdicomCFindClient() if choice == "pynetdicom" else IrisCFindClient()
