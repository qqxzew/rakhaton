"""Semantic search over one patient's reports and notes (IRIS Vector Search) for the UI and agent tools."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.errors import DependencyUnavailable, ValidationFailed
from app.search.vector_store import VectorBackend

router = APIRouter(prefix="/api/search", tags=["search"])

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class SearchHit(BaseModel):
    source_type: str
    id: str
    date: str | None
    modality: str | None = None
    score: float
    text: str | None = None


class SearchResponse(BaseModel):
    patient_id: str
    query: str
    hits: list[SearchHit]


def get_vector_backend() -> VectorBackend:
    from app.search.vector_store import IrisVectorBackend

    return IrisVectorBackend()


@router.get("/reports", response_model=SearchResponse)
def search_reports(
    patient_id: str = Query(min_length=1, max_length=128),
    q: str = Query(min_length=2, max_length=500),
    top: int = Query(5, ge=1, le=20),
    include_text: bool = False,
    backend: VectorBackend = Depends(get_vector_backend),
) -> SearchResponse:
    if not _SAFE_ID.match(patient_id):
        raise ValidationFailed("Neplatné ID pacienta")
    try:
        hits = backend.search(q, patient_id=patient_id, top_k=top * 4)
    except Exception as exc:  # noqa: BLE001 - IRIS or model unavailable
        raise DependencyUnavailable("Vektorové vyhledávání není dostupné") from exc
    best: dict[str, SearchHit] = {}
    for h in hits:
        if h.source_id in best:
            continue
        best[h.source_id] = SearchHit(
            source_type=h.source_type, id=h.source_id, date=h.doc_date.isoformat() if h.doc_date else None,
            modality=h.modality, score=round(h.score, 4), text=h.text if include_text else None,
        )
    return SearchResponse(patient_id=patient_id, query=q, hits=list(best.values())[:top])
