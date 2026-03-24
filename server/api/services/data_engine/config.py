from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _get_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _get_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


@dataclass(slots=True)
class DataEngineSettings:
    mode: str
    tick_interval_seconds: int
    seed_routes: int
    seed_days: int
    seed_if_empty: bool
    booking_rate_per_tick: float
    cancellation_rate_per_tick: float
    incident_rate_per_tick: float
    delay_sensitivity: float
    enable_cascading_delays: bool
    runtime_key: str = 'simulation_runtime'
    heartbeat_key: str = 'engine_process'


def get_data_engine_settings() -> DataEngineSettings:
    return DataEngineSettings(
        mode=os.getenv('DATA_ENGINE_MODE', 'run').strip().lower(),
        tick_interval_seconds=_get_int('DATA_ENGINE_TICK_INTERVAL_SECONDS', 30, minimum=1),
        seed_routes=_get_int('DATA_ENGINE_SEED_ROUTES', 6, minimum=1),
        seed_days=_get_int('DATA_ENGINE_SEED_DAYS', 3, minimum=1),
        seed_if_empty=_get_bool('DATA_ENGINE_SEED_IF_EMPTY', True),
        booking_rate_per_tick=_get_float('DATA_ENGINE_BOOKING_RATE_PER_TICK', 3.0, minimum=0.0),
        cancellation_rate_per_tick=_get_float('DATA_ENGINE_CANCELLATION_RATE_PER_TICK', 0.8, minimum=0.0),
        incident_rate_per_tick=_get_float('DATA_ENGINE_INCIDENT_RATE_PER_TICK', 0.4, minimum=0.0),
        delay_sensitivity=_get_float('DATA_ENGINE_DELAY_SENSITIVITY', 1.0, minimum=0.0),
        enable_cascading_delays=_get_bool('DATA_ENGINE_ENABLE_CASCADING_DELAYS', True),
    )
