"""fix missing service check columns

Revision ID: c6d7e8f9a0b1
Revises: b5c9e3f2a1d8
Create Date: 2026-04-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, Sequence[str], None] = 'b5c9e3f2a1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use IF NOT EXISTS to handle the case where a3f1c8e2b047 was stamped
    # rather than actually applied, leaving these columns absent.
    op.execute("ALTER TABLE service ADD COLUMN IF NOT EXISTS check_url VARCHAR(512)")
    op.execute("ALTER TABLE service ADD COLUMN IF NOT EXISTS healthy_codes JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE service DROP COLUMN IF EXISTS check_url")
    op.execute("ALTER TABLE service DROP COLUMN IF EXISTS healthy_codes")
