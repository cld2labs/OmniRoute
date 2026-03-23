from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .incident_simulator import simulate_incidents
from .reservation_simulator import simulate_reservations
from .trip_updater import update_trip_states


async def run_tick(
    session: AsyncSession,
    *,
    booking_rate: float,
    cancellation_rate: float,
    incident_rate: float,
    delay_sensitivity: float,
    enable_cascading_delays: bool = True,
) -> dict[str, int]:
    trip_updates = await update_trip_states(session)
    reservation_updates = await simulate_reservations(
        session,
        booking_rate=booking_rate,
        cancellation_rate=cancellation_rate,
    )
    incident_updates = await simulate_incidents(
        session,
        incident_rate=incident_rate,
        delay_sensitivity=delay_sensitivity,
        enable_cascading_delays=enable_cascading_delays,
    )
    return {
        **trip_updates,
        **reservation_updates,
        **incident_updates,
    }
