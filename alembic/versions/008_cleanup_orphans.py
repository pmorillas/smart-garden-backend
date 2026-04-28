"""cleanup orphans: SET NULL → CASCADE, data_cleanup_logs table

Revision ID: 008
Revises: 007
Create Date: 2026-04-28
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # sensor_readings: SET NULL → CASCADE
    op.alter_column(
        "sensor_readings", "zone_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default=None,
        server_default=None,
        postgresql_ondelete="CASCADE",
    )
    op.alter_column(
        "sensor_readings", "device_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default=None,
        server_default=None,
        postgresql_ondelete="CASCADE",
    )

    # alerts: SET NULL → CASCADE
    op.alter_column(
        "alerts", "zone_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default=None,
        server_default=None,
        postgresql_ondelete="CASCADE",
    )
    op.alter_column(
        "alerts", "device_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default=None,
        server_default=None,
        postgresql_ondelete="CASCADE",
    )

    # New table: data_cleanup_logs
    op.create_table(
        "data_cleanup_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("before_count", sa.Integer(), nullable=False),
        sa.Column("after_count", sa.Integer(), nullable=False),
        sa.Column("deleted_by", sa.String(100), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("data_cleanup_logs")

    op.alter_column(
        "alerts", "device_id",
        existing_type=sa.Integer(),
        nullable=True,
        postgresql_ondelete="SET NULL",
    )
    op.alter_column(
        "alerts", "zone_id",
        existing_type=sa.Integer(),
        nullable=True,
        postgresql_ondelete="SET NULL",
    )
    op.alter_column(
        "sensor_readings", "device_id",
        existing_type=sa.Integer(),
        nullable=True,
        postgresql_ondelete="SET NULL",
    )
    op.alter_column(
        "sensor_readings", "zone_id",
        existing_type=sa.Integer(),
        nullable=True,
        postgresql_ondelete="SET NULL",
    )
