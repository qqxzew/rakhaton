"""Request outcome predictions from IRIS IntegratedML (T088). Trained on a synthetic history only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.ml.history import CHANNELS

LATE_MODEL = "PacsMLLateArrival"
HOURS_MODEL = "PacsMLResponseHours"

SQL = (
    f"SELECT PROBABILITY({LATE_MODEL} FOR 1) AS LateProbability, PREDICT({HOURS_MODEL}) AS ExpectedHours "
    "FROM (SELECT ? AS Provider, ? AS Modality, ? AS Region, ? AS SendWeekday, ? AS SendHour, "
    "? AS DaysToDeadline, ? AS Channel)"
)


def features(provider: str, modality: str, region: str, sent_at: datetime, deadline: datetime,
             channel: str) -> list[Any]:
    days = max(0, min(30, round((deadline - sent_at).total_seconds() / 86400)))
    channel = next((c for c in CHANNELS if c.lower() == (channel or "").lower()), "email")
    first_region = (region or "").replace(";", ",").split(",")[0].strip() or "unknown"
    return [provider or "unknown", (modality or "unknown").upper(), first_region, sent_at.weekday(), sent_at.hour,
            days, channel]


def _parse_ts(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def prediction_for_request(data: dict[str, Any], cursor: Any = None) -> dict[str, Any] | None:
    """Prediction for a request detail dict; None when the inputs or the models are not available."""
    sent_events = [e for e in data.get("history", []) if e.get("to") == "SENT"]
    sent = _parse_ts(sent_events[0]["ts"]) if sent_events else None
    sent = sent or datetime.now().replace(minute=0, second=0, microsecond=0)
    due = _parse_ts(data.get("deadline"))
    if due is None:
        return None
    due = due.replace(hour=23, minute=59)
    channel = next((m.get("channel") for m in data.get("messages", []) if m.get("direction") == "out"), "email")
    try:
        return predict_request((data.get("provider") or {}).get("id", "unknown"), data.get("modality", ""),
                               data.get("regions", ""), sent, due, channel or "email", cursor)
    except Exception:  # noqa: BLE001 - the prediction is optional, never break the request detail
        return None


def predict_request(provider: str, modality: str, region: str, sent_at: datetime, deadline: datetime,
                    channel: str, cursor: Any = None) -> dict[str, Any]:
    """Probability that the study arrives after the deadline and the expected response time in hours."""
    close = None
    if cursor is None:
        from app.stats.projection import open_cursor

        cursor, close = open_cursor()
    try:
        cursor.execute(SQL, features(provider, modality, region, sent_at, deadline, channel))
        late, hours = cursor.fetchone()
    finally:
        if close:
            close()
    return {
        "late_probability": round(min(1.0, max(0.0, float(late))), 3),
        "expected_hours": round(max(0.0, float(hours)), 1),
        "simulated": True,
        "model": "IRIS IntegratedML (AutoML), synthetic history",
    }
