"""Add GitHub OAuth support

Revision ID: 002
Revises: 001
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("github_id", sa.String(32), nullable=True))
    op.create_unique_constraint("uq_users_github_id", "users", ["github_id"])
    op.create_index("ix_users_github_id", "users", ["github_id"])


def downgrade() -> None:
    op.drop_index("ix_users_github_id", table_name="users")
    op.drop_constraint("uq_users_github_id", "users", type_="unique")
    op.drop_column("users", "github_id")
