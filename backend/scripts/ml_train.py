"""Create, train and validate the IntegratedML models on the synthetic PacsML.RequestHistory.

IntegratedML model names cannot carry a schema, so the models are PacsMLLateArrival (classification) and
PacsMLResponseHours (regression). Run in backend/ after ml_generate_history.py:
PYTHONPATH=. uv run python scripts/ml_train.py

Prerequisite: the AutoML provider (pip package intersystems-iris-automl, installed into /durable/mgr/python)
must be present in the IRIS image, see CLAUDE.md section 20 (D5). TRAIN/VALIDATE MODEL are run in an IRIS
terminal session (docker exec) because the AutoML worker kills a client SQL connection (driver error 10053)
while it trains; PREDICT works over the driver.
"""

from __future__ import annotations

import os
import subprocess

from app.stats.projection import open_cursor

MODELS = {
    "PacsMLLateArrival": ("ArrivedLate", "PacsML.LateTrain", "PacsML.LateValid"),
    "PacsMLResponseHours": ("ResponseHours", "PacsML.HoursTrain", "PacsML.HoursValid"),
}
CONTAINER = os.environ.get("IRIS_CONTAINER", "iris-fhir")
NAMESPACE = os.environ.get("IRIS_NAMESPACE", "FHIRSERVER")


def terminal_sql(statements: list[str]) -> list[str]:
    """Run SQL statements in an IRIS terminal session; returns one 'SQLCODE message' line per statement."""
    lines = []
    for sql in statements:
        escaped = sql.replace('"', '""')
        lines.append(f'set rs=##class(%SQL.Statement).%ExecDirect(,"{escaped}") '
                     'write "RESULT ",rs.%SQLCODE," ",rs.%Message,!')
    script = "\n".join(lines) + "\nhalt\n"
    proc = subprocess.run(["docker", "exec", "-i", CONTAINER, "iris", "session", "IRIS", "-U", NAMESPACE],
                          input=script, capture_output=True, text=True, timeout=1800, check=False)
    return [ln[len("RESULT "):].strip() for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]


def failed(results: list[str]) -> list[str]:
    return [r for r in results if r != "0" and not r.startswith("0 ")]


def train_model(name: str, target: str, train: str, valid: str) -> None:
    results = terminal_sql([
        f"DROP MODEL {name}",
        f"CREATE MODEL {name} PREDICTING ({target}) FROM {train}",
        f"TRAIN MODEL {name}",
        f"VALIDATE MODEL {name} FROM {valid}",
    ])
    errors = failed(results[1:])  # the DROP of a missing model may fail
    if errors or len(results) < 4:
        raise RuntimeError(f"{name}: {errors or results}")


def metrics(cursor, name: str) -> dict[str, float]:
    cursor.execute("SELECT METRIC_NAME, METRIC_VALUE FROM INFORMATION_SCHEMA.ML_VALIDATION_METRICS "
                   "WHERE MODEL_NAME = ? AND TRAINED_MODEL_NAME = (SELECT MAX(TRAINED_MODEL_NAME) "
                   "FROM INFORMATION_SCHEMA.ML_TRAINED_MODELS WHERE MODEL_NAME = ?)", [name, name])
    return {m: float(v) for m, v in cursor.fetchall()}


def main() -> None:
    for name, (target, train, valid) in MODELS.items():
        train_model(name, target, train, valid)
    cursor, close = open_cursor()
    try:
        for name in MODELS:
            print(name, {k: round(v, 3) for k, v in sorted(metrics(cursor, name).items())})
    finally:
        close()


if __name__ == "__main__":
    main()
