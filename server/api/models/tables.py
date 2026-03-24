from __future__ import annotations

import os
from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _embedding_dim() -> int:
    raw = os.getenv('EMBEDDING_DIM', '1536')
    try:
        return int(raw)
    except ValueError:
        return 1536


class Route(Base):
    __tablename__ = 'routes'

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    origin_name: Mapped[str] = mapped_column(Text, nullable=False)
    destination_name: Mapped[str] = mapped_column(Text, nullable=False)
    base_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    popularity_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('100'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class RouteStop(Base):
    __tablename__ = 'route_stops'
    __table_args__ = (UniqueConstraint('route_id', 'stop_order', name='uq_route_stops_route_id_stop_order'),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('routes.id', ondelete='CASCADE'),
        nullable=False,
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_name: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_offset_min: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class Trip(Base):
    __tablename__ = 'trips'
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled','boarding','in_transit','delayed','cancelled','completed')",
            name='ck_trips_status_valid',
        ),
        UniqueConstraint('route_id', 'departure_time', name='uq_trips_route_id_departure_time'),
        CheckConstraint('capacity_total > 0', name='ck_trips_capacity_positive'),
        CheckConstraint('seats_available >= 0', name='ck_trips_seats_nonnegative'),
        CheckConstraint('seats_available <= capacity_total', name='ck_trips_seats_le_capacity'),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('routes.id', ondelete='RESTRICT'),
        nullable=False,
    )
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity_total: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_available: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    last_simulated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class Reservation(Base):
    __tablename__ = 'reservations'
    __table_args__ = (
        CheckConstraint(
            "status IN ('confirmed','cancelled','refunded')",
            name='ck_reservations_status_valid',
        ),
        CheckConstraint('seats_booked > 0', name='ck_reservations_seats_positive'),
        UniqueConstraint('external_id', name='uq_reservations_external_id'),
        Index('ix_reservations_trip_id', 'trip_id'),
        Index('ix_reservations_email', 'email'),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    trip_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('trips.id', ondelete='CASCADE'),
        nullable=False,
    )
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone_number: Mapped[str] = mapped_column(Text, nullable=False)
    seats_booked: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    booking_channel: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'simulated'"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class Incident(Base):
    __tablename__ = 'incidents'
    __table_args__ = (
        CheckConstraint(
            "incident_type IN ('delay','accident','weather','maintenance','mechanical_issue','traffic_disruption','staffing_issue','other')",
            name='ck_incidents_type_valid',
        ),
        UniqueConstraint('external_id', name='uq_incidents_external_id'),
        Index('ix_incidents_route_id', 'route_id'),
        Index('ix_incidents_trip_id', 'trip_id'),
        Index('ix_incidents_occurred_at', 'occurred_at'),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('routes.id', ondelete='SET NULL'),
        nullable=True,
    )
    trip_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('trips.id', ondelete='SET NULL'),
        nullable=True,
    )
    incident_type: Mapped[str] = mapped_column(Text, nullable=False)
    delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'medium'"))
    source_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    proof_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_embedding_dim()), nullable=True)


class SimulationConfig(Base):
    __tablename__ = 'simulation_configs'
    __table_args__ = (UniqueConstraint('config_name', name='uq_simulation_configs_name'),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    config_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    booking_rate_per_tick: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default=text('3.0'))
    cancellation_rate_per_tick: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default=text('0.8'))
    incident_rate_per_tick: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default=text('0.4'))
    delay_sensitivity: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default=text('1.0'))
    tick_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('60'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class SimulationJob(Base):
    __tablename__ = 'simulation_jobs'
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('seed','tick','reservation_simulator','incident_simulator','trip_updater')",
            name='ck_simulation_jobs_type_valid',
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name='ck_simulation_jobs_status_valid',
        ),
        Index('ix_simulation_jobs_type_started_at', 'job_type', 'started_at'),
        Index('ix_simulation_jobs_status_started_at', 'status', 'started_at'),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class SimulationState(Base):
    __tablename__ = 'simulation_state'

    state_key: Mapped[str] = mapped_column(Text, primary_key=True)
    state_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
