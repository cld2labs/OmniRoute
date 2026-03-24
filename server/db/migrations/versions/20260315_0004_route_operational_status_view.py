"""Add route operational status view

Revision ID: 20260315_0004
Revises: 20260314_0003
Create Date: 2026-03-15 00:00:00
"""
from __future__ import annotations

from alembic import op


revision = '20260315_0004'
down_revision = '20260314_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW route_operational_status AS
        SELECT
            r.id AS route_id,
            r.route_name,
            r.origin_name,
            r.destination_name,
            r.is_active,
            COUNT(t.id) AS total_trips_24h,
            COUNT(t.id) FILTER (WHERE t.status = 'scheduled')  AS scheduled_count,
            COUNT(t.id) FILTER (WHERE t.status = 'delayed')    AS delayed_count,
            COUNT(t.id) FILTER (WHERE t.status = 'cancelled')  AS cancelled_count,
            COUNT(t.id) FILTER (WHERE t.status = 'completed')  AS completed_count,
            ROUND(AVG(t.delay_minutes) FILTER (WHERE t.status = 'delayed'), 1) AS avg_delay_minutes,
            BOOL_OR(
                t.status = 'delayed'
                AND t.departure_time BETWEEN NOW() AND NOW() + INTERVAL '24 hours'
            ) AS has_upcoming_delay
        FROM routes r
        LEFT JOIN trips t ON t.route_id = r.id
            AND t.departure_time >= NOW() - INTERVAL '24 hours'
            AND t.departure_time <= NOW() + INTERVAL '24 hours'
        WHERE r.is_active = true
        GROUP BY r.id, r.route_name, r.origin_name, r.destination_name, r.is_active;
        """
    )


def downgrade() -> None:
    op.execute('DROP VIEW IF EXISTS route_operational_status;')
