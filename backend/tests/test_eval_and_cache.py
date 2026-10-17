"""AI quality endpoint and the overview cache (synthetic data only)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api import cache as api_cache
from app.config import get_settings
from app.main import create_app


def test_eval_reads_silver_file_or_reports_missing():
    with TestClient(create_app()) as client:
        assert client.get("/api/system/eval").json()["available"] is False
        folder = get_settings().data_dir / "eval"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "silver.json").write_text(json.dumps({"reports": 10, "recall_pct": 90.0, "extra": 1}),
                                            encoding="utf-8")
        data = client.get("/api/system/eval").json()
    assert data["available"] is True and data["reports"] == 10 and data["recall_pct"] == 90.0
    assert "extra" not in data and "Silver" in data["label"]


def test_cache_keeps_value_until_invalidated():
    calls = []
    compute = lambda: calls.append(1) or {"available": True}  # noqa: E731
    api_cache.cached("k", compute)
    api_cache.cached("k", compute)
    assert len(calls) == 1
    api_cache.cached("u", lambda: calls.append(1) or {"available": False}, keep=lambda v: v["available"])
    api_cache.cached("u", lambda: calls.append(1) or {"available": False}, keep=lambda v: v["available"])
    assert len(calls) == 3
    api_cache.invalidate()
    api_cache.cached("k", compute)
    assert len(calls) == 4
