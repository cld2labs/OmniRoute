from __future__ import annotations

from datetime import datetime


def hour_demand_multiplier(moment: datetime) -> float:
    hour = moment.hour
    if 6 <= hour <= 9:
        return 1.45
    if 16 <= hour <= 19:
        return 1.55
    if 10 <= hour <= 15:
        return 1.0
    return 0.65


def weekday_multiplier(moment: datetime) -> float:
    return 1.15 if moment.weekday() < 5 else 0.85


def route_demand_weight(popularity_score: int) -> float:
    return max(0.25, popularity_score / 100.0)
