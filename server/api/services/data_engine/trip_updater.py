from __future__ import annotations

from datetime import timedelta
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.tables import Trip
from .state import utcnow


def determine_trip_status(
    *,
    now,
    departure_time,
    arrival_time,
    delay_minutes: int,
    current_status: str,
) -> str:
    if current_status in {'completed', 'cancelled'}:
        return current_status

    boarding_end = departure_time + timedelta(minutes=20)
    effective_arrival = (arrival_time or departure_time) + timedelta(minutes=delay_minutes)

    if departure_time <= now < boarding_end:
        return 'boarding'
    if boarding_end <= now < effective_arrival:
        return 'delayed' if delay_minutes >= 15 else 'in_transit'
    if now >= effective_arrival:
        return 'completed'
    return 'scheduled'


async def update_trip_states(session: AsyncSession) -> dict[str, int]:
    now = utcnow()
    trips = (await session.execute(select(Trip).order_by(Trip.departure_time.asc()))).scalars().all()
    updated = 0
    completed = 0
    cancelled = 0
    for trip in trips:
        if trip.status in {'completed', 'cancelled'}:
            continue

        if trip.departure_time > now + timedelta(minutes=90) and trip.seats_available == trip.capacity_total and random.random() < 0.01:
            trip.status = 'cancelled'
            trip.last_simulated_at = now
            updated += 1
            cancelled += 1
            continue

        next_status = determine_trip_status(
            now=now,
            departure_time=trip.departure_time,
            arrival_time=trip.arrival_time,
            delay_minutes=trip.delay_minutes,
            current_status=trip.status,
        )

        if next_status != trip.status:
            if next_status == 'completed':
                completed += 1
            trip.status = next_status
            updated += 1
        trip.last_simulated_at = now

    return {'trips_updated': updated, 'trips_completed': completed, 'trips_cancelled': cancelled}
