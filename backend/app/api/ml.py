"""GET /api/ml/predict: simulated request outcome prediction from IRIS IntegratedML."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.ml.predict import predict_request

router = APIRouter(prefix="/api", tags=["ml"])


@router.get("/ml/predict")
def ml_predict(provider: str, modality: str, region: str = "", channel: str = "email",
               sent_at: datetime | None = None, deadline: datetime | None = None,
               days_to_deadline: float = Query(default=3, ge=0, le=30)) -> dict:
    sent = sent_at or datetime.now().replace(minute=0, second=0, microsecond=0)
    due = deadline or sent + timedelta(days=days_to_deadline)
    try:
        return predict_request(provider, modality, region, sent, due, channel)
    except Exception as exc:  # noqa: BLE001 - driver raises plain exceptions
        raise HTTPException(
            status_code=503,
            detail=f"IntegratedML models unavailable ({type(exc).__name__}); run scripts/ml_train.py",
        ) from exc
