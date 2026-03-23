"""Initial OmniRoute schema

Revision ID: 20260303_0001
Revises:
Create Date: 2026-03-03 00:00:00
"""
from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = '20260303_0001'
down_revision = None
branch_labels = None
depends_on = None


def _embedding_dim() -> int:
    raw = os.getenv('EMBEDDING_DIM', '1536')
    try:
        return int(raw)
    except ValueError:
        return 1536


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')

    op.create_table(
        'routes',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('route_name', sa.Text(), nullable=False, unique=True),
        sa.Column('origin_name', sa.Text(), nullable=False),
        sa.Column('destination_name', sa.Text(), nullable=False),
        sa.Column('base_price_cents', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'route_stops',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('route_id', sa.UUID(), sa.ForeignKey('routes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('stop_order', sa.Integer(), nullable=False),
        sa.Column('stop_name', sa.Text(), nullable=False),
        sa.Column('scheduled_offset_min', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('route_id', 'stop_order', name='uq_route_stops_route_id_stop_order'),
    )

    op.create_table(
        'trips',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('route_id', sa.UUID(), sa.ForeignKey('routes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('departure_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('arrival_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('capacity_total', sa.Integer(), nullable=False),
        sa.Column('seats_available', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('delay_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("status IN ('scheduled','delayed','cancelled','completed')", name='ck_trips_status_valid'),
    )
    op.create_index('ix_trips_route_id_departure_time', 'trips', ['route_id', 'departure_time'])

    op.create_table(
        'reservations',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('trip_id', sa.UUID(), sa.ForeignKey('trips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_name', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('phone_number', sa.Text(), nullable=False),
        sa.Column('seats_booked', sa.Integer(), nullable=False),
        sa.Column('amount_paid_cents', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("status IN ('confirmed','cancelled','refunded')", name='ck_reservations_status_valid'),
    )
    op.create_index('ix_reservations_trip_id', 'reservations', ['trip_id'])
    op.create_index('ix_reservations_email', 'reservations', ['email'])

    op.create_table(
        'incidents',
        sa.Column('id', sa.UUID(), primary_key=True, nullable=False),
        sa.Column('route_id', sa.UUID(), sa.ForeignKey('routes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('trip_id', sa.UUID(), sa.ForeignKey('trips.id', ondelete='SET NULL'), nullable=True),
        sa.Column('incident_type', sa.Text(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('details', sa.Text(), nullable=False),
        sa.Column('proof_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(
            "incident_type IN ('delay','accident','weather','maintenance','other')",
            name='ck_incidents_type_valid',
        ),
    )
    op.execute(f'ALTER TABLE incidents ADD COLUMN embedding vector({_embedding_dim()});')
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_am WHERE amname = 'hnsw') THEN
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_incidents_embedding_hnsw
                         ON incidents USING hnsw (embedding vector_cosine_ops)';
            ELSE
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_incidents_embedding_ivfflat
                         ON incidents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
            END IF;
        END
        $$;
        """
    )

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


def downgrade() -> None:
    op.drop_table('auth_users')

    op.execute('DROP INDEX IF EXISTS ix_incidents_embedding_ivfflat;')
    op.execute('DROP INDEX IF EXISTS ix_incidents_embedding_hnsw;')
    op.drop_table('incidents')

    op.drop_index('ix_reservations_email', table_name='reservations')
    op.drop_index('ix_reservations_trip_id', table_name='reservations')
    op.drop_table('reservations')

    op.drop_index('ix_trips_route_id_departure_time', table_name='trips')
    op.drop_table('trips')

    op.drop_table('route_stops')
    op.drop_table('routes')
