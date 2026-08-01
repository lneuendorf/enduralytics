"""add season goal columns to athlete_settings

Revision ID: c4d2f7a91e30
Revises: 3a1c9d5e7b02
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d2f7a91e30"
down_revision: Union[str, Sequence[str], None] = "3a1c9d5e7b02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("athlete_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("annual_tss_goal", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("annual_hours_goal", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("athlete_settings", schema=None) as batch_op:
        batch_op.drop_column("annual_hours_goal")
        batch_op.drop_column("annual_tss_goal")
