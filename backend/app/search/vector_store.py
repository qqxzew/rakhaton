"""IRIS Vector Search over radiology reports and clinical notes.

Embeddings are computed locally (fastembed, multilingual MiniLM, 384 dimensions) so report text
never leaves the machine; vectors and text chunks are stored in an IRIS SQL table next to the FHIR
repository in the same namespace (IRIS multi-model: FHIR + SQL + vectors in one database).

Used to find prior studies a report mentions without an explicit date ("ve srovnání s předchozím
CT"), and by the search endpoint / agent tools for free-text questions about a patient.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Protocol

import iris

from app.config import get_settings
from app.fhir_store.base import FhirStore
from app.pipeline.normalize import normalize_modality
from app.pipeline.timeline import decode_attachment, report_text, to_date

TABLE = "PacsVector.ReportChunk"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIM = 384
MAX_CHUNK = 500  # the MiniLM model reads about 128 tokens, so longer chunks would be silently cut
NOTE_MAX_CHUNKS = 2  # notes are long and templated; their opening (status, plan) is what is searched
IRIS_SUPERSERVER_PORT = 1972
REPORT = "DiagnosticReport"
NOTE = "DocumentReference"

DDL = f"""CREATE TABLE {TABLE} (
    PatientId VARCHAR(64) NOT NULL,
    SourceType VARCHAR(32) NOT NULL,
    SourceId VARCHAR(128) NOT NULL,
    ChunkNo INTEGER NOT NULL,
    DocDate DATE,
    Modality VARCHAR(16),
    ChunkText VARCHAR(4000),
    Embedding VECTOR(FLOAT, {DIM})
)"""


@dataclass(frozen=True)
class Chunk:
    patient_id: str
    source_type: str  # DiagnosticReport | DocumentReference
    source_id: str
    chunk_no: int
    doc_date: date | None
    modality: str | None
    text: str


@dataclass(frozen=True)
class Hit:
    source_type: str
    source_id: str
    chunk_no: int
    doc_date: date | None
    modality: str | None
    text: str
    score: float


class VectorBackend(Protocol):
    """What the product needs from a vector index; IrisVectorBackend is the real one, tests use a fake."""

    def search(self, query: str, patient_id: str | None = None, source_type: str | None = None,
               before: date | None = None, top_k: int = 5) -> list[Hit]: ...


# --- connection -------------------------------------------------------------------------------

def _iris_host(fhir_base: str) -> str:
    m = re.match(r"https?://([^:/]+)", fhir_base or "")
    return m.group(1) if m else "localhost"


def connect():
    s = get_settings()
    return iris.connect(hostname=_iris_host(s.iris_fhir_base), port=IRIS_SUPERSERVER_PORT,
                        namespace="FHIRSERVER", username=s.iris_user or "SuperUser",
                        password=s.iris_password or "SYS")


def ensure_table(conn) -> None:
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT TOP 1 PatientId FROM {TABLE}")
    except Exception:  # noqa: BLE001 - table missing
        cur.execute(DDL)
        cur.execute(f"CREATE INDEX PatientIdx ON {TABLE} (PatientId)")


def counts(conn) -> dict[str, int]:
    """Row counts for the status report: chunks, distinct sources per type, patients."""
    cur = conn.cursor()
    out: dict[str, int] = {}
    cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
    out["chunks"] = int(cur.fetchone()[0])
    cur.execute(f"SELECT SourceType, COUNT(DISTINCT SourceId) FROM {TABLE} GROUP BY SourceType")
    for source_type, n in cur.fetchall():
        out[source_type] = int(n)
    cur.execute(f"SELECT COUNT(DISTINCT PatientId) FROM {TABLE}")
    out["patients"] = int(cur.fetchone()[0])
    return out


# --- embeddings and chunking ------------------------------------------------------------------

@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    cache = get_settings().data_dir / "models"
    cache.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=MODEL, cache_dir=str(cache))


def embed(texts: list[str]) -> list[list[float]]:
    return [list(map(float, v)) for v in _model().embed(texts)]


def _vector_literal(vector: list[float]) -> str:
    return ",".join(f"{x:.6f}" for x in vector)


def split_text(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= MAX_CHUNK:
        return [text] if text else []
    parts: list[str] = []
    buf = ""
    for para in re.split(r"\n\s*\n|\n", text):
        if len(buf) + len(para) + 1 > MAX_CHUNK and buf:
            parts.append(buf)
            buf = ""
        buf = f"{buf}\n{para}".strip()
        while len(buf) > MAX_CHUNK:
            parts.append(buf[:MAX_CHUNK])
            buf = buf[MAX_CHUNK:]
    if buf:
        parts.append(buf)
    return parts


def chunks_for_patient(store: FhirStore, patient_id: str) -> Iterator[Chunk]:
    """Chunks of all radiology reports of the patient and, if the patient has imaging, the clinical notes."""
    studies = store.imaging_studies(patient_id)
    modality_by_report: dict[str, str] = {}
    for study in studies:
        sid = next((i["value"] for i in study.get("identifier", []) if i.get("value")), study["id"])
        code = ((study.get("modality") or [{}])[0]).get("code")
        modality_by_report[f"rep-{sid}"] = normalize_modality(code)
    for rep in store.radiology_reports(patient_id):
        if not any(c.get("code") == "RAD" for cat in rep.get("category", []) for c in cat.get("coding", [])):
            continue
        when = to_date(rep.get("effectiveDateTime")) or to_date(rep.get("issued"))
        for i, part in enumerate(split_text(report_text(rep))):
            yield Chunk(patient_id, REPORT, rep["id"], i, when, modality_by_report.get(rep["id"]), part)
    if not studies:
        return
    seen: set[tuple] = set()
    for doc in store.clinical_documents(patient_id):
        text = decode_attachment(doc)
        when = to_date(doc.get("date"))
        key = (when, text[:300])
        if not text.strip() or key in seen:
            continue
        seen.add(key)
        for i, part in enumerate(split_text(text)[:NOTE_MAX_CHUNKS]):
            yield Chunk(patient_id, NOTE, doc["id"], i, when, None, part)


# --- indexing ---------------------------------------------------------------------------------

def index_patient(conn, store: FhirStore, patient_id: str, batch: int = 64) -> int:
    """Replace the patient's chunks; returns the number of chunks stored."""
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE} WHERE PatientId = ?", [patient_id])
    chunks = list(chunks_for_patient(store, patient_id))
    sql = (f"INSERT INTO {TABLE} (PatientId, SourceType, SourceId, ChunkNo, DocDate, Modality, "
           f"ChunkText, Embedding) VALUES (?, ?, ?, ?, ?, ?, ?, TO_VECTOR(?, FLOAT, {DIM}))")
    for start in range(0, len(chunks), batch):
        part = chunks[start:start + batch]
        vectors = embed([c.text for c in part])
        rows = [[c.patient_id, c.source_type, c.source_id, c.chunk_no,
                 c.doc_date.isoformat() if c.doc_date else None, c.modality, c.text[:4000],
                 _vector_literal(v)] for c, v in zip(part, vectors, strict=True)]
        for row in rows:
            cur.execute(sql, row)  # executemany breaks the driver's message sequence on large batches
    return len(chunks)


# --- search -----------------------------------------------------------------------------------

def _as_date(value) -> date | None:  # noqa: ANN001 - driver returns date, datetime or str
    if value is None:
        return None
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    return to_date(str(value))


def search(conn, query: str, patient_id: str | None = None, source_type: str | None = None,
           before: date | None = None, top_k: int = 5) -> list[Hit]:
    where: list[str] = []
    params: list = [_vector_literal(embed([query])[0])]
    if patient_id:
        where.append("PatientId = ?")
        params.append(patient_id)
    if source_type:
        where.append("SourceType = ?")
        params.append(source_type)
    if before:
        where.append("DocDate < ?")
        params.append(before.isoformat())
    sql = (f"SELECT TOP {int(top_k)} SourceType, SourceId, ChunkNo, DocDate, Modality, ChunkText, "
           f"VECTOR_COSINE(Embedding, TO_VECTOR(?, FLOAT, {DIM})) AS Score FROM {TABLE}"
           + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY Score DESC")
    cur = conn.cursor()
    cur.execute(sql, params)
    return [Hit(r[0], r[1], int(r[2]), _as_date(r[3]), r[4], r[5] or "", float(r[6]))
            for r in cur.fetchall()]


class IrisVectorBackend:
    """Opens a short-lived connection per query; the index is small and queries are rare."""

    def search(self, query: str, patient_id: str | None = None, source_type: str | None = None,
               before: date | None = None, top_k: int = 5) -> list[Hit]:
        conn = connect()
        try:
            return search(conn, query, patient_id, source_type, before, top_k)
        finally:
            conn.close()
