"""devices.poll_interval_seconds: freqüència de polling per dispositiu

Revision ID: 006
Revises: 005
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "poll_interval_seconds",
            sa.Integer,
            nullable=False,
            server_default="300",
        ),
    )


def downgrade() -> None:
    op.drop_column("devices", "poll_interval_seconds")
