"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mac_address", sa.String(17), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False, server_default="Nou dispositiu"),
        sa.Column("firmware_version", sa.String(20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("relay_pin_local", sa.Integer(), nullable=True),
        sa.Column("soil_pin_a_local", sa.Integer(), nullable=True),
        sa.Column("soil_pin_b_local", sa.Integer(), nullable=True),
    )

    op.create_table(
        "zone_config",
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("humidity_min", sa.Float(), nullable=False, server_default="30.0"),
        sa.Column("humidity_max", sa.Float(), nullable=False, server_default="80.0"),
        sa.Column("max_temp_to_water", sa.Float(), nullable=True, server_default="38.0"),
        sa.Column("cooldown_hours", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("soil_dry_value", sa.Integer(), nullable=False, server_default="3800"),
        sa.Column("soil_wet_value", sa.Integer(), nullable=False, server_default="1200"),
    )

    op.create_table(
        "programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("condition_logic", sa.String(3), nullable=False, server_default="AND"),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("conditions", JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_programs_zone_id", "programs", ["zone_id"])

    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sensor_type", sa.String(30), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sensor_readings_zone_ts", "sensor_readings", ["zone_id", "timestamp"])
    op.create_index("ix_sensor_readings_type_ts", "sensor_readings", ["sensor_type", "timestamp"])

    op.create_table(
        "watering_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("programs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
    )
    op.create_index("ix_watering_events_zone_started", "watering_events", ["zone_id", "started_at"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_resolved_created", "alerts", ["resolved", "created_at"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(256), nullable=False),
        sa.Column("auth", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    op.drop_index("ix_alerts_resolved_created", "alerts")
    op.drop_table("alerts")
    op.drop_index("ix_watering_events_zone_started", "watering_events")
    op.drop_table("watering_events")
    op.drop_index("ix_sensor_readings_type_ts", "sensor_readings")
    op.drop_index("ix_sensor_readings_zone_ts", "sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_index("ix_programs_zone_id", "programs")
    op.drop_table("programs")
    op.drop_table("zone_config")
    op.drop_table("zones")
    op.drop_table("devices")
    op.drop_table("users")
