"""Simulation pivot

Revision ID: 20260314_0003
Revises: 20260303_0002
Create Date: 2026-03-14 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260314_0003'
down_revision = '20260303_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('auth_users')

    op.add_column('routes', sa.Column('popularity_score', sa.Integer(), nullable=False, server_default='100'))

    op.drop_constraint('ck_trips_status_valid', 'trips', type_='check')
    op.create_check_constraint(
        'ck_trips_status_valid',
        'trips',
        "status IN ('scheduled','boarding','in_transit','delayed','cancelled','completed')",
    )
    op.add_column('trips', sa.Column('last_simulated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('ck_trips_capacity_positive', 'trips', 'capacity_total > 0')
    op.create_check_constraint('ck_trips_seats_nonnegative', 'trips', 'seats_available >= 0')
    op.create_check_constraint('ck_trips_seats_le_capacity', 'trips', 'seats_available <= capacity_total')

    op.add_column('reservations', sa.Column('booking_channel', sa.Text(), nullable=False, server_default='simulated'))
    op.create_check_constraint('ck_reservations_seats_positive', 'reservations', 'seats_booked > 0')

    op.drop_constraint('ck_incidents_type_valid', 'incidents', type_='check')
    op.create_check_constraint(
        'ck_incidents_type_valid',
        'incidents',
        "incident_type IN ('delay','accident','weather','maintenance','mechanical_issue','traffic_disruption','staffing_issue','other')",
    )
    op.add_column('incidents', sa.Column('severity', sa.Text(), nullable=False, server_default='medium'))
    op.add_column('incidents', sa.Column('source_type', sa.Text(), nullable=False, server_default='manual'))
    op.create_index('ix_incidents_route_id', 'incidents', ['route_id'])
    op.create_index('ix_incidents_trip_id', 'incidents', ['trip_id'])
    op.create_index('ix_incidents_occurred_at', 'incidents', ['occurred_at'])

    op.create_table(
        'simulation_configs',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('config_name', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('booking_rate_per_tick', sa.Numeric(6, 2), nullable=False, server_default='3.0'),
        sa.Column('cancellation_rate_per_tick', sa.Numeric(6, 2), nullable=False, server_default='0.8'),
        sa.Column('incident_rate_per_tick', sa.Numeric(6, 2), nullable=False, server_default='0.4'),
        sa.Column('delay_sensitivity', sa.Numeric(6, 2), nullable=False, server_default='1.0'),
        sa.Column('tick_interval_seconds', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('config_name', name='uq_simulation_configs_name'),
    )

    op.create_table(
        'simulation_jobs',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('job_type', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('triggered_by', sa.Text(), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(
            "job_type IN ('seed','tick','reservation_simulator','incident_simulator','trip_updater')",
            name='ck_simulation_jobs_type_valid',
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name='ck_simulation_jobs_status_valid',
        ),
    )
    op.create_index('ix_simulation_jobs_type_started_at', 'simulation_jobs', ['job_type', 'started_at'])
    op.create_index('ix_simulation_jobs_status_started_at', 'simulation_jobs', ['status', 'started_at'])

    op.create_table(
        'simulation_state',
        sa.Column('state_key', sa.Text(), primary_key=True, nullable=False),
        sa.Column('state_value_json', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('simulation_state')
    op.drop_index('ix_simulation_jobs_status_started_at', table_name='simulation_jobs')
    op.drop_index('ix_simulation_jobs_type_started_at', table_name='simulation_jobs')
    op.drop_table('simulation_jobs')
    op.drop_table('simulation_configs')

    op.drop_index('ix_incidents_occurred_at', table_name='incidents')
    op.drop_index('ix_incidents_trip_id', table_name='incidents')
    op.drop_index('ix_incidents_route_id', table_name='incidents')
    op.drop_column('incidents', 'source_type')
    op.drop_column('incidents', 'severity')
    op.drop_constraint('ck_incidents_type_valid', 'incidents', type_='check')
    op.create_check_constraint(
        'ck_incidents_type_valid',
        'incidents',
        "incident_type IN ('delay','accident','weather','maintenance','other')",
    )

    op.drop_constraint('ck_reservations_seats_positive', 'reservations', type_='check')
    op.drop_column('reservations', 'booking_channel')

    op.drop_constraint('ck_trips_seats_le_capacity', 'trips', type_='check')
    op.drop_constraint('ck_trips_seats_nonnegative', 'trips', type_='check')
    op.drop_constraint('ck_trips_capacity_positive', 'trips', type_='check')
    op.drop_column('trips', 'last_simulated_at')
    op.drop_constraint('ck_trips_status_valid', 'trips', type_='check')
    op.create_check_constraint(
        'ck_trips_status_valid',
        'trips',
        "status IN ('scheduled','delayed','cancelled','completed')",
    )

    op.drop_column('routes', 'popularity_score')

    op.create_table(
        'auth_users',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('email', sa.Text(), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("role IN ('admin','user')", name='ck_auth_users_role_valid'),
    )
