"""add athlete_setting_entries table

Revision ID: 3a1c9d5e7b02
Revises: 0f8f8781f451
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3a1c9d5e7b02"
down_revision: Union[str, Sequence[str], None] = "0f8f8781f451"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "athlete_setting_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=48), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("athlete_setting_entries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_athlete_setting_entries_athlete_id"), ["athlete_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_athlete_setting_entries_field"), ["field"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_athlete_setting_entries_effective_date"),
            ["effective_date"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("athlete_setting_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_athlete_setting_entries_effective_date"))
        batch_op.drop_index(batch_op.f("ix_athlete_setting_entries_field"))
        batch_op.drop_index(batch_op.f("ix_athlete_setting_entries_athlete_id"))
    op.drop_table("athlete_setting_entries")
