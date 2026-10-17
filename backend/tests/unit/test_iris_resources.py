"""IRIS resource bounds and ownership, without a running IRIS server."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import httpx
import iris
import pytest
from sqlalchemy.engine import URL

from app import iris_resources as resources
from app.api.system import FhirReader, IrisSystem
from app.app_db import session
from app.app_db.session import make_engine
from app.exchange.dicom import IrisCFindClient
from app.exchange.hospitals import make_client
from app.fhir_store.iris import IrisFhirStore
from app.requests.production_client import ProductionClient
from app.stats import projection


@pytest.fixture(autouse=True)
def cleanup():
    resources.close_resources()
    yield
    resources.close_resources()


def test_iris_pool_is_bounded_and_sqlite_is_unchanged():
    engine = make_engine("iris://localhost:1972/FHIRSERVER")
    assert engine.pool.size() == 4
    assert engine.pool._max_overflow == 0
    assert engine.pool.timeout() == 3
    engine.dispose()
    sqlite = make_engine("sqlite:///:memory:")
    with sqlite.connect() as conn:
        assert conn.exec_driver_sql("SELECT 1").scalar() == 1
    sqlite.dispose()


def test_native_sessions_are_shared_and_creation_is_serialized(monkeypatch):
    connect = Mock()
    api = Mock()
    api.classMethodValue.return_value = "[]"
    monkeypatch.setattr(iris, "createConnection", connect)
    monkeypatch.setattr(iris, "createIRIS", Mock(return_value=api))

    def read(_):
        assert ProductionClient().list("CASE-TEST") == []
        assert IrisSystem().native().classMethodValue("Example", "Read") == "[]"

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(read, range(20)))
    assert connect.call_count == 1
    # The DICOM namespace has a separate, shared connection.
    for _ in range(20):
        IrisCFindClient()._api().classMethodValue("Example", "Read")
    assert connect.call_count == 2


@pytest.mark.parametrize("fail_creation", [False, True])
def test_failed_native_connections_are_closed_before_reconnecting(monkeypatch, fail_creation):
    connections = [Mock(), Mock()]
    api = Mock()
    api.classMethodValue.side_effect = [RuntimeError("disconnected"), "[]"] if not fail_creation else ["[]"]
    connect = Mock(side_effect=connections)
    monkeypatch.setattr(iris, "createConnection", connect)
    monkeypatch.setattr(iris, "createIRIS", Mock(
        side_effect=[RuntimeError("initialization failed"), api] if fail_creation else [api, api]))
    client = ProductionClient()
    from app.requests.production_client import ProductionError

    with pytest.raises(ProductionError):
        client.list()
    connections[0].close.assert_called_once()
    assert client.list() == []
    assert connect.call_count == 2


def test_fhir_clients_reuse_cookies_across_consumers_and_keep_bases_separate(monkeypatch):
    original = resources._FhirClient
    created = []

    def respond(request):
        if len(created) == 1 and request.url.path.endswith("/Patient"):
            assert request.headers.get("cookie") == "CSPSESSION=test-session"
        return httpx.Response(200, json={"total": 1}, headers={"set-cookie": "CSPSESSION=test-session; Path=/"})

    def factory(**kwargs):
        client = original(**kwargs, transport=httpx.MockTransport(respond))
        created.append(client)
        return client

    monkeypatch.setattr(resources, "_FhirClient", factory)
    base = "http://localhost:52773/fhir/r4"
    first = make_client()
    first.get(f"{base}/metadata")
    for _ in range(20):
        assert IrisFhirStore()._client is first
        assert make_client(base=base + "/") is first
        reader = FhirReader()
        assert reader.count(base, "Patient") == 1
        reader.close()
        assert not first.is_closed
    assert len(created) == 1
    assert make_client(base="http://localhost:52773/nnh/fhir/r4") is not first
    assert len(created) == 2
    resources.close_resources()
    assert all(client.is_closed for client in created)


def test_sql_readers_borrow_and_release_pooled_connections(monkeypatch):
    monkeypatch.setenv("APP_DB_URL", "iris://localhost:1972/FHIRSERVER")
    from app.config import get_settings

    get_settings.cache_clear()
    conn = Mock()
    monkeypatch.setattr(projection, "pooled_connection", Mock(return_value=conn))
    assert projection.sql_pool_enabled()  # no cloud flag required
    for _ in range(20):
        cursor, close = projection.open_cursor()
        assert cursor is conn.cursor.return_value
        close()
        system = IrisSystem()
        assert system.cursor() is conn.cursor.return_value
        system.close()
    assert conn.close.call_count == 40
    assert conn.cursor.return_value.close.call_count == 40


def test_warmup_releases_partial_acquisitions(monkeypatch):
    first = Mock()
    monkeypatch.setattr(projection, "pooled_connection", Mock(side_effect=[first, RuntimeError("pool full")]))
    projection.warm_pool()
    first.close.assert_called_once()


def test_fallback_sql_pool_creation_is_serialized_and_disposed(monkeypatch):
    engine = make_engine("iris://localhost:1972/FHIRSERVER")
    dispose = Mock(wraps=engine.dispose)
    monkeypatch.setattr(engine, "dispose", dispose)
    factory = Mock(return_value=engine)
    monkeypatch.setattr(session, "make_engine", factory)
    with ThreadPoolExecutor(8) as pool:
        engines = list(pool.map(lambda _: resources.sql_engine(URL.create("iris", host="localhost")), range(20)))
    assert all(e is engine for e in engines)
    factory.assert_called_once()
    resources.close_resources()
    dispose.assert_called_once()


def test_cleanup_continues_after_a_close_failure():
    broken, healthy = Mock(), Mock()
    broken.close.side_effect = RuntimeError("close failed")
    resources._http[("http://one.test", "", "")] = broken
    resources._http[("http://two.test", "", "")] = healthy
    resources.close_resources()
    healthy.close.assert_called_once()
    assert resources._http == {}
