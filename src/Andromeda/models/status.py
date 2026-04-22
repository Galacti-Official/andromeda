import sqlalchemy as sa
from sqlmodel import Float, SQLModel, Column, DateTime, CheckConstraint, UniqueConstraint, Enum as SAEnum, Field, text
from uuid import UUID, uuid4
from datetime import datetime, timezone
from enum import StrEnum


class ServiceStatus(StrEnum):
    operational = "operational"
    degraded = "degraded"
    partial_outage = "partial_outage"
    major_outage = "major_outage"


class IncidentStatus(StrEnum):
    investigating = "investigating"
    identified = "identified"
    monitoring = "monitoring"
    resolved = "resolved"


class IncidentImpact(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ServiceGroup(SQLModel, table=True):
    id: str = Field(primary_key=True, max_length=64)
    name: str = Field(max_length=128)


class Service(SQLModel, table=True):
    id: str = Field(primary_key=True, max_length=64)
    group_id: str = Field(foreign_key="servicegroup.id", index=True, max_length=64)
    name: str = Field(max_length=128)
    status: ServiceStatus = Field(
        sa_column=Column(SAEnum(ServiceStatus), nullable=False)
    )
    degraded_since: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    check_url: str | None = Field(default=None, max_length=512, nullable=True)
    healthy_codes: list[int] | None = Field(default=None, sa_column=Column(sa.JSON, nullable=True))


class UptimeHistory(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("service_id", "date", name="uq_uptime_service_date"),
        CheckConstraint("uptime >= 0.0 AND uptime <= 100.0", name="ck_uptime_range")
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    service_id: str = Field(foreign_key="service.id", index=True, max_length=64)
    date: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    uptime: float = Field(sa_column=Column(Float, nullable=False))


class Incident(SQLModel, table=True):
    id: str = Field(primary_key=True, max_length=64)
    title: str = Field(max_length=256)
    status: IncidentStatus = Field(
        sa_column=Column(SAEnum(IncidentStatus), nullable=False)
    )
    impact: IncidentImpact = Field(
        sa_column=Column(SAEnum(IncidentImpact), nullable=False)
    )
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()")
        )
    )
    resolved_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class IncidentService(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("incident_id", "service_id", name="uq_incident_service"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    incident_id: str = Field(foreign_key="incident.id", index=True, max_length=64)
    service_id: str = Field(foreign_key="service.id", index=True, max_length=64)


class IncidentUpdate(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    incident_id: str = Field(foreign_key="incident.id", index=True, max_length=64)
    message: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()")
        )
    )


class ServiceCheckHistory(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    service_id: str = Field(foreign_key="service.id", index=True, max_length=64)
    checked_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    healthy: bool = Field(nullable=False)
    response_time_ms: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    status_code: int | None = Field(default=None, nullable=True)
    error: str | None = Field(default=None, nullable=True)
