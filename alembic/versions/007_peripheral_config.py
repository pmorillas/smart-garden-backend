"""peripheral config: peripherals registry, zone soil sensors, zone/tank peripheral refs

Revision ID: 007
Revises: 006
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "peripherals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("pin1", sa.Integer(), nullable=True),
        sa.Column("pin2", sa.Integer(), nullable=True),
        sa.Column("i2c_address", sa.Integer(), nullable=True),
        sa.Column("i2c_bus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_config", JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_peripherals_device_id", "peripherals", ["device_id"])

    op.create_table(
        "zone_soil_sensors",
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("peripheral_id", sa.Integer(), sa.ForeignKey("peripherals.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )

    # Remove legacy pin columns from zones
    op.drop_column("zones", "relay_pin_local")
    op.drop_column("zones", "soil_pin_a_local")
    op.drop_column("zones", "soil_pin_b_local")

    op.add_column("zones", sa.Column("relay_peripheral_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_zones_relay_peripheral", "zones", "peripherals",
        ["relay_peripheral_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("zones", sa.Column(
        "soil_aggregation_mode", sa.String(10), nullable=False, server_default="AVG"
    ))

    # Remove legacy pin columns from water_tanks
    op.drop_column("water_tanks", "sensor_type")
    op.drop_column("water_tanks", "gpio_pin_1")
    op.drop_column("water_tanks", "gpio_pin_2")
    op.drop_column("water_tanks", "calibration_empty")
    op.drop_column("water_tanks", "calibration_full")

    op.add_column("water_tanks", sa.Column("peripheral_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tanks_peripheral", "water_tanks", "peripherals",
        ["peripheral_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_tanks_peripheral", "water_tanks", type_="foreignkey")
    op.drop_column("water_tanks", "peripheral_id")
    op.add_column("water_tanks", sa.Column("calibration_full", sa.Integer(), nullable=True))
    op.add_column("water_tanks", sa.Column("calibration_empty", sa.Integer(), nullable=True))
    op.add_column("water_tanks", sa.Column("gpio_pin_2", sa.Integer(), nullable=True))
    op.add_column("water_tanks", sa.Column("gpio_pin_1", sa.Integer(), nullable=True))
    op.add_column("water_tanks", sa.Column("sensor_type", sa.String(20), nullable=False, server_default="binary_single"))

    op.drop_constraint("fk_zones_relay_peripheral", "zones", type_="foreignkey")
    op.drop_column("zones", "soil_aggregation_mode")
    op.drop_column("zones", "relay_peripheral_id")
    op.add_column("zones", sa.Column("soil_pin_b_local", sa.Integer(), nullable=True))
    op.add_column("zones", sa.Column("soil_pin_a_local", sa.Integer(), nullable=True))
    op.add_column("zones", sa.Column("relay_pin_local", sa.Integer(), nullable=True))

    op.drop_table("zone_soil_sensors")
    op.drop_index("ix_peripherals_device_id", "peripherals")
    op.drop_table("peripherals")
