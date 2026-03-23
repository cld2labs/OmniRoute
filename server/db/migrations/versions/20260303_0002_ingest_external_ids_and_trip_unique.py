"""Add ingest external ids and unique trip key

Revision ID: 20260303_0002
Revises: 20260303_0001
Create Date: 2026-03-03 00:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260303_0002'
down_revision = '20260303_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reservations', sa.Column('external_id', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_reservations_external_id', 'reservations', ['external_id'])

    op.add_column('incidents', sa.Column('external_id', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_incidents_external_id', 'incidents', ['external_id'])

    op.drop_index('ix_trips_route_id_departure_time', table_name='trips')
    op.create_unique_constraint('uq_trips_route_id_departure_time', 'trips', ['route_id', 'departure_time'])


def downgrade() -> None:
    op.drop_constraint('uq_trips_route_id_departure_time', 'trips', type_='unique')
    op.create_index('ix_trips_route_id_departure_time', 'trips', ['route_id', 'departure_time'])

    op.drop_constraint('uq_incidents_external_id', 'incidents', type_='unique')
    op.drop_column('incidents', 'external_id')

    op.drop_constraint('uq_reservations_external_id', 'reservations', type_='unique')
    op.drop_column('reservations', 'external_id')
