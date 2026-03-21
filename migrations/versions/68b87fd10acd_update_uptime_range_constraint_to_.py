"""update uptime range constraint to percentage

Revision ID: 68b87fd10acd
Revises: e15f38a3c191
Create Date: 2026-03-21 19:55:26.808384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '68b87fd10acd'
down_revision = 'ef55491ddf9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_uptime_range", "uptimehistory")
    op.create_check_constraint(
        "ck_uptime_range",
        "uptimehistory",
        "uptime >= 0.0 AND uptime <= 100.0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_uptime_range", "uptimehistory")
    op.create_check_constraint(
        "ck_uptime_range",
        "uptimehistory",
        "uptime >= 0.0 AND uptime <= 1.0"
    )
