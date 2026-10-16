"""Settings read from the environment (and the git-ignored .env at the repository root)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

load_dotenv(REPO_ROOT / ".env")

DEFAULT_LLM_BASE_URL = "https://apim-rakathon-q7146n.azure-api.net/openai/v1/"
# IRIS for Health is the core store: FHIR for clinical facts, IRIS SQL for app state (docker-compose.yml).
DEFAULT_IRIS_FHIR_BASE = "http://localhost:52773/fhir/r4"
DEFAULT_APP_DB_URL = "iris://SuperUser:SYS@localhost:1972/FHIRSERVER"


def _data_dir() -> Path:
    raw = Path(os.environ.get("DATA_DIR", "data"))
    return raw if raw.is_absolute() else REPO_ROOT / raw


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    app_db_url: str
    api_key: str = field(default="", repr=False)
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_model_extract: str = "gpt-6-1-sol-dz-eu"
    llm_model_fast: str = "gpt-6-luna-dz-eu"
    fhir_backend: str = "iris"
    iris_fhir_base: str = DEFAULT_IRIS_FHIR_BASE
    iris_user: str = field(default="", repr=False)
    iris_password: str = field(default="", repr=False)
    demo_today: date | None = None

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def fhir_out_dir(self) -> Path:
        return self.data_dir / "fhir_out"


def _resolve_db_url(url: str) -> str:
    """Relative SQLite paths (as in .env.example) are relative to the repository root, not the CWD."""
    prefix = "sqlite:///"
    if url.startswith(prefix) and ":memory:" not in url:
        path = Path(url.removeprefix(prefix))
        if not path.is_absolute():
            return f"{prefix}{(REPO_ROOT / path).as_posix()}"
    return url


@lru_cache
def get_settings() -> Settings:
    data_dir = _data_dir()
    demo_today = os.environ.get("DEMO_TODAY", "").strip()
    return Settings(
        data_dir=data_dir,
        app_db_url=_resolve_db_url(
            os.environ.get("APP_DB_URL", "").strip() or DEFAULT_APP_DB_URL
        ),
        api_key=os.environ.get("API_KEY", "").strip(),
        llm_base_url=os.environ.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
        llm_model_extract=os.environ.get("LLM_MODEL_EXTRACT", "gpt-6-1-sol-dz-eu"),
        llm_model_fast=os.environ.get("LLM_MODEL_FAST", "gpt-6-luna-dz-eu"),
        fhir_backend=os.environ.get("FHIR_BACKEND", "").strip() or "iris",
        iris_fhir_base=os.environ.get("IRIS_FHIR_BASE", "").strip() or DEFAULT_IRIS_FHIR_BASE,
        iris_user=os.environ.get("IRIS_USER", ""),
        iris_password=os.environ.get("IRIS_PASSWORD", ""),
        demo_today=date.fromisoformat(demo_today) if demo_today else None,
    )


def today() -> date:
    return get_settings().demo_today or date.today()
