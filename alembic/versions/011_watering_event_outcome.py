"""Add outcome and skip_reason to watering_events

Revision ID: 011
Revises: 010
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("watering_events", sa.Column("outcome", sa.String(20), nullable=False, server_default="active"))
    op.add_column("watering_events", sa.Column("skip_reason", sa.String(50), nullable=True))


def downgrade():
    op.drop_column("watering_events", "skip_reason")
    op.drop_column("watering_events", "outcome")
