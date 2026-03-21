from pydantic import BaseModel, ConfigDict
from datetime import datetime

from Andromeda.models.status import ServiceStatus, IncidentStatus, IncidentImpact


class Meta(BaseModel):
    version: str = "1"
    updated_at: datetime
    next_update_at: datetime | None = None


class Summary(BaseModel):
    status: ServiceStatus
    message: str


class UptimeHistory(BaseModel):
    date: datetime
    uptime: float


class Service(BaseModel):
    id: str
    name: str
    status: ServiceStatus
    degraded_since: datetime | None = None
    uptime_history: list[UptimeHistory] = []


class Group(BaseModel):
    id: str
    name: str
    services: list[Service]


class Services(BaseModel):
    groups: list[Group]


class IncidentUpdate(BaseModel):
    message: str
    created_at: datetime


class Incident(BaseModel):
    id: str
    title: str
    status: IncidentStatus
    impact: IncidentImpact
    affected_services: list[str] = []
    started_at: datetime
    resolved_at: datetime | None = None
    updates: list[IncidentUpdate] = []


class Incidents(BaseModel):
    active: list[Incident]
    recent: list[Incident]


class StatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    meta: Meta
    summary: Summary
    services: Services
    incidents: Incidents
