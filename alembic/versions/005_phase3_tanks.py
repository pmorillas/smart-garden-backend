"""phase3: water_tanks, tank_readings, zones.tank_id, tank alert rules

Revision ID: 005
Revises: 004
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "water_tanks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("device_id", sa.Integer, sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sensor_type", sa.String(20), nullable=False, server_default="binary_single"),
        sa.Column("gpio_pin_1", sa.Integer, nullable=True),
        sa.Column("gpio_pin_2", sa.Integer, nullable=True),
        sa.Column("capacity_liters", sa.Float, nullable=True),
        sa.Column("calibration_empty", sa.Integer, nullable=True),
        sa.Column("calibration_full", sa.Integer, nullable=True),
        sa.Column("low_threshold_pct", sa.Integer, nullable=False, server_default="20"),
        sa.Column("empty_threshold_pct", sa.Integer, nullable=False, server_default="5"),
    )

    op.create_table(
        "tank_readings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tank_id", sa.Integer, sa.ForeignKey("water_tanks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_value", sa.Float, nullable=False),
        sa.Column("level_percent", sa.Float, nullable=True),
        sa.Column("sensor_state", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tank_readings_tank_id", "tank_readings", ["tank_id"])

    op.add_column("zones", sa.Column("tank_id", sa.Integer, nullable=True))
    op.create_foreign_key(
        "fk_zones_tank_id", "zones", "water_tanks", ["tank_id"], ["id"], ondelete="SET NULL"
    )

    # Add tank_low and tank_empty alert rule types
    op.execute(
        sa.text(
            "INSERT INTO alert_rules (name, alert_type, enabled, threshold, cooldown_minutes, notification_channels) VALUES "
            "('Dipòsit baix', 'tank_low', true, NULL, 120, '[\"push\"]'),"
            "('Dipòsit buit', 'tank_empty', true, NULL, 30, '[\"push\"]')"
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_zones_tank_id", "zones", type_="foreignkey")
    op.drop_column("zones", "tank_id")
    op.drop_index("ix_tank_readings_tank_id", "tank_readings")
    op.drop_table("tank_readings")
    op.drop_table("water_tanks")
    op.execute(sa.text("DELETE FROM alert_rules WHERE alert_type IN ('tank_low', 'tank_empty')"))
