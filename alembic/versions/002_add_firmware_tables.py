"""add firmware tables

Revision ID: 002
Revises: 001
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "firmware_releases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(20), unique=True, nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "firmware_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("release_id", sa.Integer(), sa.ForeignKey("firmware_releases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_firmware_updates_device_id", "firmware_updates", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_firmware_updates_device_id", "firmware_updates")
    op.drop_table("firmware_updates")
    op.drop_table("firmware_releases")
