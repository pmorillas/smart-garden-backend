"""add raw_value to sensor_readings for firmware-side raw ADC reporting

Revision ID: 009
Revises: 008
Create Date: 2026-04-29
"""

import sqlalchemy as sa
from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sensor_readings",
        sa.Column("raw_value", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sensor_readings", "raw_value")
