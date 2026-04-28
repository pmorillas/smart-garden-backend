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
    # sensor_readings.zone_id: SET NULL → CASCADE
    op.drop_constraint("sensor_readings_zone_id_fkey", "sensor_readings", type_="foreignkey")
    op.create_foreign_key(
        "sensor_readings_zone_id_fkey", "sensor_readings", "zones",
        ["zone_id"], ["id"], ondelete="CASCADE"
    )

    # sensor_readings.device_id: SET NULL → CASCADE
    op.drop_constraint("sensor_readings_device_id_fkey", "sensor_readings", type_="foreignkey")
    op.create_foreign_key(
        "sensor_readings_device_id_fkey", "sensor_readings", "devices",
        ["device_id"], ["id"], ondelete="CASCADE"
    )

    # alerts.zone_id: SET NULL → CASCADE
    op.drop_constraint("alerts_zone_id_fkey", "alerts", type_="foreignkey")
    op.create_foreign_key(
        "alerts_zone_id_fkey", "alerts", "zones",
        ["zone_id"], ["id"], ondelete="CASCADE"
    )

    # alerts.device_id: SET NULL → CASCADE
    op.drop_constraint("alerts_device_id_fkey", "alerts", type_="foreignkey")
    op.create_foreign_key(
        "alerts_device_id_fkey", "alerts", "devices",
        ["device_id"], ["id"], ondelete="CASCADE"
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

    op.drop_constraint("alerts_device_id_fkey", "alerts", type_="foreignkey")
    op.create_foreign_key(
        "alerts_device_id_fkey", "alerts", "devices",
        ["device_id"], ["id"], ondelete="SET NULL"
    )

    op.drop_constraint("alerts_zone_id_fkey", "alerts", type_="foreignkey")
    op.create_foreign_key(
        "alerts_zone_id_fkey", "alerts", "zones",
        ["zone_id"], ["id"], ondelete="SET NULL"
    )

    op.drop_constraint("sensor_readings_device_id_fkey", "sensor_readings", type_="foreignkey")
    op.create_foreign_key(
        "sensor_readings_device_id_fkey", "sensor_readings", "devices",
        ["device_id"], ["id"], ondelete="SET NULL"
    )

    op.drop_constraint("sensor_readings_zone_id_fkey", "sensor_readings", type_="foreignkey")
    op.create_foreign_key(
        "sensor_readings_zone_id_fkey", "sensor_readings", "zones",
        ["zone_id"], ["id"], ondelete="SET NULL"
    )
