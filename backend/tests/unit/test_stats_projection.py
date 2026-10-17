"""Stats from the SQL projection, tested with a fake DB-API cursor (synthetic values only)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.stats import projection


class FakeCursor:
    def __init__(self) -> None:
        self.rows: list = []
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, tuple(params)))
        if "FROM PacsProjection.ImagingStudy\nGROUP BY Modality" in sql:
            self.rows = [("CT", 5), ("MR", 2)]
        elif "PacsAvailable IN" in sql:
            self.rows = [(7, 4, 2)]
        elif "FROM PacsProjection.Task\nWHERE" in sql:
            self.rows = [("SENT", 3), ("DRAFTED", 1)]
        elif "PacsProjection.Observation" in sql:
            self.rows = [(6, 1, 2)]
        elif "Recipient" in sql:
            self.rows = [("Test hospital", 2), ("neznámé", 1)]
        elif "PacsProjection.ServiceRequest" in sql:
            self.rows = [("PET", 2)]
        else:
            raise AssertionError(sql)

    def fetchall(self) -> list:
        return self.rows


def test_collect_stats_shapes_all_figures() -> None:
    cursor = FakeCursor()
    stats = projection.collect_stats(cursor)
    assert stats["studies"] == {
        "total": 7, "per_modality": {"CT": 5, "MR": 2}, "in_pacs": 4, "not_in_pacs": 2, "pacs_unknown": 1,
    }
    assert stats["open_tasks"] == {"total": 4, "per_state": {"SENT": 3, "DRAFTED": 1}}
    assert stats["cited_priors"] == {"total": 6, "undated": 1, "not_found": 2}
    assert stats["requests_per_hospital"] == {"Test hospital": 2, "neznámé": 1}
    assert stats["planned_exams_per_modality"] == {"PET": 2}
    assert stats["simulated"] is True


def test_only_projection_tables_are_queried_and_closed_states_excluded() -> None:
    cursor = FakeCursor()
    projection.collect_stats(cursor)
    for sql, _ in cursor.executed:
        assert "PacsProjection." in sql
    task_params = [params for sql, params in cursor.executed if "Task\nWHERE" in sql][0]
    assert task_params == projection.CLOSED_TASK_STATUSES


def test_empty_projection_gives_zeros() -> None:
    class Empty(FakeCursor):
        def execute(self, sql: str, params: tuple = ()) -> None:
            self.rows = []

    stats = projection.collect_stats(Empty())
    assert stats["studies"]["total"] == 0
    assert stats["cited_priors"]["not_found"] == 0
    assert stats["open_tasks"]["per_state"] == {}


def test_endpoint_returns_stats_and_503_when_unavailable(monkeypatch) -> None:
    from app.main import create_app

    client = TestClient(create_app())
    monkeypatch.setattr("app.api.stats.load_stats", lambda: {"studies": {"total": 1}})
    assert client.get("/api/stats").json() == {"studies": {"total": 1}}

    def boom() -> dict:
        raise ConnectionError

    monkeypatch.setattr("app.api.stats.load_stats", boom)
    assert client.get("/api/stats").status_code == 503
