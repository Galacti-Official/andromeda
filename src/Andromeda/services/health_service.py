import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from time import perf_counter
from typing import NamedTuple

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete as sa_delete
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.api.database.database import engine
from Andromeda.models.status import (
    Incident, IncidentImpact, IncidentService, IncidentStatus, IncidentUpdate,
    Service, ServiceCheckHistory, ServiceStatus, UptimeHistory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHECK_INTERVAL_MINUTES = 10
CHECK_TIMEOUT_SECONDS = 10
CHECK_CONCURRENCY_LIMIT = 20
PARTIAL_OUTAGE_ESCALATION_THRESHOLD = timedelta(minutes=30)
MAJOR_OUTAGE_ESCALATION_THRESHOLD = timedelta(hours=2)
CHECK_HISTORY_RETENTION_DAYS = 7

_IMPACT_MAP = {
    ServiceStatus.degraded: IncidentImpact.low,
    ServiceStatus.partial_outage: IncidentImpact.medium,
    ServiceStatus.major_outage: IncidentImpact.high,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class CheckResult(NamedTuple):
    service_id: str
    healthy: bool
    response_time_ms: float | None
    status_code: int | None
    error: str | None


def _utc_midnight(value: datetime) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _incident_id(service_id: str, started_at: datetime) -> str:
    return f"auto-{service_id}-{started_at.strftime('%Y%m%d%H%M%S%f')}"


async def _unresolved_auto_incident_for_service(session: AsyncSession, service_id: str) -> Incident | None:
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
    impact = _IMPACT_MAP.get(status, IncidentImpact.low)

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
    incident = await _unresolved_auto_incident_for_service(session, service.id)
    if not incident:
        return

    incident.status = IncidentStatus.resolved
    incident.resolved_at = now
    session.add(incident)
    session.add(IncidentUpdate(
        incident_id=incident.id,
        message=f"Automated monitoring confirmed {service.name} has fully recovered.",
    ))
    logger.info("Resolved incident %s for service %s", incident.id, service.id)


async def _check_service(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    service_id: str,
    url: str,
    healthy_codes: set[int],
) -> CheckResult:
    async with semaphore:
        try:
            start = perf_counter()
            response = await client.get(url)
            elapsed_ms = (perf_counter() - start) * 1000

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
            # First clean check after an outage: recover service and move incident to monitoring.
            # The incident will be fully resolved on the next clean check.
            logger.info("Service %s recovered; marking operational, incident moved to monitoring", service.id)
            service.status = ServiceStatus.operational
            service.degraded_since = None
            session.add(service)
            incident = await _unresolved_auto_incident_for_service(session, service.id)
            if incident:
                incident.status = IncidentStatus.monitoring
                session.add(incident)
                session.add(IncidentUpdate(
                    incident_id=incident.id,
                    message=f"{service.name} appears to have recovered. Monitoring for stability.",
                ))
        else:
            # Already operational: close out any incident still in monitoring state.
            incident = await _unresolved_auto_incident_for_service(session, service.id)
            if incident and incident.status == IncidentStatus.monitoring:
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
            incident = await _unresolved_auto_incident_for_service(session, service.id)
            if incident:
                incident.impact = IncidentImpact.medium
                session.add(incident)
                session.add(IncidentUpdate(
                    incident_id=incident.id,
                    message=f"Issue escalated — {service.name} has been degraded for over 30 minutes.",
                ))
            else:
                await _create_incident(session, service, ServiceStatus.partial_outage, now)
        elif (
            service.status == ServiceStatus.partial_outage
            and service.degraded_since
            and (now - service.degraded_since) > MAJOR_OUTAGE_ESCALATION_THRESHOLD
        ):
            logger.warning("Service %s in partial outage too long; escalating to major_outage", service.id)
            service.status = ServiceStatus.major_outage
            session.add(service)
            incident = await _unresolved_auto_incident_for_service(session, service.id)
            if incident:
                incident.impact = IncidentImpact.high
                session.add(incident)
                session.add(IncidentUpdate(
                    incident_id=incident.id,
                    message=f"Major outage — {service.name} has been in partial outage for over 2 hours.",
                ))
            else:
                await _create_incident(session, service, ServiceStatus.major_outage, now)


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

async def run_health_checks() -> None:
    """Check all configured service endpoints and update their status."""
    async with AsyncSession(engine) as session:
        services = (await session.exec(select(Service))).all()
        monitorable = [(s, s.check_url) for s in services if s.check_url]

        if not monitorable:
            logger.warning("No services with check_url configured; skipping health checks")
            return

        logger.info("Running health checks for %d services", len(monitorable))
        semaphore = asyncio.Semaphore(CHECK_CONCURRENCY_LIMIT)
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS, follow_redirects=False) as client:
            check_batch = [
                _check_service(client, semaphore, s.id, url, set(s.healthy_codes or [200]))
                for s, url in monitorable
            ]
            results = await asyncio.gather(*check_batch, return_exceptions=True)
        now = datetime.now(timezone.utc)

        for (service, _url), result in zip(monitorable, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "Unexpected error checking service %s",
                    service.id,
                    exc_info=(type(result), result, result.__traceback__),
                )
                continue

            logger.info(
                "Health check: service=%s healthy=%s status_code=%s response_time_ms=%s error=%s",
                service.id, result.healthy, result.status_code,
                result.response_time_ms, result.error,
            )

            session.add(ServiceCheckHistory(
                service_id=service.id,
                checked_at=now,
                healthy=result.healthy,
                response_time_ms=result.response_time_ms,
                status_code=result.status_code,
                error=result.error,
            ))

            await _update_service_status(session, service, result)

        await session.commit()


async def write_daily_uptime() -> None:
    """Calculate and persist uptime for the previous day; based on available checks only."""
    yesterday = _utc_midnight(datetime.now(timezone.utc) - timedelta(days=1))
    today = yesterday + timedelta(days=1)
    logger.info("Writing daily uptime for %s", yesterday.date())

    async with AsyncSession(engine) as session:
        services = (await session.exec(select(Service))).all()

        for service in services:
            if not service.check_url:
                continue

            checks = (await session.exec(
                select(ServiceCheckHistory).where(
                    col(ServiceCheckHistory.service_id) == service.id,
                    col(ServiceCheckHistory.checked_at) >= yesterday,
                    col(ServiceCheckHistory.checked_at) < today,
                )
            )).all()

            if not checks:
                logger.warning("No check history for service %s on %s; uptime not written", service.id, yesterday.date())
                continue

            uptime_pct = round((sum(c.healthy for c in checks) / len(checks)) * 100, 2)

            existing = (await session.exec(
                select(UptimeHistory).where(
                    col(UptimeHistory.service_id) == service.id,
                    col(UptimeHistory.date) == yesterday,
                )
            )).first()

            if existing:
                existing.uptime = uptime_pct
                session.add(existing)
            else:
                session.add(UptimeHistory(service_id=service.id, date=yesterday, uptime=uptime_pct))

            logger.info("Uptime for %s on %s: %.2f%%", service.id, yesterday.date(), uptime_pct)

        await session.commit()


async def cleanup_check_history() -> None:
    """Delete check history records older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=CHECK_HISTORY_RETENTION_DAYS)
    async with AsyncSession(engine) as session:
        await session.exec(
            sa_delete(ServiceCheckHistory).where(col(ServiceCheckHistory.checked_at) < cutoff)
        )
        await session.commit()
    logger.info("Cleaned up check history older than %d days", CHECK_HISTORY_RETENTION_DAYS)


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
    _scheduler.add_job(
        run_health_checks,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id="health_checks",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(write_daily_uptime, "cron", hour=0, minute=0, id="daily_uptime")
    _scheduler.add_job(cleanup_check_history, "cron", hour=1, minute=0, id="cleanup_check_history")
    _scheduler.start()
    logger.info("Health check scheduler started")


def stop_scheduler() -> None:
    global _scheduler

    if not _scheduler:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Health check scheduler stopped")
