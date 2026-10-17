"""Test configuration: synthetic data only, an isolated data directory, no access to data/raw."""

from __future__ import annotations

import builtins
import pathlib
from pathlib import Path

import pytest

from app import config as app_config

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = (REPO_ROOT / "data" / "raw").resolve()


def _is_forbidden(path: object) -> bool:
    try:
        resolved = Path(str(path)).resolve()
    except (OSError, ValueError, TypeError):
        return False
    return resolved == FORBIDDEN or FORBIDDEN in resolved.parents


@pytest.fixture(autouse=True)
def _no_real_dataset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Fail any test that tries to read the real dataset, and isolate DATA_DIR in a temp folder."""
    real_open = builtins.open
    real_path_open = pathlib.Path.open
    real_read_text = pathlib.Path.read_text
    real_read_bytes = pathlib.Path.read_bytes

    def guard(path: object) -> None:
        if _is_forbidden(path):
            raise AssertionError("tests must not read data/raw")

    def guarded_open(file, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        guard(file)
        return real_open(file, *args, **kwargs)

    def guarded_path_open(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        guard(self)
        return real_path_open(self, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        guard(self)
        return real_read_text(self, *args, **kwargs)

    def guarded_read_bytes(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        guard(self)
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(pathlib.Path, "open", guarded_path_open)
    monkeypatch.setattr(pathlib.Path, "read_text", guarded_read_text)
    monkeypatch.setattr(pathlib.Path, "read_bytes", guarded_read_bytes)

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    for name in ("APP_DB_URL", "DEMO_TODAY", "FHIR_BACKEND", "IRIS_FHIR_BASE", "IRIS_USER", "IRIS_PASSWORD",
                 "LLM_BASE_URL", "LLM_MODEL_EXTRACT", "LLM_MODEL_FAST", "AVAILABILITY_ADAPTER"):
        monkeypatch.delenv(name, raising=False)
    # Production defaults are IRIS; unit tests run on local files and SQLite so they need no containers.
    monkeypatch.setenv("FHIR_BACKEND", "local")
    monkeypatch.setenv("AVAILABILITY_ADAPTER", "dataset_flag")
    monkeypatch.setenv("APP_DB_URL", f"sqlite:///{(tmp_path / 'data' / 'app.db').as_posix()}")
    monkeypatch.setenv("API_KEY", "test-key-not-real")
    app_config.get_settings.cache_clear()
    from app.api import cache as api_cache

    api_cache.invalidate()
    yield
    app_config.get_settings.cache_clear()
