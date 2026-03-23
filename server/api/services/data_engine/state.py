from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.tables import SimulationState


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_state(session: AsyncSession, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    result = await session.execute(select(SimulationState).where(SimulationState.state_key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return default.copy() if default else {}
    return dict(row.state_value_json or {})


async def set_state(session: AsyncSession, key: str, value: dict[str, Any]) -> None:
    result = await session.execute(select(SimulationState).where(SimulationState.state_key == key))
    row = result.scalar_one_or_none()
    now = utcnow()
    if row is None:
        session.add(SimulationState(state_key=key, state_value_json=value, updated_at=now))
        return
    row.state_value_json = value
    row.updated_at = now
