"""Statistics read ONLY from the FHIR SQL Builder projection (SQL package PacsProjection).

The projection is created by scripts/sql_projection_setup.py; these queries never touch the FHIR
repository or the app database. All values are counts, no patient data leaves this module.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.engine import URL, make_url

SCHEMA = "PacsProjection"
CLOSED_TASK_STATUSES = ("completed", "cancelled", "rejected", "failed", "entered-in-error")
UNKNOWN_LABEL = "neznámé"

STUDIES_PER_MODALITY = f"""
SELECT COALESCE(Modality, '{UNKNOWN_LABEL}'), COUNT(*) FROM {SCHEMA}.ImagingStudy
GROUP BY Modality ORDER BY COUNT(*) DESC"""

STUDIES_PACS = f"""
SELECT COUNT(*),
       SUM(CASE WHEN PacsAvailable IN ('1', 'true') THEN 1 ELSE 0 END),
       SUM(CASE WHEN PacsAvailable IN ('0', 'false') THEN 1 ELSE 0 END)
FROM {SCHEMA}.ImagingStudy"""

OPEN_TASKS = f"""
SELECT COALESCE(BusinessStatus, Status, '{UNKNOWN_LABEL}'), COUNT(*) FROM {SCHEMA}.Task
WHERE Status IS NULL OR Status NOT IN ({", ".join("?" for _ in CLOSED_TASK_STATUSES)})
GROUP BY COALESCE(BusinessStatus, Status, '{UNKNOWN_LABEL}') ORDER BY COUNT(*) DESC"""

# A cited prior is "not found" when the same patient has no projected study of that modality
# starting on the cited date (day or month precision). Priors without a date cannot be matched.
PRIORS = f"""
SELECT COUNT(*),
       SUM(CASE WHEN o.RefDate IS NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN o.RefDate IS NOT NULL AND NOT EXISTS (
             SELECT 1 FROM {SCHEMA}.ImagingStudy s
             WHERE s.Patient = o.Patient AND s.Modality = o.Modality
               AND SUBSTRING(s.Started, 1, LENGTH(o.RefDate)) = o.RefDate) THEN 1 ELSE 0 END)
FROM {SCHEMA}.Observation o WHERE o.Category = 'imaging-reference'"""

REQUESTS_PER_HOSPITAL = f"""
SELECT COALESCE(Recipient, '{UNKNOWN_LABEL}'), COUNT(*) FROM {SCHEMA}.Task
GROUP BY Recipient ORDER BY COUNT(*) DESC"""

PLANNED_PER_MODALITY = f"""
SELECT COALESCE(Modality, '{UNKNOWN_LABEL}'), COUNT(*) FROM {SCHEMA}.ServiceRequest
WHERE Intent = 'plan' OR Intent IS NULL GROUP BY Modality ORDER BY COUNT(*) DESC"""


class Cursor(Protocol):
    def execute(self, sql: str, params: Any = ...) -> Any: ...
    def fetchall(self) -> list[Any]: ...


def _pairs(cursor: Cursor, sql: str, params: tuple = ()) -> dict[str, int]:
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    return {str(row[0]): int(row[1]) for row in cursor.fetchall()}


def _row(cursor: Cursor, sql: str) -> tuple[int, ...]:
    cursor.execute(sql)
    rows = cursor.fetchall()
    return tuple(int(value or 0) for value in rows[0]) if rows else ()


def collect_stats(cursor: Cursor) -> dict[str, Any]:
    studies_total, in_pacs, not_in_pacs = _row(cursor, STUDIES_PACS) or (0, 0, 0)
    priors_total, priors_undated, priors_not_found = _row(cursor, PRIORS) or (0, 0, 0)
    tasks = _pairs(cursor, OPEN_TASKS, CLOSED_TASK_STATUSES)
    return {
        "source": f"FHIR SQL Builder projection {SCHEMA}",
        "studies": {
            "total": studies_total,
            "per_modality": _pairs(cursor, STUDIES_PER_MODALITY),
            "in_pacs": in_pacs,
            "not_in_pacs": not_in_pacs,
            "pacs_unknown": studies_total - in_pacs - not_in_pacs,
        },
        "open_tasks": {"total": sum(tasks.values()), "per_state": tasks},
        "cited_priors": {"total": priors_total, "undated": priors_undated, "not_found": priors_not_found},
        "requests_per_hospital": _pairs(cursor, REQUESTS_PER_HOSPITAL),
        "planned_exams_per_modality": _pairs(cursor, PLANNED_PER_MODALITY),
        "simulated": True,
    }


def sql_pool_enabled() -> bool:
    """IRIS app state always shares its bounded pool; the flag also supports explicit opt-in."""
    from app.config import get_settings

    return (make_url(get_settings().app_db_url).get_backend_name() == "iris"
            or os.environ.get("IRIS_SQL_POOL", "").strip() == "1")


def pooled_connection() -> Any:
    """A DBAPI connection from the app_db engine pool (same IRIS namespace); close() returns it to the pool."""
    from app.app_db.session import get_engine

    return get_engine().raw_connection()


def warm_pool(size: int = 4) -> None:
    """Pay the slow first statement once per pooled connection, concurrently, right after startup."""
    from concurrent.futures import ThreadPoolExecutor

    conns = []
    try:
        for _ in range(size):
            conns.append(pooled_connection())

        def ping(conn: Any) -> None:
            cur = conn.cursor()
            try:
                cur.execute("SELECT 1")
                cur.fetchall()
            finally:
                cur.close()

        with ThreadPoolExecutor(size) as pool:
            list(pool.map(ping, conns))
    except Exception:  # noqa: BLE001 - warming is best effort
        pass
    finally:
        for conn in conns:
            conn.close()


def sql_connection() -> Any:
    """Borrow SQL connections, even when app state uses SQLite (local fallback)."""
    if sql_pool_enabled():
        return pooled_connection()
    from app.config import get_settings
    from app.iris_resources import sql_engine

    s = get_settings()
    url = URL.create(
        "iris", s.iris_user or "SuperUser", s.iris_password or "SYS",
        host=os.environ.get("IRIS_SQL_HOST", "localhost"), port=int(os.environ.get("IRIS_SQL_PORT", "1972")),
        database=os.environ.get("IRIS_NAMESPACE", "FHIRSERVER"),
    )
    return sql_engine(url).raw_connection()


def open_cursor() -> tuple[Any, Callable[[], None]]:
    """A cursor whose cleanup closes it and returns its connection to the bounded pool."""
    conn = sql_connection()
    try:
        cur = conn.cursor()
    except Exception:
        conn.close()
        raise

    def close() -> None:
        try:
            cur.close()
        finally:
            conn.close()

    return cur, close


def load_stats() -> dict[str, Any]:
    cursor, close = open_cursor()
    try:
        return collect_stats(cursor)
    finally:
        close()
