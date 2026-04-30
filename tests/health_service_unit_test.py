from datetime import datetime, timedelta, timezone
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

fake_database_module = types.ModuleType("Andromeda.api.database.database")
setattr(fake_database_module, "engine", object())
sys.modules.setdefault("Andromeda.api.database.database", fake_database_module)

from Andromeda.models.status import (
    Incident, IncidentImpact, IncidentStatus, Service, ServiceCheckHistory,
    ServiceStatus, UptimeHistory,
)
from Andromeda.services import health_service
from Andromeda.services.health_service import CheckResult, _update_service_status, write_daily_uptime


class FrozenDateTime(datetime):
    current = datetime(2026, 3, 21, 0, 2, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        value = cls.current
        if tz is not None:
            return value.astimezone(tz)
        return value.replace(tzinfo=None)


class QueryResult:
    """Wraps a list to support both .all() and .first() on mocked exec() calls."""
    def __init__(self, items):
        self._items = items if isinstance(items, list) else []

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_service(
    status: ServiceStatus,
    degraded_since: datetime | None = None,
    check_url: str | None = None,
) -> Service:
    return Service(
        id="api",
        group_id="core",
        name="API",
        status=status,
        degraded_since=degraded_since,
        check_url=check_url,
    )


def make_result(healthy: bool) -> CheckResult:
    return CheckResult(
        service_id="api",
        healthy=healthy,
        response_time_ms=100.0,
        status_code=200 if healthy else 503,
        error=None if healthy else "bad gateway",
    )


def make_incident(status: IncidentStatus = IncidentStatus.investigating) -> Incident:
    return Incident(
        id="auto-api-20260321000000",
        title="API is experiencing issues",
        status=status,
        impact=IncidentImpact.low,
        started_at=FrozenDateTime.current - timedelta(minutes=10),
    )


# ---------------------------------------------------------------------------
# _update_service_status — unhealthy paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unhealthy_operational_service_becomes_degraded():
    session = MagicMock()
    service = make_service(ServiceStatus.operational)

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "_create_incident", new=AsyncMock()),
    ):
        await _update_service_status(session, service, make_result(False))

    assert service.status == ServiceStatus.degraded
    assert service.degraded_since == FrozenDateTime.current
    session.add.assert_called_once_with(service)


@pytest.mark.asyncio
async def test_unhealthy_degraded_service_escalates_to_partial_outage_after_30_minutes():
    session = MagicMock()
    service = make_service(
        ServiceStatus.degraded,
        degraded_since=FrozenDateTime.current - timedelta(minutes=31),
    )

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "_unresolved_auto_incident_for_service", new=AsyncMock(return_value=None)),
        patch.object(health_service, "_create_incident", new=AsyncMock()),
    ):
        await _update_service_status(session, service, make_result(False))

    assert service.status == ServiceStatus.partial_outage
    assert service.degraded_since == FrozenDateTime.current - timedelta(minutes=31)
    session.add.assert_called_once_with(service)


@pytest.mark.asyncio
async def test_unhealthy_degraded_service_does_not_escalate_before_30_minutes():
    session = MagicMock()
    service = make_service(
        ServiceStatus.degraded,
        degraded_since=FrozenDateTime.current - timedelta(minutes=20),
    )

    with patch.object(health_service, "datetime", FrozenDateTime):
        await _update_service_status(session, service, make_result(False))

    assert service.status == ServiceStatus.degraded
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_unhealthy_partial_outage_escalates_to_major_outage_after_2_hours():
    session = MagicMock()
    service = make_service(
        ServiceStatus.partial_outage,
        degraded_since=FrozenDateTime.current - timedelta(hours=2, minutes=1),
    )

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "_unresolved_auto_incident_for_service", new=AsyncMock(return_value=None)),
        patch.object(health_service, "_create_incident", new=AsyncMock()),
    ):
        await _update_service_status(session, service, make_result(False))

    assert service.status == ServiceStatus.major_outage
    session.add.assert_called_once_with(service)


@pytest.mark.asyncio
async def test_unhealthy_partial_outage_does_not_escalate_before_2_hours():
    session = MagicMock()
    service = make_service(
        ServiceStatus.partial_outage,
        degraded_since=FrozenDateTime.current - timedelta(hours=1),
    )

    with patch.object(health_service, "datetime", FrozenDateTime):
        await _update_service_status(session, service, make_result(False))

    assert service.status == ServiceStatus.partial_outage
    session.add.assert_not_called()


# ---------------------------------------------------------------------------
# _update_service_status — recovery paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recovery_moves_incident_to_monitoring():
    """First clean check after an outage moves the incident to monitoring, not resolved."""
    session = MagicMock()
    service = make_service(
        ServiceStatus.degraded,
        degraded_since=FrozenDateTime.current - timedelta(minutes=10),
    )
    incident = make_incident(IncidentStatus.investigating)

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "_unresolved_auto_incident_for_service", new=AsyncMock(return_value=incident)),
    ):
        await _update_service_status(session, service, make_result(True))

    assert service.status == ServiceStatus.operational
    assert service.degraded_since is None
    assert incident.status == IncidentStatus.monitoring
    # service + incident + IncidentUpdate
    assert session.add.call_count == 3


@pytest.mark.asyncio
async def test_recovery_without_open_incident_only_updates_service():
    session = MagicMock()
    service = make_service(
        ServiceStatus.degraded,
        degraded_since=FrozenDateTime.current - timedelta(minutes=10),
    )

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "_unresolved_auto_incident_for_service", new=AsyncMock(return_value=None)),
    ):
        await _update_service_status(session, service, make_result(True))

    assert service.status == ServiceStatus.operational
    assert service.degraded_since is None
    session.add.assert_called_once_with(service)


@pytest.mark.asyncio
async def test_second_clean_check_resolves_monitoring_incident():
    """When service is operational and a monitoring incident is open, the next clean check resolves it."""
    session = MagicMock()
    service = make_service(ServiceStatus.operational)
    incident = make_incident(IncidentStatus.monitoring)

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "_unresolved_auto_incident_for_service", new=AsyncMock(return_value=incident)),
        patch.object(health_service, "_resolve_incident", new=AsyncMock()) as mock_resolve,
    ):
        await _update_service_status(session, service, make_result(True))

    mock_resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_clean_check_on_already_operational_service_with_no_incident_is_noop():
    session = MagicMock()
    service = make_service(ServiceStatus.operational)

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "_unresolved_auto_incident_for_service", new=AsyncMock(return_value=None)),
    ):
        await _update_service_status(session, service, make_result(True))

    session.add.assert_not_called()


# ---------------------------------------------------------------------------
# write_daily_uptime
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_daily_uptime_computes_from_db_history():
    yesterday = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
    service = make_service(ServiceStatus.operational, check_url="https://example.com")
    checks = [
        ServiceCheckHistory(service_id="api", checked_at=yesterday, healthy=True, response_time_ms=50.0),
        ServiceCheckHistory(service_id="api", checked_at=yesterday, healthy=False, response_time_ms=None),
    ]

    session = MagicMock()
    session.exec = AsyncMock(side_effect=[
        QueryResult([service]),  # select(Service)
        QueryResult(checks),     # select(ServiceCheckHistory)
        QueryResult([]),         # select(UptimeHistory) — no existing record
    ])
    session.commit = AsyncMock()

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "AsyncSession", return_value=SessionContext(session)),
    ):
        await write_daily_uptime()

    assert session.add.call_count == 1
    added = session.add.call_args.args[0]
    assert added.service_id == "api"
    assert added.date == yesterday
    assert added.uptime == 50.0


@pytest.mark.asyncio
async def test_write_daily_uptime_updates_existing_record():
    yesterday = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
    service = make_service(ServiceStatus.operational, check_url="https://example.com")
    existing = UptimeHistory(service_id="api", date=yesterday, uptime=80.0)
    checks = [
        ServiceCheckHistory(service_id="api", checked_at=yesterday, healthy=True, response_time_ms=50.0),
        ServiceCheckHistory(service_id="api", checked_at=yesterday, healthy=True, response_time_ms=60.0),
        ServiceCheckHistory(service_id="api", checked_at=yesterday, healthy=True, response_time_ms=55.0),
        ServiceCheckHistory(service_id="api", checked_at=yesterday, healthy=False, response_time_ms=None),
    ]

    session = MagicMock()
    session.exec = AsyncMock(side_effect=[
        QueryResult([service]),
        QueryResult(checks),
        QueryResult([existing]),
    ])
    session.commit = AsyncMock()

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "AsyncSession", return_value=SessionContext(session)),
    ):
        await write_daily_uptime()

    assert existing.uptime == 75.0
    session.add.assert_called_once_with(existing)


@pytest.mark.asyncio
async def test_write_daily_uptime_skips_services_without_check_url():
    service = make_service(ServiceStatus.operational, check_url=None)

    session = MagicMock()
    session.exec = AsyncMock(return_value=QueryResult([service]))
    session.commit = AsyncMock()

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "AsyncSession", return_value=SessionContext(session)),
    ):
        await write_daily_uptime()

    # Only the initial Service select is issued — no ServiceCheckHistory query
    assert session.exec.call_count == 1
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_write_daily_uptime_noops_when_no_history():
    service = make_service(ServiceStatus.operational, check_url="https://example.com")

    session = MagicMock()
    session.exec = AsyncMock(side_effect=[
        QueryResult([service]),  # select(Service)
        QueryResult([]),         # select(ServiceCheckHistory) — empty
    ])
    session.commit = AsyncMock()

    with (
        patch.object(health_service, "datetime", FrozenDateTime),
        patch.object(health_service, "AsyncSession", return_value=SessionContext(session)),
    ):
        await write_daily_uptime()

    session.add.assert_not_called()
    session.commit.assert_awaited_once()
