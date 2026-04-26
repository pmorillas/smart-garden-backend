"""phase2: alert_rules table with default rules

Revision ID: 004
Revises: 003
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=True),
        sa.Column("threshold", sa.Float, nullable=True),
        sa.Column("cooldown_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("notification_channels", sa.JSON, nullable=False),
    )
    op.create_index("ix_alert_rules_alert_type", "alert_rules", ["alert_type"])

    # Seed default rules — one per alert type (global, zone_id=NULL)
    op.execute(
        sa.text(
            "INSERT INTO alert_rules (name, alert_type, enabled, threshold, cooldown_minutes, notification_channels) VALUES "
            "('Humitat terra baixa', 'humidity_low', true, 30, 60, '[\"push\"]'),"
            "('Dispositiu desconnectat', 'device_offline', true, 30, 120, '[\"push\"]'),"
            "('Error de reg', 'water_failed', true, NULL, 60, '[\"push\"]'),"
            "('Reg completat', 'water_completed', false, NULL, 0, '[\"push\"]'),"
            "('Error de sensor', 'sensor_error', true, NULL, 60, '[\"push\"]')"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_alert_rules_alert_type", "alert_rules")
    op.drop_table("alert_rules")
