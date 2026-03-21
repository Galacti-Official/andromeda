"""seed core status data

Revision ID: e15f38a3c191
Revises: ef55491ddf9d
Create Date: 2026-03-21 19:44:21.110777

"""
import datetime
from random import uniform
from typing import Sequence, Union

from alembic import op
from sqlmodel import Session
from random import uniform, random
import sqlalchemy as sa
from sqlmodel import col, delete
import sqlmodel.sql.sqltypes

from Andromeda.models.status import Service, ServiceGroup, ServiceStatus, UptimeHistory


# revision identifiers, used by Alembic.
revision = 'e15f38a3c191'
down_revision = '68b87fd10acd' 
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _generate_uptime_history(service_id: str, days: int = 90) -> list[UptimeHistory]:
    now = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []

    for i in range(days):
        date = now - datetime.timedelta(days=(days - 1 - i))

        roll = random()
        if roll > 0.10:
            uptime = 99.999
            uptime = round(uniform(95.0, 99.9), 2)
        else:
            uptime = round(uniform(80.0, 95.0), 2)

        rows.append(UptimeHistory(service_id=service_id, date=date, uptime=uptime))

    return rows


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    group = ServiceGroup(id="core", name="Core")
    session.add(group)
    session.flush()

    for svc_id, svc_name in [("website", "Website"), ("dashboard", "Dashboard"), ("api", "API")]:
        session.add(Service(
            id=svc_id,
            name=svc_name,
            group_id="core",
            status=ServiceStatus.operational,
        ))
        for row in _generate_uptime_history(svc_id):
            session.add(row)

    session.commit()


def downgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    session.exec(delete(UptimeHistory).where(col(UptimeHistory.service_id).in_(["website", "dashboard", "api"])))
    session.exec(delete(Service).where(col(Service.group_id) == "core"))
    session.exec(delete(ServiceGroup).where(col(ServiceGroup.id) == "core"))
    session.commit()
