"""Add incident delay minutes

Revision ID: 20260315_0005
Revises: 20260315_0004
Create Date: 2026-03-15 00:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260315_0005'
down_revision = '20260315_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('incidents', sa.Column('delay_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('incidents', 'delay_minutes')
