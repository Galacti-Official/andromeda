import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from typing import NamedTuple

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.api.database.database import engine
from Andromeda.models.status import Incident, IncidentImpact, IncidentService, IncidentStatus, IncidentUpdate, Service, ServiceStatus, UptimeHistory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHECK_INTERVAL_MINUTES = 10
CHECK_TIMEOUT_SECONDS = 10
PARTIAL_OUTAGE_ESCALATION_THRESHOLD = timedelta(minutes=30)

SERVICE_HEALTH_ENDPOINTS: dict[str, str] = {
    "website": "https://galacti.org/",
    "dashboard": "https://dashboard.galacti.org/",
    "api": "https://api.galacti.org/",
}

SERVICE_HEALTHY_CODES: dict[str, set[int]] = {
    "website": {200, 301, 302},
    "dashboard": {200, 301, 302},
    "api": {200},
}

_IMPACT_MAP = {
    ServiceStatus.degraded: IncidentImpact.low,
    ServiceStatus.partial_outage: IncidentImpact.medium,
    ServiceStatus.major_outage: IncidentImpact.high,
}


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

class CheckResult(NamedTuple):
    service_id: str
    healthy: bool
    response_time_ms: float | None
    status_code: int | None
    error: str | None


_check_results: dict[datetime, dict[str, list[bool]]] = {}


def _utc_midnight(value: datetime) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _incident_id(service_id: str, started_at: datetime) -> str:
    return f"auto-{service_id}-{started_at.strftime('%Y%m%d%H%M%S')}"


async def _open_incident_for_service(session: AsyncSession, service_id: str) -> Incident | None:
    """Return the unresolved auto-generated incident for a service, if any."""
    result = await session.exec(
        select(Incident)
        .where(
            col(Incident.id).in_(
                select(IncidentService.incident_id).where(
                    IncidentService.service_id == service_id
                )
            ),
            Incident.resolved_at.is_(None),  # type: ignore[union-attr]
            col(Incident.id).startswith("auto-"),
        )
    )
    return result.first()


async def _create_incident(session: AsyncSession, service: Service, status: ServiceStatus, now: datetime) -> None:
    incident_id = _incident_id(service.id, now)
    impact = _IMPACT_MAP[status]

    incident = Incident(
        id=incident_id,
        title=f"{service.name} is experiencing issues",
        status=IncidentStatus.investigating,
        impact=impact,
        started_at=now,
    )
    session.add(incident)
    session.add(IncidentService(incident_id=incident_id, service_id=service.id))
    session.add(IncidentUpdate(
        incident_id=incident_id,
        message=f"Automated monitoring detected {status} on {service.name}.",
    ))
    logger.warning("Created incident %s for service %s (%s)", incident_id, service.id, status)


async def _resolve_incident(session: AsyncSession, service: Service, now: datetime) -> None:
    incident = await _open_incident_for_service(session, service.id)
    if not incident:
        return

    incident.status = IncidentStatus.resolved
    incident.resolved_at = now
    session.add(incident)
    session.add(IncidentUpdate(
        incident_id=incident.id,
        message=f"Automated monitoring confirmed {service.name} has recovered.",
    ))
    logger.info("Resolved incident %s for service %s", incident.id, service.id)


async def _check_service(service_id: str, url: str) -> CheckResult:
    healthy_codes = SERVICE_HEALTHY_CODES.get(service_id, {200})

    try:
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS, follow_redirects=False) as client:
            start = datetime.now(timezone.utc)
            response = await client.get(url)
            elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        healthy = response.status_code in healthy_codes
        return CheckResult(
            service_id=service_id,
            healthy=healthy,
            response_time_ms=round(elapsed_ms, 2),
            status_code=response.status_code,
            error=None,
        )
    except httpx.TimeoutException:
        return CheckResult(service_id=service_id, healthy=False, response_time_ms=None, status_code=None, error="timeout")
    except httpx.RequestError as e:
        return CheckResult(service_id=service_id, healthy=False, response_time_ms=None, status_code=None, error=str(e))


async def _update_service_status(session: AsyncSession, service: Service, result: CheckResult) -> None:
    now = datetime.now(timezone.utc)

    if result.healthy:
        if service.status != ServiceStatus.operational:
            logger.info("Service %s recovered; marking operational", service.id)
            service.status = ServiceStatus.operational
            service.degraded_since = None
            session.add(service)
            await _resolve_incident(session, service, now)
    else:
        if service.status == ServiceStatus.operational:
            logger.warning("Service %s unhealthy; marking degraded", service.id)
            service.status = ServiceStatus.degraded
            service.degraded_since = now
            session.add(service)
            await _create_incident(session, service, ServiceStatus.degraded, now)
        elif (
            service.status == ServiceStatus.degraded
            and service.degraded_since
            and (now - service.degraded_since) > PARTIAL_OUTAGE_ESCALATION_THRESHOLD
        ):
            logger.warning("Service %s degraded too long; escalating to partial_outage", service.id)
            service.status = ServiceStatus.partial_outage
            session.add(service)

            # Update the existing incident's impact rather than creating a new one.
            incident = await _open_incident_for_service(session, service.id)
            if incident:
                incident.impact = IncidentImpact.medium
                session.add(incident)
                session.add(IncidentUpdate(
                    incident_id=incident.id,
                    message=f"Issue escalated — {service.name} has been degraded for over 30 minutes.",
                ))


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

async def run_health_checks() -> None:
    """Check all configured service endpoints and update their status."""
    result_day = _utc_midnight(datetime.now(timezone.utc))
    logger.info("Running health checks for %d services", len(SERVICE_HEALTH_ENDPOINTS))

    async with AsyncSession(engine) as session:
        services = (await session.exec(select(Service))).all()
        services_by_id = {s.id: s for s in services}
        # Materialize once because we iterate the endpoints for both gather() and result handling.
        endpoint_items = list(SERVICE_HEALTH_ENDPOINTS.items())
        check_batch = [
            _check_service(service_id, url)
            for service_id, url in endpoint_items
        ]
        results = await asyncio.gather(*check_batch, return_exceptions=True)

        for (service_id, _url), result in zip(endpoint_items, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Unexpected error checking service %s: %s", service_id, result, exc_info=result)
                continue

            check_result = result
            logger.info(
                "Health check: service=%s healthy=%s status_code=%s response_time_ms=%s error=%s",
                service_id, check_result.healthy, check_result.status_code,
                check_result.response_time_ms, check_result.error,
            )

            # Track result for daily uptime calculation.
            _check_results.setdefault(result_day, {}).setdefault(service_id, []).append(check_result.healthy)

            # Update service status in DB
            service = services_by_id.get(service_id)
            if service:
                await _update_service_status(session, service, check_result)
            else:
                logger.warning("Service %s not found in database; skipping status update", service_id)

        await session.commit()


async def write_daily_uptime() -> None:
    """
    Calculate and persist uptime percentage for the previous day.
    Runs at midnight UTC. Clears the in-memory check results after writing.
    """
    yesterday = _utc_midnight((datetime.now(timezone.utc) - timedelta(days=1)))
    results_by_service = _check_results.pop(yesterday, {})
    logger.info("Writing daily uptime for %s", yesterday)

    if not results_by_service:
        logger.warning("No in-memory check results found for %s; uptime not written", yesterday)
        return

    async with AsyncSession(engine) as session:
        for service_id, results in results_by_service.items():
            uptime_pct = round((sum(results) / len(results)) * 100, 2)

            # Avoid duplicate entries
            existing = (await session.exec(
                select(UptimeHistory).where(
                    col(UptimeHistory.service_id) == service_id,
                    col(UptimeHistory.date) == yesterday,
                )
            )).first()

            if existing:
                existing.uptime = uptime_pct
                session.add(existing)
            else:
                session.add(UptimeHistory(service_id=service_id, date=yesterday, uptime=uptime_pct))

            logger.info("Uptime for %s on %s: %.2f%%", service_id, yesterday, uptime_pct)

        await session.commit()


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Health check scheduler already running")
        return

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(run_health_checks, "interval", minutes=CHECK_INTERVAL_MINUTES, id="health_checks")
    _scheduler.add_job(write_daily_uptime, "cron", hour=0, minute=0, id="daily_uptime")
    _scheduler.start()
    logger.info("Health check scheduler started")


def stop_scheduler() -> None:
    global _scheduler

    if not _scheduler:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Health check scheduler stopped")
