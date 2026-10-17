"""Generate the synthetic request history table PacsML.RequestHistory (simulated data only).

Run in backend/: PYTHONPATH=. uv run python scripts/ml_generate_history.py [--rows 3000]
"""

from __future__ import annotations

import argparse

from app.ml.history import COLUMNS, generate_history
from app.stats.projection import open_cursor

DDL = """CREATE TABLE PacsML.RequestHistory (
  Provider VARCHAR(30), Modality VARCHAR(10), Region VARCHAR(20), SendWeekday INTEGER, SendHour INTEGER,
  DaysToDeadline INTEGER, Channel VARCHAR(10), Reminders INTEGER, VoiceEscalated INTEGER,
  ResponseHours DOUBLE, ArrivedLate INTEGER, Simulated INTEGER)"""

FEATURES = "Provider, Modality, Region, SendWeekday, SendHour, DaysToDeadline, Channel"
# 80 % train, 20 % hold-out for VALIDATE MODEL
VIEWS = {
    "LateTrain": ("ArrivedLate", "<>"), "LateValid": ("ArrivedLate", "="),
    "HoursTrain": ("ResponseHours", "<>"), "HoursValid": ("ResponseHours", "="),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=88)
    args = parser.parse_args()
    cursor, close = open_cursor()
    try:
        for stmt in [*(f"DROP VIEW PacsML.{n}" for n in VIEWS), "DROP TABLE PacsML.RequestHistory"]:
            try:
                cursor.execute(stmt)
            except Exception:  # noqa: BLE001 - object may not exist yet
                pass
        cursor.execute(DDL)
        rows = generate_history(args.rows, args.seed)
        marks = ",".join("?" * len(COLUMNS))
        sql = f"INSERT INTO PacsML.RequestHistory ({','.join(COLUMNS)}) VALUES ({marks})"
        for row in rows:
            cursor.execute(sql, [row[c] for c in COLUMNS])
        # Only features known when a request is sent may be used for training (no reminders, no response time).
        for name, (target, op) in VIEWS.items():
            cursor.execute(f"CREATE VIEW PacsML.{name} AS SELECT {FEATURES}, {target} "
                           f"FROM PacsML.RequestHistory WHERE %ID # 5 {op} 0")
        cursor.execute("SELECT COUNT(*), SUM(ArrivedLate), AVG(ResponseHours) FROM PacsML.RequestHistory")
        total, late, avg = cursor.fetchone()
        print(f"PacsML.RequestHistory: {total} rows (Simulated=1), late {late}, mean response {avg:.1f} h")
    finally:
        close()


if __name__ == "__main__":
    main()
