"""phase1: zones config_synced, program_zones, program execution_mode

Revision ID: 003
Revises: 002
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add config_synced to zones
    op.add_column(
        "zones",
        sa.Column("config_synced", sa.Boolean(), nullable=False, server_default="true"),
    )

    # 2. Add execution_mode to programs
    op.add_column(
        "programs",
        sa.Column("execution_mode", sa.String(20), nullable=False, server_default="simultaneous"),
    )

    # 3. Create program_zones junction table
    op.create_table(
        "program_zones",
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("zone_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_override_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("program_id", "zone_id"),
    )
    op.create_index("ix_program_zones_zone_id", "program_zones", ["zone_id"])

    # 4. Migrate existing program-zone links
    op.execute("""
        INSERT INTO program_zones (program_id, zone_id, order_index)
        SELECT id, zone_id, 0 FROM programs WHERE zone_id IS NOT NULL
    """)

    # 5. Make programs.zone_id nullable (was NOT NULL CASCADE, now nullable SET NULL)
    op.drop_constraint("programs_zone_id_fkey", "programs", type_="foreignkey")
    op.drop_index("ix_programs_zone_id", table_name="programs")
    op.alter_column("programs", "zone_id", nullable=True)
    op.create_foreign_key(
        "programs_zone_id_fkey", "programs", "zones", ["zone_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("programs_zone_id_fkey", "programs", type_="foreignkey")
    op.alter_column("programs", "zone_id", nullable=False)
    op.create_foreign_key(
        "programs_zone_id_fkey", "programs", "zones", ["zone_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_programs_zone_id", "programs", ["zone_id"])

    op.drop_index("ix_program_zones_zone_id", table_name="program_zones")
    op.drop_table("program_zones")

    op.drop_column("programs", "execution_mode")
    op.drop_column("zones", "config_synced")
