"""Process-owned IRIS sessions: persistent FHIR cookies and serialized native connections."""

from __future__ import annotations

import threading
from typing import Any

import httpx
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from app.config import Settings, get_settings
from app.logging import get_logger

log = get_logger(__name__)
_lock = threading.Lock()
_http: dict[tuple[str, str, str], httpx.Client] = {}
_native: dict[tuple, NativeSession] = {}
_sql: dict[URL, Engine] = {}


class _FhirClient(httpx.Client):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._session_lock = threading.Lock()

    def request(self, *args: Any, **kwargs: Any) -> httpx.Response:
        # Build the next request only after the preceding response has installed its CSP cookie.
        with self._session_lock:
            return super().request(*args, **kwargs)


def fhir_client(base: str, settings: Settings | None = None) -> httpx.Client:
    """One keep-alive client and CSP cookie jar per configured FHIR base and credentials."""
    s = settings or get_settings()
    key = (base.rstrip("/"), s.iris_user or "SuperUser", s.iris_password or "SYS")
    with _lock:
        client = _http.get(key)
        if client is None or client.is_closed:
            client = _FhirClient(
                auth=key[1:], headers={"Accept": "application/fhir+json"},
                timeout=httpx.Timeout(60, connect=5, pool=3),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=None),
            )
            _http[key] = client
        return client


class NativeSession:
    """A native connection is not thread-safe; serialize both creation and calls."""

    def __init__(self, args: tuple) -> None:
        self._args = args
        self._lock = threading.RLock()
        self._conn: Any = None
        self._api: Any = None

    def _call(self, method: str, *args: Any) -> Any:
        import iris

        with self._lock:
            try:
                if self._api is None:
                    self._conn = iris.createConnection(*self._args)
                    self._api = iris.createIRIS(self._conn)
                return getattr(self._api, method)(*args)
            except Exception:
                try:
                    self.close()
                except Exception:  # noqa: BLE001 - preserve the original call failure
                    pass
                raise

    def classMethodValue(self, *args: Any) -> Any:
        return self._call("classMethodValue", *args)

    def get(self, *args: Any) -> Any:
        return self._call("get", *args)

    def close(self) -> None:
        with self._lock:
            try:
                if self._conn is not None:
                    self._conn.close()
            finally:
                self._conn = self._api = None


def native_session(*args: Any) -> NativeSession:
    """Share a single native session per server/namespace/credentials, including across clients."""
    with _lock:
        if args not in _native:
            _native[args] = NativeSession(args)
        return _native[args]


def sql_engine(url: URL) -> Engine:
    """The local/SQLite fallback still needs a bounded IRIS pool for projection reads."""
    from app.app_db.session import make_engine

    with _lock:
        if url not in _sql:
            _sql[url] = make_engine(url.render_as_string(hide_password=False))
        return _sql[url]


def close_resources() -> None:
    """Release process-owned resources on application shutdown."""
    with _lock:
        for resource in [*_http.values(), *_native.values(), *_sql.values()]:
            try:
                if isinstance(resource, Engine):
                    resource.dispose()
                else:
                    resource.close()
            except Exception as exc:  # noqa: BLE001 - release the remaining sessions even after a close failure
                log.warning("IRIS resource cleanup failed", extra={"fields": {"error": type(exc).__name__}})
        _http.clear()
        _sql.clear()
