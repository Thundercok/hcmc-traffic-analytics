"""Deterministic traffic priors used for cold-start data deficiency handling.

These estimates are not a substitute for live camera predictions. They provide a
clearly labeled baseline for demos, cold starts, and forecast fallback when the
database does not yet contain enough history.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime


def density_level_from_count(total_count: int) -> str:
    """Map a vehicle count to the app's density labels."""
    if total_count < 50:
        return "low"
    if total_count < 200:
        return "moderate"
    if total_count < 400:
        return "heavy"
    return "severe"


def _stable_unit(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _district_factor(district: str | None) -> float:
    text = (district or "").lower()
    central_keywords = ("quan 1", "quan 3", "quan 5", "binh thanh", "phu nhuan")
    suburban_keywords = ("can gio", "cu chi", "hoc mon", "nha be")

    if any(key in text for key in central_keywords):
        return 1.25
    if any(key in text for key in suburban_keywords):
        return 0.78
    return 1.0


def time_multiplier(ts: datetime) -> float:
    """Return a simple HCMC traffic multiplier for a timestamp."""
    hour = ts.hour + ts.minute / 60
    weekday = ts.weekday()
    weekend = weekday >= 5

    morning = math.exp(-((hour - 8.0) ** 2) / 4.0)
    evening = math.exp(-((hour - 17.6) ** 2) / 4.5)
    lunch = math.exp(-((hour - 12.0) ** 2) / 9.0)
    night = 0.55 if hour < 5.5 or hour >= 22 else 1.0
    weekend_factor = 0.82 if weekend else 1.0

    return max(0.35, (0.65 + 0.75 * morning + 0.9 * evening + 0.22 * lunch) * night * weekend_factor)


def estimate_prediction(camera: dict, ts: datetime) -> dict:
    """Create a deterministic baseline prediction for a camera and timestamp."""
    camera_id = str(camera.get("id", "unknown"))
    camera_seed = _stable_unit(camera_id)
    daily_phase = 2 * math.pi * ((ts.hour * 60 + ts.minute) / 1440)
    weekly_phase = 2 * math.pi * (ts.weekday() / 7)

    base = 24 + 105 * camera_seed
    district = _district_factor(camera.get("district"))
    periodic = 1 + 0.08 * math.sin(daily_phase + camera_seed * 3) + 0.05 * math.cos(weekly_phase)
    total = int(max(4, round(base * district * time_multiplier(ts) * periodic)))

    motorbike_ratio = 0.68 + 0.13 * _stable_unit(camera_id + ":moto")
    motorbike_count = max(1, int(round(total * motorbike_ratio)))
    car_count = max(1, total - motorbike_count)

    return {
        "total_count": total,
        "car_count": car_count,
        "motorbike_count": motorbike_count,
        "density_level": density_level_from_count(total),
        "confidence": 0.35,
        "quality_score": 0.45,
        "data_source": "synthetic_bootstrap",
    }


def time_features(ts: datetime) -> dict:
    hour = ts.hour
    return {
        "hour": hour,
        "day_of_week": ts.weekday(),
        "is_morning_rush": 7 <= hour <= 9,
        "is_evening_rush": 16 <= hour <= 19,
        "is_weekend": ts.weekday() >= 5,
    }
