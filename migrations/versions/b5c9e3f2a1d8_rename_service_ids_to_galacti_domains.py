"""rename service ids to galacti domains

Revision ID: b5c9e3f2a1d8
Revises: a3f1c8e2b047
Create Date: 2026-04-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op


revision: str = 'b5c9e3f2a1d8'
down_revision: Union[str, Sequence[str], None] = 'a3f1c8e2b047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RENAMES = [
    ("website", "galacti.org"),
    ("dashboard", "dashboard.galacti.org"),
    ("api", "api.galacti.org"),
]

# Tables that already exist and have FK constraints to drop/recreate
_EXISTING_FK_TABLES = [
    ("uptimehistory", "uptimehistory_service_id_fkey"),
    ("incidentservice", "incidentservice_service_id_fkey"),
]

# All tables with a service_id column (including new ones)
_ALL_FK_TABLES = _EXISTING_FK_TABLES + [("servicecheckhistory", None)]


def _update_ids(renames: list[tuple[str, str]], tables=None) -> None:
    if tables is None:
        tables = _ALL_FK_TABLES
    for old_id, new_id in renames:
        for table, _ in tables:
            op.execute(f"UPDATE {table} SET service_id = '{new_id}' WHERE service_id = '{old_id}'")
        op.execute(f"UPDATE service SET id = '{new_id}' WHERE id = '{old_id}'")


def upgrade() -> None:
    op.create_table(
        'servicecheckhistory',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('service_id', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('healthy', sa.Boolean(), nullable=False),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['service_id'], ['service.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_servicecheckhistory_service_id', 'servicecheckhistory', ['service_id'], unique=False)
    op.create_index('ix_servicecheckhistory_checked_at', 'servicecheckhistory', ['checked_at'], unique=False)

    for table, constraint in _EXISTING_FK_TABLES:
        op.drop_constraint(constraint, table, type_="foreignkey")

    _update_ids(_RENAMES)

    for table, _ in _EXISTING_FK_TABLES:
        op.create_foreign_key(None, table, "service", ["service_id"], ["id"])


def downgrade() -> None:
    op.drop_index('ix_servicecheckhistory_checked_at', table_name='servicecheckhistory')
    op.drop_index('ix_servicecheckhistory_service_id', table_name='servicecheckhistory')
    op.drop_table('servicecheckhistory')

    for table, constraint in _EXISTING_FK_TABLES:
        op.drop_constraint(constraint, table, type_="foreignkey")

    reversed_renames = [(new_id, old_id) for old_id, new_id in _RENAMES]

    # If old-format rows already exist (duplicate state), remove them before renaming
    for _, old_id in reversed_renames:
        op.execute(f"DELETE FROM service WHERE id = '{old_id}'")

    _update_ids(reversed_renames, tables=_EXISTING_FK_TABLES)

    for table, _ in _EXISTING_FK_TABLES:
        op.create_foreign_key(None, table, "service", ["service_id"], ["id"])
