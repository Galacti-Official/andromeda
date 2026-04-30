from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.models.status import (
    ServiceGroup, Service, ServiceStatus, UptimeHistory,
    Incident, IncidentUpdate, IncidentService
)

from Andromeda.schemas.status import (
    StatusResponse, Meta as MetaSchema, Summary as SummarySchema, UptimeHistory as UptimeHistorySchema,
    Service as ServiceSchema, Group as GroupSchema, Incident as IncidentSchema, Incidents as IncidentsSchema,
    Services as ServicesSchema, IncidentUpdate as IncidentUpdateSchema
)


STATUS_PRIORITY = [
    ServiceStatus.major_outage,
    ServiceStatus.partial_outage,
    ServiceStatus.degraded,
    ServiceStatus.operational,
]

STATUS_MESSAGES: dict[ServiceStatus, str] = {
    ServiceStatus.major_outage: "We are experiencing a major outage affecting multiple services.",
    ServiceStatus.partial_outage: "Some services are experiencing an outage.",
    ServiceStatus.degraded: "Some services are experiencing degraded performance.",
    ServiceStatus.operational: "All systems are operational.",
}

UPTIME_HISTORY_DAYS = 90
RECENT_INCIDENT_DAYS = 90
REFRESH_INTERVAL_MINUTES = 5

_CACHE_TTL = timedelta(minutes=REFRESH_INTERVAL_MINUTES)


@dataclass
class _StatusCache:
    response: StatusResponse
    expires_at: datetime


_cache: _StatusCache | None = None


def _worst_status(statuses: list[ServiceStatus]) -> ServiceStatus:
    for status in STATUS_PRIORITY:
        if status in statuses:
            return status
    return ServiceStatus.operational


def _build_incident(
    incident: Incident,
    updates_by_incident: dict[str, list[IncidentUpdate]],
    services_by_incident: dict[str, list[str]]
) -> IncidentSchema:
    return IncidentSchema(
        id=incident.id,
        title=incident.title,
        status=incident.status,
        impact=incident.impact,
        started_at=incident.started_at,
        resolved_at=incident.resolved_at,
        affected_services=services_by_incident.get(incident.id, []),
        updates=[
            IncidentUpdateSchema(message=u.message, created_at=u.created_at)
            for u in updates_by_incident.get(incident.id, [])
        ]
    )


async def _fetch_status(session: AsyncSession) -> StatusResponse:
    now = datetime.now(timezone.utc)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    uptime_cutoff = today_midnight - timedelta(days=UPTIME_HISTORY_DAYS)
    recent_incident_cutoff = today_midnight - timedelta(days=RECENT_INCIDENT_DAYS)

    # Fetch and materialise all results immediately
    groups = (await session.exec(
        select(ServiceGroup).order_by(col(ServiceGroup.name).asc(), col(ServiceGroup.id).asc())
    )).all()
    services = (await session.exec(
        select(Service).order_by(col(Service.name).asc(), col(Service.id).asc())
    )).all()
    uptime_rows = (await session.exec(
        select(UptimeHistory)
        .where(col(UptimeHistory.date) >= uptime_cutoff)
        .order_by(col(UptimeHistory.date).asc())
    )).all()

    active_incidents = (await session.exec(
        select(Incident).where(col(Incident.resolved_at).is_(None))
    )).all()

    recent_incidents = (await session.exec(
        select(Incident).where(
            col(Incident.resolved_at).isnot(None),
            col(Incident.resolved_at) >= recent_incident_cutoff
        )
    )).all()

    incident_ids = [i.id for i in active_incidents] + [i.id for i in recent_incidents]

    updates_by_incident: dict[str, list[IncidentUpdate]] = {}
    updates = (await session.exec(
        select(IncidentUpdate)
        .where(col(IncidentUpdate.incident_id).in_(incident_ids))
        .order_by(col(IncidentUpdate.created_at).desc())
    )).all() if incident_ids else []
    for update in updates:
        updates_by_incident.setdefault(update.incident_id, []).append(update)

    services_by_incident: dict[str, list[str]] = {}
    incident_services = (await session.exec(
        select(IncidentService).where(col(IncidentService.incident_id).in_(incident_ids))
    )).all() if incident_ids else []
    for row in incident_services:
        services_by_incident.setdefault(row.incident_id, []).append(row.service_id)

    # Build lookup dicts
    uptime_by_service: dict[str, list[UptimeHistory]] = {}
    for u in uptime_rows:
        uptime_by_service.setdefault(u.service_id, []).append(u)

    services_by_group: dict[str, list[Service]] = {}
    for s in services:
        services_by_group.setdefault(s.group_id, []).append(s)

    # Assemble groups and services
    assembled_groups = [
        GroupSchema(
            id=g.id,
            name=g.name,
            services=[
                ServiceSchema(
                    id=s.id,
                    name=s.name,
                    status=s.status,
                    degraded_since=s.degraded_since,
                    uptime_history=[
                        UptimeHistorySchema(date=u.date, uptime=u.uptime)
                        for u in uptime_by_service.get(s.id, [])
                    ]
                )
                for s in services_by_group.get(g.id, [])
            ]
        )
        for g in groups
    ]

    all_statuses = [s.status for s in services]
    overall_status = _worst_status(all_statuses)

    meta = MetaSchema(
        updated_at=now,
        next_update_at=now + _CACHE_TTL,
    )
    summary = SummarySchema(status=overall_status, message=STATUS_MESSAGES[overall_status])

    return StatusResponse(
        meta=meta,
        summary=summary,
        services=ServicesSchema(groups=assembled_groups),
        incidents=IncidentsSchema(
            active=[_build_incident(i, updates_by_incident, services_by_incident) for i in active_incidents],
            recent=[_build_incident(i, updates_by_incident, services_by_incident) for i in recent_incidents],
        )
    )


async def get_status(session: AsyncSession) -> StatusResponse:
    global _cache
    now = datetime.now(timezone.utc)
    if _cache is not None and now < _cache.expires_at:
        return _cache.response
    response = await _fetch_status(session)
    _cache = _StatusCache(response=response, expires_at=now + _CACHE_TTL)
    return response
