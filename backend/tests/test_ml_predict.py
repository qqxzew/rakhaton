"""IntegratedML prediction helpers with a fake DB cursor and synthetic history (no IRIS needed)."""

from __future__ import annotations

import random
from datetime import datetime

from app.ml.history import COLUMNS, generate_history, make_row
from app.ml.predict import SQL, features, predict_request, prediction_for_request


class FakeCursor:
    def __init__(self, row=(0.8, 100.0)):
        self.row, self.calls = row, []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.row


SENT = datetime(2026, 10, 16, 15, 0)  # a Friday afternoon
DUE = datetime(2026, 10, 19, 15, 0)


def test_features_vector():
    assert features("nnh", "pet", "chest,abdomen", SENT, DUE, "mhd") == ["nnh", "PET", "chest", 4, 15, 3, "MHD"]


def test_features_defaults_and_clamping():
    f = features("", "CT", "", DUE, SENT, "carrier pigeon")
    assert f == ["unknown", "CT", "unknown", 0, 15, 0, "email"]


def test_predict_request_uses_one_row_input_and_rounds():
    cur = FakeCursor((1.2, -3.0))
    out = predict_request("nnh", "CT", "chest", SENT, DUE, "email", cur)
    assert out == {"late_probability": 1.0, "expected_hours": 0.0, "simulated": True,
                   "model": "IRIS IntegratedML (AutoML), synthetic history"}
    sql, params = cur.calls[0]
    assert sql == SQL and "PROBABILITY(" in sql and "PREDICT(" in sql and len(params) == 7


def test_prediction_for_request_detail():
    cur = FakeCursor((0.25, 12.34))
    data = {"provider": {"id": "homolka"}, "modality": "PET", "regions": "chest,pelvis", "deadline": "2026-10-20",
            "history": [{"to": "SENT", "ts": "2026-10-16T15:00:00"}], "messages": [{"direction": "out", "channel": "email"}]}
    out = prediction_for_request(data, cur)
    assert out["late_probability"] == 0.25 and out["expected_hours"] == 12.3 and out["simulated"] is True
    assert cur.calls[0][1][:5] == ["homolka", "PET", "chest", 4, 15]


def test_prediction_for_request_is_optional():
    assert prediction_for_request({"deadline": ""}, FakeCursor()) is None

    class Broken(FakeCursor):
        def execute(self, sql, params=None):
            raise RuntimeError("model missing")

    assert prediction_for_request({"deadline": "2026-10-20"}, Broken()) is None


def test_history_is_simulated_and_has_the_planted_patterns():
    rows = generate_history(2000, seed=1)
    assert all(r["Simulated"] == 1 and set(r) == set(COLUMNS) for r in rows)
    assert not any("PAC" in str(v) for r in rows for v in r.values())

    def late_rate(sel):
        part = [r for r in rows if sel(r)]
        return sum(r["ArrivedLate"] for r in part) / len(part)

    assert late_rate(lambda r: r["Provider"] == "homolka") > late_rate(lambda r: r["Provider"] == "motol")
    assert late_rate(lambda r: r["DaysToDeadline"] <= 2) > late_rate(lambda r: r["DaysToDeadline"] >= 8)
    assert late_rate(lambda r: r["Modality"] == "PET") > late_rate(lambda r: r["Modality"] == "RTG")


def test_row_is_consistent():
    row = make_row(random.Random(3), ["nnh"])
    assert row["ArrivedLate"] == int(row["ResponseHours"] > row["DaysToDeadline"] * 24)
