"""Synthetic request history for IntegratedML (T088). Every row is simulated; there are no patient ids."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

PROVIDERS_FILE = Path(__file__).resolve().parents[3] / "config" / "providers.json"
MODALITIES = ["CT", "MR", "PET", "RTG", "SONO", "MAMO"]
REGIONS = ["chest", "abdomen", "pelvis", "head", "neck", "spine", "breast", "whole_body"]
CHANNELS = ["email", "FHIR", "MHD"]

# Median response hours per provider (synthetic): one provider is clearly slow, Motol itself is fast.
PROVIDER_BASE_HOURS = {"motol": 6, "nnh": 30, "homolka": 90, "vfn": 28, "fnm": 34, "ikem": 26,
                       "bulovka": 40, "thomayer": 44, "plzen": 52, "brno": 56, "unknown": 70}

COLUMNS = ["Provider", "Modality", "Region", "SendWeekday", "SendHour", "DaysToDeadline", "Channel",
           "Reminders", "VoiceEscalated", "ResponseHours", "ArrivedLate", "Simulated"]


def provider_ids() -> list[str]:
    data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data["providers"]
    return [p["id"] for p in items]


def response_hours(rng: random.Random, provider: str, modality: str, weekday: int, hour: int, channel: str) -> float:
    hours = PROVIDER_BASE_HOURS.get(provider, 48) * rng.lognormvariate(0, 0.35)
    if modality == "PET":
        hours *= 1.8
    elif modality in ("MR", "CT"):
        hours *= 1.1
    if channel == "MHD":
        hours *= 0.6
    elif channel == "FHIR":
        hours *= 0.8
    if weekday == 4 and hour >= 14:
        hours += 48  # Friday afternoon waits for Monday
    elif weekday >= 5:
        hours += 24
    elif hour >= 16 or hour < 7:
        hours += 12
    return round(hours, 1)


def make_row(rng: random.Random, providers: list[str]) -> dict[str, Any]:
    provider = rng.choice(providers)
    modality = rng.choices(MODALITIES, weights=[30, 20, 10, 20, 10, 10])[0]
    weekday, hour = rng.randrange(0, 7), rng.randrange(6, 20)
    days = rng.choices(range(1, 15), weights=[8, 10, 10, 9, 8, 7, 7, 5, 4, 3, 3, 2, 2, 2])[0]
    channel = rng.choices(CHANNELS, weights=[6, 2, 2])[0]
    hours = response_hours(rng, provider, modality, weekday, hour, channel)
    late = int(hours > days * 24)
    reminders = min(3, int(hours // 24))
    voice = int(reminders >= 2 and hours > 48)
    return {
        "Provider": provider, "Modality": modality, "Region": rng.choice(REGIONS), "SendWeekday": weekday,
        "SendHour": hour, "DaysToDeadline": days, "Channel": channel, "Reminders": reminders,
        "VoiceEscalated": voice, "ResponseHours": hours, "ArrivedLate": late, "Simulated": 1,
    }


def generate_history(n: int = 3000, seed: int = 88) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    providers = provider_ids()
    return [make_row(rng, providers) for _ in range(n)]
