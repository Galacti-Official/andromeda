"""add service check fields

Revision ID: a3f1c8e2b047
Revises: 2275d459751b
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision: str = 'a3f1c8e2b047'
down_revision: Union[str, Sequence[str], None] = '2275d459751b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('service', sa.Column('check_url', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True))
    op.add_column('service', sa.Column('healthy_codes', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('service', 'healthy_codes')
    op.drop_column('service', 'check_url')
