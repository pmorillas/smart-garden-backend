"""Add tank_id to alert_rules and tank_level_low alert type

Revision ID: 010
Revises: 009
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alert_rules",
        sa.Column(
            "tank_id",
            sa.Integer(),
            sa.ForeignKey("water_tanks.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("alert_rules", "tank_id")
