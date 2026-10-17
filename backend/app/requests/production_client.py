"""Thin native-API client of the PacsComparator production in IRIS (T081, T082).

The backend only submits events to the business service and reads the production's state.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.iris_resources import native_session

NAMESPACE = "FHIRSERVER"
INTAKE = "PacsComparator.BS.RequestIntake"
API = "PacsComparator.Req.Api"
VISUAL_TRACE_PATH = "/csp/healthshare/fhirserver/EnsPortal.VisualTrace.zen"


class ProductionError(RuntimeError):
    pass


def visual_trace_url(session_id: str | int, host: str = "http://localhost:52773") -> str:
    return f"{host}{VISUAL_TRACE_PATH}?SESSIONID={session_id}"


class ProductionClient:
    def __init__(self, host: str = "localhost", port: int = 1972, user: str | None = None,
                 password: str | None = None) -> None:
        settings = get_settings()
        self._args = (host, port, NAMESPACE, user or settings.iris_user or "SuperUser",
                      password or settings.iris_password or "SYS")
        self._irispy: Any = None

    def _api(self) -> Any:
        if self._irispy is None:
            try:
                self._irispy = native_session(*self._args)
            except Exception as exc:  # connection errors come in several native types
                raise ProductionError(f"IRIS production unreachable: {exc}") from exc
        return self._irispy

    def _call(self, cls: str, method: str, *args: Any) -> Any:
        try:
            raw = self._api().classMethodValue(cls, method, *args)
        except ProductionError:
            raise
        except Exception as exc:
            self._irispy = None
            raise ProductionError(f"{cls}.{method} failed: {exc}") from exc
        return json.loads(raw) if isinstance(raw, str) and raw[:1] in "{[" else raw

    def submit(self, action: str, request_id: str = "", payload: dict | None = None, actor: str = "system") -> dict:
        result = self._call(INTAKE, "Submit", action, request_id, json.dumps(payload or {}), actor)
        if not isinstance(result, dict) or not result.get("ok"):
            error = result.get("error") if isinstance(result, dict) else result
            raise ProductionError(str(error or "production rejected the event"))
        return result

    def get(self, request_id: str) -> dict | None:
        data = self._call(API, "Get", request_id)
        return data if data.get("found") else None

    def list(self, case_id: str = "") -> list[dict]:
        return self._call(API, "List", case_id)

    def draft_ids(self, case_ids: list[str] | None = None) -> list[str]:
        raw = self._call(API, "DraftIds", ",".join(case_ids or []))
        return [i for i in str(raw or "").split(",") if i]

    def advance_time(self, hours: float) -> dict:
        return self._call(API, "AdvanceTime", hours)

    def reset_clock(self) -> dict:
        return self._call(API, "ResetClock")

    def audio(self, message_id: str | int) -> bytes:
        raw = self._call(API, "Audio", str(message_id))
        return base64.b64decode(raw) if raw else b""


@lru_cache
def get_client() -> ProductionClient:
    return ProductionClient()


def sync_files(request: dict, client: ProductionClient, data_dir: Path | None = None) -> None:
    """Mirror outgoing emails and voice messages to data/outbox and data/voice (git-ignored)."""
    base = data_dir or get_settings().data_dir
    for message in request.get("messages", []):
        if message["kind"] in ("email", "reminder") and message["direction"] == "out":
            folder = base / "outbox"
            folder.mkdir(parents=True, exist_ok=True)
            text = (f"Subject: {message['subject']}\nTo: {request['provider'].get('email', '')}\n"
                    f"X-Simulation: true\nContent-Type: text/plain; charset=utf-8\n\n{message['body']}\n")
            (folder / f"{request['requestId']}-{message['id']}.eml").write_text(text, encoding="utf-8")
        if message.get("hasAudio"):
            folder = base / "voice"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{request['requestId']}.mp3"
            if not target.exists():
                target.write_bytes(client.audio(message["id"]))
