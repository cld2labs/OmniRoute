from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.tables import Incident, Reservation, Route, RouteStop, Trip
from .validators import IncidentRowInput, ReservationRowInput, StopInput


async def upsert_route(
    db_session: AsyncSession,
    *,
    route_name: str,
    origin_name: str,
    destination_name: str,
    base_price_cents: int,
) -> UUID:
    stmt = (
        insert(Route)
        .values(
            route_name=route_name,
            origin_name=origin_name,
            destination_name=destination_name,
            base_price_cents=base_price_cents,
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[Route.route_name],
            set_={
                'origin_name': origin_name,
                'destination_name': destination_name,
                'base_price_cents': base_price_cents,
                'is_active': True,
                'updated_at': func.now(),
            },
        )
        .returning(Route.id)
    )
    result = await db_session.execute(stmt)
    return result.scalar_one()


async def upsert_route_stops(
    db_session: AsyncSession,
    *,
    route_id: UUID,
    stops: list[StopInput],
) -> None:
    for stop in sorted(stops, key=lambda item: item.stop_order):
        stmt = (
            insert(RouteStop)
            .values(
                route_id=route_id,
                stop_order=stop.stop_order,
                stop_name=stop.stop_name,
                scheduled_offset_min=stop.scheduled_offset_min,
            )
            .on_conflict_do_update(
                constraint='uq_route_stops_route_id_stop_order',
                set_={
                    'stop_name': stop.stop_name,
                    'scheduled_offset_min': stop.scheduled_offset_min,
                },
            )
        )
        await db_session.execute(stmt)


async def upsert_trip(
    db_session: AsyncSession,
    *,
    route_id: UUID,
    departure_time: datetime,
    arrival_time: datetime,
    capacity_total: int,
    seats_available: int,
    status: str,
    delay_minutes: int,
) -> UUID:
    stmt = (
        insert(Trip)
        .values(
            route_id=route_id,
            departure_time=departure_time,
            arrival_time=arrival_time,
            capacity_total=capacity_total,
            seats_available=seats_available,
            status=status,
            delay_minutes=delay_minutes,
        )
        .on_conflict_do_update(
            constraint='uq_trips_route_id_departure_time',
            set_={
                'arrival_time': arrival_time,
                'capacity_total': capacity_total,
                'seats_available': seats_available,
                'status': status,
                'delay_minutes': delay_minutes,
                'updated_at': func.now(),
            },
        )
        .returning(Trip.id)
    )
    result = await db_session.execute(stmt)
    return result.scalar_one()


async def upsert_reservation(
    db_session: AsyncSession,
    *,
    trip_id: UUID,
    reservation: ReservationRowInput,
) -> UUID:
    stmt = (
        insert(Reservation)
        .values(
            external_id=reservation.external_id,
            trip_id=trip_id,
            customer_name=reservation.customer_name,
            email=reservation.email,
            phone_number=reservation.phone_number,
            seats_booked=reservation.seats_booked,
            status=reservation.status,
            amount_paid_cents=reservation.amount_paid_cents,
        )
        .on_conflict_do_update(
            constraint='uq_reservations_external_id',
            set_={
                'trip_id': trip_id,
                'customer_name': reservation.customer_name,
                'email': reservation.email,
                'phone_number': reservation.phone_number,
                'seats_booked': reservation.seats_booked,
                'status': reservation.status,
                'amount_paid_cents': reservation.amount_paid_cents,
                'updated_at': func.now(),
            },
        )
        .returning(Reservation.id)
    )
    result = await db_session.execute(stmt)
    return result.scalar_one()


async def upsert_incident(
    db_session: AsyncSession,
    *,
    route_id: UUID,
    trip_id: UUID | None,
    incident: IncidentRowInput,
) -> UUID:
    stmt = (
        insert(Incident)
        .values(
            external_id=incident.external_id,
            route_id=route_id,
            trip_id=trip_id,
            incident_type=incident.incident_type,
            occurred_at=incident.occurred_at,
            summary=incident.summary,
            details=incident.details,
            proof_url=incident.proof_url,
        )
        .on_conflict_do_update(
            constraint='uq_incidents_external_id',
            set_={
                'route_id': route_id,
                'trip_id': trip_id,
                'incident_type': incident.incident_type,
                'occurred_at': incident.occurred_at,
                'summary': incident.summary,
                'details': incident.details,
                'proof_url': incident.proof_url,
            },
        )
        .returning(Incident.id)
    )
    result = await db_session.execute(stmt)
    return result.scalar_one()


async def resolve_route_id_by_name(db_session: AsyncSession, route_name: str) -> UUID | None:
    stmt = select(Route.id).where(Route.route_name == route_name)
    result = await db_session.execute(stmt)
    return result.scalar_one_or_none()


async def resolve_trip_id_by_route_and_departure(
    db_session: AsyncSession,
    *,
    route_name: str,
    departure_time: datetime,
) -> UUID | None:
    stmt = (
        select(Trip.id)
        .join(Route, Trip.route_id == Route.id)
        .where(Route.route_name == route_name, Trip.departure_time == departure_time)
    )
    result = await db_session.execute(stmt)
    return result.scalar_one_or_none()
