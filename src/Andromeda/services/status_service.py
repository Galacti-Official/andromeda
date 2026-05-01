import asyncio
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

# O(1) rank lookup; lower rank = worse status
_STATUS_RANK: dict[ServiceStatus, int] = {s: i for i, s in enumerate(STATUS_PRIORITY)}

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
_cache_lock = asyncio.Lock()


@dataclass
class _StatusCache:
    response: StatusResponse
    expires_at: datetime


_cache: _StatusCache | None = None


def _worst_status(statuses: list[ServiceStatus]) -> ServiceStatus:
    if not statuses:
        return ServiceStatus.operational
    return min(statuses, key=lambda s: _STATUS_RANK.get(s, len(STATUS_PRIORITY)))


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
        .order_by(col(Incident.started_at).asc())
    )).all()

    recent_incidents = (await session.exec(
        select(Incident).where(
            col(Incident.resolved_at).isnot(None),
            col(Incident.resolved_at) >= recent_incident_cutoff
        ).order_by(col(Incident.started_at).asc())
    )).all()

    _relevant_incident = (
        col(Incident.resolved_at).is_(None) |
        (col(Incident.resolved_at) >= recent_incident_cutoff)
    )

    updates_by_incident: dict[str, list[IncidentUpdate]] = {}
    for update in (await session.exec(
        select(IncidentUpdate)
        .join(Incident, col(IncidentUpdate.incident_id) == col(Incident.id))
        .where(_relevant_incident)
    )).all():
        updates_by_incident.setdefault(update.incident_id, []).append(update)
    for bucket in updates_by_incident.values():
        bucket.sort(key=lambda u: u.created_at, reverse=True)

    services_by_incident: dict[str, list[str]] = {}
    for row in (await session.exec(
        select(IncidentService)
        .join(Incident, col(IncidentService.incident_id) == col(Incident.id))
        .where(_relevant_incident)
    )).all():
        services_by_incident.setdefault(row.incident_id, []).append(row.service_id)

    uptime_by_service: dict[str, list[UptimeHistory]] = {}
    for u in uptime_rows:
        uptime_by_service.setdefault(u.service_id, []).append(u)
    for bucket in uptime_by_service.values():
        bucket.sort(key=lambda u: u.date)

    services_by_group: dict[str, list[Service]] = {}
    for s in services:
        services_by_group.setdefault(s.group_id, []).append(s)

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

    overall_status = _worst_status([s.status for s in services])

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


def invalidate_cache() -> None:
    """Invalidate cache after any write that changes status or incident data."""
    global _cache
    _cache = None


async def get_status(session: AsyncSession) -> StatusResponse:
    global _cache
    now = datetime.now(timezone.utc)
    if _cache is not None and now < _cache.expires_at:
        return _cache.response
    async with _cache_lock:
        now = datetime.now(timezone.utc)
        if _cache is not None and now < _cache.expires_at:
            return _cache.response
        response = await _fetch_status(session)
        _cache = _StatusCache(response=response, expires_at=now + _CACHE_TTL)
    return _cache.response
