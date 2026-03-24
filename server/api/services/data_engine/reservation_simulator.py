from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.tables import Reservation, Route, Trip
from .demand_model import hour_demand_multiplier, route_demand_weight, weekday_multiplier
from .state import utcnow


def estimate_booking_attempts(
    *,
    booking_rate: float,
    departure_time,
    popularity_score: int,
    seats_available: int,
    trip_status: str,
) -> int:
    if trip_status in {'cancelled', 'completed'} or seats_available <= 0:
        return 0
    demand_weight = hour_demand_multiplier(departure_time) * weekday_multiplier(departure_time)
    route_popularity = route_demand_weight(int(popularity_score or 100))
    attempts = int(round(booking_rate * demand_weight * route_popularity))
    return max(0, min(seats_available, attempts))


def clamp_seats_available(*, capacity_total: int, seats_available: int) -> int:
    return max(0, min(capacity_total, seats_available))


async def simulate_reservations(session: AsyncSession, *, booking_rate: float, cancellation_rate: float) -> dict[str, int]:
    now = utcnow()
    stmt = (
        select(Trip, Route.popularity_score, Route.base_price_cents)
        .join(Route, Route.id == Trip.route_id)
        .where(Trip.departure_time >= now - timedelta(hours=2))
        .where(Trip.departure_time <= now + timedelta(days=2))
        .where(Trip.status.in_(('scheduled', 'boarding', 'in_transit', 'delayed')))
        .order_by(Trip.departure_time.asc())
    )
    rows = (await session.execute(stmt)).all()
    created = 0
    cancelled = 0

    for trip, popularity_score, base_price_cents in rows:
        booking_attempts = estimate_booking_attempts(
            booking_rate=booking_rate,
            departure_time=trip.departure_time,
            popularity_score=int(popularity_score or 100),
            seats_available=trip.seats_available,
            trip_status=trip.status,
        )

        if trip.status != 'cancelled' and trip.seats_available > 0:
            for _ in range(booking_attempts):
                reservation = Reservation(
                    trip_id=trip.id,
                    customer_name=f'Sim Booker {created + 1}',
                    email=f'booking-{trip.id}-{created + 1}@omniroute.internal',
                    phone_number=f'555-200{created:04d}',
                    seats_booked=1,
                    amount_paid_cents=int(base_price_cents),
                    booking_channel='simulated',
                    status='confirmed',
                )
                session.add(reservation)
                trip.seats_available = clamp_seats_available(
                    capacity_total=trip.capacity_total,
                    seats_available=trip.seats_available - 1,
                )
                created += 1

        existing_confirmed_stmt = (
            select(Reservation)
            .where(Reservation.trip_id == trip.id)
            .where(Reservation.status == 'confirmed')
            .order_by(Reservation.created_at.asc())
        )
        confirmed = (await session.execute(existing_confirmed_stmt)).scalars().all()
        cancellation_ceiling = min(len(confirmed), int(max(0, round(cancellation_rate * max(1.0, booking_attempts / 2)))))
        max_cancellations = 0 if trip.status == 'cancelled' else cancellation_ceiling
        for reservation in random.sample(confirmed, k=max_cancellations) if max_cancellations else []:
            reservation.status = 'cancelled'
            trip.seats_available = clamp_seats_available(
                capacity_total=trip.capacity_total,
                seats_available=trip.seats_available + reservation.seats_booked,
            )
            cancelled += 1

        trip.last_simulated_at = now

    return {'reservations_created': created, 'reservations_cancelled': cancelled}
