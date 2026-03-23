from __future__ import annotations

import random
from datetime import timedelta
from itertools import cycle, islice

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.tables import Incident, Reservation, Route, RouteStop, Trip
from .state import utcnow

ROUTE_BLUEPRINTS = [
    ('Pacific Connector', 'Los Angeles', 'San Diego'),
    ('Valley Express', 'Fresno', 'Sacramento'),
    ('Capital Link', 'Sacramento', 'San Jose'),
    ('Coastal Runner', 'Santa Barbara', 'Monterey'),
    ('Metro North', 'Los Angeles', 'Bakersfield'),
    ('Sierra Loop', 'Reno', 'Sacramento'),
    ('Sunset Corridor', 'San Diego', 'Irvine'),
    ('Golden Gate Shuttle', 'San Jose', 'San Francisco'),
    ('Desert Line', 'Palm Springs', 'Los Angeles'),
    ('Capitol Commuter', 'Oakland', 'Sacramento'),
    ('Bay Connector', 'San Francisco', 'San Jose'),
    ('Central Corridor', 'Modesto', 'Stockton'),
]


def _iter_route_blueprints(route_count: int) -> list[tuple[str, str, str]]:
    variants: list[tuple[str, str, str]] = []
    for index, (route_name, origin, destination) in enumerate(islice(cycle(ROUTE_BLUEPRINTS), route_count), start=1):
        if index <= len(ROUTE_BLUEPRINTS):
            variants.append((route_name, origin, destination))
            continue
        variants.append((f'{route_name} {index}', origin, destination))
    return variants


async def seed_network(session: AsyncSession, *, route_count: int, days: int) -> dict[str, int]:
    route_total = await session.scalar(select(func.count(Route.id)))
    if route_total and route_total > 0:
        return {'routes_created': 0, 'trips_created': 0, 'reservations_created': 0, 'incidents_created': 0}

    now = utcnow()
    routes_created = 0
    trips_created = 0
    reservations_created = 0
    incidents_created = 0

    selected_blueprints = _iter_route_blueprints(route_count)
    for index, (route_name, origin, destination) in enumerate(selected_blueprints, start=1):
        popularity = 80 + (index * 12)
        route = Route(
            route_name=route_name,
            origin_name=origin,
            destination_name=destination,
            base_price_cents=1800 + (index * 250),
            popularity_score=popularity,
            is_active=True,
        )
        session.add(route)
        await session.flush()
        routes_created += 1

        stops = [
            RouteStop(route_id=route.id, stop_order=1, stop_name=origin, scheduled_offset_min=0),
            RouteStop(route_id=route.id, stop_order=2, stop_name=f'{route_name} Midpoint', scheduled_offset_min=70 + (index * 2)),
            RouteStop(route_id=route.id, stop_order=3, stop_name=destination, scheduled_offset_min=145 + (index * 3)),
        ]
        session.add_all(stops)

        for day_offset in range(days):
            for hour in (6, 7, 9, 12, 16, 18, 21):
                departure = now.replace(hour=hour, minute=(index * 7) % 60, second=0, microsecond=0) + timedelta(days=day_offset)
                arrival = departure + timedelta(minutes=150 + (index * 3))
                capacity = 42 + (index * 4)
                trip = Trip(
                    route_id=route.id,
                    departure_time=departure,
                    arrival_time=arrival,
                    capacity_total=capacity,
                    seats_available=capacity,
                    status='scheduled',
                    delay_minutes=0,
                    last_simulated_at=now,
                )
                session.add(trip)
                await session.flush()
                trips_created += 1

                demand_floor = 0.22 if hour in {12, 21} else 0.35
                demand_ceiling = 0.52 if hour in {7, 9, 16, 18} else 0.42
                initial_bookings = random.randint(int(capacity * demand_floor), int(capacity * demand_ceiling))
                for seat_index in range(initial_bookings):
                    reservation = Reservation(
                        trip_id=trip.id,
                        customer_name=f'Sim Rider {index}-{day_offset}-{seat_index}',
                        email=f'sim-{index}-{day_offset}-{seat_index}@omniroute.internal',
                        phone_number=f'555-01{index:02d}{seat_index:02d}',
                        seats_booked=1,
                        amount_paid_cents=route.base_price_cents,
                        booking_channel='simulated',
                        status='confirmed',
                    )
                    session.add(reservation)
                    reservations_created += 1
                trip.seats_available = max(0, trip.capacity_total - initial_bookings)

                if random.random() < (0.06 if hour in {12, 21} else 0.1):
                    incident = Incident(
                        route_id=route.id,
                        trip_id=trip.id,
                        incident_type=random.choice(['delay', 'maintenance', 'weather']),
                        delay_minutes=None,
                        severity=random.choice(['low', 'medium']),
                        source_type='simulated',
                        occurred_at=departure - timedelta(minutes=random.randint(10, 35)),
                        summary=f'{route.route_name} operational disruption',
                        details='Synthetic seed incident to support incident intelligence and delay history.',
                    )
                    session.add(incident)
                    if incident.incident_type in {'delay', 'maintenance', 'weather'}:
                        trip.delay_minutes = random.randint(5, 20)
                        incident.delay_minutes = trip.delay_minutes
                        trip.status = 'delayed'
                    incidents_created += 1

    await session.flush()
    return {
        'routes_created': routes_created,
        'trips_created': trips_created,
        'reservations_created': reservations_created,
        'incidents_created': incidents_created,
    }
