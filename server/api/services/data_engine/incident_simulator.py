from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.tables import Incident, Route, Trip
from ..embeddings.jobs import enqueue_incident_embedding_job
from .state import utcnow

INCIDENT_TYPES = [
    ('accident', 'critical'),
    ('maintenance', 'medium'),
    ('weather', 'high'),
    ('mechanical_issue', 'high'),
    ('traffic_disruption', 'medium'),
    ('staffing_issue', 'medium'),
    ('delay', 'low'),
]


def _apply_cascading_delay(trips: list[Trip], *, route_id, anchor_departure, delay_minutes: int) -> int:
    affected = 0
    for trip in trips:
        if trip.route_id != route_id or trip.status in {'completed', 'cancelled'}:
            continue
        if trip.departure_time <= anchor_departure:
            continue
        if trip.departure_time > anchor_departure + timedelta(hours=4):
            continue
        trip.delay_minutes += max(3, delay_minutes // 3)
        trip.status = 'delayed'
        affected += 1
    return affected


async def simulate_incidents(
    session: AsyncSession,
    *,
    incident_rate: float,
    delay_sensitivity: float,
    enable_cascading_delays: bool = True,
) -> dict[str, int]:
    now = utcnow()
    trips = (
        await session.execute(
            select(Trip, Route.popularity_score)
            .join(Route, Route.id == Trip.route_id)
            .where(Trip.departure_time >= now - timedelta(hours=1))
            .where(Trip.departure_time <= now + timedelta(hours=12))
            .where(Trip.status.in_(('scheduled', 'boarding', 'in_transit', 'delayed')))
            .order_by(Trip.departure_time.asc())
        )
    ).all()

    created = 0
    cascaded = 0
    trip_cancelled = 0
    trip_list = [trip for trip, _ in trips]
    for trip, popularity_score in trips:
        trigger_threshold = min(0.08, 0.008 * incident_rate * max(0.7, (popularity_score or 100) / 100))
        if random.random() >= trigger_threshold:
            continue

        incident_type, severity = random.choice(INCIDENT_TYPES)
        delay_minutes = random.randint(8, 35) if incident_type != 'staffing_issue' else random.randint(15, 45)
        incident = Incident(
            route_id=trip.route_id,
            trip_id=trip.id,
            incident_type=incident_type,
            delay_minutes=delay_minutes,
            severity=severity,
            source_type='simulated',
            occurred_at=now,
            summary=f'{incident_type.replace("_", " ").title()} affecting trip {trip.id}',
            details='Simulator-generated operational incident tied to a live trip.',
        )
        session.add(incident)
        trip.delay_minutes += int(delay_minutes * max(0.5, delay_sensitivity))
        if incident_type in {'mechanical_issue', 'accident'} and random.random() < 0.12:
            trip.status = 'cancelled'
            trip_cancelled += 1
        elif trip.status not in {'completed', 'cancelled'}:
            trip.status = 'delayed'
        trip.last_simulated_at = now
        created += 1
        if enable_cascading_delays and trip.status != 'cancelled':
            cascaded += _apply_cascading_delay(
                trip_list,
                route_id=trip.route_id,
                anchor_departure=trip.departure_time,
                delay_minutes=delay_minutes,
            )

        await session.flush()
        await enqueue_incident_embedding_job(str(incident.id))

    return {
        'incidents_created': created,
        'cascaded_trip_delays': cascaded,
        'incident_trip_cancellations': trip_cancelled,
    }
